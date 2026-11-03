from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.utils import add_days, get_last_day, getdate, nowdate

from central.billing.catalog import seats
from central.billing.catalog.pricing import set_catalog_rate
from central.billing.revenue.invoicing.lines import compute_line_items
from central.billing.tests.utils import make_plan
from central.tests.test_trial_lifecycle import TrialOnAMachine


class SeatsOnATrial(TrialOnAMachine):
	"""A product trial site whose team pays 50 USD a seat, with 3 seats included."""

	def setUp(self):
		super().setUp()
		self.enterContext(
			self.change_settings(
				"Central Settings",
				seat_price=50,
				included_seats=3,
				included_storage_gb=10,
				storage_price_per_gb=2,
			)
		)
		self.price_trial(30)
		product = frappe.get_doc(
			{
				"doctype": "Product",
				"product_key": "seats-" + frappe.generate_hash(length=6),
				"title": "CRM",
				"signup_app": "crm",
			}
		).insert()
		self.product = product.name
		self.site().db_set("product", self.product)
		self.server.db_set({"status": "Running", "vcpus": 1, "memory_megabytes": 2048, "disk_gigabytes": 25})
		# The server is built, so no action is pending on it.
		frappe.db.set_value("Resource Action", {"server": self.server.name}, "status", "Succeeded")
		self.set_seats(4)

	def set_seats(self, count: int) -> None:
		frappe.db.set_value("Team", self.team.name, "seats", count)

	def subscribe(self) -> frappe._dict:
		"""Open the server's subscription, as a conversion does."""
		return frappe.get_doc(
			{
				"doctype": "Subscription",
				"team": self.team.name,
				"server_id": self.server.name,
				"plan": "trial-lifecycle-plan",
				"enabled": 1,
			}
		).insert(ignore_permissions=True)

	def changes(self, subscription: str) -> list:
		return frappe.get_all(
			"Subscription Change",
			filters={"subscription": subscription},
			fields=["name", "change_type", "locked_rate", "new_value", "effective_at"],
			order_by="effective_at asc, creation asc",
		)


class TestSeatPrice(SeatsOnATrial):
	def test_seats_below_the_included_seats_bill_the_included_seats(self):
		self.set_seats(2)

		quote = seats.get_seat_quote(self.team.name)
		self.assertEqual((quote.billed_seats, quote.monthly_rate, quote.currency), (3, 150, "USD"))
		self.assertEqual(seats.get_seat_quote(self.team.name, 10).monthly_rate, 500)

	def test_a_product_rate_overrides_the_seat_price(self):
		set_catalog_rate("Product", self.product, "USD", 40)

		self.assertEqual(seats.get_seat_quote(self.team.name).monthly_rate, 160)

	def test_a_team_without_seats_or_a_seat_price_is_billed_by_its_plan(self):
		self.set_seats(0)
		self.assertIsNone(seats.get_seat_quote(self.team.name))

		self.set_seats(4)
		frappe.db.set_single_value("Central Settings", "seat_price", 0)
		self.assertIsNone(seats.get_seat_quote(self.team.name))

	def test_the_seat_band_names_the_server_plan(self):
		bands = {
			seat_count: seats.get_plan_for_seats(seat_count) for seat_count in (1, 5, 6, 15, 16, 40, 41, 500)
		}

		self.assertEqual(
			bands,
			{
				1: "plan-1vcpu",
				5: "plan-1vcpu",
				6: "plan-2vcpu",
				15: "plan-2vcpu",
				16: "plan-4vcpu",
				40: "plan-4vcpu",
				41: "plan-8vcpu",
				500: "plan-8vcpu",
			},
		)

	def test_storage_above_the_included_storage_is_charged(self):
		self.assertEqual(seats.get_storage_charge(25), 30)
		self.assertEqual(seats.get_storage_charge(5), 0)

	def test_a_seat_change_today_adds_the_rest_of_the_month_by_the_day(self):
		self.assertEqual(seats.get_prorated_amount(150, 300, "2026-11-16"), 75)
		self.assertEqual(seats.get_prorated_amount(300, 150, "2026-11-30"), -5)


