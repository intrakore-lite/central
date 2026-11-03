import re

import frappe
from frappe import _
from frappe.utils import cint, flt

from central.billing.catalog import seats as seat_billing
from central.signups.eligibility import has_active_payment_method
from central.signups.trial import TrialSettings
from central.signups.trial_product import resolve_trial_product

# UAE VAT. The plan summary shows it as an estimate; invoices take the rate from the Tax Profile.
VAT_PERCENT = 5
# The largest seat band a customer VM is sized for.
MAX_SEATS = 40
ORGANISATION_FIELDS = ("business_type", "headcount_bracket", "turnover_band")
SUBDOMAIN_LENGTH = 30

# Every claim here must be true for this platform today. Central Settings > Onboarding Trust Content
# replaces a key with real figures, a real quote or a certification once it exists.
DEFAULT_TRUST_CONTENT = {
	"profile_badge": "30 days free",
	"profile_footer": ["Encrypted in transit (TLS 1.2+)", "Hosted in Frankfurt, EU"],
	"profile_trust_line": "Zero charge today — cancel before day 30",
	"guarantee": {"title": "Zero charge today", "text": "Cancel before day 30"},
	"payment_badges": [
		"Card stored by Checkout.com (PCI-DSS Level 1)",
		"Encrypted in transit (TLS 1.2+)",
		"Hosted in Frankfurt, EU",
	],
	"proof": {"title": "What your team gets", "text": "From first tender to estimate on one platform"},
	"benefits": [
		"Qualify tenders with a bid/no-bid matrix",
		"Hand won bids straight to estimation",
		"Price from shared BOQs and rate books",
	],
	"quote": None,
	"help": {"title": "Questions before you start?", "text": "Our team answers billing and setup questions."},
	# Steps 3 and 4. A key set to None shows nothing until Central Settings gives it a value.
	"team_badge": "Invitations are sent by your own workspace",
	"team_features": [
		{
			"title": "Access by module",
			"text": "Give each member CRM, Estimation or both, with a role that fits their work.",
		},
		{
			"title": "Activation by email",
			"text": "Your workspace emails each member a link to set a password and sign in.",
		},
		{
			"title": "One seat per member",
			"text": "Each active member uses one of the seats you chose in step 1.",
		},
	],
	"team_stat": None,
	"team_caption": None,
	"setup_footer_line": "You can change every setting later in your workspace.",
}


def get_onboarding(team: str, product: str | None) -> dict:
	"""What the onboarding pages show for a team: the product, the saved profile, the seat
	prices and the trust content."""
	product = get_team_product(team, product)

	return {
		"team": team,
		"product": get_product_summary(team, product),
		"profile": get_profile(team),
		"options": get_profile_options(),
		"pricing": get_seat_pricing(product),
		"trust": get_trust_content(),
		"has_payment_method": has_active_payment_method(team),
		"progress": get_progress(team),
	}


def get_team_product(team: str, product: str | None) -> str | None:
	"""The product the team starts with: the one asked for, the one its invitation names, the
	product of its first signup link, else the default trial product."""
	invited = frappe.get_all(
		"Trial Invitation",
		filters={"status": "Accepted"},
		or_filters={"team": team, "email": frappe.session.user},
		pluck="product",
		order_by="creation desc",
		limit=1,
	)
	return resolve_trial_product(
		product or (invited[0] if invited else None) or frappe.db.get_value("Team", team, "landing_product")
	)


def get_product_summary(team: str, product: str | None) -> dict | None:
	"""The public branding of the product the team starts with, and the apps it includes."""
	if not product:
		return None

	# Product is an operator DocType. The page reads only its public branding, as signup does.
	summary = frappe.db.get_value("Product", product, ["name", "title", "subtitle", "logo"], as_dict=True)
	summary.modules = get_product_modules(team, product)
	return summary


