import json
from unittest.mock import Mock, patch

import frappe
import requests
from frappe.tests import IntegrationTestCase

from central.api import onboarding as api
from central.api.teams import create_team
from central.billing.tests.utils import give_team_a_card, reset_gateway_roster
from central.signups import onboarding, site_onboarding
from central.signups.site_onboarding import (
	HEADER,
	SiteOnboardingClient,
	SiteRateLimited,
	SiteRefused,
	SiteRejected,
	SiteUnavailable,
)
from central.tests.test_team_onboarding import create_user

SECRET = "s3cret-value-for-the-test"
SITE_URL = "https://apex.example.test"


def response(status: int, body: dict | None = None) -> Mock:
	answer = Mock(status_code=status)
	answer.json.return_value = body if body is not None else {}
	return answer


def client_with(*responses) -> tuple[SiteOnboardingClient, Mock]:
	session = Mock()
	session.post.side_effect = list(responses)
	return SiteOnboardingClient(SITE_URL, SECRET, session), session


class TestSiteOnboardingClient(IntegrationTestCase):
	"""The client of a site's onboarding API: secret header, retries and errors."""

	def setUp(self):
		self.enterContext(patch("central.signups.site_onboarding.time.sleep"))

	def test_a_call_posts_json_with_the_secret_header(self):
		client, session = client_with(response(200, {"message": {"setup_complete": True}}))

		self.assertEqual(client.get_state(), {"setup_complete": True})

		url = session.post.call_args.args[0]
		kwargs = session.post.call_args.kwargs
		self.assertEqual(url, f"{SITE_URL}/api/method/intrakore_master.cloud_onboarding.get_state")
		self.assertEqual(kwargs["headers"][HEADER], SECRET)
		self.assertEqual(kwargs["json"], {})
		self.assertFalse(kwargs["allow_redirects"])

	def test_each_method_wraps_its_payload_under_the_sites_argument(self):
		client, session = client_with(*(response(200, {"message": {}}) for _ in range(3)))

		client.complete_setup({"full_name": "A"})
		client.invite_members([{"email": "a@example.test"}])
		client.apply_master_setup({"crm": {}})

		payloads = [call.kwargs["json"] for call in session.post.call_args_list]
		self.assertEqual(
			payloads,
			[
				{"profile": {"full_name": "A"}},
				{"rows": [{"email": "a@example.test"}]},
				{"config": {"crm": {}}},
			],
		)

	def test_a_5xx_is_retried_then_succeeds(self):
		client, session = client_with(response(502), response(503), response(200, {"message": "ok"}))

		self.assertEqual(client.call("get_state"), "ok")
		self.assertEqual(session.post.call_count, 3)

	def test_a_5xx_that_persists_is_unavailable(self):
		client, session = client_with(response(500), response(500), response(500))

		with self.assertRaises(SiteUnavailable):
			client.get_state()
		self.assertEqual(session.post.call_count, 3)

	def test_a_refused_secret_is_not_retried(self):
		client, session = client_with(response(403))

		with self.assertRaises(SiteRefused) as raised:
			client.get_state()
		self.assertEqual(session.post.call_count, 1)
		self.assertNotIn(SECRET, raised.exception.message)

	def test_a_rate_limit_is_its_own_error(self):
		client, _session = client_with(response(429))

		with self.assertRaises(SiteRateLimited):
			client.get_state()

	def test_a_validation_error_carries_the_sites_message(self):
		messages = json.dumps([json.dumps({"message": "Unknown currency XYZ"})])
		client, session = client_with(response(417, {"_server_messages": messages}))

		with self.assertRaises(SiteRejected) as raised:
			client.apply_master_setup({"crm": {"deal_currency": "XYZ"}})
		self.assertEqual(raised.exception.message, "Unknown currency XYZ")
		self.assertEqual(session.post.call_count, 1)

	def test_a_site_that_does_not_answer_is_unavailable(self):
		session = Mock()
		session.post.side_effect = requests.ConnectionError("refused")

		with self.assertRaises(SiteUnavailable):
			SiteOnboardingClient(SITE_URL, SECRET, session).get_state()

	def test_a_404_means_the_api_is_not_served_yet(self):
		client, _session = client_with(response(404))

		with self.assertRaises(SiteUnavailable):
			client.get_state()


