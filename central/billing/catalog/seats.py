# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import frappe
import requests
from frappe import _
from frappe.utils import cint, date_diff, flt, get_last_day, getdate, nowdate

from central.billing.catalog.pricing import get_catalog_rates, resolve_rate

MAX_SEATS = 1000
# The server of a product site follows its seat count. The customer never sees the plan.
SEAT_BANDS = ((5, "plan-1vcpu"), (15, "plan-2vcpu"), (40, "plan-4vcpu"))
LARGEST_BAND_PLAN = "plan-8vcpu"
LIVE_SERVER_STATES = ("Running", "Paused", "Stopped")
USERS_RESOURCE_TYPE = "Users"


@dataclass(frozen=True)
class SeatQuote:
	"""The monthly seat price of a team's product site. Included Seats is the least it bills."""

	team: str
	site: str
	server: str
	seats: int
	billed_seats: int
	seat_price: float
	currency: str

	@property
	def monthly_rate(self) -> float:
		return flt(self.billed_seats * self.seat_price, 2)

	@property
	def label(self) -> str:
		return _("{0} seats").format(self.seats)

	def as_dict(self) -> dict:
		return {
			"seats": self.seats,
			"billed_seats": self.billed_seats,
			"seat_price": self.seat_price,
			"monthly_rate": self.monthly_rate,
			"currency": self.currency,
		}


def get_plan_for_seats(seats: int) -> str:
	"""The server plan of a seat band: 1 to 5 seats, 6 to 15, 16 to 40, and 41 or more."""
	for most_seats, plan in SEAT_BANDS:
		if seats <= most_seats:
			return plan
	return LARGEST_BAND_PLAN


def get_seat_site(team: str) -> frappe._dict | None:
	"""The team's oldest product site whose server is not terminated, or None."""
	site = frappe.qb.DocType("Site")
	machine = frappe.qb.DocType("Virtual Machine")
	rows = (
		frappe.qb.from_(site)
		.join(machine)
		.on(machine.name == site.server)
		.select(site.name, site.server, site.product, site.trial_state, site.trial_ends_on)
		.where((site.team == team) & site.product.isnotnull() & (site.product != ""))
		.where(machine.status != "Terminated")
		.orderby(site.creation)
		.limit(1)
	).run(as_dict=True)
	return rows[0] if rows else None


def get_seat_price(team: str, product: str) -> tuple[float, str] | None:
	"""The monthly price of one seat in the team's currency. The first that is set wins: the
	Product's Catalog Rate, the Catalog Rate of the Users resource type, then Central Settings
	when its Seat Price Currency is the team's. None when the team has no currency or no price."""
	currency = frappe.db.get_value("Billing Profile", team, "currency")
	if not currency:
		return None

	price = resolve_rate(get_catalog_rates("Product", product), currency)
	if price is None:
		price = resolve_rate(get_catalog_rates("Resource Type", USERS_RESOURCE_TYPE), currency)
	if price is None and frappe.db.get_single_value("Central Settings", "seat_price_currency") in (
		None,
		"",
		currency,
	):
		price = frappe.db.get_single_value("Central Settings", "seat_price")
	return (flt(price), currency) if flt(price) > 0 else None


def get_seat_quote(team: str, seats: int | None = None) -> SeatQuote | None:
	"""The team's seat price, for its current seats or for `seats`. None when the team is not
	billed per seat: it has no seats, no product site, or no seat price."""
	seats = cint(frappe.db.get_value("Team", team, "seats")) if seats is None else cint(seats)
	site = get_seat_site(team) if seats > 0 else None
	price = get_seat_price(team, site.product) if site else None
	if not price:
		return None

	included = cint(frappe.db.get_single_value("Central Settings", "included_seats"))
	return SeatQuote(team, site.name, site.server, seats, max(seats, included), *price)


def get_subscription_seat_quote(subscription) -> SeatQuote | None:
	"""The seat price that a server subscription bills in place of its plan, or None.
	TODO(OPS-218): also bill storage above Included Storage (`get_storage_charge`) once metering
	records the server's used disk. Today only telemetry has it."""
	if not subscription.get("server_id") or not subscription.get("team"):
		return None

	quote = get_seat_quote(subscription.team)
	return quote if quote and quote.server == subscription.server_id else None


def get_storage_charge(used_gb: float) -> float:
	"""The monthly charge for storage above Included Storage."""
	included = cint(frappe.db.get_single_value("Central Settings", "included_storage_gb"))
	price = flt(frappe.db.get_single_value("Central Settings", "storage_price_per_gb"))
	return flt(max(0.0, flt(used_gb) - included) * price, 2)


