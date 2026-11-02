# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt
"""Set up a site that bills in USD through Stripe, with VAT by country, and check it.

`configure_usd_stripe_market` writes the settings an operator would otherwise set by
hand in Desk. It is idempotent and keeps every value an operator has already set,
except the ones it names. It never writes a gateway key, never enables a gateway and
never sets a price: keys and prices are the operator's.

`ensure_bundle_product` adds the first product, disabled until its trial image exists.

`readiness` lists what is still missing before the first paid customer.

    pilot frappe --site <site> execute central.billing.market_setup.configure_usd_stripe_market
    pilot frappe --site <site> execute central.billing.market_setup.readiness

`execute` commits when the call returns, so nothing here commits.
"""

import frappe

from central.billing.settings import SETTINGS

CURRENCY = "USD"
GATEWAY = "Stripe"
HOME_COUNTRY = "United Arab Emirates"

# The only rate set here. Other GCC rates are a tax advisor's decision: add them in
# Billing Settings, VAT Rates by Country.
SEED_VAT_RATES = {HOME_COUNTRY: 5.0}

# The first product: INTRAKORE CRM and Estimation on one trial site, with their base apps.
# A Product names one Signup App, the `app` tag of its trial image, so the bundle image
# carries this tag. The Frappe version is the branch the image is built on.
BUNDLE_PRODUCT = {
	"product_key": "crm-estimation",
	"title": "CRM + Estimation",
	"signup_app": "intrakore_crm",
	"frappe_version": "version-16",
	"trial_days": 60,
}

# Central Settings for a trial that runs free without a card and asks for one at the end.
TRIAL_SETTINGS = {
	"trial_days": 60,
	"trial_deletion_days": 14,
	"trial_notice_days": 7,
	# A paid server, and so a trial that is kept, needs a payment method.
	"require_payment_method": 1,
}


def configure_usd_stripe_market(
	home_country: str = HOME_COUNTRY,
	trial_days: int = TRIAL_SETTINGS["trial_days"],
	trial_deletion_days: int = TRIAL_SETTINGS["trial_deletion_days"],
	trial_notice_days: int = TRIAL_SETTINGS["trial_notice_days"],
) -> dict:
	"""Make USD through Stripe the billing path, seed the home country's VAT, set the trial
	clock and add the first product."""
	ensure_stripe_usd_default()
	ensure_billing_settings(home_country)
	ensure_bundle_product()
	frappe.db.set_single_value(
		"Central Settings",
		{
			"trial_days": trial_days,
			"trial_deletion_days": trial_deletion_days,
			"trial_notice_days": trial_notice_days,
			"require_payment_method": 1,
		},
	)
	frappe.clear_document_cache("Central Settings", "Central Settings")
	return readiness()


def ensure_bundle_product(
	signup_app: str = BUNDLE_PRODUCT["signup_app"],
	frappe_version: str = BUNDLE_PRODUCT["frappe_version"],
) -> str:
	"""Create the CRM + Estimation Product, disabled, when it does not exist. An existing
	one is left as it is. Enable it once Preview Trial Images shows its image."""
	key = BUNDLE_PRODUCT["product_key"]
	if not frappe.db.exists("Product", key):
		frappe.get_doc(
			{
				"doctype": "Product",
				**BUNDLE_PRODUCT,
				"signup_app": signup_app,
				"frappe_version": frappe_version,
				# No signups until the trial image is built and checked.
				"enabled": 0,
			}
		).insert(ignore_permissions=True)
	return key


def ensure_stripe_usd_default() -> None:
	"""Give the Stripe gateway a USD row that is the default for USD, with no silent-debit ceiling.

	Keys and Enabled stay as they are. Another gateway's USD default row is cleared, so
	USD resolves to Stripe whichever gateway is enabled."""
	from central.billing.gateways.setup import ensure_gateway_records

	ensure_gateway_records()
	gateway = frappe.get_doc("Payment Gateway", GATEWAY)
	row = next((r for r in gateway.currencies if r.currency == CURRENCY), None)
	if not row:
		row = gateway.append("currencies", {"currency": CURRENCY})
	row.is_default = 1
	row.max_silent_charge = 0
	row.requires_predebit_notice = 0
	# Only the currency row changes; any stored keys were proven when they were entered.
	gateway.flags.skip_credential_validation = True
	gateway.save(ignore_permissions=True)

	others = frappe.get_all(
		"Payment Gateway Currency",
		filters={"currency": CURRENCY, "is_default": 1, "parent": ["!=", GATEWAY]},
		pluck="name",
	)
	for name in others:
		frappe.db.set_value("Payment Gateway Currency", name, "is_default", 0, update_modified=False)