class TestOnboardingSecret(IntegrationTestCase):
	"""Central makes one secret per site creation and boots the machine with it."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)
		self.action = Mock(resource_type="Site", team=None)
		self.action.name = f"ACT-{frappe.generate_hash(length=8)}"

	def test_a_site_creation_gets_a_secret_and_the_onboarding_flag(self):
		config = site_onboarding.get_boot_site_config(self.action)

		self.assertGreaterEqual(len(config["intrakore_onboarding_secret"]), 40)
		self.assertEqual(config["intrakore_cloud_onboarding"], 1)

	def test_the_secret_is_stored_encrypted_and_kept_for_a_second_build(self):
		first = site_onboarding.get_boot_site_config(self.action)["intrakore_onboarding_secret"]
		second = site_onboarding.get_boot_site_config(self.action)["intrakore_onboarding_secret"]

		self.assertEqual(first, second)
		auth = frappe.qb.Table("__Auth")
		stored = (
			frappe.qb.from_(auth)
			.select(auth.password)
			.where(
				(auth.doctype == "Resource Action")
				& (auth.name == self.action.name)
				& (auth.fieldname == "onboarding_secret")
			)
			.run(pluck=True)
		)
		stored = stored[0] if stored else None
		self.assertTrue(stored)
		self.assertNotEqual(stored, first)

	def test_each_creation_gets_its_own_secret(self):
		other = Mock(resource_type="Site", team=None)
		other.name = f"ACT-{frappe.generate_hash(length=8)}"

		self.assertNotEqual(
			site_onboarding.get_boot_site_config(self.action)["intrakore_onboarding_secret"],
			site_onboarding.get_boot_site_config(other)["intrakore_onboarding_secret"],
		)

	def test_a_ready_site_gets_the_teams_seat_cap_in_its_own_config(self):
		owner = create_user("seats")
		frappe.set_user(owner)
		with patch("central.geo.get_country_from_ip", return_value="United Arab Emirates"):
			team = create_team("Seats Team")["name"]
		frappe.set_user("Administrator")
		frappe.db.set_value("Team", team, "seats", 7)
		site = Mock(team=team)

		with patch("central.billing.catalog.seats.push_user_limit") as push:
			site_onboarding.push_site_seat_limit(site)
			push.assert_called_once_with(site, 7)

			frappe.db.set_value("Team", team, "seats", 0)
			push.reset_mock()
			site_onboarding.push_site_seat_limit(site)
			push.assert_not_called()

	def test_the_site_outgoing_email_rides_in_the_boot_config(self):
		settings = frappe.get_single("Central Settings")
		saved = {
			k: settings.get(k)
			for k in ("site_mail_server", "site_mail_port", "site_mail_login", "site_mail_sender")
		}
		self.addCleanup(frappe.db.set_single_value, "Central Settings", saved)

		frappe.db.set_single_value("Central Settings", "site_mail_server", "")
		frappe.clear_document_cache("Central Settings", "Central Settings")
		self.assertNotIn("mail_server", site_onboarding.get_boot_site_config(self.action))

		frappe.db.set_single_value(
			"Central Settings",
			{
				"site_mail_server": "mail.example.com",
				"site_mail_port": 2525,
				"site_mail_use_tls": 1,
				"site_mail_login": "sites@example.com",
				"site_mail_sender": "",
			},
		)
		frappe.clear_document_cache("Central Settings", "Central Settings")
		config = site_onboarding.get_boot_site_config(self.action)
		self.assertEqual(
			(
				config["mail_server"],
				config["mail_port"],
				config["use_tls"],
				config["mail_login"],
				config["auto_email_id"],
			),
			("mail.example.com", 2525, 1, "sites@example.com", "sites@example.com"),
		)
		self.assertIn("intrakore_onboarding_secret", config)

	def test_the_boot_config_leaves_the_seat_cap_to_the_bootstrap(self):
		self.assertNotIn("max_system_users", site_onboarding.get_boot_site_config(self.action))

	def test_a_server_creation_gets_no_site_keys(self):
		self.action.resource_type = "Server"

		self.assertEqual(site_onboarding.get_boot_site_config(self.action), {})

	def test_the_site_record_takes_over_the_secret(self):
		secret = site_onboarding.get_boot_site_config(self.action)["intrakore_onboarding_secret"]
		site = frappe.new_doc("Site")

		site_onboarding.adopt_action_secret(site, self.action.name)

		self.assertEqual(site.onboarding_secret, secret)
		self.assertIsNone(
			frappe.utils.password.get_decrypted_password(
				"Resource Action", self.action.name, "onboarding_secret", raise_exception=False
			)
		)


class TestSiteOnboardingApi(IntegrationTestCase):
	"""Steps 3 and 4 through Central: who may call them, and what reaches the site."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, "Administrator")
		reset_gateway_roster()
		self.owner = create_user("siteowner")
		frappe.set_user(self.owner)
		with patch("central.geo.get_country_from_ip", return_value="United Arab Emirates"):
			self.team = create_team("Apex Team")["name"]

	def test_another_team_cannot_reach_the_site(self):
		frappe.set_user("Administrator")
		stranger = create_user("sitestranger")
		frappe.set_user(stranger)

		calls = (
			lambda: api.site_state(team=self.team),
			lambda: api.complete_site_setup(team=self.team),
			lambda: api.invite_members(rows=[], team=self.team),
			lambda: api.finish_team_step(team=self.team),
			lambda: api.apply_master_setup(config={}, team=self.team),
		)
		for call in calls:
			with self.assertRaises(frappe.PermissionError):
				call()

	def test_without_a_creation_the_site_waits_for_the_card(self):
		self.assertEqual(api.site_state(team=self.team)["stage"], "waiting")

	def test_invitations_are_checked_before_they_reach_the_site(self):
		bad_rows = (
			[{"email": "not-an-email", "modules": "crm", "role": "Admin"}],
			[{"email": "a@example.test", "modules": "hr", "role": "Admin"}],
			[{"email": "a@example.test", "modules": "crm", "role": "Owner"}],
			[{"email": f"m{n}@example.test", "modules": "crm", "role": "Admin"} for n in range(201)],
		)
		with patch.object(onboarding, "call_site") as call_site:
			for rows in bad_rows:
				with self.assertRaises(frappe.ValidationError):
					api.invite_members(rows=rows, team=self.team)
		call_site.assert_not_called()

	def test_invitations_reach_the_site_trimmed_and_without_the_owner(self):
		rows = [
			{"full_name": " Layla ", "email": " Layla@Example.test ", "modules": "Both", "role": "Estimator"},
			{"full_name": "Me", "email": self.owner, "modules": "crm", "role": "Admin"},
		]
		with patch.object(onboarding, "call_site", return_value={"results": []}) as call_site:
			api.invite_members(rows=rows, team=self.team)

		call_site.assert_called_once_with(
			self.team,
			"invite_members",
			[{"full_name": "Layla", "email": "layla@example.test", "modules": "both", "role": "Estimator"}],
		)

	def test_bid_weights_must_add_up_to_100(self):
		with self.assertRaises(frappe.ValidationError):
			api.apply_master_setup(
				config={"crm": {"bid_weights": {"solvency": 50, "margin_risk": 30, "capacity": 30}}},
				team=self.team,
			)

	def test_master_setup_finishes_onboarding_and_drops_unknown_keys(self):
		config = {
			"crm": {"bid_weights": {"solvency": 35, "margin_risk": 40, "capacity": 25}, "extra": 1},
			"estimation": {"uom_system": "metric"},
			"hr": {"anything": True},
		}
		with patch.object(onboarding, "call_site", return_value={"applied": {}}) as call_site:
			api.apply_master_setup(config=config, team=self.team)

		sent = call_site.call_args.args[2]
		self.assertEqual(
			sent,
			{
				"crm": {"bid_weights": {"solvency": 35, "margin_risk": 40, "capacity": 25}},
				"estimation": {"uom_system": "metric"},
			},
		)
		self.assertTrue(frappe.db.get_value("Team", self.team, "setup_completed_at"))
		self.assertTrue(onboarding.get_progress(self.team)["done"])

	def test_progress_follows_the_steps(self):
		self.assertEqual(onboarding.get_progress(self.team)["step"], 1)

		frappe.db.set_value("Team", self.team, {"seats": 5, "business_type": "General Contracting"})
		self.assertEqual(onboarding.get_progress(self.team)["step"], 2)

		give_team_a_card(self.team)
		with patch.object(onboarding, "get_site_creation", return_value=frappe._dict(status="Queued")):
			self.assertEqual(onboarding.get_progress(self.team)["step"], 3)
			api.finish_team_step(team=self.team)
			self.assertEqual(onboarding.get_progress(self.team)["step"], 4)

	def test_the_site_profile_comes_from_step_1(self):
		frappe.db.set_value(
			"Team",
			self.team,
			{"business_type": "MEP Contracting", "headcount_bracket": "16–50", "turnover_band": ""},
		)
		frappe.db.set_value(
			"Billing Profile",
			self.team,
			{
				"legal_name": "Apex Contracting LLC",
				"phone": "+971508329410",
				"country": "United Arab Emirates",
				"tax_id": "100123456700003",
				"address_line1": "Office 12",
				"city": "Dubai",
			},
		)

		profile = site_onboarding.site_profile(self.team)

		self.assertEqual(profile["email"], self.owner)
		self.assertEqual(profile["company_name"], "Apex Contracting LLC")
		self.assertEqual(profile["currency"], "AED")
		self.assertEqual(profile["timezone"], "Asia/Dubai")
		self.assertEqual(profile["trn"], "100123456700003")
		self.assertEqual(profile["address"]["city"], "Dubai")
		self.assertEqual(profile["business_type"], "MEP Contracting")
		self.assertNotIn("turnover_band", profile)

	def test_a_failed_call_is_logged_without_the_secret(self):
		site = Mock(name="site", url=SITE_URL)
		site.name = "apex.example.test"
		site.get_password.return_value = SECRET
		session = Mock()
		session.post.return_value = response(403)
		with (
			patch.object(onboarding, "get_onboarding_site", return_value=site),
			patch("central.signups.site_onboarding.requests.Session", return_value=session),
			patch("frappe.log_error") as log_error,
		):
			with self.assertRaises(frappe.ValidationError):
				onboarding.call_site(self.team, "invite_members", [])

		logged = json.dumps(
			[str(arg) for arg in (*log_error.call_args.args, *log_error.call_args.kwargs.values())]
		)
		self.assertNotIn(SECRET, logged)