def get_product_modules(team: str, product: str) -> list[str]:
	"""The product's own apps by title, from the app tags of its newest trial image. The signup
	app alone when no region has an image."""
	from central.signups.server_products import get_app_title, get_image_apps
	from central.site_provisioning import preferred_image, signup_offering, trial_images, trial_regions

	signup_product = frappe.get_cached_doc("Product", product)
	try:
		offering = signup_offering()
		for region in trial_regions():
			if images := trial_images(team, region, offering, signup_product):
				tags = preferred_image(images).get("tags") or {}
				return [app["title"] for app in get_image_apps(tags) if not app["is_core"]]
	except Exception:
		# The list only describes the plan. A region that does not answer must not block onboarding.
		frappe.log_error(title=f"Onboarding modules of {product} not read")

	return [get_app_title(signup_product.signup_app)] if signup_product.signup_app else []


def get_profile(team: str) -> dict:
	"""The answers already saved, so a returning owner sees them again."""
	user = frappe.session.user
	team_values = frappe.db.get_value(
		"Team", team, ["team_name", "seats", *ORGANISATION_FIELDS], as_dict=True
	)
	billing = (
		frappe.db.get_value(
			"Billing Profile",
			team,
			["legal_name", "phone", "address_line1", "city", "country", "tax_id"],
			as_dict=True,
		)
		or frappe._dict()
	)

	return {
		"full_name": frappe.db.get_value("User", user, "full_name") or "",
		"email": user,
		"mobile": billing.phone or "",
		"organisation": billing.legal_name or "",
		"business_type": team_values.business_type or "",
		"headcount_bracket": team_values.headcount_bracket or "",
		"turnover_band": team_values.turnover_band or "",
		"seats": cint(team_values.seats),
		"address_line1": billing.address_line1 or "",
		"city": billing.city or "",
		"country": billing.country or "",
		"tax_id": billing.tax_id or "",
	}


def get_profile_options() -> dict:
	"""The choices of the profile selects, from the Team DocType, so the page and the
	validation share one list."""
	meta = frappe.get_meta("Team")
	return {
		field: [option for option in meta.get_options(field).split("\n") if option]
		for field in ORGANISATION_FIELDS
	}


def get_seat_pricing(product: str | None = None) -> dict:
	"""The seat prices of Central Settings > Seat Billing, which seat billing charges from day
	30, and the monthly price of every seat count the counter offers. The team has no site yet,
	so the quote reads the settings, not the site's subscription."""
	settings = frappe.get_cached_doc("Central Settings")
	seat_price = flt(settings.seat_price)
	included_seats = cint(settings.included_seats)

	return {
		"currency": settings.seat_price_currency or "AED",
		"seat_price": seat_price,
		"included_seats": included_seats,
		"storage_price_per_gb": flt(settings.storage_price_per_gb),
		"trial_ai_cap": flt(settings.trial_ai_cap),
		"vat_percent": VAT_PERCENT,
		"max_seats": MAX_SEATS,
		"trial_days": TrialSettings(product).days,
		"quotes": [get_seat_quote(seats, seat_price, included_seats) for seats in range(1, MAX_SEATS + 1)],
	}


def get_seat_quote(seats: int, seat_price: float, included_seats: int) -> dict:
	"""The monthly price after the trial: the base plan bills at least its included seats."""
	billed_seats = max(seats, included_seats)
	monthly = flt(billed_seats * seat_price, 2)
	vat = flt(monthly * VAT_PERCENT / 100, 2)

	return {
		"seats": seats,
		"billed_seats": billed_seats,
		"monthly": monthly,
		"vat": vat,
		"total": flt(monthly + vat, 2),
	}


def get_trust_content() -> dict:
	"""The defaults, with each key that Central Settings sets replaced by its value."""
	configured = frappe.parse_json(frappe.get_cached_doc("Central Settings").onboarding_trust_content or "{}")
	if not isinstance(configured, dict):
		configured = {}

	return {
		**DEFAULT_TRUST_CONTENT,
		**{key: configured[key] for key in DEFAULT_TRUST_CONTENT if key in configured},
	}


