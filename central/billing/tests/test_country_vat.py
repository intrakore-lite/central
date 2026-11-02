# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt
"""VAT by billing country, from Billing Settings, VAT Rates by Country.

India keeps GST. Any other country is VAT at the rate in the table, or untaxed when
the table has no row for it. A team billed in USD through Stripe never gets GST."""

import frappe

from central.billing import market_setup, settings
from central.billing.gateways.registry import resolve_gateway_for_currency
from central.billing.payments import provisioning
from central.billing.revenue import tax
from central.billing.tests.test_stripe_adapter import make_stripe_gateway
from central.billing.tests.utils import BillingTestCase, ensure_team, make_user

TEAM = "team-country-vat"
UAE = "United Arab Emirates"


def make_profile(country, currency="USD"):
	"""A minimal Billing Profile, as signup stamps it: the country and its currency."""
	frappe.get_doc(
		{"doctype": "Billing Profile", "team": TEAM, "country": country, "currency": currency}
	).insert(ignore_permissions=True, ignore_mandatory=True)


class TestCountryVat(BillingTestCase):
	def setUp(self):
		ensure_team(TEAM, owner=make_user("billing-country-vat-owner@example.com"))
		make_stripe_gateway()  # USD defaults to Stripe
		self.saved = frappe.get_doc(settings.SETTINGS).as_dict()
		self.set_rates({UAE: 5})

	def tearDown(self):
		doc = frappe.get_doc(settings.SETTINGS)
		doc.signup_fallback_country = self.saved.get("signup_fallback_country")
		doc.set("country_tax_rates", [])
		for row in self.saved.get("country_tax_rates") or []:
			doc.append(
				"country_tax_rates", {"country": row.country, "vat_rate": row.vat_rate, "note": row.note}
			)
		doc.save(ignore_permissions=True)

	def set_rates(self, rates: dict, fallback: str | None = None):
		doc = frappe.get_doc(settings.SETTINGS)
		doc.set("country_tax_rates", [])
		for country, rate in rates.items():
			doc.append("country_tax_rates", {"country": country, "vat_rate": rate})
		doc.signup_fallback_country = fallback
		doc.save(ignore_permissions=True)

	def tax_profile(self):
		return frappe.db.get_value("Tax Profile", TEAM, ["output_tax_type", "output_tax_rate"], as_dict=True)

	def test_uae_team_is_billed_five_percent_vat(self):
		make_profile(UAE)
		provisioning.ensure_tax_profile(TEAM)

		self.assertEqual(self.tax_profile(), {"output_tax_type": "VAT", "output_tax_rate": 5})
		block = tax.resolve_tax(TEAM, 1000)
		self.assertEqual(block["output_tax_type"], "VAT")
		self.assertEqual(block["output_tax_amount"], 50)

	def test_country_without_a_rate_is_untaxed(self):
		make_profile("Germany")
		provisioning.ensure_tax_profile(TEAM)

		self.assertEqual(self.tax_profile(), {"output_tax_type": "None", "output_tax_rate": 0})
		self.assertEqual(tax.resolve_tax(TEAM, 1000)["output_tax_amount"], 0)

	def test_zero_rate_row_is_untaxed(self):
		self.set_rates({UAE: 5, "Qatar": 0})
		make_profile("Qatar")
		provisioning.ensure_tax_profile(TEAM)

		self.assertEqual(self.tax_profile().output_tax_type, "None")

	def test_usd_stripe_team_never_resolves_gst(self):
		self.assertEqual(resolve_gateway_for_currency("USD"), "Stripe")
		for country in (UAE, "Saudi Arabia", "United States"):
			with self.subTest(country=country):
				frappe.db.delete("Tax Profile", {"team": TEAM})
				frappe.db.delete("Billing Profile", {"team": TEAM})
				make_profile(country)
				provisioning.ensure_tax_profile(TEAM)

				self.assertNotEqual(self.tax_profile().output_tax_type, "GST")
				self.assertNotEqual(tax.resolve_tax(TEAM, 1000)["output_tax_type"], "GST")

	def test_vat_follows_a_country_corrected_before_invoicing(self):
		make_profile(UAE)
		provisioning.ensure_tax_profile(TEAM)

		profile = frappe.get_doc("Billing Profile", TEAM)
		profile.country = "Germany"
		profile.flags.ignore_mandatory = True
		profile.save(ignore_permissions=True)

		self.assertEqual(self.tax_profile(), {"output_tax_type": "None", "output_tax_rate": 0})

	def test_signup_without_a_country_uses_the_fallback_country(self):
		self.set_rates({UAE: 5}, fallback=UAE)

		provisioning.provision_signup_billing(TEAM, None)

		profile = frappe.db.get_value("Billing Profile", TEAM, ["country", "currency"], as_dict=True)
		self.assertEqual(profile, {"country": UAE, "currency": "USD"})
		self.assertEqual(self.tax_profile(), {"output_tax_type": "VAT", "output_tax_rate": 5})

	def test_signup_fallback_is_india_when_unset(self):
		self.assertEqual(settings.signup_fallback_country(), "India")

	def test_india_cannot_have_a_vat_row(self):
		with self.assertRaises(frappe.ValidationError):
			self.set_rates({"India": 5})

	def test_a_country_has_one_vat_row(self):
		doc = frappe.get_doc(settings.SETTINGS)
		doc.append("country_tax_rates", {"country": UAE, "vat_rate": 10})
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)


class TestMarketSetup(BillingTestCase):
	def setUp(self):
		self.saved = frappe.get_doc(settings.SETTINGS).as_dict()
		self.saved_trial = frappe.db.get_value(
			"Central Settings", "Central Settings", list(market_setup.TRIAL_SETTINGS), as_dict=True
		)

	def tearDown(self):
		doc = frappe.get_doc(settings.SETTINGS)
		doc.signup_fallback_country = self.saved.get("signup_fallback_country")
		doc.set("country_tax_rates", [])
		for row in self.saved.get("country_tax_rates") or []:
			doc.append(
				"country_tax_rates", {"country": row.country, "vat_rate": row.vat_rate, "note": row.note}
			)
		doc.save(ignore_permissions=True)
		frappe.db.set_single_value("Central Settings", dict(self.saved_trial))
		frappe.db.delete("Product", {"name": market_setup.BUNDLE_PRODUCT["product_key"]})

	def test_configure_sets_usd_stripe_vat_trial_and_product(self):
		result = market_setup.configure_usd_stripe_market()

		row = frappe.db.get_value(
			"Payment Gateway Currency",
			{"parent": "Stripe", "currency": "USD"},
			["is_default", "requires_predebit_notice"],
			as_dict=True,
		)
		self.assertEqual(row, {"is_default": 1, "requires_predebit_notice": 0})
		self.assertEqual(settings.signup_fallback_country(), UAE)
		self.assertEqual(settings.vat_rate_for_country(UAE), 5)
		self.assertIsNone(settings.vat_rate_for_country("Saudi Arabia"))
		self.assertEqual(frappe.db.get_single_value("Central Settings", "trial_days"), 60)
		product = frappe.db.get_value("Product", "crm-estimation", ["enabled", "trial_days"], as_dict=True)
		self.assertEqual(product, {"enabled": 0, "trial_days": 60})
		# Keys and prices are the operator's, so the site is not ready yet.
		self.assertFalse(result["ready"])

	def test_configure_is_idempotent(self):
		market_setup.configure_usd_stripe_market()
		market_setup.configure_usd_stripe_market()

		rows = [r for r in frappe.get_doc(settings.SETTINGS).country_tax_rates if r.country == UAE]
		self.assertEqual(len(rows), 1)
