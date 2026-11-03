# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt

import hashlib
import xml.etree.ElementTree as ElementTree
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import frappe
import requests

from central.billing.gateways.base import GatewayTimeout, GatewayUnsupported
from central.billing.gateways.registry import get_adapter
from central.billing.gateways.telr_adapter import TelrAdapter
from central.billing.tests.gateway_contract import GatewayAdapterContract
from central.billing.tests.utils import BillingTestCase as IntegrationTestCase
from central.billing.tests.utils import complete_billing_profile, configure_gateway, ensure_team

TAS_FIELDS = (
	"tran_store",
	"tran_type",
	"tran_class",
	"tran_test",
	"tran_ref",
	"tran_prevref",
	"tran_firstref",
	"tran_order",
	"tran_currency",
	"tran_amount",
	"tran_cartid",
	"tran_desc",
	"tran_status",
	"tran_authcode",
	"tran_authmessage",
)
ORDER_CALLBACK_FIELDS = (
	"tran_store",
	"tran_cartid",
	"tran_order",
	"tran_ref",
	"tran_type",
	"tran_authstatus",
	"tran_authcode",
	"tran_authmessage",
	"tran_currency",
	"tran_amount",
)


def make_telr_gateway(currencies=(("AED", 1),), **values):
	"""The Telr gateway, configured for test mode. There is only one (named "Telr")."""
	return configure_gateway(
		"Telr",
		currencies,
		api_key="telr_hosted_key",
		api_secret="telr_remote_key",
		webhook_secret="telr_tas_secret",
		telr_store_id="12345",
		telr_test_mode=1,
		is_enabled=1,
		**values,
	)


def auth(status="A", code="123456", message="Authorised", tranref="100000000002"):
	"""A Remote API `<auth>` block, as `_remote` returns it."""
	return {"status": status, "code": code, "message": message, "tranref": tranref}


def remote_answer(status, code, message, tranref="000000000000"):
	"""The raw XML the Remote API answers with."""
	body = (
		f'<?xml version="1.0" encoding="UTF-8"?><remote><auth><status>{status}</status><code>{code}</code>'
		f"<message>{message}</message><tranref>{tranref}</tranref><cvv>X</cvv><avs>X</avs>"
		"<trace>4000/1/test</trace></auth></remote>"
	)
	return MagicMock(content=body.encode(), status_code=200)


def signed(advice: dict, fields=TAS_FIELDS, secret="telr_tas_secret") -> dict:
	plain = ":".join([secret, *(str(advice.get(field, "")) for field in fields)])
	return {**advice, "tran_check": hashlib.sha1(plain.encode()).hexdigest()}


def cont_sale_advice(**values) -> dict:
	return {
		"tran_store": "12345",
		"tran_type": "sale",
		"tran_class": "cont",
		"tran_test": "1",
		"tran_ref": "100000000003",
		"tran_prevref": "100000000001",
		"tran_firstref": "100000000001",
		"tran_order": "",
		"tran_currency": "AED",
		"tran_amount": "367.25",
		"tran_cartid": "PA-0001",
		"tran_desc": "Invoice INV-1",
		"tran_status": "A",
		"tran_authcode": "123456",
		"tran_authmessage": "Authorised",
		**values,
	}


def checked_order(code=2, transaction_status="A", ref="100000000001", cartid="setup-team"):
	"""A hosted-page `check` answer."""
	return {
		"method": "check",
		"order": {
			"ref": "ORDREF1",
			"cartid": cartid,
			"amount": "1.00",
			"currency": "AED",
			"status": {"code": code, "text": "Authorised"},
			"transaction": {
				"ref": ref,
				"status": transaction_status,
				"code": "31",
				"message": "Not authorised",
			},
			"card": {"type": "Visa", "last4": "1111", "expiry": {"month": "12", "year": "2029"}},
		},
	}