def save_profile(team: str, profile: dict) -> dict:
	"""Store step 1: the admin's name, the organisation and the seats on the Team, and the
	legal name and mobile on the Billing Profile. The mobile's country is the billing country
	until step 2 asks for the address."""
	from central.api.identity import update_profile
	from central.billing.api.dashboard.account import save_billing_profile
	from central.signups.doctype.trial_invitation.trial_invitation import link_team

	profile = validated_profile(profile)
	update_profile(profile["full_name"])

	doc = frappe.get_doc("Team", team)
	doc.team_name = profile["organisation"]
	doc.update({field: profile[field] for field in ORGANISATION_FIELDS})
	doc.save()
	save_seats(team, profile["seats"])
	# A first team links its invitation when it is created. An invitee who already had a team links here.
	link_team(frappe.session.user, team)

	save_billing_profile(
		team,
		legal_name=profile["organisation"],
		email=frappe.session.user,
		phone=profile["mobile"],
		country=profile["country"],
	)
	return get_profile(team)


def save_seats(team: str, seats: int) -> None:
	"""Store the seat count. A team whose site already bills per seat changes it through seat
	billing. Otherwise the count waits on the Team, and the seat limit job sends it to the site."""
	if seat_billing.get_seat_site(team):
		seat_billing.change_seats(team, seats, changed_by=frappe.session.user)
		return

	frappe.db.set_value("Team", team, "seats", seats)
	frappe.enqueue(
		seat_billing.sync_seat_limits,
		team=team,
		queue="short",
		enqueue_after_commit=True,
		job_id=f"seat-limits:{team}",
		deduplicate=True,
	)


def validated_profile(profile: dict) -> dict:
	"""The step 1 answers, trimmed, or a refusal that names the first missing one."""
	profile = {key: (value.strip() if isinstance(value, str) else value) for key, value in profile.items()}
	required = {
		"full_name": _("Enter your full name."),
		"mobile": _("Enter your mobile number."),
		"country": _("Choose the country code of your mobile number."),
		"organisation": _("Enter the legal name of your organisation."),
		"business_type": _("Choose a business classification."),
		"headcount_bracket": _("Choose a headcount bracket."),
	}
	for field, message in required.items():
		if not profile.get(field):
			frappe.throw(message, frappe.ValidationError)

	seats = cint(profile.get("seats"))
	if not 1 <= seats <= MAX_SEATS:
		frappe.throw(_("Choose between 1 and {0} seats.").format(MAX_SEATS), frappe.ValidationError)

	return {**profile, "seats": seats, "turnover_band": profile.get("turnover_band") or ""}


def start_site(team: str, product: str | None) -> dict:
	"""Queue the team's site once its card is saved. The page moves on at once, and the site
	is created in the background through the trial site path."""
	if not has_active_payment_method(team):
		frappe.throw(_("Add a card before your site is created."), frappe.ValidationError)

	product = get_team_product(team, product)
	if not product:
		frappe.throw(_("No product is available to start your site."), frappe.ValidationError)

	frappe.enqueue(
		"central.signups.onboarding.create_site",
		queue="default",
		timeout=600,
		job_id=f"onboarding-site::{team}",
		deduplicate=True,
		enqueue_after_commit=True,
		team=team,
		product=product,
		user=frappe.session.user,
	)
	return {"team": team, "product": product, "queued": True}


def create_site(team: str, product: str, user: str) -> None:
	"""Create the team's site of the product, as the owner, unless one is already on its way."""
	from central.api.sites import find_onboarding
	from central.site_provisioning import create_trial_site

	# The job runs as the owner who saved the card, so the site path checks that owner's capabilities.
	frappe.set_user(user)  # nosemgrep: frappe-semgrep-rules.rules.security.frappe-setuser
	site, creation = find_onboarding(team, product)
	if site or (creation and creation.status not in ("Failed", "Timed Out")):
		return

	organisation, seats = frappe.db.get_value("Team", team, ["team_name", "seats"])
	try:
		create_trial_site(
			team,
			free_subdomain(organisation or team),
			frappe.generate_hash(length=20),
			product,
			plan=seat_billing.get_plan_for_seats(cint(seats) or 1),
		)
	except Exception:
		frappe.log_error(title=f"Onboarding site for {team} not created")
		raise


