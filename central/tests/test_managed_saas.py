"""Managed SaaS mode: customers keep their sites and products, operators keep the server tools."""

from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from central.api.identity import my_capabilities
from central.api.servers import _is_managed_plan_change, open_console
from central.api.sites import login_site, resolve_trial_product, trial_offer
from central.api.ssh_keys import create_team_ssh_key
from central.api.wireguard import list_wireguard_devices
from central.errors import AtlasResourceGone, to_error_response
from central.iam import (
	MANAGED_STAFF_CAPABILITIES,
	can,
	clear_grants_cache,
	is_managed_customer,
	is_managed_team,
)
from central.infrastructure.doctype.site.site import Site
from central.integrations.images import list_images, list_offerings
from central.resource_actions import submit_request
from central.signups.trial_product import get_default_trial_product
from central.tests.test_iam import ensure_user
from central.tests.test_sites import SiteOnAMachine
from central.tests.utils import central_limit, ensure_server


@contextmanager
def managed(enabled: bool = True):
	"""Turn Managed SaaS Mode on or off for one block. Grants are cached per request, so
	they are resolved again on both sides of the switch."""
	with central_limit("managed_saas_mode", int(enabled)):
		clear_grants_cache()
		try:
			yield
		finally:
			clear_grants_cache()


def add_member(team, user: str, role: str) -> None:
	team.append("members", {"user": user, "role": role, "status": "Active"})
	team.save(ignore_permissions=True)
	clear_grants_cache()


class ManagedTeam(IntegrationTestCase):
	"""A customer team with an Owner, a Developer and a Viewer, and one running server."""

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, "Administrator")
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(clear_grants_cache)
		suffix = frappe.generate_hash(length=8)
		self.owner = ensure_user(f"managed-owner-{suffix}@example.test")
		self.developer = ensure_user(f"managed-developer-{suffix}@example.test")
		self.viewer = ensure_user(f"managed-viewer-{suffix}@example.test")
		self.team = frappe.get_doc(
			{"doctype": "Team", "team_name": f"Managed {suffix}", "owner_user": self.owner}
		).insert(ignore_permissions=True)
		add_member(self.team, self.developer, "Developer")
		add_member(self.team, self.viewer, "Viewer")
		self.server = ensure_server(f"managed-{suffix}", self.team.name, status="Stopped")

	def as_user(self, user: str) -> None:
		frappe.set_user(user)
		clear_grants_cache()


class TestManagedCapabilities(ManagedTeam):
	def test_a_customer_loses_the_server_tools_and_keeps_the_site(self):
		with managed():
			for capability in MANAGED_STAFF_CAPABILITIES:
				self.assertFalse(can(self.owner, self.team.name, capability), capability)
				self.assertFalse(can(self.developer, self.team.name, capability, server=self.server))
			for capability in ("server:view", "server:create", "server:power", "server:site-login"):
				self.assertTrue(can(self.developer, self.team.name, capability, server=self.server))
			self.assertTrue(can(self.owner, self.team.name, "billing:manage"))

			self.as_user(self.owner)
			self.assertFalse(MANAGED_STAFF_CAPABILITIES & set(my_capabilities(self.team.name)))

	def test_the_tools_come_back_when_the_mode_is_off(self):
		with managed(False):
			for capability in MANAGED_STAFF_CAPABILITIES:
				self.assertTrue(can(self.owner, self.team.name, capability), capability)
			self.assertFalse(is_managed_customer(self.owner))

	def test_an_operator_keeps_every_tool(self):
		with managed():
			self.assertFalse(is_managed_customer("Administrator"))
			for capability in MANAGED_STAFF_CAPABILITIES:
				self.assertTrue(can("Administrator", self.team.name, capability, server=self.server))

	def test_a_customer_is_refused_the_console_ssh_keys_wireguard_and_the_bench(self):
		with managed():
			self.as_user(self.owner)
			with self.assertRaises(frappe.PermissionError):
				open_console(team=self.team.name, resource_id=self.server, mode="ssh")
			with self.assertRaises(frappe.PermissionError):
				create_team_ssh_key(self.team.name, "Laptop", "ssh-ed25519 AAAA laptop")
			with self.assertRaises(frappe.PermissionError):
				list_wireguard_devices(self.team.name)
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc("Virtual Machine", self.server).get_bench_login_url(self.owner)

	def test_an_operator_passes_the_capability_gates(self):
		with managed(), patch("central.api.servers.get_console_url", return_value="https://console") as url:
			self.assertEqual(
				open_console(team=self.team.name, resource_id=self.server, mode="ssh"),
				{"url": "https://console"},
			)
			url.assert_called_once()
			# The capability check passes, so the stopped server is the only refusal.
			with self.assertRaisesRegex(frappe.ValidationError, "stopped"):
				frappe.get_doc("Virtual Machine", self.server).get_bench_login_url("Administrator")

	def test_a_customer_may_change_the_plan_but_not_compose_a_size(self):
		with managed():
			self.as_user(self.owner)
			self.assertTrue(_is_managed_plan_change(team=self.team.name, plan="plan-2vcpu"))
			self.assertFalse(
				_is_managed_plan_change(team=self.team.name, plan="plan-2vcpu", disk_gigabytes=40)
			)
			self.assertFalse(
				_is_managed_plan_change(team=self.team.name, includes=[{"resource_type": "Disk"}])
			)

			# A developer has no billing:manage, so no plan change either.
			self.as_user(self.developer)
			self.assertFalse(_is_managed_plan_change(team=self.team.name, plan="plan-2vcpu"))

		with managed(False):
			self.as_user(self.owner)
			self.assertFalse(_is_managed_plan_change(team=self.team.name, plan="plan-2vcpu"))


