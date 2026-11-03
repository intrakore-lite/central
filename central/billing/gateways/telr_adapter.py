# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt
"""Telr GatewayAdapter (UAE, AED) over Telr's classic APIs, with no SDK.

Two Telr APIs, two keys, one store:

- Hosted Payment Page, `order.json` (`ivp_method` create / check), signed with the
  hosted-page authentication key (`api_key`). The card form runs in Telr's iframe
  (`ivp_framed=2`), so card data never reaches Central. `bill_custref` = the team
  turns on Telr Stored Cards for that customer.
- Remote API, `remote.xml`, signed with the Remote API key (`api_secret`). It moves
  money with no card data: a `sale` of class `cont` (continuous authority) against
  `ref`, the reference of an earlier transaction on the same card. Each approved cont
  sale returns a new reference, and that one is the `ref` of the next charge.

A card is added as a 1 AED `auth` on the hosted page. `read_saved_card` reads it back
with `check`, and `validate_payment_method` releases the 1 AED. The released auth is
the first cont reference.

Fallback: when Telr refuses cont on the referenced transaction (code 57) or the
reference itself (22, 25), the charge fails with a customer-present code
(`payments.decline.CUSTOMER_PRESENT_CODES`). Billing then flags the card
`reauth_required` and raises Action Required, the customer pays that invoice once on
the hosted page, and the approved hosted sale becomes the card's new cont reference
(`payments.payments.rearm_customer_present_method`).

Live mode answers only requests from the IPs Telr has whitelisted for the store; from
any other address Telr answers E01 "Invalid request". Test mode (`ivp_test=1`) works
from any address. Every call is a small private method, so tests stub those."""

import hashlib
import hmac
import xml.etree.ElementTree as ElementTree
from typing import ClassVar

import frappe
import requests
from frappe.utils import get_url

from central.billing.gateways.base import (
	GatewayAdapter,
	GatewayAuthError,
	GatewayError,
	GatewayTimeout,
	GatewayUnsupported,
	NormalisedEvent,
	PaymentResult,
	RefundResult,
	VerifiedPayment,
)
from central.billing.gateways.telr_codes import (
	ADVICE_SIGNATURE_LAYOUTS,
	ORDER_STATUS,
	advice_event_type,
	advice_status,
	advice_type,
	failure_from_auth,
	is_ambiguous,
	is_credential_error,
)

ORDER_URL = "https://secure.telr.com/gateway/order.json"
REMOTE_URL = "https://secure.telr.com/gateway/remote.xml"

# A card is added by authorising this much and then releasing it.
SETUP_AMOUNT = 1.0
SETUP_CURRENCY = "AED"
# ivp_framed=2 shows the hosted page in an iframe on our page (Telr "framed" mode).
FRAMED_MODE = 2
# Telr's plugins refund and release with class ecom, whatever the original class was.
FOLLOW_UP_CLASS = "ecom"

_TRANSIENT = (requests.exceptions.RequestException, ValueError)

TELR_WEBHOOK_EVENTS = (
	"telr.sale.approved",
	"telr.sale.held",
	"telr.sale.declined",
	"telr.sale.error",
	"telr.capture.approved",
	"telr.refund.approved",
	"telr.refund.declined",
	"telr.refund.error",
)