class TestTelrAdapter(GatewayAdapterContract, IntegrationTestCase):
	def tearDown(self):
		configure_gateway("Telr", [], is_enabled=0)

	def make_adapter(self):
		return TelrAdapter(make_telr_gateway())

	def webhook_headers(self):
		return {"Content-Type": "application/x-www-form-urlencoded"}

	@contextmanager
	def signature_valid(self):
		with patch.object(TelrAdapter, "_has_valid_check", return_value=True):
			yield

	@contextmanager
	def signature_invalid(self):
		with patch.object(TelrAdapter, "_has_valid_check", return_value=False):
			yield

	def make_charge_inputs(self):
		invoice = frappe._dict(amount=367.25, currency="AED", name="INV-1")
		method = frappe._dict(gateway_method_id="100000000001")
		return invoice, method, "PA-TELR-001"

	@contextmanager
	def charge_succeeds(self, txn_id="txn_ok"):
		with patch.object(TelrAdapter, "_remote", return_value=auth(tranref=txn_id)) as m:
			self._remote = m
			yield

	@contextmanager
	def charge_declines(self, code="card_declined"):
		declined = auth("D", "31", "Not authorised", "000000000000")
		with patch.object(TelrAdapter, "_remote", return_value=declined) as m:
			self._remote = m
			yield

	@contextmanager
	def charge_times_out(self):
		with patch.object(
			TelrAdapter, "_remote", side_effect=requests.exceptions.ConnectionError("timeout")
		) as m:
			self._remote = m
			yield

	def captured_idempotency_key(self):
		return self._remote.call_args.args[0]["cartid"]

	def make_refund_inputs(self):
		attempt = frappe._dict(gateway_transaction_id="100000000002", currency="AED", name="PA-1")
		return attempt, 100.0, "duplicate charge"

	@contextmanager
	def refund_succeeds(self, refund_id="rfnd_ok"):
		with patch.object(TelrAdapter, "_remote", return_value=auth(tranref=refund_id)):
			yield

	def parse_event_inputs(self):
		payload = cont_sale_advice()
		return payload, self.webhook_headers(), "100000000003:A", "telr.sale.approved"

	def setup_inputs(self):
		return "Team-1", {}

	@contextmanager
	def stub_setup(self):
		created = {"method": "create", "order": {"ref": "ORDREF1", "url": "https://secure.telr.com/x"}}
		with patch.object(TelrAdapter, "_order", return_value=created):
			yield

	def validation_inputs(self):
		return frappe._dict(gateway_method_id="100000000001")

	@contextmanager
	def stub_validation_success(self):
		with patch.object(TelrAdapter, "_remote", return_value=auth(message="Released")):
			yield

	def expected_account_currency(self):
		return None

	@contextmanager
	def stub_credentials_valid(self):
		with (
			patch.object(
				TelrAdapter, "_remote", return_value=auth("E", "22", "Invalid transaction reference")
			),
			patch.object(TelrAdapter, "_order", return_value={"error": {"message": "E22:Invalid order"}}),
		):
			yield

	@contextmanager
	def stub_credentials_invalid(self):
		with (
			patch.object(TelrAdapter, "_remote", return_value=auth("E", "01", "Invalid request")),
			patch.object(TelrAdapter, "_order", return_value={"error": {"message": "E01:Invalid request"}}),
		):
			yield

	# --- registry and setup ----------------------------------------------------

	def test_registry_resolves_telr(self):
		self.assertIsInstance(get_adapter(make_telr_gateway()), TelrAdapter)

	def test_the_webhook_url_is_set_in_the_telr_admin(self):
		with self.assertRaises(GatewayUnsupported):
			self.make_adapter().register_webhook("https://cloud.example/api/method/x")

	def test_card_setup_opens_a_framed_one_dirham_auth_for_the_team(self):
		response = MagicMock(status_code=200)
		response.json.return_value = {
			"method": "create",
			"order": {"ref": "ORDREF1", "url": "https://secure.telr.com/gateway/process.html?o=ORDREF1"},
		}
		with patch("central.billing.gateways.telr_adapter.requests.post", return_value=response) as post:
			handles = self.make_adapter().setup_payment_method("Team-1", {})

		sent = post.call_args.kwargs["data"]
		self.assertEqual(post.call_args.args[0], "https://secure.telr.com/gateway/order.json")
		self.assertEqual(
			{key: sent[key] for key in ("ivp_method", "ivp_trantype", "ivp_amount", "ivp_currency")},
			{"ivp_method": "create", "ivp_trantype": "auth", "ivp_amount": "1.00", "ivp_currency": "AED"},
		)
		self.assertEqual((sent["ivp_framed"], sent["ivp_test"], sent["bill_custref"]), (2, 1, "Team-1"))
		self.assertEqual((sent["ivp_store"], sent["ivp_authkey"]), ("12345", "telr_hosted_key"))
		self.assertTrue(sent["ivp_update_url"].endswith("central.billing.payments.webhooks.telr"))
		self.assertEqual(handles["setup_intent_id"], "ORDREF1")
		self.assertTrue(handles["iframe_url"].endswith("o=ORDREF1"))

	def test_a_finished_setup_reads_the_reference_and_card(self):
		with patch.object(TelrAdapter, "_order", return_value=checked_order()):
			card = self.make_adapter().read_saved_card("ORDREF1")
		self.assertEqual(
			card,
			{
				"payment_method": "100000000001",
				"customer": None,
				"brand": "Visa",
				"last4": "1111",
				"exp_month": 12,
				"exp_year": 2029,
			},
		)

	def test_an_unfinished_setup_reads_as_not_saved(self):
		with patch.object(TelrAdapter, "_order", return_value=checked_order(code=1, transaction_status="")):
			self.assertEqual(self.make_adapter().read_saved_card("ORDREF1"), {})

	def test_a_declined_setup_carries_the_bank_reason(self):
		with patch.object(TelrAdapter, "_order", return_value=checked_order(code=-3, transaction_status="D")):
			card = self.make_adapter().read_saved_card("ORDREF1")
		self.assertEqual(card["setup_error"], {"failure_code": "card_declined", "decline_code": "telr_31"})

	def test_the_card_check_is_released(self):
		with patch.object(TelrAdapter, "_remote", return_value=auth(message="Released")) as remote:
			result = self.make_adapter().validate_payment_method(
				frappe._dict(gateway_method_id="100000000001")
			)
		sent = remote.call_args.args[0]
		self.assertTrue(result.success)
		self.assertEqual((sent["type"], sent["ref"], sent["amount"]), ("release", "100000000001", 1.0))

	def test_a_failed_release_does_not_fail_an_approved_card(self):
		with patch.object(TelrAdapter, "_remote", return_value=auth("E", "26", "Already voided")):
			result = self.make_adapter().validate_payment_method(
				frappe._dict(gateway_method_id="100000000001")
			)
		self.assertTrue(result.success)

	# --- Remote API ------------------------------------------------------------

	def test_a_charge_is_a_cont_sale_against_the_reference_without_card_data(self):
		adapter = self.make_adapter()
		request = adapter._remote_request(
			{"type": "sale", "class": "cont", "ref": "100000000001", "amount": 367.25, "currency": "AED"}
		)
		root = ElementTree.fromstring(request)
		self.assertEqual((root.findtext("store"), root.findtext("key")), ("12345", "telr_remote_key"))
		self.assertEqual(
			{child.tag: child.text for child in root.find("tran")},
			{
				"type": "sale",
				"class": "cont",
				"ref": "100000000001",
				"amount": "367.25",
				"currency": "AED",
				"test": "1",
			},
		)
		self.assertIsNone(root.find("card"))

	def test_the_remote_answer_is_parsed(self):
		answer = remote_answer("A", "904492", "Authorised", "029724176180")
		with patch("central.billing.gateways.telr_adapter.requests.post", return_value=answer):
			result = self.make_adapter()._remote({"type": "sale", "class": "cont", "ref": "1"})
		self.assertEqual((result["status"], result["tranref"]), ("A", "029724176180"))

	def test_an_approved_charge_becomes_the_next_reference(self):
		team = ensure_team("team-telr-reference")
		method = frappe.get_doc(
			{
				"doctype": "Payment Method",
				"team": team,
				"gateway": make_telr_gateway().name,
				"method_type": "Card",
				"status": "Active",
				"gateway_method_id": "100000000001",
			}
		).insert(ignore_permissions=True)
		invoice = frappe._dict(amount=367.25, currency="AED", name="INV-1")
		with patch.object(TelrAdapter, "_remote", return_value=auth(tranref="100000000009")) as remote:
			result = self.make_adapter().charge(invoice, method, "PA-REF-1")

		self.assertEqual(remote.call_args.args[0]["ref"], "100000000001")
		self.assertEqual(result.gateway_transaction_id, "100000000009")
		self.assertEqual(
			frappe.db.get_value("Payment Method", method.name, "gateway_method_id"), "100000000009"
		)

	def test_telr_codes_map_to_billing_failures(self):
		cases = {
			("D", "57"): ("continuous_authority_unavailable", "telr_57"),
			("E", "25"): ("reference_invalid", "telr_25"),
			("E", "22"): ("reference_invalid", "telr_22"),
			("E", "39"): ("request_refused", "telr_39"),
			("D", "41"): ("card_declined", "insufficient_funds"),
			("D", "31"): ("card_declined", "telr_31"),
			("D", "66"): ("card_declined", "do_not_try_again"),
		}
		invoice, method, key = self.make_charge_inputs()
		for (status, code), expected in cases.items():
			with self.subTest(code=code):
				with patch.object(TelrAdapter, "_remote", return_value=auth(status, code, "refused", "0")):
					result = self.make_adapter().charge(invoice, method, key)
				self.assertEqual((result.success, result.status), (False, "Failed"))
				self.assertEqual((result.failure_code, result.decline_code), expected)

	def test_a_duplicate_cart_id_is_unknown_not_a_decline(self):
		invoice, method, key = self.make_charge_inputs()
		with patch.object(TelrAdapter, "_remote", return_value=auth("E", "56", "Duplicate transaction", "0")):
			with self.assertRaises(GatewayTimeout):
				self.make_adapter().charge(invoice, method, key)

	def test_a_held_sale_stays_open(self):
		invoice, method, key = self.make_charge_inputs()
		with patch.object(
			TelrAdapter, "_remote", return_value=auth("H", "123456", "On hold", "100000000004")
		):
			result = self.make_adapter().charge(invoice, method, key)
		self.assertEqual((result.success, result.status), (False, "Pending"))
		self.assertTrue(result.hold_until)

	def test_a_refused_refund_is_failed(self):
		attempt, amount, reason = self.make_refund_inputs()
		with patch.object(
			TelrAdapter, "_remote", return_value=auth("E", "35", "Unable to refund", "0")
		) as remote:
			result = self.make_adapter().refund(attempt, amount, reason)
		self.assertEqual(result.status, "Failed")
		self.assertEqual(
			{key: remote.call_args.args[0][key] for key in ("type", "class", "ref")},
			{"type": "refund", "class": "ecom", "ref": "100000000002"},
		)

	# --- advice (webhook) -------------------------------------------------------

	def test_a_signed_transaction_advice_is_accepted_and_a_tampered_one_is_not(self):
		adapter = self.make_adapter()
		advice = signed(cont_sale_advice())
		self.assertTrue(adapter.verify_webhook_signature(frappe.as_json(advice).encode(), {}))

		advice["tran_amount"] = "1.00"
		self.assertFalse(adapter.verify_webhook_signature(frappe.as_json(advice).encode(), {}))

	def test_an_order_callback_is_checked_against_the_order(self):
		advice = {
			"tran_store": "12345",
			"tran_cartid": "PA-0002",
			"tran_order": "ORDREF2",
			"tran_ref": "100000000005",
			"tran_type": "1",
			"tran_authstatus": "A",
			"tran_authcode": "123456",
			"tran_authmessage": "Authorised",
			"tran_currency": "AED",
			"tran_amount": "367.25",
		}
		payload = frappe.as_json(signed(advice, ORDER_CALLBACK_FIELDS, secret="telr_hosted_key")).encode()
		adapter = self.make_adapter()
		with patch.object(TelrAdapter, "_order", return_value=checked_order(code=3, cartid="PA-0002")):
			self.assertTrue(adapter.verify_webhook_signature(payload, {}))
		with patch.object(TelrAdapter, "_order", return_value=checked_order(code=3, cartid="someone-else")):
			self.assertFalse(adapter.verify_webhook_signature(payload, {}))

	def test_advices_normalise_to_charge_and_refund_events(self):
		adapter = self.make_adapter()
		cases = {
			("sale", "A"): "telr.sale.approved",
			("sale", "D"): "telr.sale.declined",
			("refund", "A"): "telr.refund.approved",
			("3", "A"): "telr.refund.approved",
			("auth", "A"): "telr.auth.approved",
		}
		for (tran_type, status), expected in cases.items():
			with self.subTest(tran_type=tran_type, status=status):
				event = adapter.parse_webhook_event(cont_sale_advice(tran_type=tran_type, tran_status=status))
				self.assertEqual(event.event_type, expected)

	def test_an_advice_carries_the_payment_refund_and_decline(self):
		payment = TelrAdapter.payment_from_event(cont_sale_advice())
		self.assertEqual(
			(payment.payment_id, payment.amount, payment.currency), ("100000000003", 367.25, "AED")
		)
		self.assertTrue(payment.captured)

		refund = TelrAdapter.refund_from_event(cont_sale_advice(tran_type="refund", tran_ref="100000000006"))
		self.assertEqual(refund, {"id": "100000000006", "status": "Completed"})

		failure = TelrAdapter.failure_from_event(
			cont_sale_advice(tran_status="D", tran_authcode="57", tran_authmessage="No continuous authority")
		)
		self.assertEqual(failure["failure_code"], "continuous_authority_unavailable")

	def test_a_hosted_order_status_reads_from_check(self):
		with patch.object(TelrAdapter, "_order", return_value=checked_order(code=3)):
			self.assertEqual(self.make_adapter().get_transaction_status("ORDREF1"), "paid")

	def test_a_remote_transaction_status_reads_from_its_advice(self):
		adapter = self.make_adapter()
		self.assertEqual(adapter.get_transaction_status("100000000077"), "unknown")
		frappe.get_doc(
			{
				"doctype": "Webhook Event",
				"gateway": "Telr",
				"gateway_event_id": "100000000077:A",
				"event_type": "telr.sale.approved",
				"raw_payload": frappe.as_json(cont_sale_advice(tran_ref="100000000077")),
				"status": "Processed",
			}
		).insert(ignore_permissions=True)
		self.assertEqual(adapter.get_transaction_status("100000000077"), "captured")


