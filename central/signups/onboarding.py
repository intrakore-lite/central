import re

import frappe
from frappe import _
from frappe.utils import cint, flt

from central.signups.eligibility import has_active_payment_method
from central.signups.trial import TrialSettings
from central.signups.trial_product import resolve_trial_product

# UAE VAT. The plan summary shows it as an estimate; invoices take the rate from the Tax Profile.
VAT_PERCENT = 5
# The largest seat band a customer VM is sized for.
MAX_SEATS = 40
ORGANISATION_FIELDS = ("business_type", "headcount_bracket", "turnover_band")
SUBDOMAIN_LENGTH = 30
# The server plan of each seat band. central.billing.catalog.seats.get_plan_for_seats (OPS-218)
# replaces this table once it is on develop.
SEAT_BANDS = ((5, "plan-1vcpu"), (15, "plan-2vcpu"), (40, "plan-4vcpu"))
LARGEST_BAND_PLAN = "plan-8vcpu"

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


def get_plan_for_seats(seats: int) -> str:
	"""The server plan of a seat band: 1 to 5 seats, 6 to 15, 16 to 40, and more."""
	for most_seats, plan in SEAT_BANDS:
		if seats <= most_seats:
			return plan
	return LARGEST_BAND_PLAN


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
	"""The placeholder seat prices from Central Settings, and the monthly price of every seat
	count the counter offers. Seat billing does not read them yet."""
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
	doc.seats = profile["seats"]
	doc.update({field: profile[field] for field in ORGANISATION_FIELDS})
	doc.save()
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
			plan=get_plan_for_seats(cint(seats) or 1),
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
