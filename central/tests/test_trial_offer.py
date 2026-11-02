from urllib.parse import parse_qs, urlsplit

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import set_request
from frappe.website.serve import get_response

from central.signups.trial_offer import get_trial_offer


class TestTrialOffer(IntegrationTestCase):
	"""The /try link and the sign-in page offer the Default Trial Product of Central Settings."""

	def setUp(self):
		self.product = frappe.get_doc(
			{
				"doctype": "Product",
				"product_key": "try-" + frappe.generate_hash(length=6),
				"title": "CRM + Estimation",
				"signup_app": "intrakore_crm",
				"trial_days": 60,
			}
		).insert()
		self.set_default_trial_product(self.product.name)

	def set_default_trial_product(self, value: str | None) -> None:
		previous = frappe.db.get_single_value("Central Settings", "default_trial_product")
		frappe.db.set_single_value("Central Settings", "default_trial_product", value)
		frappe.clear_document_cache("Central Settings", "Central Settings")
		self.addCleanup(frappe.db.set_single_value, "Central Settings", "default_trial_product", previous)
		self.addCleanup(frappe.clear_document_cache, "Central Settings", "Central Settings")

	def follow_try(self, query: str = "") -> tuple[int, str, dict]:
		set_request(method="GET", path=f"/try?{query}" if query else "/try")
		response = get_response()
		location = urlsplit(response.headers["Location"])
		return response.status_code, location.path, parse_qs(location.query)

	def test_try_opens_the_trial_signup_and_keeps_the_campaign(self):
		status, path, query = self.follow_try("utm_source=intrakore.com&utm_campaign=try-intrakore")

		self.assertEqual(status, 302)
		self.assertEqual(path, "/dashboard/signup")
		self.assertEqual(
			query,
			{
				"utm_source": ["intrakore.com"],
				"utm_campaign": ["try-intrakore"],
				"product": [self.product.name],
			},
		)

	def test_try_without_a_trial_product_opens_the_plain_signup(self):
		self.set_default_trial_product(None)

		self.assertEqual(self.follow_try(), (302, "/dashboard/signup", {}))
		self.assertIsNone(get_trial_offer())

	def test_a_disabled_trial_product_is_not_offered(self):
		self.product.db_set("enabled", 0)

		self.assertIsNone(get_trial_offer())
		self.assertEqual(
			self.follow_try("utm_source=ads"), (302, "/dashboard/signup", {"utm_source": ["ads"]})
		)

	def test_the_sign_in_page_reads_the_offer_with_its_trial_days(self):
		self.assertEqual(
			get_trial_offer(),
			{"product": self.product.name, "title": "CRM + Estimation", "days": 60},
		)
