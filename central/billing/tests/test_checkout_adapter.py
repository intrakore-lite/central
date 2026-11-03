# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt

import hashlib
import hmac
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import frappe
import requests

from central.billing.gateways.base import GatewayAuthError, GatewayTimeout, WebhookNotFound
from central.billing.gateways.checkout_adapter import (
	CheckoutAdapter,
	CheckoutNotFound,
	CheckoutRefused,
	from_minor,
	to_minor,
)
from central.billing.gateways.checkout_codes import failure_from_response
from central.billing.gateways.registry import get_adapter
from central.billing.payments import decline
from central.billing.tests.gateway_contract import GatewayAdapterContract
from central.billing.tests.utils import BillingTestCase as IntegrationTestCase
from central.billing.tests.utils import complete_billing_profile, configure_gateway, ensure_team

SOURCE = "src_wmlfc3zyhqzehihu7giusaaawu"
STORED_PAYMENT = "pay_mbabizu24mvu3mela5njyhpit4"
WEBHOOK_SECRET = "cko_signature_key"


def make_checkout_gateway(currencies=(("AED", 1),), **values):
	"""The Checkout gateway in the sandbox. There is only one (named "Checkout")."""
	config = {
		"api_key": "pk_sbox_public",
		"api_secret": "sk_sbox_secret",
		"webhook_secret": WEBHOOK_SECRET,
		"checkout_environment": "Sandbox",
		"processing_channel_id": "pc_q4dbxom5jbgudnjzjpz7j2z6uq",
		"checkout_api_prefix": "",
		"is_enabled": 1,
	}
	return configure_gateway("Checkout", currencies, **{**config, **values})


def payment(status="Captured", approved=True, payment_id="pay_ok", response_code="10000", **values):
	"""A Checkout.com payment, as POST /payments or GET /payments/{id} answers."""
	return {
		"id": payment_id,
		"action_id": "act_1",
		"amount": 36725,
		"currency": "AED",
		"approved": approved,
		"status": status,
		"response_code": response_code,
		"response_summary": "Approved" if approved else "Declined",
		"reference": "INV-1",
		"requested_on": "2026-11-03T10:00:00Z",
		"source": {
			"type": "card",
			"id": SOURCE,
			"scheme": "Visa",
			"last4": "4242",
			"expiry_month": 12,
			"expiry_year": 2029,
		},
		"customer": {"id": "cus_team"},
		"scheme_id": "483299310332879",
		**values,
	}


def webhook(event_type="payment_captured", **data):
	return {
		"id": "evt_caxmnvuvbe4elkbdx2imwbnjxu",
		"type": event_type,
		"version": "1.0.29",
		"created_on": "2026-11-03T10:00:01Z",
		"data": {
			"id": "pay_griq7wyqkggu7mnk7ecm6ysrl4",
			"action_id": "act_gl5cpqgccxeulozrvaassd4lta",
			"amount": 36725,
			"currency": "AED",
			"reference": "PA-1",
			"response_code": "10000",
			"response_summary": "Approved",
			**data,
		},
	}


def answer(status_code=200, body=None):
	response = MagicMock(status_code=status_code, content=b"{}" if body is not None else b"")
	response.json.return_value = body or {}
	return response


