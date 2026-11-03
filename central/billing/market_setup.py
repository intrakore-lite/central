# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt
"""Set up a site that bills in AED through Checkout.com, with UAE VAT, and check it.

`configure_aed_checkout_market` writes the settings an operator would otherwise set by
hand in Desk. It is idempotent and keeps every value an operator has already set,
except the ones it names. It never writes a gateway key and never enables a gateway:
keys are the operator's. The AED prices it adds are the USD prices at the dirham's
fixed peg (`AED_PER_USD`), and only where a plan has no AED price yet, so a price the
owner set in AED is kept.

`ensure_bundle_product` adds the first product, disabled until its trial image exists.

`readiness` lists what is still missing before the first paid customer.

    pilot frappe --site <site> execute central.billing.market_setup.configure_aed_checkout_market
    pilot frappe --site <site> execute central.billing.market_setup.readiness

`execute` commits when the call returns, so nothing here commits.
"""

from decimal import ROUND_HALF_UP, Decimal

import frappe

from central.billing.settings import SETTINGS

CURRENCY = "AED"
GATEWAY = "Checkout"
HOME_COUNTRY = "United Arab Emirates"

# The UAE dirham is pegged to the US dollar at this rate.
SOURCE_CURRENCY = "USD"
AED_PER_USD = 3.6725

# The statutory invoice series when the market bills in AED: no Indian fiscal year in it.
UAE_INVOICE_SERIES = "INV/.YYYY./.#####"

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
	# 0: the product runs the Central Settings trial, so one setting moves every bundle.
	"trial_days": 0,
}

# Central Settings for the 30-day trial: the card is stored at signup and charged on day 30.
TRIAL_SETTINGS = {
	"trial_days": 30,
	"trial_deletion_days": 14,
	"trial_notice_days": 7,
	# A paid server, and so a trial that is kept, needs a payment method.
	"require_payment_method": 1,
}


def configure_aed_checkout_market(
	home_country: str = HOME_COUNTRY,
	trial_days: int = TRIAL_SETTINGS["trial_days"],
	trial_deletion_days: int = TRIAL_SETTINGS["trial_deletion_days"],
	trial_notice_days: int = TRIAL_SETTINGS["trial_notice_days"],
) -> dict:
	"""Make AED through Checkout.com the billing path, seed the home country's VAT, price the plans
	and the trust tiers in AED, set the trial clock and add the first product."""
	ensure_checkout_aed_default()
	ensure_billing_settings(home_country)
	ensure_aed_catalog_rates()
	ensure_aed_trust_thresholds()
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


def ensure_checkout_aed_default() -> None:
	"""Give the Checkout gateway an AED row that is the default for AED, with no silent-debit
	ceiling.

	Keys and Enabled stay as they are. Another gateway's AED default row is cleared, so
	AED resolves to Checkout.com whichever gateway is enabled."""
	from central.billing.gateways.setup import ensure_gateway_records

	ensure_gateway_records()
	if not frappe.db.get_value("Currency", CURRENCY, "enabled"):
		frappe.db.set_value("Currency", CURRENCY, "enabled", 1)
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
	"""Set the signup fallback country, the billing currency and the UAE invoice series, and
	add each seed VAT rate that has no row yet."""
	doc = frappe.get_doc(SETTINGS)
	doc.signup_fallback_country = home_country
	doc.billing_currency = CURRENCY
	doc.series_uae = doc.series_uae or UAE_INVOICE_SERIES
	configured = {row.country for row in doc.country_tax_rates}
	for country, rate in SEED_VAT_RATES.items():
		if country not in configured:
			doc.append(
				"country_tax_rates",
				{"country": country, "vat_rate": rate, "note": "UAE VAT standard rate"},
			)
	doc.save(ignore_permissions=True)