def free_subdomain(organisation: str) -> str:
	"""A free site name from the organisation name, such as apex-contracting, then
	apex-contracting-2 and on."""
	from central.site_provisioning import subdomain_availability

	base = re.sub(r"[^a-z0-9]+", "-", organisation.lower()).strip("-")[:SUBDOMAIN_LENGTH].strip("-")
	base = base or "site"
	for suffix in ("", *(f"-{number}" for number in range(2, 10))):
		if subdomain_availability(f"{base}{suffix}")["available"]:
			return f"{base}{suffix}"

	return f"{base}-{frappe.generate_hash(length=5)}"


# --- steps 3 and 4: the customer's site -------------------------------------------------------

# Where the owner is in the four steps. 5 means onboarding is done.
STEP_DONE = 5
# A rough share of the wait for each stage of the site, for the progress bar.
STAGE_PROGRESS = {"waiting": 0, "building": 30, "starting": 60, "setting_up": 85, "ready": 100, "failed": 100}
FAILED_CREATION_STATES = ("Failed", "Timed Out")


def get_progress(team: str) -> dict:
	"""The step the owner resumes at: 1 profile, 2 card and site, 3 team, 4 master setup, 5 done."""
	values = frappe.db.get_value(
		"Team",
		team,
		["seats", "business_type", "setup_team_done_at", "setup_completed_at"],
		as_dict=True,
	)
	if values.setup_completed_at:
		step = STEP_DONE
	elif not (values.seats and values.business_type):
		step = 1
	elif not (has_active_payment_method(team) and get_site_creation(team)):
		step = 2
	elif not values.setup_team_done_at:
		step = 3
	else:
		step = 4

	return {"step": step, "done": step == STEP_DONE}


def get_onboarding_site(team: str):
	"""The team's newest site on a live server, or None."""
	names = frappe.get_list(
		"Site",
		filters={"team": team, "server.status": ["!=", "Terminated"]},
		pluck="name",
		order_by="creation desc",
		limit=1,
	)
	return frappe.get_doc("Site", names[0]) if names else None


def get_site_creation(team: str) -> frappe._dict | None:
	"""The newest site creation request of the team."""
	rows = frappe.get_list(
		"Resource Action",
		filters={"team": team, "resource_type": "Site", "action": "create"},
		fields=["name", "status", "server", "error_message"],
		order_by="creation desc",
		limit=1,
	)
	return rows[0] if rows else None


def get_site_state(team: str) -> dict:
	"""Where the team's site is: waiting for the card, building, starting, setting up its company,
	ready or failed. Once the site answers and its setup has not started, this starts it, so the
	customer never sees Frappe's setup wizard."""
	from central.integrations.pilot import is_site_reachable
	from central.signups.site_onboarding import SiteOnboardingClient, SiteOnboardingError

	site = get_onboarding_site(team)
	if not site:
		creation = get_site_creation(team)
		if not creation:
			return site_answer("waiting")
		if creation.status in FAILED_CREATION_STATES:
			return site_answer("failed", message=_("Your workspace could not be created. Contact support."))
		return site_answer("building")

	if not is_site_reachable(site.url):
		return site_answer("starting", site)
	site.record_ready()

	try:
		client = SiteOnboardingClient.for_site(site)
		state = client.get_state()
		job = state.get("setup_job") or {}
		if not state.get("setup_complete") and not job:
			client.complete_setup(site_profile_of(team))
			return site_answer("setting_up", site, state)
	except SiteOnboardingError as error:
		return site_answer("starting" if is_retryable(error) else "failed", site, message=error.message)

	if state.get("setup_complete"):
		return site_answer("ready", site, state)
	if job.get("status") == "failed":
		return site_answer("failed", site, state, message=job.get("error") or _("Your company setup failed."))
	return site_answer("setting_up", site, state)