def get_prorated_amount(old_rate: float, new_rate: float, today: date | None = None) -> float:
	"""What a seat change today adds to this month's bill. The billing run gives the day of a
	change to the new rate (`lines._owned_dates`), so today is counted."""
	today = getdate(today or nowdate())
	days_in_month = get_last_day(today).day
	days_left = days_in_month - today.day + 1
	return flt((flt(new_rate) - flt(old_rate)) * days_left / days_in_month, 2)


def get_seat_subscription(server: str) -> str | None:
	return frappe.db.get_value("Subscription", {"server_id": server, "enabled": 1}, "name")


def get_seat_summary(team: str, seats: int | None = None) -> dict:
	"""The Seats card: the seat price, the change a new count makes this month, and the cancellation."""
	quote = get_seat_quote(team, seats)
	if not quote:
		return {"is_seat_billed": False}

	current = get_seat_quote(team)
	subscription = get_seat_subscription(quote.server)
	site = frappe.db.get_value("Site", quote.site, ["trial_state", "trial_ends_on"], as_dict=True)
	is_on_trial = site.trial_state == "Active"
	return {
		"is_seat_billed": True,
		**quote.as_dict(),
		"current_seats": current.seats if current else 0,
		"current_monthly_rate": current.monthly_rate if current else 0,
		"included_seats": cint(frappe.db.get_single_value("Central Settings", "included_seats")),
		"included_storage_gb": cint(frappe.db.get_single_value("Central Settings", "included_storage_gb")),
		"storage_price_per_gb": flt(frappe.db.get_single_value("Central Settings", "storage_price_per_gb")),
		"is_on_trial": is_on_trial,
		"billing_starts_on": site.trial_ends_on if is_on_trial else None,
		"prorated_amount": get_prorated_amount(current.monthly_rate if current else 0, quote.monthly_rate)
		if subscription
		else 0,
		"subscription_ends_on": frappe.db.get_value("Team", team, "subscription_ends_on"),
	}


def change_seats(team: str, seats: int, changed_by: str | None = None) -> dict:
	"""Set the team's seat count. A paid site bills the new count from today, by the day. The site's
	user limit and its server size follow in the background."""
	seats = cint(seats)
	if not 1 <= seats <= MAX_SEATS:
		frappe.throw(_("Choose between 1 and {0} seats.").format(MAX_SEATS))

	frappe.db.get_value("Team", team, "name", for_update=True)
	previous = get_seat_quote(team)
	quote = get_seat_quote(team, seats)
	if not quote:
		frappe.throw(_("This team has no site that is billed per seat."))
	if previous and previous.seats == seats:
		return get_seat_summary(team)

	subscription = get_seat_subscription(quote.server)
	if subscription and quote.monthly_rate > (previous.monthly_rate if previous else 0):
		from central.billing.catalog.subscriptions import enforce_headroom

		enforce_headroom(team, quote.monthly_rate, exclude=subscription)

	frappe.db.set_value("Team", team, "seats", seats)
	if subscription:
		frappe.get_doc("Subscription", subscription).log_rate_change(
			previous.label if previous else None, changed_by
		)

	frappe.enqueue(
		sync_seat_limits,
		team=team,
		queue="short",
		enqueue_after_commit=True,
		job_id=f"seat-limits:{team}",
		deduplicate=True,
	)
	return get_seat_summary(team)


def sync_seat_limits(team: str) -> None:
	"""Background job: hold the site's user limit at the seat count, and size its server to the
	seat band. A failure is a comment on the Site and an Error Log, and the next seat change sends both again."""
	quote = get_seat_quote(team)
	if not quote:
		return

	site = frappe.get_doc("Site", quote.site)
	push_user_limit(site, quote.seats)
	resize_to_seat_band(site, quote.seats)


def push_user_limit(site, seats: int) -> None:
	"""Write `max_system_users` into the site's config through its Pilot."""
	from central.integrations.pilot import update_site_config

	try:
		update_site_config(site.server, site.get_pilot_site_names(), {"max_system_users": seats})
	# A sleeping or busy server can miss the call. The operator reads why on the Site.
	except requests.RequestException:
		frappe.log_error(title="Seat limit not sent", reference_doctype="Site", reference_name=site.name)
		site.add_comment("Info", _("Central could not set the site's user limit to {0}.").format(seats))


