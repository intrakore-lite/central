import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from central.api.onboarding import get_onboarding, save_profile, start_site
from central.api.teams import create_team
from central.billing.tests.utils import give_team_a_card, reset_gateway_roster
from central.signups import onboarding
from central.tests.test_team_onboarding import create_user

PROFILE = {
	"full_name": "Tariq Al-Mansoor",
	"mobile": "+971 50 832 9410",
	"country": "United Arab Emirates",
	"organisation": "Apex Contracting LLC",
	"business_type": "General Contracting",
	"headcount_bracket": "51–200",
	"turnover_band": "25–100M",
	"seats": 12,
}


class TestOnboardingProfile(IntegrationTestCase):
	"""Onboarding step 1 stores the organisation on the Team and its Billing Profile."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, "Administrator")
		reset_gateway_roster()
		self.owner = create_user("owner")
		frappe.set_user(self.owner)
		with patch("central.geo.get_country_from_ip", return_value="India"):
			self.team = create_team("Owner's Team")["name"]

	def test_profile_is_stored_on_the_team_and_billing_profile(self):
		saved = save_profile(team=self.team, **PROFILE)

		team = frappe.get_doc("Team", self.team)
		self.assertEqual(team.team_name, "Apex Contracting LLC")
		self.assertEqual(team.business_type, "General Contracting")
		self.assertEqual(team.headcount_bracket, "51–200")
		self.assertEqual(team.turnover_band, "25–100M")
		self.assertEqual(team.seats, 12)
		billing = frappe.db.get_value(
			"Billing Profile", self.team, ["legal_name", "phone", "country"], as_dict=True
		)
		self.assertEqual(billing.legal_name, "Apex Contracting LLC")
		self.assertEqual(billing.phone, "+971508329410")
		self.assertEqual(billing.country, "United Arab Emirates")
		self.assertEqual(saved["full_name"], "Tariq Al-Mansoor")

	def test_the_invitation_gets_the_team_and_names_its_product(self):
		from central.signups.doctype.trial_invitation.trial_invitation import invite

		frappe.set_user("Administrator")
		with patch("central.signups.doctype.trial_invitation.trial_invitation.frappe.sendmail"):
			invitation = invite(self.owner, "Tariq Al-Mansoor", "Apex Contracting LLC")
		invitation.db_set({"status": "Accepted", "team": None, "product": "crm"})
		frappe.set_user(self.owner)

		save_profile(team=self.team, **PROFILE)

		self.assertEqual(frappe.db.get_value("Trial Invitation", invitation.name, "team"), self.team)
		with patch("central.signups.onboarding.resolve_trial_product", side_effect=lambda name: name):
			self.assertEqual(onboarding.get_team_product(self.team, None), "crm")

	def test_turnover_is_optional(self):
		save_profile(team=self.team, **{**PROFILE, "turnover_band": None})

		self.assertFalse(frappe.db.get_value("Team", self.team, "turnover_band"))

	def test_seats_outside_the_bands_are_refused(self):
		for seats in (0, onboarding.MAX_SEATS + 1):
			with self.assertRaises(frappe.ValidationError):
				save_profile(team=self.team, **{**PROFILE, "seats": seats})

	def test_a_missing_answer_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			save_profile(team=self.team, **{**PROFILE, "organisation": "  "})

	def test_another_team_cannot_read_or_change_the_profile(self):
		frappe.set_user("Administrator")
		stranger = create_user("stranger")
		frappe.set_user(stranger)

		with self.assertRaises(frappe.PermissionError):
			get_onboarding(team=self.team)
		with self.assertRaises(frappe.PermissionError):
			save_profile(team=self.team, **PROFILE)

	def test_a_site_starts_only_after_a_card_is_saved(self):
		with self.assertRaises(frappe.ValidationError):
			start_site(team=self.team)

		frappe.set_user("Administrator")
		give_team_a_card(self.team)
		frappe.set_user(self.owner)
		with (
			patch("central.signups.onboarding.resolve_trial_product", return_value="crm"),
			patch("frappe.enqueue") as enqueue,
		):
			self.assertTrue(start_site(team=self.team)["queued"])

		self.assertEqual(enqueue.call_args.kwargs["team"], self.team)
		self.assertEqual(enqueue.call_args.kwargs["user"], self.owner)


class TestOnboardingContent(IntegrationTestCase):
	"""The trust content and site name of the onboarding pages."""

	def tearDown(self):
		frappe.db.set_single_value("Central Settings", "onboarding_trust_content", None)
		frappe.clear_document_cache("Central Settings")

	def test_settings_replace_only_the_keys_they_set(self):
		frappe.db.set_single_value(
			"Central Settings",
			"onboarding_trust_content",
			json.dumps({"profile_badge": "ISO 9001", "unknown": "ignored"}),
		)
		frappe.clear_document_cache("Central Settings")

		content = onboarding.get_trust_content()

		self.assertEqual(content["profile_badge"], "ISO 9001")
		self.assertEqual(content["benefits"], onboarding.DEFAULT_TRUST_CONTENT["benefits"])
		self.assertNotIn("unknown", content)

	def test_defaults_make_no_claim_the_platform_cannot_back(self):
		text = json.dumps(onboarding.DEFAULT_TRUST_CONTENT)

		for claim in ("SOC 2", "DIFC", "ADGM", "500+", "14B", "Farhan"):
			self.assertNotIn(claim, text)

	def test_the_base_plan_bills_at_least_its_included_seats(self):
		self.assertEqual(
			onboarding.get_seat_quote(3, 100, 5),
			{"seats": 3, "billed_seats": 5, "monthly": 500, "vat": 25, "total": 525},
		)
		self.assertEqual(onboarding.get_seat_quote(12, 99.5, 5)["total"], 1253.7)

	def test_the_site_plan_follows_the_seat_band(self):
		self.assertEqual(onboarding.get_plan_for_seats(1), "plan-1vcpu")
		self.assertEqual(onboarding.get_plan_for_seats(5), "plan-1vcpu")
		self.assertEqual(onboarding.get_plan_for_seats(6), "plan-2vcpu")
		self.assertEqual(onboarding.get_plan_for_seats(40), "plan-4vcpu")
		self.assertEqual(onboarding.get_plan_for_seats(41), "plan-8vcpu")

	def test_a_hosted_card_page_returns_only_to_this_site(self):
		from central.billing.api.dashboard.methods import _own_site_url

		own = f"{frappe.utils.get_url()}/dashboard/onboarding/card-saved"
		self.assertEqual(_own_site_url(own), own)
		self.assertIsNone(_own_site_url(None))
		with self.assertRaises(frappe.ValidationError):
			_own_site_url("https://evil.example/dashboard")

	def test_site_name_follows_the_organisation_and_skips_taken_names(self):
		taken = {"apex-contracting-llc"}
		with patch(
			"central.site_provisioning.subdomain_availability",
			side_effect=lambda name: {"available": name not in taken},
		):
			self.assertEqual(onboarding.free_subdomain("Apex Contracting LLC"), "apex-contracting-llc-2")


class TestTaxRegistrationNumber(IntegrationTestCase):
	"""A UAE billing profile keeps a TRN of 15 digits."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.team = frappe.get_doc(
			{"doctype": "Team", "team_name": "TRN", "owner_user": "Administrator"}
		).insert()
		self.profile = frappe.get_doc(
			{"doctype": "Billing Profile", "team": self.team.name, "country": "United Arab Emirates"}
		)

	def test_trn_is_stored_without_dashes(self):
		self.profile.tax_id = "100-1234-5678-9003"
		self.profile.insert(ignore_permissions=True)

		self.assertEqual(self.profile.tax_id, "100123456789003")

	def test_short_trn_is_refused(self):
		self.profile.tax_id = "1234"
		with self.assertRaises(frappe.ValidationError):
			self.profile.insert(ignore_permissions=True)