def start_site_setup(team: str, site: str | None = None) -> None:
	"""Job, when a site is first ready: write its seat cap and outgoing email into its config, then start its company
	setup. The job runs as the system: it only reads the team's own site and sends the owner's
	saved answers."""
	from central.signups.site_onboarding import push_site_mail, push_site_seat_limit

	if site:
		site_doc = frappe.get_doc("Site", site)
		push_site_seat_limit(site_doc)
		push_site_mail(site_doc)
	get_site_state(team)


def site_answer(stage: str, site=None, state: dict | None = None, message: str | None = None) -> dict:
	state = state or {}
	return {
		"stage": stage,
		"progress": STAGE_PROGRESS[stage],
		"message": message,
		"site": {"name": site.name, "url": site.primary_url} if site else None,
		"seats": state.get("seats"),
		"company": (state.get("company") or {}).get("company_name"),
		"master_setup": state.get("master_setup"),
	}


def is_retryable(error) -> bool:
	from central.signups.site_onboarding import SiteRateLimited, SiteUnavailable

	return isinstance(error, SiteUnavailable | SiteRateLimited)


def site_profile_of(team: str) -> dict:
	from central.signups.site_onboarding import site_profile

	return site_profile(team)


def complete_site_setup(team: str) -> dict:
	"""Run the site's setup wizard again from the step 1 answers, such as after a failure."""
	return call_site(team, "complete_setup", site_profile_of(team))


def invite_members(team: str, rows: list) -> dict:
	"""Invite members to the team's site. Each row gets its own result; the site sends the emails."""
	from central.signups.site_onboarding import validated_rows

	owner = frappe.db.get_value("Team", team, "owner_user")
	rows = [row for row in validated_rows(rows) if row["email"] != owner]
	if not rows:
		frappe.throw(_("You are already the owner of this workspace."), frappe.ValidationError)
	return call_site(team, "invite_members", rows)


def finish_team_step(team: str) -> dict:
	"""Record that the owner left step 3, with or without invitations."""
	if not frappe.db.get_value("Team", team, "setup_team_done_at"):
		frappe.db.set_value("Team", team, "setup_team_done_at", frappe.utils.now_datetime())
	return get_progress(team)


def apply_master_setup(team: str, config: dict) -> dict:
	"""Send the CRM and Estimation defaults to the site, then mark onboarding done. Keys the site
	has no place for come back under `skipped`: the page shows them as saved for later."""
	from central.signups.site_onboarding import validated_config

	report = call_site(team, "apply_master_setup", validated_config(config))
	frappe.db.set_value(
		"Team",
		team,
		{
			"setup_team_done_at": frappe.db.get_value("Team", team, "setup_team_done_at")
			or frappe.utils.now_datetime(),
			"setup_completed_at": frappe.utils.now_datetime(),
		},
	)
	site = get_onboarding_site(team)
	return {**(report or {}), "site": site.name if site else None}


def call_site(team: str, method: str, payload) -> dict:
	"""Call the team's site, or refuse with the reason in the customer's words."""
	from central.signups.site_onboarding import SiteOnboardingClient, SiteOnboardingError

	site = get_onboarding_site(team)
	if not site:
		frappe.throw(
			_("Your workspace is still being created. Try again in a minute."), frappe.ValidationError
		)

	try:
		return getattr(SiteOnboardingClient.for_site(site), method)(payload)
	except SiteOnboardingError as error:
		frappe.log_error(
			title=f"Site onboarding {method} failed: {site.name}",
			message=f"{type(error).__name__} status={error.status}",
		)
		frappe.throw(error.message, frappe.ValidationError)