class TestCustomerPresentFallback(IntegrationTestCase):
	"""Telr refuses cont on the referenced transaction (57): the card is held, the customer
	pays once on the hosted page, and that payment is the card's next reference."""

	TEAM = "team-telr-fallback"

	def setUp(self):
		ensure_team(self.TEAM)
		complete_billing_profile(self.TEAM, currency="AED")
		frappe.db.set_value("Billing Profile", self.TEAM, "collection_mode", "Auto Charge")
		make_telr_gateway()
		self.method = frappe.get_doc(
			{
				"doctype": "Payment Method",
				"team": self.TEAM,
				"gateway": "Telr",
				"method_type": "Card",
				"status": "Active",
				"is_default": 1,
				"gateway_customer_id": self.TEAM,
				"gateway_method_id": "100000000001",
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		configure_gateway("Telr", [], is_enabled=0)

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

	def test_no_continuous_authority_holds_the_card_and_asks_the_customer(self):
		from central.billing.payments import charges, payments

		refused = auth("D", "57", "Continuous authority not available on referenced transaction", "0")
		with patch.object(TelrAdapter, "_remote", return_value=refused):
			result = charges.pay_invoice(self._invoice())

		self.assertEqual(
			(result["charged"], result["failure_code"]), (False, "continuous_authority_unavailable")
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

	def test_a_hosted_payment_rearms_the_held_card(self):
		from central.billing.payments import payments

		payments.hold_for_customer_present_payment(self.method.name)
		attempt = frappe._dict(
			name="PA-HOSTED-1",
			team=self.TEAM,
			gateway="Telr",
			gateway_order_id="ORDREF9",
			payment_method=None,
		)
		paid = checked_order(code=3, ref="100000000010")
		with patch.object(TelrAdapter, "_order", return_value=paid):
			self.assertEqual(payments.rearm_customer_present_method(attempt), self.method.name)

		method = frappe.get_doc("Payment Method", self.method.name)
		self.assertEqual((method.gateway_method_id, method.reauth_required), ("100000000010", 0))
		self.assertEqual(method.display_label, "Visa ···· 1111")
		self.assertEqual(frappe.db.get_value("Billing Profile", self.TEAM, "collection_mode"), "Auto Charge")
