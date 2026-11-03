from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from central.api import trial_metrics
from central.tests.test_iam import ensure_user
from central.tests.utils import ensure_atlas_instance


class TestTrialMetrics(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, "Administrator")
		self.addCleanup(frappe.db.rollback)
		self.suffix = frappe.generate_hash(length=8)
		self.region = ensure_atlas_instance(f"trials-{self.suffix}")
		owner = ensure_user("trial.metrics.owner@example.test")
		self.team = frappe.get_doc(
			{
				"doctype": "Team",
				"team_name": f"Trial Metrics {self.suffix}",
				"owner_user": owner,
				"members": [{"user": owner, "role": "Owner", "status": "Active"}],
			}
		).insert(ignore_permissions=True)

	def site(self, label: str, **trial):
		machine = frappe.get_doc(
			{
				"doctype": "Virtual Machine",
				"resource_id": f"server-{label}-{self.suffix}",
				"team": self.team.name,
				"region": self.region,
				"status": "Running",
			}
		).insert(ignore_permissions=True)
		site = frappe.get_doc(
			{
				"doctype": "Site",
				"site_name": f"{label}-{self.suffix}.example.test",
				"team": self.team.name,
				"server": machine.name,
			}
		).insert(ignore_permissions=True)
		site.db_set(trial)
		return site

	def test_counts_cost_and_conversion_of_trial_sites(self):
		before = trial_metrics.get_trial_counts()
		cost_before = trial_metrics.get_trial_cost()["usd_total"]

		self.site("soon", trial_state="Active", trial_ends_on=add_days(nowdate(), 3))
		self.site("later", trial_state="Active", trial_ends_on=add_days(nowdate(), 20))
		self.site("won", trial_state="Converted", trial_cost=36.725, trial_currency="AED")
		self.site("lost", trial_state="Ended", trial_cost=5, trial_currency="USD")

		after = trial_metrics.get_trial_counts()
		self.assertEqual(after["active"] - before["active"], 2)
		self.assertEqual(after["ending_in_7_days"] - before["ending_in_7_days"], 1)
		self.assertEqual(after["converted"] - before["converted"], 1)
		self.assertEqual(after["ended"] - before["ended"], 1)
		self.assertAlmostEqual(trial_metrics.get_trial_cost()["usd_total"] - cost_before, 15, places=1)

	def test_the_summary_is_for_operators_only(self):
		frappe.set_user(ensure_user("trial.metrics.customer@example.test"))
		with self.assertRaises(frappe.PermissionError):
			trial_metrics.summary()
		with self.assertRaises(frappe.PermissionError):
			trial_metrics.trial_cost_card()

	def test_the_summary_answers_without_the_invitation_doctype(self):
		with (
			patch.object(trial_metrics, "get_invitation_funnel", return_value=None),
			patch.object(trial_metrics, "get_free_trial_subsidy", return_value=0.0),
		):
			summary = trial_metrics.summary()
		self.assertIsNone(summary["invitations"])
		self.assertIn("conversion_rate", summary["trials"])
		self.assertIn("usd_total", summary["trial_cost"])

	def test_no_invitation_doctype_means_no_funnel(self):
		real_exists = frappe.db.exists

		def exists(doctype, name=None, *args, **kwargs):
			if doctype == "DocType" and name == trial_metrics.INVITATION_DOCTYPE:
				return None
			return real_exists(doctype, name, *args, **kwargs)

		with patch.object(trial_metrics.frappe.db, "exists", side_effect=exists):
			self.assertIsNone(trial_metrics.get_invitation_funnel())
