import frappe
from frappe.tests import IntegrationTestCase

from central.branding import BRAND_LOGO, get_brand


class TestBranding(IntegrationTestCase):
	def setUp(self):
		self.set_brand_name("")

	def set_brand_name(self, value: str) -> None:
		previous = frappe.db.get_single_value("Central Settings", "brand_name")
		frappe.db.set_single_value("Central Settings", "brand_name", value)
		frappe.clear_document_cache("Central Settings", "Central Settings")
		self.addCleanup(frappe.db.set_single_value, "Central Settings", "brand_name", previous)
		self.addCleanup(frappe.clear_document_cache, "Central Settings", "Central Settings")

	def test_the_base_email_shows_the_intrakore_brand_only(self):
		html = frappe.render_template("templates/emails/base.html", {})

		self.assertIn(">Intrakore Cloud</span>", html)
		self.assertIn("a member of a team on Intrakore Cloud", html)
		self.assertIn(BRAND_LOGO, html)
		self.assertNotIn("Frappe Cloud", html)
		self.assertNotIn("frappe.io", html)

	def test_the_invitation_email_names_the_brand(self):
		args = {
			"team_name": "Acme",
			"invited_by": "Ann",
			"role": "Admin",
			"invitation_url": "https://example.test/join",
			"expires_on": "1 Dec",
		}
		html = frappe.render_template("templates/emails/team_invitation.html", args)

		self.assertIn("Join Acme on Intrakore Cloud", html)
		self.assertNotIn("Frappe Cloud", html)

	def test_central_settings_rename_the_brand_everywhere(self):
		self.set_brand_name("Acme Cloud")

		html = frappe.render_template("templates/emails/base.html", {})

		self.assertEqual(get_brand()["title"], "Acme Cloud")
		self.assertIn(">Acme Cloud</span>", html)
		self.assertNotIn("Intrakore Cloud", html)