class TelrAdapter(GatewayAdapter):
	conf_keys: ClassVar[dict[str, str]] = {
		"api_key": "telr_auth_key",
		"api_secret": "telr_remote_key",
		"webhook_secret": "telr_webhook_secret",
	}
	webhook_events = TELR_WEBHOOK_EVENTS
	supports_off_session_charge = True
	# A customer-present hosted sale gives a card the cont reference it lost.
	rearms_on_customer_present_payment = True

	# --- universal -----------------------------------------------------------

	def validate_credentials(self) -> dict:
		"""Prove both keys without moving money.

		The Remote API key: void reference 0. Telr answers E01 (invalid request) or E04
		(invalid store) for a bad key or store, and E22 (invalid reference) for good ones.
		The hosted-page key: check order 0, which Telr answers with an error code in the
		same table. Telr exposes no settlement currency, so `currency` is None."""
		try:
			auth = self._remote({"type": "void", "class": FOLLOW_UP_CLASS, "ref": "0", "cartid": "check-0"})
			order = self._order({"ivp_method": "check", "order_ref": "0"})
		except _TRANSIENT as e:
			raise GatewayTimeout(str(e)) from e
		if is_credential_error(auth.get("code")):
			raise GatewayAuthError(f"Telr refused the Remote API key: {auth.get('message')}")
		if is_credential_error(_order_error_code(order)):
			raise GatewayAuthError(f"Telr refused the hosted page key: {_order_error_message(order)}")
		return {"account_id": self._store_id(), "currency": None}

	def default_currency(self) -> str | None:
		return super().default_currency() or SETUP_CURRENCY

	def register_webhook(self, callback_url: str, events: list[str] | None = None) -> dict:
		"""Telr has no API for this. Set the Transaction Advice Service URL to the gateway's
		callback URL in the Telr admin (Integrations, Transaction Advice). Central also sends
		it as `ivp_update_url` on every hosted order it creates."""
		raise GatewayUnsupported(
			f"Telr has no webhook API. Set the Transaction Advice URL in the Telr admin to {callback_url}."
		)

	def create_customer(self, team) -> str:
		"""Telr keys stored cards by `bill_custref`, which Central sets to the team."""
		return getattr(team, "name", None) or (team.get("name") if hasattr(team, "get") else str(team))

	def setup_payment_method(self, team, setup_data: dict) -> dict:
		"""Open a framed hosted order that authorises 1 AED and stores the card for the team.
		Returns the iframe URL and the order reference the confirm reads back."""
		team_name = self.create_customer(team) if not isinstance(team, str) else team
		order = self._create_hosted_order(
			amount=SETUP_AMOUNT,
			currency=SETUP_CURRENCY,
			cart=f"setup-{team_name}-{frappe.generate_hash(length=10)}",
			description="Card check, released at once",
			transaction_type="auth",
			customer_reference=team_name,
			return_url=setup_data.get("return_url"),
			email=setup_data.get("email"),
		)
		return {
			"setup_intent_id": order["ref"],
			"order_ref": order["ref"],
			"iframe_url": order["url"],
			"framed": True,
			"customer_id": team_name,
		}

	def read_saved_card(self, setup_reference: str) -> dict:
		"""The card on a hosted order, read with `check`. `{}` while the customer has not
		finished; `setup_error` when the bank refused it."""
		order = self._check_order(setup_reference)
		status = _order_status_code(order)
		transaction = order.get("transaction") or {}
		if status in (2, 3) and transaction.get("status") == "A":
			return _saved_card(order)
		if status in (-1, -2, -3) or transaction.get("status") in ("D", "E", "C"):
			failure = (
				failure_from_auth(transaction)
				if transaction.get("status")
				else {"failure_code": f"order_{ORDER_STATUS[status]}", "decline_code": None}
			)
			return {
				"setup_error": {
					"failure_code": failure["failure_code"],
					"decline_code": failure["decline_code"],
				}
			}
		return {}

	def validate_payment_method(self, payment_method) -> PaymentResult:
		"""The approved 1 AED auth proved the card. Release it so the customer is not held.

		A release that fails does not fail the card: the auth was approved, and Telr lets an
		unreleased auth expire on its own. The failure goes to the Error Log."""
		if not payment_method.gateway_method_id:
			return PaymentResult(
				success=False,
				status="Failed",
				failure_code="token_missing",
				failure_reason="Telr returned no transaction reference for this card.",
			)
		try:
			auth = self._remote(
				{
					"type": "release",
					"class": FOLLOW_UP_CLASS,
					"ref": payment_method.gateway_method_id,
					"amount": SETUP_AMOUNT,
					"currency": SETUP_CURRENCY,
					"cartid": f"release-{payment_method.gateway_method_id}",
				}
			)
		except _TRANSIENT:
			auth = {"status": "E", "message": "Telr did not answer the release."}
		if auth.get("status") != "A":
			frappe.log_error(
				title="Telr: card check not released",
				message=f"Reference {payment_method.gateway_method_id}: {auth.get('message')}",
			)
		return PaymentResult(success=True, status="Validated", raw=dict(auth))

	def charge(self, invoice, payment_method, idempotency_key: str) -> PaymentResult:
		"""A Remote API `sale`, class `cont`, against the card's latest reference.

		`idempotency_key` is the Telr cart id. Telr refuses a second transaction with the
		same cart id (E56), so a retry after a lost answer never charges twice; E56 is
		reported as unknown and left to reconciliation."""
		try:
			auth = self._remote(
				{
					"type": "sale",
					"class": "cont",
					"ref": payment_method.gateway_method_id,
					"amount": invoice.get("amount"),
					"currency": (invoice.get("currency") or SETUP_CURRENCY).upper(),
					"cartid": idempotency_key,
					"description": f"Invoice {invoice.get('name') or ''}".strip(),
				}
			)
		except _TRANSIENT as e:
			raise GatewayTimeout(str(e)) from e
		if is_ambiguous(auth):
			raise GatewayTimeout(f"Telr outcome unknown for {idempotency_key}: {auth.get('message')}")

		if auth.get("status") == "H":
			hold = frappe.utils.add_days(frappe.utils.now_datetime(), 3)
			return PaymentResult(
				success=False,
				status="Pending",
				gateway_transaction_id=auth.get("tranref"),
				hold_until=str(hold),
				raw=dict(auth),
			)
		if auth.get("status") != "A":
			return PaymentResult(success=False, status="Failed", raw=dict(auth), **failure_from_auth(auth))

		self._store_next_reference(payment_method, auth["tranref"])
		return PaymentResult(
			success=True, status="Captured", gateway_transaction_id=auth["tranref"], raw=dict(auth)
		)

	def refund(
		self, payment_attempt, amount, reason: str, idempotency_key: str | None = None
	) -> RefundResult:
		try:
			auth = self._remote(
				{
					"type": "refund",
					"class": FOLLOW_UP_CLASS,
					"ref": payment_attempt.gateway_transaction_id,
					"amount": amount,
					"currency": (payment_attempt.get("currency") or SETUP_CURRENCY).upper(),
					"cartid": idempotency_key
					or f"refund-{payment_attempt.get('name') or payment_attempt.gateway_transaction_id}",
					"description": (reason or "Refund")[:60],
				}
			)
		except _TRANSIENT as e:
			raise GatewayTimeout(str(e)) from e
		if is_ambiguous(auth):
			raise GatewayTimeout(f"Telr refund outcome unknown: {auth.get('message')}")
		return RefundResult(
			status="Completed" if auth.get("status") == "A" else "Failed",
			gateway_refund_id=auth.get("tranref"),
			raw=dict(auth),
		)

	def verify_webhook_signature(self, payload: bytes, headers: dict) -> bool:
		"""Check `tran_check`, then confirm a hosted-order advice with Telr.

		`tran_check` is the SHA1 of the secret followed by `:<value>` for a fixed list of
		fields. Telr's own plugins (Magento 2, WooCommerce) and its TAS samples name two
		different lists, so each documented layout is tried. The secret is the Webhook
		Secret, and else the hosted-page key, which Telr's plugins sign the order callback
		with. An advice that names a hosted order is then checked against Telr: the order
		must exist in this store with the same cart id."""
		advice = _decode(payload)
		if not self._has_valid_check(advice):
			return False
		if not advice.get("tran_order"):
			return True
		try:
			order = self._check_order(advice["tran_order"])
		except GatewayError:
			return False
		return str(order.get("cartid") or "") == str(advice.get("tran_cartid") or "")

	def parse_webhook_event(self, payload: dict, headers: dict | None = None) -> NormalisedEvent:
		"""One event per transaction and outcome: a held sale that is approved later is a
		second event, and a repeated advice is the same one."""
		return NormalisedEvent(
			gateway_event_id=f"{payload.get('tran_ref')}:{advice_status(payload)}",
			event_type=advice_event_type(payload),
			payload=payload,
		)

	def get_transaction_status(self, gateway_txn_id: str) -> str:
		"""What Telr reports for a transaction.

		A hosted order is read with `check`. Telr has no query for a Remote API
		transaction, so its status is the latest signed advice Central stored for it, or
		`unknown` while none arrived."""
		if not _is_transaction_reference(gateway_txn_id):
			return ORDER_STATUS.get(_order_status_code(self._check_order(gateway_txn_id)), "unknown")
		advice = self._latest_advice(gateway_txn_id)
		if not advice:
			return "unknown"
		return {"A": "captured", "H": "processing", "D": "declined", "C": "cancelled"}.get(
			advice_status(advice), "failed"
		)

	def get_refund_status(self, gateway_refund_id: str) -> str:
		advice = self._latest_advice(gateway_refund_id)
		if not advice:
			raise GatewayUnsupported("Telr has no refund query; no advice has arrived for this refund.")
		return "Completed" if advice_status(advice) == "A" else "Failed"

	@staticmethod
	def payment_from_event(payload: dict) -> VerifiedPayment | None:
		if advice_type(payload) not in ("sale", "capture") or not payload.get("tran_ref"):
			return None
		return VerifiedPayment(
			payment_id=str(payload["tran_ref"]),
			captured=advice_status(payload) == "A",
			amount=frappe.utils.flt(payload.get("tran_amount")),
			currency=str(payload.get("tran_currency") or "").upper(),
			order_id=payload.get("tran_order") or None,
		)

	@staticmethod
	def refund_from_event(payload: dict) -> dict | None:
		if advice_type(payload) != "refund":
			return None
		return {
			"id": payload.get("tran_ref"),
			"status": "Completed" if advice_status(payload) == "A" else "Failed",
		}

	@staticmethod
	def failure_from_event(payload: dict) -> dict | None:
		"""The decline an advice carries, in the shape `charges._extract_failure` returns."""
		if advice_status(payload) in ("A", "H"):
			return None
		auth = {
			"status": advice_status(payload),
			"code": payload.get("tran_authcode"),
			"message": payload.get("tran_authmessage"),
		}
		return {**failure_from_auth(auth), "raw": auth}

	# --- on-session payments -------------------------------------------------

	def create_order(
		self, amount, currency: str, receipt: str, notes: dict | None = None, customer: str | None = None
	) -> dict:
		"""A framed hosted sale for an invoice or top-up the customer pays now. With
		`bill_custref` the customer can pick the stored card."""
		team = customer or (notes or {}).get("team")
		order = self._create_hosted_order(
			amount=amount,
			currency=currency,
			cart=receipt,
			description=f"Payment {receipt}",
			transaction_type="sale",
			customer_reference=team,
		)
		return {"order_id": order["ref"], "iframe_url": order["url"], "checkout_url": order["url"]}

	def create_checkout_session(
		self,
		amount,
		currency: str,
		receipt: str,
		success_url: str,
		cancel_url: str,
		notes: dict | None = None,
		customer: str | None = None,
	) -> dict:
		order = self._create_hosted_order(
			amount=amount,
			currency=currency,
			cart=receipt,
			description=f"Payment {receipt}",
			transaction_type="sale",
			customer_reference=customer or (notes or {}).get("team"),
			return_url=success_url,
			cancel_url=cancel_url,
			framed=False,
		)
		return {"checkout_url": order["url"], "session_id": order["ref"]}

	def find_order_payment(self, order_id: str) -> VerifiedPayment | None:
		"""The paid transaction on a hosted order, or None while it is not paid (status 3)."""
		order = self._check_order(order_id)
		if _order_status_code(order) != 3:
			return None
		transaction = order.get("transaction") or {}
		return VerifiedPayment(
			payment_id=str(transaction.get("ref")),
			captured=transaction.get("status") == "A",
			amount=frappe.utils.flt(order.get("amount")),
			currency=str(order.get("currency") or "").upper(),
			order_id=order_id,
		)

	def checkout_payment(self, session_id: str) -> VerifiedPayment | None:
		return self.find_order_payment(session_id)

	# --- gateway I/O (the stubbed seam) -------------------------------------

	def _store_id(self) -> str:
		store = (frappe.conf.get("telr_store_id") or self.gateway.get("telr_store_id") or "").strip()
		if not store:
			raise GatewayAuthError("The Telr store ID is not set on the Payment Gateway.")
		return store

	def _is_test(self) -> int:
		return 1 if frappe.utils.cint(self.gateway.get("telr_test_mode")) else 0

	def _create_hosted_order(
		self,
		amount,
		currency: str,
		cart: str,
		description: str,
		transaction_type: str,
		customer_reference: str | None = None,
		return_url: str | None = None,
		cancel_url: str | None = None,
		email: str | None = None,
		framed: bool = True,
	) -> dict:
		"""`create` a hosted order and return its `{ref, url}`. A refused create raises
		GatewayError with Telr's message; a network failure raises GatewayTimeout."""
		back = return_url or f"{get_url()}/dashboard/billing"
		params = {
			"ivp_method": "create",
			"ivp_amount": f"{frappe.utils.flt(amount):.2f}",
			"ivp_currency": (currency or SETUP_CURRENCY).upper(),
			"ivp_test": self._is_test(),
			"ivp_cart": cart,
			"ivp_desc": description,
			"ivp_trantype": transaction_type,
			"ivp_framed": FRAMED_MODE if framed else 0,
			"ivp_update_url": self.gateway.webhook_callback_url(),
			"return_auth": back,
			"return_decl": back,
			"return_can": cancel_url or back,
		}
		if customer_reference:
			params["bill_custref"] = customer_reference
		if email:
			params["bill_email"] = email
		try:
			body = self._order(params)
		except _TRANSIENT as e:
			raise GatewayTimeout(str(e)) from e
		order = body.get("order") or {}
		if body.get("error") or not order.get("ref"):
			raise GatewayError(f"Telr refused the order: {_order_error_message(body)}")
		return {"ref": order["ref"], "url": order.get("url")}

	def _check_order(self, order_ref: str) -> dict:
		try:
			body = self._order({"ivp_method": "check", "order_ref": order_ref})
		except _TRANSIENT as e:
			raise GatewayTimeout(str(e)) from e
		if body.get("error"):
			raise GatewayError(f"Telr could not read order {order_ref}: {_order_error_message(body)}")
		return body.get("order") or {}

	def _order(self, params: dict) -> dict:
		"""POST to the hosted-page API (form encoded) and return its JSON body."""
		data = {"ivp_store": self._store_id(), "ivp_authkey": self.get_credential("api_key"), **params}
		response = requests.post(ORDER_URL, data=data, timeout=30)
		response.raise_for_status()
		return response.json()

	def _remote(self, transaction: dict) -> dict:
		"""POST one transaction to the Remote API and return its `<auth>` block, keys lower-cased."""
		response = requests.post(
			REMOTE_URL,
			data=self._remote_request(transaction),
			headers={"Content-Type": "application/xml"},
			timeout=30,
		)
		response.raise_for_status()
		return _parse_auth(response.content)

	def _remote_request(self, transaction: dict) -> bytes:
		root = ElementTree.Element("remote")
		ElementTree.SubElement(root, "store").text = self._store_id()
		ElementTree.SubElement(root, "key").text = self.get_credential("api_secret") or ""
		tran = ElementTree.SubElement(root, "tran")
		values = {**transaction, "test": self._is_test()}
		if "amount" in values:
			values["amount"] = f"{frappe.utils.flt(values['amount']):.2f}"
		for name in ("type", "class", "cartid", "description", "test", "currency", "amount", "ref"):
			if values.get(name) is not None:
				ElementTree.SubElement(tran, name).text = str(values[name])
		return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)

	def _has_valid_check(self, advice: dict) -> bool:
		received = str(advice.get("tran_check") or "").strip().lower()
		if not received:
			return False
		secrets = {self.get_credential("webhook_secret"), self.get_credential("api_key")} - {None, ""}
		for secret in secrets:
			for fields in ADVICE_SIGNATURE_LAYOUTS:
				plain = ":".join([secret, *(str(advice.get(field) or "") for field in fields)])
				expected = hashlib.sha1(plain.encode()).hexdigest()  # Telr's scheme is SHA1
				if hmac.compare_digest(expected, received):
					return True
		return False

	def _latest_advice(self, reference: str) -> dict | None:
		rows = frappe.get_all(
			"Webhook Event",
			filters={"gateway": self.gateway.name, "gateway_event_id": ["like", f"{reference}:%"]},
			fields=["raw_payload"],
			order_by="creation desc",
			limit=1,
		)
		return frappe.parse_json(rows[0].raw_payload) if rows else None

	def _store_next_reference(self, payment_method, reference: str) -> None:
		"""Each approved cont sale is the reference of the next one (Telr continuous authority)."""
		name = payment_method.get("name") if hasattr(payment_method, "get") else None
		if name and frappe.db.exists("Payment Method", name):
			frappe.db.set_value("Payment Method", name, "gateway_method_id", reference, update_modified=False)