class TestManagedCreation(ManagedTeam):
	def request(self, **values) -> dict:
		return {
			"team": self.team.name,
			"region": "scope-test",
			"title": "Acme",
			"offering": "pilot",
			"image_id": "image-1",
			"request_key": "managed-request-" + frappe.generate_hash(length=8),
			"plan": "any-plan",
			**values,
		}

	def test_a_customer_creates_from_a_product_only(self):
		with managed():
			self.as_user(self.owner)
			with self.assertRaisesRegex(frappe.PermissionError, "product"):
				submit_request(**self.request())

	def test_a_customer_cannot_send_ssh_keys_or_user_data(self):
		with managed():
			self.as_user(self.owner)
			for values in ({"ssh_key_ids": ["key-1"]}, {"user_data": "#!/bin/sh\nid"}):
				with self.assertRaisesRegex(frappe.PermissionError, "SSH keys and user data"):
					submit_request(**self.request(product="crm", **values))

	def test_a_customer_sees_no_raw_image_choice(self):
		with managed():
			self.as_user(self.owner)
			self.assertEqual(list_offerings(self.team.name), [])
			with self.assertRaises(frappe.PermissionError):
				list_images(self.team.name, "scope-test", "pilot")

	def test_an_operator_keeps_the_image_catalog(self):
		with managed():
			self.assertIsInstance(list_offerings(self.team.name), list)
			with patch("central.integrations.images.frappe.get_list", return_value=[{"name": "pilot"}]):
				self.assertEqual(list_offerings(self.team.name), [{"name": "pilot"}])


class TestManagedJobCopy(ManagedTeam):
	"""A background job runs as a system user, so the team decides the copy it stores."""

	def action_for(self, team: str):
		return frappe.get_doc({"doctype": "Resource Action", "action": "start", "team": team})

	def test_a_job_stores_site_copy_for_a_customer_team(self):
		with managed():
			self.assertFalse(is_managed_customer())
			action = self.action_for(self.team.name)
			self.assertTrue(action.reads_as_site)
			self.assertEqual(
				action.build_envelope("RESOURCE_GONE")["title"], "This site is no longer available"
			)
			envelope = to_error_response(AtlasResourceGone(), managed=action.reads_as_site)
			self.assertEqual(envelope["remediation"], "Refresh your site list to see the current state.")

	def test_a_team_an_operator_owns_keeps_server_copy(self):
		operator_team = frappe.get_doc(
			{"doctype": "Team", "team_name": f"Operator {self.team.name}", "owner_user": "Administrator"}
		).insert(ignore_permissions=True)
		with managed():
			self.assertFalse(is_managed_team(operator_team.name))
			action = self.action_for(operator_team.name)
			self.assertEqual(
				action.build_envelope("RESOURCE_GONE")["title"], "This server is no longer available"
			)

	def test_without_the_mode_a_customer_team_keeps_server_copy(self):
		with managed(False):
			self.assertFalse(is_managed_team(self.team.name))
			self.assertEqual(
				self.action_for(self.team.name).build_envelope("RESOURCE_GONE")["title"],
				"This server is no longer available",
			)


