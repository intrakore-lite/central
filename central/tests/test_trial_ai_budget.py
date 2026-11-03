from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from central.services import trial_ai_budget

MODULE = "central.services.trial_ai_budget"


def settings(**values):
	return SimpleNamespace(get=values.get)


class TestTrialAIBudget(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.db.rollback)
		frappe.db.set_single_value("AI Settings", "trial_key_cap", 2)

	def budget(self, **values):
		with patch(f"{MODULE}.frappe.get_cached_doc", return_value=settings(**values)):
			return trial_ai_budget.get_budget_usd()

	def test_an_aed_cap_converts_at_the_peg(self):
		self.assertEqual(self.budget(trial_ai_cap=50, seat_price_currency="AED"), 13.61)

	def test_a_usd_cap_is_used_as_is(self):
		self.assertEqual(self.budget(trial_ai_cap=10, seat_price_currency="USD"), 10)

	def test_without_a_trial_ai_cap_the_trial_key_cap_applies(self):
		self.assertEqual(self.budget(), 2)

	def test_a_cap_in_a_currency_that_does_not_convert_falls_back(self):
		with patch(f"{MODULE}.frappe.log_error") as log_error:
			self.assertEqual(self.budget(trial_ai_cap=1000, seat_price_currency="INR"), 2)
		log_error.assert_called_once()

	def test_the_trial_key_is_minted_with_the_budget_rounded_up(self):
		with patch(f"{MODULE}.get_budget_usd", return_value=13.61):
			self.assertEqual(trial_ai_budget.get_trial_key_cap(), 14)

	def test_only_a_free_trial_or_a_managed_team_gets_the_budget(self):
		paid = SimpleNamespace(is_free_trial=0, team="TEAM-X")
		trial = SimpleNamespace(is_free_trial=1, team="TEAM-X")
		with (
			patch(f"{MODULE}.iam.is_managed_team", return_value=False),
			patch(f"{MODULE}.get_budget_usd", return_value=13.61),
		):
			self.assertEqual(trial_ai_budget.get_site_config(paid), {})
			self.assertEqual(
				trial_ai_budget.get_site_config(trial),
				{"intrakore_ai_monthly_budget_usd": 13.61, "intrakore_ai_over_budget_action": "stop"},
			)
		with (
			patch(f"{MODULE}.iam.is_managed_team", return_value=True),
			patch(f"{MODULE}.get_budget_usd", return_value=13.61),
		):
			self.assertIn("intrakore_ai_monthly_budget_usd", trial_ai_budget.get_site_config(paid))

	def test_no_budget_writes_no_keys(self):
		trial = SimpleNamespace(is_free_trial=1, team="TEAM-X")
		with patch(f"{MODULE}.get_budget_usd", return_value=0):
			self.assertEqual(trial_ai_budget.get_site_config(trial), {})