def ensure_aed_catalog_rates() -> list[str]:
	"""Add an AED Catalog Rate for every USD plan rate that has none, at `AED_PER_USD`.

	Returns the names it added. An AED rate that exists is never changed."""
	added = []
	for rate in frappe.get_all(
		"Catalog Rate",
		filters={"priced_doctype": "Plan", "currency": SOURCE_CURRENCY},
		fields=["priced_doctype", "priced_for", "cluster", "rate"],
	):
		target = {
			"priced_doctype": rate.priced_doctype,
			"priced_for": rate.priced_for,
			"cluster": rate.cluster,
			"currency": CURRENCY,
		}
		if frappe.db.exists("Catalog Rate", {**target, "cluster": rate.cluster or ["is", "not set"]}):
			continue
		doc = frappe.get_doc({"doctype": "Catalog Rate", **target, "rate": to_aed(rate.rate)})
		doc.insert(ignore_permissions=True)
		added.append(doc.name)
	return added


def ensure_aed_trust_thresholds() -> list[str]:
	"""Add an AED threshold to every Trust Tier Level that has a USD one and no AED one.

	The fixture carries the same rows; this covers a site whose ladder was edited."""
	added = []
	for name in frappe.get_all("Trust Tier Level", pluck="name"):
		level = frappe.get_doc("Trust Tier Level", name)
		rows = {row.currency: row for row in level.thresholds}
		if CURRENCY in rows or SOURCE_CURRENCY not in rows:
			continue
		usd = rows[SOURCE_CURRENCY]
		level.append(
			"thresholds",
			{
				"currency": CURRENCY,
				"max_spend": to_aed(usd.max_spend),
				"min_cumulative_paid": to_aed(usd.min_cumulative_paid),
			},
		)
		level.save(ignore_permissions=True)
		added.append(name)
	return added


def to_aed(usd_amount) -> float:
	"""The AED amount at the peg, rounded half up to fils, as the fixture's AED rows are."""
	aed = Decimal(str(frappe.utils.flt(usd_amount))) * Decimal(str(AED_PER_USD))
	return float(aed.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def readiness() -> dict:
	"""What an AED Checkout.com site still needs before it can take a paid customer.

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
		[
			"is_enabled",
			"credentials_validated_at",
			"processing_channel_id",
			"checkout_environment",
			"webhook_endpoint_id",
			"is_webhook_active",
		],
		as_dict=True,
	)
	if not gateway or not gateway.credentials_validated_at:
		gaps.append(f"{GATEWAY} keys are not validated. Enter them on the Payment Gateway and save.")
	if not gateway or not (
		gateway.processing_channel_id or frappe.conf.get("checkout_processing_channel_id")
	):
		gaps.append(f"{GATEWAY} Processing Channel ID is not set on the Payment Gateway.")
	if gateway and gateway.checkout_environment != "Live":
		gaps.append(f"{GATEWAY} is in the Sandbox environment. Set Live once the live keys are in.")
	if not gateway or not gateway.webhook_endpoint_id or not gateway.is_webhook_active:
		gaps.append(f"{GATEWAY} webhook is not registered. Use Re-register Webhook on the Payment Gateway.")
	from central.billing.gateways.registry import get_adapter

	if gateway and not get_adapter(frappe.get_doc("Payment Gateway", GATEWAY)).get_credential(
		"webhook_secret"
	):
		gaps.append(f"{GATEWAY} Webhook Secret is empty. Re-register the webhook to set it.")
	return gaps


def _tax_gaps() -> list[str]:
	from central.billing import settings

	gaps = []
	if settings.signup_fallback_country() != HOME_COUNTRY:
		gaps.append(f"Billing Settings, Signup Fallback Country is not {HOME_COUNTRY}.")
	if settings.billing_currency() != CURRENCY:
		gaps.append(f"Billing Settings, Billing Currency is not {CURRENCY}.")
	if not frappe.db.get_single_value(SETTINGS, "series_uae"):
		gaps.append("Billing Settings, UAE Invoice Series is empty.")
	if not frappe.db.get_single_value(SETTINGS, "company_trn"):
		gaps.append("Billing Settings, Company TRN is empty. The tax invoice must show it.")
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
	"""A trial needs a plan marked Available on Trial, and converts onto a paid plan with an AED rate."""
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