class TestSeatSubscription(SeatsOnATrial):
	def test_a_seat_subscription_bills_the_seats_not_the_plan(self):
		subscription = self.subscribe()

		created = self.changes(subscription.name)[0]
		self.assertEqual((created.change_type, created.locked_rate), ("Created", 200))
		self.assertEqual(created.new_value, "4 seats")

	def test_a_seat_change_is_billed_by_the_day_on_the_invoice(self):
		subscription = self.subscribe()
		seats.change_seats(self.team.name, 10)

		created, changed = self.changes(subscription.name)
		self.assertEqual((changed.change_type, changed.locked_rate), ("Plan Changed", 500))
		frappe.db.set_value("Subscription Change", created.name, "effective_at", datetime(2026, 11, 1))
		frappe.db.set_value("Subscription Change", changed.name, "effective_at", datetime(2026, 11, 16))

		lines = compute_line_items(self.team.name, self.region.name, "2026-11-01", "2026-11-30")
		# 15 days at 4 seats (200 a month), then 15 days at 10 seats (500 a month).
		self.assertEqual(sum(line["amount"] for line in lines), 350)

	def test_a_seat_change_sends_the_user_limit_and_resizes_to_the_seat_band(self):
		seats.change_seats(self.team.name, 10)

		frappe.enqueue.assert_any_call(
			seats.sync_seat_limits,
			team=self.team.name,
			queue="short",
			enqueue_after_commit=True,
			job_id=f"seat-limits:{self.team.name}",
			deduplicate=True,
		)

		make_plan(
			"plan-2vcpu",
			includes=[
				{"resource_type": "Compute", "quantity": 2, "unit": "vCPU"},
				{"resource_type": "Memory", "quantity": 4, "unit": "GB"},
				{"resource_type": "Disk", "quantity": 50, "unit": "GB"},
			],
		)
		with patch("central.integrations.pilot.update_site_config") as update_site_config:
			seats.sync_seat_limits(self.team.name)

		update_site_config.assert_called_once_with(
			self.server.name, self.site().get_pilot_site_names(), {"max_system_users": 10}
		)
		resize = frappe.get_last_doc("Resource Action", {"server": self.server.name, "action": "resize"})
		configuration = resize.get_resize_configuration()
		self.assertEqual(resize.requested_by, "Administrator")
		self.assertEqual(configuration.plan, "plan-2vcpu")
		self.assertEqual(
			configuration.shape.model_dump(), {"vcpus": 2, "memory_megabytes": 4096, "disk_gigabytes": 50}
		)

	def test_a_seat_change_inside_the_band_does_not_resize(self):
		make_plan(
			"plan-1vcpu",
			includes=[
				{"resource_type": "Compute", "quantity": 1, "unit": "vCPU"},
				{"resource_type": "Memory", "quantity": 2, "unit": "GB"},
				{"resource_type": "Disk", "quantity": 25, "unit": "GB"},
			],
		)
		with patch("central.integrations.pilot.update_site_config"):
			seats.sync_seat_limits(self.team.name)

		self.assertFalse(
			frappe.db.exists("Resource Action", {"server": self.server.name, "action": "resize"})
		)

	def test_only_a_billing_manager_changes_the_seats(self):
		from central.billing.api.dashboard.seats import change_seats

		with self.set_user("Guest"), self.assertRaises(frappe.PermissionError):
			change_seats(10, self.team.name)

		self.assertEqual(frappe.db.get_value("Team", self.team.name, "seats"), 4)


class TestSeatTrial(SeatsOnATrial):
	def test_the_day_before_the_end_reminds_the_team_of_its_first_payment(self):
		with patch("central.signups.trial.has_active_payment_method", return_value=True):
			for days in (11, 12, 13, 13):
				self.run_on(days)

		self.assertEqual(self.sent_events(), ["trial_expiring"])
		context = self.notices.call_args.kwargs["context"]
		ends_on = getdate(self.site().trial_ends_on)
		self.assertEqual(context["seats"], 4)
		self.assertEqual(
			context["first_payment_on"], frappe.utils.formatdate(add_days(get_last_day(ends_on), 1))
		)
		self.assertTrue(context["first_payment"])

	def test_the_trial_status_carries_the_seat_price(self):
		status = self.trial_status()

		self.assertEqual(status["seats"]["monthly_rate"], 200)
		self.assertEqual(status["seats"]["seats"], 4)

	def test_a_cancelled_trial_ends_on_its_end_date_with_a_card_on_file(self):
		seats.set_cancellation(self.team.name, True)
		self.assertEqual(
			getdate(frappe.db.get_value("Team", self.team.name, "subscription_ends_on")),
			getdate(self.site().trial_ends_on),
		)

		with (
			patch("central.signups.trial.has_active_payment_method", return_value=True),
			patch.object(type(self.trial()), "enqueue_job"),
		):
			site = self.run_on(14)

		self.assertEqual(site.trial_state, "Ended")
		self.assertNotIn("trial_converted", self.sent_events())

	def test_a_cancelled_paid_site_stops_after_the_month_and_is_terminated_later(self):
		self.site().db_set("trial_state", "Converted")
		subscription = self.subscribe()
		seats.set_cancellation(self.team.name, True)
		ends_on = getdate(frappe.db.get_value("Team", self.team.name, "subscription_ends_on"))
		self.assertEqual(ends_on, get_last_day(nowdate()))

		with patch("central.resource_actions.submit_billing_command") as submit_billing_command:
			seats.run_cancellations(add_days(ends_on, 1))

		submit_billing_command.assert_called_once_with("stop", self.server.name)
		self.assertFalse(frappe.db.get_value("Subscription", subscription.name, "enabled"))
		cancelled = self.changes(subscription.name)[-1]
		self.assertEqual(cancelled.change_type, "Cancelled")
		self.assertEqual(cancelled.effective_at, datetime.combine(add_days(ends_on, 1), datetime.min.time()))

		seats.run_cancellations(add_days(ends_on, 9))
		self.assertTrue(
			frappe.db.exists(
				"Resource Action",
				{"server": self.server.name, "action": "terminate", "requested_by": "Administrator"},
			)
		)

	def test_keeping_the_subscription_withdraws_the_cancellation(self):
		seats.set_cancellation(self.team.name, True)
		seats.set_cancellation(self.team.name, False)

		self.assertFalse(frappe.db.get_value("Team", self.team.name, "subscription_ends_on"))

	def trial(self):
		from central.signups.trial import Trial

		return Trial(self.site())

	def trial_status(self) -> dict:
		from central.signups.trial import get_trial_status

		return get_trial_status(self.server.name)