class TestManagedSiteLogin(SiteOnAMachine):
	"""A customer signs in to their own site as themselves, without the console capability."""

	def setUp(self):
		super().setUp()
		self.addCleanup(clear_grants_cache)
		self.enroll()
		from central.integrations.servers import observe_server

		observe_server(self.server)
		suffix = frappe.generate_hash(length=8)
		self.developer = ensure_user(f"site-developer-{suffix}@example.test")
		self.viewer = ensure_user(f"site-viewer-{suffix}@example.test")
		add_member(self.team, self.developer, "Developer")
		add_member(self.team, self.viewer, "Viewer")

	def login(self, user: str):
		frappe.set_user(user)
		clear_grants_cache()
		with (
			patch("central.api.sites.is_site_reachable", return_value=True),
			patch.object(Site, "get_login_url", return_value="https://site.example.test/app?sid=x") as minted,
		):
			state = login_site(self.site().name)
		return state, minted

	def test_a_customer_signs_in_as_themselves(self):
		with managed():
			site = self.site()
			self.assertEqual(site.get_login_user(self.developer)[0], self.developer)
			self.assertEqual(site.get_login_capability(self.developer), "server:site-login")
			self.assertFalse(can(self.developer, self.team.name, "server:console", server=self.server.name))

			state, minted = self.login(self.developer)

		self.assertEqual(state["login_url"], "https://site.example.test/app?sid=x")
		minted.assert_called_once_with(self.developer, None)

	def test_a_viewer_cannot_sign_in(self):
		with managed(), self.assertRaises(frappe.PermissionError):
			self.login(self.viewer)

	def test_an_operator_outside_the_team_signs_in_as_administrator(self):
		outsider = ensure_user(f"operator-{frappe.generate_hash(length=8)}@example.test")
		frappe.get_doc("User", outsider).add_roles("System Manager")
		with managed():
			site = self.site()
			self.assertEqual(site.get_login_user(outsider), (None, None))
			self.assertEqual(site.get_login_capability(outsider), "server:console")
			state, _minted = self.login(outsider)

		self.assertTrue(state["login_url"])

	def test_without_the_mode_a_bought_site_keeps_administrator(self):
		with managed(False):
			site = self.site()
			self.assertEqual(site.get_login_user(self.developer), (None, None))
			self.assertEqual(site.get_login_capability(self.developer), "server:console")
			_state, minted = self.login(self.developer)

		minted.assert_called_once_with(self.developer, None)


class TestTrialOffer(ManagedTeam):
	"""The Sites page offers the default trial product to a team whose next site is free."""

	def setUp(self):
		super().setUp()
		self.product = frappe.get_doc(
			{
				"doctype": "Product",
				"product_key": "offer-" + frappe.generate_hash(length=6),
				"title": "CRM + Estimation",
				"signup_app": "intrakore_crm",
			}
		).insert(ignore_permissions=True)
		self.enterContext(
			patch("central.signups.trial_product.get_default_trial_product", return_value=self.product.name)
		)

	def test_an_eligible_team_gets_the_offer(self):
		self.as_user(self.owner)
		offer = trial_offer(self.team.name)

		self.assertEqual(offer["product"], self.product.name)
		self.assertEqual(offer["title"], "CRM + Estimation")

	def test_a_paying_team_or_an_open_trial_gets_none(self):
		self.as_user(self.owner)
		with patch("central.signups.eligibility.has_active_payment_method", return_value=True):
			self.assertIsNone(trial_offer(self.team.name))
		with patch("central.signups.eligibility.get_open_trial_of_owner", return_value=object()):
			self.assertIsNone(trial_offer(self.team.name))

	def test_a_viewer_gets_none_and_an_outsider_is_refused(self):
		outsider = ensure_user(f"outsider-{frappe.generate_hash(length=8)}@example.test")
		self.as_user(self.viewer)
		self.assertIsNone(trial_offer(self.team.name))

		self.as_user(outsider)
		with self.assertRaises(frappe.PermissionError):
			trial_offer(self.team.name)

	def test_an_unknown_product_falls_back_to_the_default(self):
		self.as_user(self.owner)
		self.assertEqual(resolve_trial_product("no-such-product"), {"product": self.product.name})
		self.assertEqual(resolve_trial_product(self.product.name), {"product": self.product.name})


class TestDefaultTrialProduct(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.db.rollback)
		frappe.db.delete("Product")

	def test_the_oldest_enabled_signup_product_is_the_default(self):
		self.assertIsNone(get_default_trial_product())
		for key, enabled in (("disabled-one", 0), ("first-one", 1), ("second-one", 1)):
			frappe.get_doc(
				{
					"doctype": "Product",
					"product_key": key,
					"title": key,
					"signup_app": "app",
					"enabled": enabled,
				}
			).insert(ignore_permissions=True)

		self.assertEqual(get_default_trial_product(), "first-one")


class TestProductApps(IntegrationTestCase):
	"""A product card lists the apps its image carries, by friendly name."""

	def test_the_app_tags_become_friendly_names_with_core_apps_last(self):
		from central.signups.server_products import get_image_apps

		apps = get_image_apps(
			{
				"purpose": "pilot",
				"app": "intrakore_crm",
				"app_intrakore_ui": "0.3.0",
				"app_intrakore_master": "",
				"app_intrakore_estimation": "0.0.1",
				"app_intrakore_crm": "1.6.8",
				"app_intrakore_fixed_assets": "2.0.0",
			}
		)

		self.assertEqual(
			[(app["title"], app["version"], app["is_core"]) for app in apps],
			[
				("CRM", "1.6.8", False),
				("Estimation", "0.0.1", False),
				("Fixed Assets", "2.0.0", False),
				("Master", None, True),
				("UI", "0.3.0", True),
			],
		)
		self.assertEqual(apps[0]["app"], "intrakore_crm")