def _parse_auth(content: bytes) -> dict:
	"""The `<auth>` block of a Remote API answer, as `{status, code, message, tranref, ...}`."""
	root = ElementTree.fromstring(content)
	auth = root.find("auth")
	if auth is None:
		raise ValueError("Telr answered without an <auth> block.")
	return {child.tag.lower(): (child.text or "").strip() for child in auth}


def _decode(payload) -> dict:
	body = payload.decode() if isinstance(payload, bytes) else payload
	return frappe.parse_json(body) if isinstance(body, str) else dict(body or {})


def _order_status_code(order: dict) -> int | None:
	code = (order.get("status") or {}).get("code")
	return frappe.utils.cint(code) if code not in (None, "") else None


def _order_error_message(body: dict) -> str:
	error = body.get("error") or {}
	return " ".join(part for part in (error.get("message"), error.get("note")) if part) or "no reason given"


def _order_error_code(body: dict) -> str | None:
	"""The code of a hosted-page error such as `E56:Duplicate transaction`."""
	message = str((body.get("error") or {}).get("message") or "")
	head = message.split(":", 1)[0].strip().upper()
	return head[1:] if head.startswith("E") and head[1:].isdigit() else None


def _is_transaction_reference(reference: str) -> bool:
	"""Telr transaction references are 12 digits; hosted order references are not."""
	return str(reference or "").isdigit()


def _saved_card(order: dict) -> dict:
	card = order.get("card") or {}
	expiry = card.get("expiry") or {}
	return {
		"payment_method": str((order.get("transaction") or {}).get("ref")),
		# Central created the order with bill_custref = the team, so there is no other customer.
		"customer": None,
		"brand": card.get("type"),
		"last4": card.get("last4"),
		"exp_month": frappe.utils.cint(expiry.get("month")) or None,
		"exp_year": _four_digit_year(expiry.get("year")),
	}


def _four_digit_year(year) -> int | None:
	year = frappe.utils.cint(year)
	if not year:
		return None
	return year + 2000 if year < 100 else year