def resize_to_seat_band(site, seats: int) -> None:
	"""Resize the site's server to its seat band, as the system, so a customer needs no
	`server:resize`. A server never shrinks its disk. An ended or deleted trial is not resized."""
	from central.billing.catalog.subscriptions import get_plan_shape, get_server_shape
	from central.infrastructure.doctype.resource_action.resource_action import PENDING_STATES, ResourceAction
	from central.server_models import ResizeConfiguration

	plan = get_plan_for_seats(seats)
	server = frappe.get_doc("Virtual Machine", site.server)
	shape = get_plan_shape(plan) if frappe.db.exists("Plan", plan) else None
	if not shape or site.trial_state in ("Ended", "Deleted") or server.status not in LIVE_SERVER_STATES:
		return
	if (flt(server.vcpus), cint(server.memory_megabytes)) == (shape["vcpus"], shape["memory_megabytes"]):
		return
	if frappe.db.exists("Resource Action", {"resource_id": server.name, "status": ["in", PENDING_STATES]}):
		site.add_comment("Info", _("Another action is running on the server. Change the seats again later."))
		return

	shape["disk_gigabytes"] = max(shape["disk_gigabytes"], cint(server.disk_gigabytes))
	configuration = ResizeConfiguration.model_validate(
		{
			"subscription": get_seat_subscription(server.name),
			"plan": plan,
			"shape": shape,
			"from_plan": server.plan,
			"from_shape": get_server_shape(server),
		}
	)
	ResourceAction.queue(
		"resize",
		server.team,
		server.region,
		server.title or server.name,
		server=server.name,
		remote_vm_id=server.atlas_vm_id,
		requested_by="Administrator",
		request_payload=configuration.model_dump(),
	)


def set_cancellation(team: str, cancel: bool) -> dict:
	"""Cancel the team's seat subscription, or keep it. A trial stops on its end date and is not
	charged. A paid site is billed to the end of this month, then stops."""
	quote = get_seat_quote(team)
	if not quote:
		frappe.throw(_("This team has no site that is billed per seat."))

	ends_on = None
	if cancel:
		site = frappe.db.get_value("Site", quote.site, ["trial_state", "trial_ends_on"], as_dict=True)
		ends_on = site.trial_ends_on if site.trial_state == "Active" else get_last_day(nowdate())
	frappe.db.set_value("Team", team, "subscription_ends_on", ends_on)
	return get_seat_summary(team)


def is_cancelled(team: str) -> bool:
	return bool(frappe.db.get_value("Team", team, "subscription_ends_on"))


def run_cancellations(today: date | str | None = None) -> None:
	"""Daily job: stop each cancelled paid site after its last day, and terminate it after the
	trial deletion days. A trial ends through its own clock (`Trial.advance_active`)."""
	from central.billing.platform.jobs import each_isolated

	today = getdate(today or nowdate())
	teams = frappe.get_all("Team", filters={"subscription_ends_on": ["<", today]}, pluck="name")
	each_isolated("Seat cancellation", "Team", teams, lambda team: close_cancelled_site(team, today))


def close_cancelled_site(team: str, today: date) -> None:
	from central.signups.trial import OPEN_STATES, TrialSettings

	site = get_seat_site(team)
	ends_on = frappe.db.get_value("Team", team, "subscription_ends_on")
	if not site or not ends_on or site.trial_state in OPEN_STATES:
		return

	if subscription := get_seat_subscription(site.server):
		stop_at_period_end(subscription, site.server, ends_on)
	elif date_diff(today, ends_on) > TrialSettings(site.product).deletion_days:
		terminate_server(site.server)


def stop_at_period_end(subscription: str, server: str, ends_on: date) -> None:
	"""Close billing at the end of the last day, then stop the server as the system."""
	from central.billing.catalog.subscriptions import end_subscription
	from central.resource_actions import submit_billing_command

	period_end = datetime.combine(getdate(ends_on) + timedelta(days=1), time.min)
	end_subscription(subscription, changed_by="Administrator", effective_at=period_end)
	if frappe.db.get_value("Virtual Machine", server, "status") in ("Running", "Paused"):
		submit_billing_command("stop", server)


def terminate_server(server_name: str) -> None:
	from central.infrastructure.doctype.resource_action.resource_action import ResourceAction

	server = frappe.get_doc("Virtual Machine", server_name)
	if ResourceAction.get_pending(server.name, "terminate"):
		return

	ResourceAction.queue(
		"terminate",
		server.team,
		server.region,
		server.title or server.name,
		server=server.name,
		remote_vm_id=server.atlas_vm_id,
		requested_by="Administrator",
	)