class TestCheckoutAdapter(GatewayAdapterContract, IntegrationTestCase):
	def tearDown(self):
		configure_gateway("Checkout", [], is_enabled=0)

	def make_adapter(self):
		return CheckoutAdapter(make_checkout_gateway())

	def webhook_headers(self):
		return {"Content-Type": "application/json", "Cko-Signature": "x"}

	@contextmanager
	def signature_valid(self):
		with patch("central.billing.gateways.checkout_adapter.hmac.compare_digest", return_value=True):
			yield

	@contextmanager
	def signature_invalid(self):
		with patch("central.billing.gateways.checkout_adapter.hmac.compare_digest", return_value=False):
			yield

	def make_charge_inputs(self):
		invoice = frappe._dict(amount=367.25, currency="AED", name="INV-1")
		method = frappe._dict(gateway_method_id=SOURCE, gateway_mandate_id=STORED_PAYMENT)
		return invoice, method, "PA-CKO-001"

	@contextmanager
	def _stub(self, **kwargs):
		with patch.object(CheckoutAdapter, "_request", **kwargs) as m:
			self.request = m
			yield m

	def charge_succeeds(self, txn_id="txn_ok"):
		return self._stub(return_value=payment("Authorized", payment_id=txn_id))

	def charge_declines(self, code="card_declined"):
		return self._stub(return_value=payment("Declined", approved=False, response_code="20005"))

	def charge_times_out(self):
		return self._stub(side_effect=GatewayTimeout("timeout"))

	def captured_idempotency_key(self):
		return self.request.call_args.kwargs["idempotency_key"]

	def make_refund_inputs(self):
		attempt = frappe._dict(gateway_transaction_id="pay_charged", currency="AED", name="PA-1")
		return attempt, 100.0, "duplicate charge"

	@contextmanager
	def refund_succeeds(self, refund_id="rfnd_ok"):
		def respond(method, path, **kwargs):
			if method == "POST":
				return {"action_id": "act_refund", "reference": "refund-PA-1"}
			return [{"id": "act_refund", "type": "Refund", "approved": True, "response_code": "10000"}]

		with self._stub(side_effect=respond):
			yield

	def test_refund_returns_completed_result(self):
		"""The contract case, with Checkout.com's own refund id: `<payment>:<action>`."""
		adapter = self.make_adapter()
		attempt, amount, reason = self.make_refund_inputs()
		with self.refund_succeeds():
			result = adapter.refund(attempt, amount, reason)
		self.assertTrue(result.success)
		self.assertEqual(result.status, "Completed")
		self.assertEqual(result.gateway_refund_id, "pay_charged:act_refund")

	def parse_event_inputs(self):
		payload = webhook()
		return payload, self.webhook_headers(), "evt_caxmnvuvbe4elkbdx2imwbnjxu", "payment_captured"

	def setup_inputs(self):
		return "Team-1", {"customer_id": "cus_team", "currency": "AED"}

	def stub_setup(self):
		return self._stub(
			return_value={"id": "ps_1", "payment_session_secret": "pss_1", "payment_session_token": "tok"}
		)

	def validation_inputs(self):
		return frappe._dict(gateway_method_id=SOURCE, gateway_mandate_id=STORED_PAYMENT)

	@contextmanager
	def stub_validation_success(self):
		yield

	def expected_account_currency(self):
		return None

	def stub_credentials_valid(self):
		return self._stub(return_value={"total_count": 0, "data": []})

	def stub_credentials_invalid(self):
		return self._stub(side_effect=GatewayAuthError("401"))

	# --- registry and HTTP -------------------------------------------------------

	def test_registry_resolves_checkout(self):
		self.assertIsInstance(get_adapter(make_checkout_gateway()), CheckoutAdapter)

	def test_requests_go_to_the_environment_host_with_the_secret_key(self):
		cases = {
			("Sandbox", ""): "https://api.sandbox.checkout.com/payments/pay_1",
			("Live", ""): "https://api.checkout.com/payments/pay_1",
			("Live", "abc123"): "https://abc123.api.checkout.com/payments/pay_1",
		}
		for (environment, prefix), url in cases.items():
			with self.subTest(environment=environment, prefix=prefix):
				adapter = CheckoutAdapter(
					make_checkout_gateway(checkout_environment=environment, checkout_api_prefix=prefix)
				)
				with patch(
					"central.billing.gateways.checkout_adapter.requests.request",
					return_value=answer(200, payment()),
				) as http:
					adapter._request("GET", "/payments/pay_1", idempotency_key="key-1")
				self.assertEqual(http.call_args.args[:2], ("GET", url))
				headers = http.call_args.kwargs["headers"]
				self.assertEqual(headers["Authorization"], "Bearer sk_sbox_secret")
				self.assertEqual(headers["Cko-Idempotency-Key"], "key-1")

	def test_http_answers_map_to_gateway_errors(self):
		cases = {
			401: GatewayAuthError,
			404: CheckoutNotFound,
			422: CheckoutRefused,
			403: CheckoutRefused,
			409: GatewayTimeout,
			429: GatewayTimeout,
			502: GatewayTimeout,
		}
		adapter = self.make_adapter()
		for code, error in cases.items():
			with self.subTest(code=code):
				with patch(
					"central.billing.gateways.checkout_adapter.requests.request",
					return_value=answer(code, {"error_codes": ["x"]}),
				):
					with self.assertRaises(error):
						adapter._request("GET", "/payments")
		with patch(
			"central.billing.gateways.checkout_adapter.requests.request",
			side_effect=requests.exceptions.ConnectionError("down"),
		):
			with self.assertRaises(GatewayTimeout):
				adapter._request("GET", "/payments")

	def test_a_key_from_the_other_environment_is_refused(self):
		adapter = CheckoutAdapter(make_checkout_gateway(checkout_environment="Live"))
		with self._stub(return_value={}) as request:
			with self.assertRaises(GatewayAuthError):
				adapter.validate_credentials()
		request.assert_not_called()

	def test_amounts_are_sent_in_minor_units(self):
		self.assertEqual(to_minor(367.25, "AED"), 36725)
		self.assertEqual(to_minor(1.5, "KWD"), 1500)
		self.assertEqual(to_minor(100, "JPY"), 100)
		self.assertEqual(from_minor(36725, "AED"), 367.25)

	# --- adding a card ---------------------------------------------------------

	def test_card_setup_opens_a_zero_amount_unscheduled_flow_session(self):
		with self.stub_setup() as request:
			handles = self.make_adapter().setup_payment_method(*self.setup_inputs())

		method, path = request.call_args.args
		body = request.call_args.kwargs["json"]
		self.assertEqual((method, path), ("POST", "/payment-sessions"))
		self.assertEqual(
			{key: body[key] for key in ("amount", "currency", "payment_type", "enabled_payment_methods")},
			{
				"amount": 0,
				"currency": "AED",
				"payment_type": "Unscheduled",
				"enabled_payment_methods": ["card"],
			},
		)
		self.assertEqual(body["3ds"], {"enabled": True})
		self.assertEqual(body["customer"], {"id": "cus_team"})
		self.assertEqual(body["processing_channel_id"], "pc_q4dbxom5jbgudnjzjpz7j2z6uq")
		self.assertEqual(body["billing"], {"address": {"country": "AE"}})
		self.assertEqual(body["reference"], handles["setup_intent_id"])
		self.assertLessEqual(len(body["reference"]), 30)
		flow = handles["checkout"]
		self.assertEqual(flow["payment_session"]["id"], "ps_1")
		self.assertEqual(
			(flow["public_key"], flow["environment"], flow["flow_script_url"]),
			("pk_sbox_public", "sandbox", "https://checkout-web-components.checkout.com/index.js"),
		)

	def test_a_verified_card_reads_its_source_and_stored_payment(self):
		verified = payment("Card Verified", payment_id=STORED_PAYMENT, amount=0)
		with self._stub(return_value={"data": [verified]}) as request:
			card = self.make_adapter().read_saved_card("card-ref")

		self.assertEqual(request.call_args.kwargs["params"]["reference"], "card-ref")
		self.assertEqual(
			{key: card[key] for key in ("payment_method", "mandate", "customer", "brand", "last4")},
			{
				"payment_method": SOURCE,
				"mandate": STORED_PAYMENT,
				"customer": "cus_team",
				"brand": "Visa",
				"last4": "4242",
			},
		)
		self.assertEqual((card["exp_month"], card["exp_year"]), (12, 2029))

	def test_the_newest_payment_with_the_reference_is_read(self):
		old = payment("Declined", approved=False, payment_id="pay_old", requested_on="2026-11-03T09:00:00Z")
		new = payment("Card Verified", payment_id="pay_new", requested_on="2026-11-03T09:05:00Z")
		with self._stub(return_value={"data": [old, new]}):
			self.assertEqual(self.make_adapter().read_saved_card("card-ref")["mandate"], "pay_new")

	def test_the_flow_payment_id_is_used_only_for_its_own_setup(self):
		mine = payment("Card Verified", payment_id="pay_mine", reference="card-ref")
		other = payment("Card Verified", payment_id="pay_other", reference="card-someone-else")
		listed = payment("Card Verified", payment_id="pay_listed", reference="card-ref")

		def respond(method, path, **kwargs):
			if path == "/payments":
				return {"data": [listed]}
			return {"/payments/pay_mine": mine, "/payments/pay_other": other}[path]

		adapter = self.make_adapter()
		with self._stub(side_effect=respond):
			self.assertEqual(
				adapter.read_saved_card("card-ref", payment_id="pay_mine")["mandate"], "pay_mine"
			)
			self.assertEqual(
				adapter.read_saved_card("card-ref", payment_id="pay_other")["mandate"], "pay_listed"
			)

	def test_an_unfinished_setup_reads_as_not_saved(self):
		for answer_body in ({"data": []}, {"data": [payment("Pending", approved=False)]}):
			with self.subTest(answer=answer_body):
				with self._stub(return_value=answer_body):
					self.assertEqual(self.make_adapter().read_saved_card("card-ref"), {})

	def test_a_declined_setup_carries_the_bank_reason(self):
		declined = payment("Declined", approved=False, response_code=None)
		declined.pop("response_code")

		def respond(method, path, **kwargs):
			if path == "/payments":
				return {"data": [declined]}
			return [{"id": "act_1", "type": "Card Verification", "response_code": "20051"}]

		with self._stub(side_effect=respond):
			card = self.make_adapter().read_saved_card("card-ref")
		self.assertEqual(
			card, {"setup_error": {"failure_code": "card_declined", "decline_code": "insufficient_funds"}}
		)

	def test_a_card_without_its_stored_payment_is_not_valid(self):
		result = self.make_adapter().validate_payment_method(frappe._dict(gateway_method_id=SOURCE))
		self.assertEqual((result.success, result.failure_code), (False, "token_missing"))

	def test_a_customer_is_created_for_the_team(self):
		with self._stub(return_value={"id": "cus_new"}) as request:
			customer = self.make_adapter().create_customer(
				frappe._dict(name="Acme LLC", owner_user="ops@acme.example")
			)
		self.assertEqual(customer, "cus_new")
		self.assertEqual(request.call_args.kwargs["json"], {"name": "Acme LLC", "email": "ops@acme.example"})

	# --- charges -------------------------------------------------------------------

	def test_a_charge_is_merchant_initiated_and_linked_to_the_stored_payment(self):
		invoice, method, key = self.make_charge_inputs()
		with self.charge_succeeds() as request:
			self.make_adapter().charge(invoice, method, key)

		body = request.call_args.kwargs["json"]
		self.assertEqual(request.call_args.args, ("POST", "/payments"))
		self.assertEqual(
			body["source"], {"type": "id", "id": SOURCE}, "the charge sends no card data, only the source"
		)
		self.assertEqual(
			{key: body[key] for key in ("amount", "currency", "payment_type", "merchant_initiated")},
			{"amount": 36725, "currency": "AED", "payment_type": "Unscheduled", "merchant_initiated": True},
		)
		self.assertEqual(body["previous_payment_id"], STORED_PAYMENT)
		self.assertEqual(body["processing_channel_id"], "pc_q4dbxom5jbgudnjzjpz7j2z6uq")
		self.assertTrue(body["capture"])

	def test_a_card_without_a_stored_payment_asks_for_the_customer(self):
		invoice, _method, key = self.make_charge_inputs()
		with self._stub(return_value={}) as request:
			result = self.make_adapter().charge(invoice, frappe._dict(gateway_method_id=SOURCE), key)
		request.assert_not_called()
		self.assertTrue(decline.needs_customer_present_payment(result.failure_code))

	def test_checkout_codes_map_to_billing_failures(self):
		cases = {
			"20154": (decline.CUSTOMER_AUTHENTICATION_REQUIRED, "authentication_required"),
			"43401": (decline.CUSTOMER_AUTHENTICATION_REQUIRED, "authentication_required"),
			"20114": (decline.STORED_CREDENTIAL_INVALID, None),
			"20051": ("card_declined", "insufficient_funds"),
			"20054": ("expired_card", None),
			"200N7": ("incorrect_cvc", None),
			"30043": ("card_declined", "stolen_card"),
			"200R1": ("card_declined", "revocation_of_authorization"),
			"20046": ("card_declined", "cko_20046"),
			"30099": ("card_declined", "do_not_try_again"),
			"41301": ("card_declined", "do_not_try_again"),
			"20157": (decline.REQUEST_REFUSED, None),
		}
		invoice, method, key = self.make_charge_inputs()
		for code, expected in cases.items():
			with self.subTest(code=code):
				with self._stub(return_value=payment("Declined", approved=False, response_code=code)):
					result = self.make_adapter().charge(invoice, method, key)
				self.assertEqual((result.success, result.status), (False, "Failed"))
				self.assertEqual((result.failure_code, result.decline_code), expected)

	def test_soft_and_hard_declines_retry_as_billing_expects(self):
		self.assertTrue(decline.is_retryable_later(**_codes("20051")))
		self.assertFalse(decline.is_retryable_later(**_codes("30041")))
		self.assertFalse(decline.is_retryable_later(**_codes("20154")))

	def test_a_refused_request_moved_no_money(self):
		invoice, method, key = self.make_charge_inputs()
		with self._stub(side_effect=CheckoutRefused("422", {"error_codes": ["amount_invalid"]})):
			result = self.make_adapter().charge(invoice, method, key)
		self.assertEqual((result.status, result.failure_code), ("Failed", decline.REQUEST_REFUSED))

	def test_a_pending_charge_stays_open(self):
		invoice, method, key = self.make_charge_inputs()
		with self._stub(return_value={"id": "pay_pending", "status": "Pending"}):
			result = self.make_adapter().charge(invoice, method, key)
		self.assertEqual((result.success, result.status), (False, "Pending"))
		self.assertTrue(result.hold_until)

	def test_a_refund_still_processing_is_pending(self):
		def respond(method, path, **kwargs):
			if method == "POST":
				return {"action_id": "act_refund"}
			return [{"id": "act_capture", "type": "Capture", "response_code": "10000"}]

		attempt, amount, reason = self.make_refund_inputs()
		with self._stub(side_effect=respond) as request:
			result = self.make_adapter().refund(attempt, amount, reason, idempotency_key="RF-1")
		self.assertEqual((result.status, result.gateway_refund_id), ("Pending", "pay_charged:act_refund"))
		post = request.call_args_list[0]
		self.assertEqual(post.args, ("POST", "/payments/pay_charged/refunds"))
		self.assertEqual((post.kwargs["json"]["amount"], post.kwargs["idempotency_key"]), (10000, "RF-1"))

	def test_a_refused_refund_is_failed(self):
		attempt, amount, reason = self.make_refund_inputs()
		with self._stub(side_effect=CheckoutRefused("403")):
			self.assertEqual(self.make_adapter().refund(attempt, amount, reason).status, "Failed")

	def test_the_refund_status_reads_its_action(self):
		with self._stub(return_value=[{"id": "act_r", "response_code": "50003"}]) as request:
			self.assertEqual(self.make_adapter().get_refund_status("pay_1:act_r"), "Failed")
		self.assertEqual(request.call_args.args, ("GET", "/payments/pay_1/actions"))

	def test_the_transaction_status_reads_the_payment(self):
		cases = {
			"Captured": "captured",
			"Authorized": "authorised",
			"Declined": "failed",
			"Pending": "processing",
		}
		for status, expected in cases.items():
			with self.subTest(status=status):
				with self._stub(return_value=payment(status)):
					self.assertEqual(self.make_adapter().get_transaction_status("pay_1"), expected)

	# --- on-session payments ---------------------------------------------------------

	def test_an_invoice_payment_session_is_found_by_its_receipt(self):
		session = {"id": "ps_2", "payment_session_secret": "pss_2", "payment_session_token": "tok"}
		with self._stub(return_value=session) as request:
			handles = self.make_adapter().create_order(
				367.25, "AED", "PA-77", notes={"team": "team-none", "purpose": "invoice_payment"}
			)
		body = request.call_args.kwargs["json"]
		self.assertEqual(
			(body["amount"], body["reference"], body["payment_type"]), (36725, "PA-77", "Regular")
		)
		self.assertEqual((handles["order_id"], handles["checkout"]["payment_session"]), ("PA-77", session))

	def test_a_paid_order_is_found_by_reference(self):
		with self._stub(return_value={"data": [payment("Captured", reference="PA-77")]}):
			found = self.make_adapter().find_order_payment("PA-77")
		self.assertEqual((found.payment_id, found.amount, found.order_id), ("pay_ok", 367.25, "PA-77"))
		self.assertTrue(found.captured)

	# --- webhooks ------------------------------------------------------------------

	def test_the_signature_is_the_hmac_of_the_raw_body(self):
		adapter = self.make_adapter()
		body = frappe.as_json(webhook()).encode()
		signature = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
		self.assertTrue(adapter.verify_webhook_signature(body, {"cko-signature": signature}))
		self.assertFalse(adapter.verify_webhook_signature(body + b" ", {"Cko-Signature": signature}))
		self.assertFalse(adapter.verify_webhook_signature(body, {}))

	def test_a_webhook_carries_the_payment_refund_decline_and_dispute(self):
		captured = CheckoutAdapter.payment_from_event(webhook())
		self.assertEqual(
			(captured.payment_id, captured.amount, captured.currency, captured.order_id),
			("pay_griq7wyqkggu7mnk7ecm6ysrl4", 367.25, "AED", "PA-1"),
		)
		self.assertTrue(captured.captured)
		self.assertFalse(CheckoutAdapter.payment_from_event(webhook("payment_approved")).captured)
		self.assertIsNone(CheckoutAdapter.payment_from_event(webhook("card_verified")))

		declined = CheckoutAdapter.failure_from_event(webhook("payment_declined", response_code="20154"))
		self.assertEqual(declined["failure_code"], decline.CUSTOMER_AUTHENTICATION_REQUIRED)
		self.assertIsNone(CheckoutAdapter.failure_from_event(webhook()))

		refund = CheckoutAdapter.refund_from_event(webhook("payment_refunded"))
		self.assertEqual(
			refund,
			{"id": "pay_griq7wyqkggu7mnk7ecm6ysrl4:act_gl5cpqgccxeulozrvaassd4lta", "status": "Completed"},
		)
		lost = webhook("dispute_lost", id="dsp_1", payment_id="pay_1", amount=8150, category="fraudulent")
		self.assertEqual(
			CheckoutAdapter.dispute_from_event(lost),
			{"id": "dsp_1", "payment_id": "pay_1", "amount": 81.5, "reason": "fraudulent", "status": "lost"},
		)
		self.assertEqual(
			CheckoutAdapter.dispute_from_event(webhook("dispute_evidence_required"))["status"], "open"
		)

	def test_the_webhook_is_a_signed_workflow_for_every_event(self):
		with self._stub(return_value={"id": "wf_1"}) as request:
			result = self.make_adapter().register_webhook("https://cloud.example/api/method/x")

		body = request.call_args.kwargs["json"]
		self.assertEqual(request.call_args.args, ("POST", "/workflows"))
		action = body["actions"][0]
		self.assertEqual((action["type"], action["url"]), ("webhook", "https://cloud.example/api/method/x"))
		self.assertEqual(action["signature"], {"method": "HMACSHA256", "key": result["secret"]})
		self.assertEqual(result["endpoint_id"], "wf_1")
		self.assertGreaterEqual(len(result["secret"]), 32)
		events = body["conditions"][0]["events"]
		self.assertIn("payment_captured", events["gateway"])
		self.assertIn("dispute_lost", events["dispute"])
		self.assertEqual(
			body["conditions"][1],
			{"type": "processing_channel", "processing_channels": ["pc_q4dbxom5jbgudnjzjpz7j2z6uq"]},
		)

	def test_the_workflow_is_read_and_its_events_replaced(self):
		workflow = {
			"id": "wf_1",
			"active": True,
			"conditions": [{"id": "wfc_1", "type": "event", "events": {"gateway": ["payment_captured"]}}],
			"actions": [{"id": "wfa_1", "type": "webhook", "url": "https://cloud.example/x"}],
		}
		adapter = self.make_adapter()
		with self._stub(return_value=workflow):
			self.assertEqual(
				adapter.get_webhook("wf_1"),
				{"url": "https://cloud.example/x", "is_active": True, "events": ["payment_captured"]},
			)
		with self._stub(return_value=workflow) as request:
			adapter.update_webhook_events(
				"wf_1", "https://cloud.example/x", ["payment_captured", "dispute_won"]
			)
		put = request.call_args
		self.assertEqual(put.args, ("PUT", "/workflows/wf_1/conditions/wfc_1"))
		self.assertEqual(
			put.kwargs["json"],
			{"type": "event", "events": {"gateway": ["payment_captured"], "dispute": ["dispute_won"]}},
		)
		with self._stub(side_effect=CheckoutNotFound("404")):
			with self.assertRaises(WebhookNotFound):
				adapter.get_webhook("wf_gone")

	def test_the_callback_url_is_the_checkout_endpoint(self):
		self.assertTrue(
			make_checkout_gateway()
			.webhook_callback_url()
			.endswith("/api/method/central.billing.payments.webhooks.checkout")
		)