def ensure_billing_settings(home_country: str) -> None:
	"""Set the signup fallback country and add each seed VAT rate that has no row yet."""
	doc = frappe.get_doc(SETTINGS)
	doc.signup_fallback_country = home_country
	doc.billing_currency = CURRENCY
	configured = {row.country for row in doc.country_tax_rates}
	for country, rate in SEED_VAT_RATES.items():
		if country not in configured:
			doc.append(
				"country_tax_rates",
				{"country": country, "vat_rate": rate, "note": "UAE VAT standard rate"},
			)
	doc.save(ignore_permissions=True)


def readiness() -> dict:
	"""What a USD Stripe site still needs before it can take a paid customer.

	Returns `ready` and a list of `missing` items an operator acts on. Reads only."""
	missing = []
	missing += _gateway_gaps()
	missing += _tax_gaps()
	missing += _trial_gaps()
	missing += _plan_gaps()
	missing += _product_gaps()
	return {"ready": not missing, "missing": missing}


def _gateway_gaps() -> list[str]:
	from central.billing.gateways.registry import GatewayNotFound, resolve_gateway_for_currency

	gaps = []
	try:
		if resolve_gateway_for_currency(CURRENCY) != GATEWAY:
			gaps.append(f"{CURRENCY} resolves to a gateway other than {GATEWAY}.")
	except GatewayNotFound:
		gaps.append(f"No enabled gateway is the default for {CURRENCY}. Enable {GATEWAY}.")

	gateway = frappe.db.get_value(
		"Payment Gateway",
		GATEWAY,
		["is_enabled", "credentials_validated_at", "is_webhook_active"],
		as_dict=True,
	)
	if not gateway or not gateway.credentials_validated_at:
		gaps.append(f"{GATEWAY} keys are not validated. Enter them on the Payment Gateway and save.")
	if not gateway or not gateway.is_webhook_active:
		gaps.append(f"{GATEWAY} webhook is not active. Use Re-register Webhook on the Payment Gateway.")
	return gaps


def _tax_gaps() -> list[str]:
	from central.billing import settings

	gaps = []
	if settings.signup_fallback_country() != HOME_COUNTRY:
		gaps.append(f"Billing Settings, Signup Fallback Country is not {HOME_COUNTRY}.")
	if settings.billing_currency() != CURRENCY:
		gaps.append(f"Billing Settings, Billing Currency is not {CURRENCY}.")
	for country, rate in SEED_VAT_RATES.items():
		if settings.vat_rate_for_country(country) != rate:
			gaps.append(f"Billing Settings, VAT Rates by Country has no {rate}% row for {country}.")
	return gaps


def _trial_gaps() -> list[str]:
	stored = frappe.db.get_value("Central Settings", "Central Settings", list(TRIAL_SETTINGS), as_dict=True)
	return [
		f"Central Settings, {field} is {stored.get(field)}, expected {value}."
		for field, value in TRIAL_SETTINGS.items()
		if frappe.utils.cint(stored.get(field)) != value
	]


def _plan_gaps() -> list[str]:
	"""A trial needs a plan marked Available on Trial, and converts onto a paid plan with a USD rate."""
	gaps = []
	if not frappe.db.exists("Plan", {"is_active": 1, "available_on_trial": 1}):
		gaps.append("No active Plan is marked Available on Trial.")
	paid = frappe.get_all("Plan", filters={"is_active": 1, "available_on_trial": 0}, pluck="name")
	priced = set(
		frappe.get_all(
			"Catalog Rate",
			filters={"priced_doctype": "Plan", "currency": CURRENCY, "rate": [">", 0]},
			pluck="priced_for",
		)
	)
	if not any(plan in priced for plan in paid):
		gaps.append(f"No active paid Plan has a {CURRENCY} Catalog Rate. The owner sets the prices.")
	return gaps


def _product_gaps() -> list[str]:
	product = frappe.db.get_value(
		"Product", BUNDLE_PRODUCT["product_key"], ["enabled", "trial_days"], as_dict=True
	)
	if not product:
		return [f"Product {BUNDLE_PRODUCT['product_key']} does not exist. Run ensure_bundle_product."]
	gaps = []
	if not product.enabled:
		gaps.append(
			f"Product {BUNDLE_PRODUCT['product_key']} is disabled. Enable it once its trial image exists."
		)
	if product.trial_days and product.trial_days != BUNDLE_PRODUCT["trial_days"]:
		gaps.append(f"Product {BUNDLE_PRODUCT['product_key']} runs trials of {product.trial_days} days.")
	return gaps