def _codes(code: str) -> dict:
	failure = failure_from_response(code)
	return {"failure_code": failure["failure_code"], "decline_code": failure["decline_code"]}


class TestCustomerPresentFallback(IntegrationTestCase):
	"""The bank asks for the cardholder (20154): the card is held, the customer pays once in
	Flow, and that payment stores the card again and links the next charge to it."""

	TEAM = "team-checkout-fallback"

	def setUp(self):
		ensure_team(self.TEAM)
		complete_billing_profile(self.TEAM, currency="AED")
		frappe.db.set_value("Billing Profile", self.TEAM, "collection_mode", "Auto Charge")
		make_checkout_gateway()
		self.method = frappe.get_doc(
			{
				"doctype": "Payment Method",
				"team": self.TEAM,
				"gateway": "Checkout",
				"method_type": "Card",
				"status": "Active",
				"is_default": 1,
				"gateway_customer_id": "cus_team",
				"gateway_method_id": SOURCE,
				"gateway_mandate_id": STORED_PAYMENT,
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		configure_gateway("Checkout", [], is_enabled=0)

	def _invoice(self):
		return (
			frappe.get_doc(
				{
					"doctype": "Invoice",
					"team": self.TEAM,
					"invoice_type": "Billable",
					"status": "Open",
					"period_start": "2026-06-01",
					"period_end": "2026-06-30",
					"currency": "AED",
					"subtotal": 367.25,
					"total": 367.25,
					"expected_collection": 367.25,
					"items": [
						{"resource_type": "bundle", "plan": "p", "rate": 367.25, "days": 30, "amount": 367.25}
					],
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def test_authentication_required_holds_the_card_and_asks_the_customer(self):
		from central.billing.payments import charges, payments

		refused = payment("Declined", approved=False, payment_id="pay_refused", response_code="20154")
		with patch.object(CheckoutAdapter, "_request", return_value=refused):
			result = charges.pay_invoice(self._invoice())

		self.assertEqual(
			(result["charged"], result["failure_code"]), (False, decline.CUSTOMER_AUTHENTICATION_REQUIRED)
		)
		method = frappe.db.get_value(
			"Payment Method", self.method.name, ["status", "reauth_required"], as_dict=True
		)
		self.assertEqual(method, {"status": "Active", "reauth_required": 1})
		profile = frappe.db.get_value(
			"Billing Profile", self.TEAM, ["collection_mode", "collection_action_reason"], as_dict=True
		)
		self.assertEqual(
			profile,
			{
				"collection_mode": "Action Required",
				"collection_action_reason": payments.CUSTOMER_PRESENT_REASON,
			},
		)

	def test_the_customer_present_session_stores_the_card_again(self):
		from central.billing.payments import payments

		payments.hold_for_customer_present_payment(self.method.name)
		with patch.object(CheckoutAdapter, "_request", return_value={"id": "ps_3"}) as request:
			CheckoutAdapter(frappe.get_doc("Payment Gateway", "Checkout")).create_order(
				367.25, "AED", "PA-88", notes={"team": self.TEAM, "purpose": "invoice_payment"}
			)
		self.assertEqual(request.call_args.kwargs["json"]["payment_type"], "Unscheduled")

	def test_a_customer_present_payment_rearms_the_held_card(self):
		from central.billing.payments import payments

		payments.hold_for_customer_present_payment(self.method.name)
		attempt = frappe._dict(
			name="PA-PRESENT-1",
			team=self.TEAM,
			gateway="Checkout",
			gateway_order_id="PA-PRESENT-1",
			payment_method=None,
		)
		paid = payment(
			"Captured",
			payment_id="pay_present",
			reference="PA-PRESENT-1",
			source={
				"id": "src_new",
				"scheme": "Mastercard",
				"last4": "5454",
				"expiry_month": 1,
				"expiry_year": 2031,
			},
		)
		with patch.object(CheckoutAdapter, "_request", return_value={"data": [paid]}):
			self.assertEqual(payments.rearm_customer_present_method(attempt), self.method.name)

		method = frappe.get_doc("Payment Method", self.method.name)
		self.assertEqual(
			(method.gateway_method_id, method.gateway_mandate_id, method.reauth_required),
			("src_new", "pay_present", 0),
		)
		self.assertEqual(method.display_label, "Mastercard ···· 5454")
		self.assertEqual(frappe.db.get_value("Billing Profile", self.TEAM, "collection_mode"), "Auto Charge")


class TestCardRail(IntegrationTestCase):
	"""An AED team saves its card on Checkout.com, the AED default; USD stays on Stripe."""

	def setUp(self):
		from central.billing.tests.test_stripe_adapter import make_stripe_gateway

		make_stripe_gateway([("USD", 1)])
		make_checkout_gateway()

	def tearDown(self):
		from central.billing.tests.utils import reset_gateway_roster

		reset_gateway_roster()

	def test_the_card_rail_follows_the_currency_default(self):
		from central.billing.payments import instruments

		self.assertEqual(instruments.card_gateway("AED"), "Checkout")
		self.assertEqual(instruments.card_gateway("USD"), "Stripe")
		tiles = instruments.available("AED", instruments.MANDATE)
		self.assertEqual([(t["instrument"], t["adapter_key"]) for t in tiles], [("Card", "Checkout")])
		# A Checkout.com top-up has no console form yet.
		self.assertIsNone(instruments.gateway_for("Card", "AED", instruments.RECHARGE))
