# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt
"""Checkout.com GatewayAdapter (UAE, AED) over the REST API, with no SDK.

Keys on the Payment Gateway row:

- API Key: the public key (`pk_...`). The browser uses it to start Flow.
- API Secret: the secret key (`sk_...`), sent as `Authorization: Bearer`. This is the
  key of a NAS account; a legacy (ABC) account is not supported.
- Webhook Secret: the signature key of the webhook workflow. Central makes it and
  registers the workflow (`register_webhook`), so no one copies it by hand.
- Checkout Environment: Sandbox or Live. Processing Channel ID (`pc_...`) goes on
  every payment. API Prefix is the account's own host prefix, if Checkout.com gave one.

Cards are collected by Flow, Checkout.com's web component, so card data never
reaches Central. A card is added with a payment session for amount 0 (a card
verification) of type Unscheduled with 3DS: the cardholder is present once, and
Checkout.com stores the card as a source (`src_...`). The session reference is
Central's own (`setup_reference`), so the card is read back by that reference and
not by anything the browser sends.

Off-session charges are merchant-initiated: `source.type = id`, `merchant_initiated =
true`, `payment_type = Unscheduled` and `previous_payment_id` = the customer-present
payment that stored the card (kept as the method's Gateway Mandate ID). The
idempotency key is sent as `Cko-Idempotency-Key`.

Fallback: when the bank asks for the cardholder (20154, 43401) or the stored source
is no longer usable, the charge fails with a customer-present code
(`decline.CUSTOMER_PRESENT_CODES`). Billing holds the card and raises Action
Required, the customer pays that invoice once in Flow, and that payment becomes the
card's new source and previous payment (`payments.rearm_customer_present_method`).

Every call to Checkout.com goes through `_request`, so tests stub that one method."""

import hashlib
import hmac
import secrets
from decimal import ROUND_HALF_UP, Decimal
from typing import ClassVar

import frappe
import requests
from frappe.utils import get_url

from central.billing.gateways.base import (
	GatewayAdapter,
	GatewayAuthError,
	GatewayError,
	GatewayTimeout,
	NormalisedEvent,
	PaymentResult,
	RefundResult,
	VerifiedPayment,
	WebhookNotFound,
	header_value,
)
from central.billing.gateways.checkout_codes import failure_from_response, is_approved
from central.billing.payments.decline import REQUEST_REFUSED, STORED_CREDENTIAL_INVALID

SANDBOX = "Sandbox"
LIVE = "Live"
_HOSTS = {SANDBOX: "api.sandbox.checkout.com", LIVE: "api.checkout.com"}
# The `environment` option of CheckoutWebComponents.
_FLOW_ENVIRONMENTS = {SANDBOX: "sandbox", LIVE: "production"}
# Checkout.com says to load Flow from its own host, never bundled or self-hosted.
FLOW_SCRIPT_URL = "https://checkout-web-components.checkout.com/index.js"

SIGNATURE_HEADER = "Cko-Signature"
DEFAULT_CURRENCY = "AED"
# A merchant-initiated charge on a stored card with no fixed schedule or amount.
STORED_CARD_PAYMENT_TYPE = "Unscheduled"
# Amex limits a reference to 30 characters.
REFERENCE_LIMIT = 30

# The ISO 4217 minor unit where it is not 2, for the currencies Checkout.com settles.
_ZERO_DECIMAL = {"BIF", "CLP", "DJF", "GNF", "ISK", "JPY", "KMF", "KRW", "PYG", "RWF", "UGX"}
_ZERO_DECIMAL |= {"VND", "VUV", "XAF", "XOF", "XPF"}
_THREE_DECIMAL = {"BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"}

# Workflow event sources, as Checkout.com names them in a workflow condition.
GATEWAY_EVENTS = (
	"card_verified",
	"card_verification_declined",
	"payment_approved",
	"payment_declined",
	"payment_captured",
	"payment_capture_declined",
	"payment_refunded",
	"payment_refund_declined",
)
DISPUTE_EVENTS = (
	"dispute_evidence_required",
	"dispute_canceled",
	"dispute_expired",
	"dispute_lost",
	"dispute_resolved",
	"dispute_won",
)
CHECKOUT_WEBHOOK_EVENTS = GATEWAY_EVENTS + DISPUTE_EVENTS

_CAPTURED = ("Captured", "Partially Captured", "Partially Refunded", "Refunded", "Paid")
_SAVED = ("Card Verified", "Authorized", *_CAPTURED)
_FAILED = ("Declined", "Canceled", "Expired", "Voided")
_STATUS = {
	"Captured": "captured",
	"Partially Captured": "captured",
	"Paid": "captured",
	"Partially Refunded": "refunded",
	"Refunded": "refunded",
	"Authorized": "authorised",
	"Card Verified": "verified",
	"Pending": "processing",
	"Retry Scheduled": "processing",
	"Declined": "failed",
	"Expired": "failed",
	"Canceled": "cancelled",
	"Voided": "cancelled",
}


class CheckoutNotFound(GatewayError):
	"""Checkout.com answered 404 for the object."""


class CheckoutRefused(GatewayError):
	"""Checkout.com refused the request as invalid (422) or not allowed (403)."""

	def __init__(self, message: str, body: dict | None = None):
		super().__init__(message)
		self.body = body or {}


class CheckoutAdapter(GatewayAdapter):
	conf_keys: ClassVar[dict[str, str]] = {
		"api_key": "checkout_public_key",
		"api_secret": "checkout_secret_key",
		"webhook_secret": "checkout_webhook_secret",
	}
	webhook_events = CHECKOUT_WEBHOOK_EVENTS
	supports_off_session_charge = True
	# A customer-present payment stores the card again and links the next charge to it.
	rearms_on_customer_present_payment = True

	# --- gateway setup -----------------------------------------------------------

	def validate_credentials(self) -> dict:
		"""Prove the secret key with a payment search by a reference no payment has.

		The key must match the environment: a sandbox key (`sk_sbox_`) is refused by the
		live host, and the reverse. Checkout.com exposes no account currency, so
		`currency` is None. The account is named by its processing channel."""
		secret = self.get_credential("api_secret") or ""
		if not secret:
			raise GatewayAuthError("The Checkout.com secret key is not set.")
		if _is_sandbox_key(secret) != (self._environment() == SANDBOX):
			raise GatewayAuthError(
				f"The secret key does not belong to the {self._environment()} environment."
			)
		public = self.get_credential("api_key") or ""
		if public and _is_sandbox_key(public) != (self._environment() == SANDBOX):
			raise GatewayAuthError(
				f"The public key does not belong to the {self._environment()} environment."
			)
		self._request("GET", "/payments", params={"reference": "central-credential-check", "limit": 1})
		return {
			"account_id": self._processing_channel() or f"checkout-{self._environment().lower()}",
			"currency": None,
		}

	def default_currency(self) -> str | None:
		return super().default_currency() or DEFAULT_CURRENCY

	def register_webhook(self, callback_url: str, events: list[str] | None = None) -> dict:
		"""Create a workflow that posts the events to `callback_url`, signed with a key
		Central makes. Returns the workflow id and that key."""
		key = secrets.token_urlsafe(32)
		body = {
			"name": "Intrakore Central billing",
			"active": True,
			"conditions": self._conditions(events or list(self.webhook_events)),
			"actions": [
				{
					"type": "webhook",
					"url": callback_url,
					"signature": {"method": "HMACSHA256", "key": key},
				}
			],
		}
		workflow = self._request("POST", "/workflows", json=body)
		return {"endpoint_id": workflow.get("id"), "secret": key}

	def get_webhook(self, endpoint_id: str) -> dict:
		try:
			workflow = self._request("GET", f"/workflows/{endpoint_id}")
		except CheckoutNotFound as e:
			raise WebhookNotFound(f"Workflow {endpoint_id} is not in this Checkout.com account.") from e
		action = next((a for a in workflow.get("actions") or [] if a.get("type") == "webhook"), {})
		condition = _event_condition(workflow)
		events = [event for names in (condition.get("events") or {}).values() for event in names]
		return {"url": action.get("url"), "is_active": bool(workflow.get("active")), "events": events}

	def update_webhook_events(self, endpoint_id: str, callback_url: str, events: list[str]) -> None:
		"""Replace the event condition of the workflow. The signature key does not change."""
		try:
			workflow = self._request("GET", f"/workflows/{endpoint_id}")
		except CheckoutNotFound as e:
			raise WebhookNotFound(f"Workflow {endpoint_id} is not in this Checkout.com account.") from e
		condition = self._event_source_condition(events)
		existing = _event_condition(workflow)
		if existing.get("id"):
			self._request("PUT", f"/workflows/{endpoint_id}/conditions/{existing['id']}", json=condition)
		else:
			self._request("POST", f"/workflows/{endpoint_id}/conditions", json=condition)

	def create_customer(self, team) -> str:
		"""A Checkout.com customer for the team. A card saved under it is checked against
		it on confirm, so a card saved for another team is refused."""
		email = _get(team, "owner_user")
		body = {"name": (_get(team, "name") or "")[:255]}
		if email:
			body["email"] = email
		return self._request("POST", "/customers", json=body)["id"]

	# --- adding a card -----------------------------------------------------------

	def setup_payment_method(self, team, setup_data: dict) -> dict:
		"""Open a Flow payment session that verifies the card (amount 0) and stores it.

		The dashboard mounts Flow with `payment_session`, `public_key` and `environment`
		(see the module docstring of `dashboard/src/lib/checkout.ts`), then confirms the
		Payment Method. Central reads the card back by `setup_intent_id`, the session
		reference it made here."""
		team_name = team if isinstance(team, str) else _get(team, "name")
		currency = (setup_data.get("currency") or DEFAULT_CURRENCY).upper()
		reference = f"card-{frappe.generate_hash(length=20)}"
		session = self._payment_session(
			amount=0,
			currency=currency,
			reference=reference,
			payment_type=STORED_CARD_PAYMENT_TYPE,
			team=team_name,
			customer_id=setup_data.get("customer_id"),
			description="Card check",
			return_url=setup_data.get("return_url"),
		)
		return {
			"setup_intent_id": reference,
			"reference": reference,
			"customer_id": setup_data.get("customer_id"),
			"amount": 0,
			"currency": currency,
			**self._flow_handles(session),
		}

	def read_saved_card(self, setup_reference: str, payment_id: str | None = None) -> dict:
		"""The card the payment of this setup stored, or `{}` while the customer has not
		finished. A refused card gives only `setup_error`.

		`payment_id` is what Flow's onPaymentCompleted gave the browser. It is read from
		Checkout.com and used only when the payment carries `setup_reference`, which
		Central set on the session; otherwise the latest payment with that reference is."""
		payment = self._payment_of_setup(setup_reference, payment_id)
		if not payment or payment.get("status") in ("Pending", "Retry Scheduled"):
			return {}
		if payment.get("approved") and payment.get("status") in _SAVED:
			source = payment.get("source") or {}
			if not source.get("id"):
				return {}
			return {
				"payment_method": source["id"],
				# The customer-present payment every merchant-initiated charge links to.
				"mandate": payment.get("id"),
				"customer": (payment.get("customer") or {}).get("id"),
				"brand": source.get("scheme"),
				"last4": source.get("last4") or source.get("last_4"),
				"exp_month": frappe.utils.cint(source.get("expiry_month")) or None,
				"exp_year": frappe.utils.cint(source.get("expiry_year")) or None,
				"scheme_id": payment.get("scheme_id"),
				"three_ds": payment.get("3ds") or {},
			}
		failure = self._payment_failure(payment)
		return {
			"setup_error": {"failure_code": failure["failure_code"], "decline_code": failure["decline_code"]}
		}

	def validate_payment_method(self, payment_method) -> PaymentResult:
		"""The amount-0 verification with the cardholder present already proved the card,
		so nothing is charged here. A card can be charged off-session only with both its
		source and the payment it was stored by."""
		if payment_method.gateway_method_id and payment_method.get("gateway_mandate_id"):
			return PaymentResult(success=True, status="Validated")
		return PaymentResult(
			success=False,
			status="Failed",
			failure_code="token_missing",
			failure_reason="Checkout.com returned no stored card for this setup.",
		)

	# --- charges and refunds -----------------------------------------------------

	def charge(self, invoice, payment_method, idempotency_key: str) -> PaymentResult:
		"""A merchant-initiated payment on the stored card, linked to its stored payment.

		Approved is Captured: the payment asks for capture, and payment_captured settles the
		invoice. A refused request (422) moved no money. A lost answer raises GatewayTimeout,
		and a retry with the same idempotency key gets the same payment back."""
		source_id = payment_method.gateway_method_id
		previous = payment_method.get("gateway_mandate_id")
		if not source_id or not previous:
			# Without both the charge would be refused: ask the customer to pay once.
			return PaymentResult(
				success=False,
				status="Failed",
				failure_code=STORED_CREDENTIAL_INVALID,
				failure_reason="The card has no stored Checkout.com payment to link this charge to.",
			)
		currency = (invoice.get("currency") or DEFAULT_CURRENCY).upper()
		body = {
			"source": {"type": "id", "id": source_id},
			"amount": to_minor(invoice.get("amount"), currency),
			"currency": currency,
			"payment_type": STORED_CARD_PAYMENT_TYPE,
			"merchant_initiated": True,
			"previous_payment_id": previous,
			"capture": True,
			"reference": _reference(invoice.get("name") or idempotency_key),
			"description": f"Invoice {invoice.get('name') or ''}".strip(),
		}
		if invoice.get("customer_id"):
			body["customer"] = {"id": invoice.get("customer_id")}
		self._add_processing_channel(body)
		try:
			payment = self._request("POST", "/payments", json=body, idempotency_key=idempotency_key)
		except CheckoutRefused as e:
			return PaymentResult(
				success=False,
				status="Failed",
				failure_code=REQUEST_REFUSED,
				failure_reason=str(e)[:140],
				raw=e.body,
			)
		return self._charge_result(payment)

	def refund(
		self, payment_attempt, amount, reason: str, idempotency_key: str | None = None
	) -> RefundResult:
		"""Refund a captured payment. Checkout.com accepts a refund (202) and reports the
		outcome on the payment's actions and in payment_refunded. The refund id is
		`<payment id>:<action id>`, because an action is read through its payment."""
		payment_id = payment_attempt.gateway_transaction_id
		currency = (payment_attempt.get("currency") or DEFAULT_CURRENCY).upper()
		body = {
			"amount": to_minor(amount, currency),
			"reference": _reference(idempotency_key or f"refund-{payment_attempt.get('name') or payment_id}"),
		}
		try:
			accepted = self._request(
				"POST", f"/payments/{payment_id}/refunds", json=body, idempotency_key=idempotency_key
			)
		except (CheckoutRefused, CheckoutNotFound) as e:
			return RefundResult(status="Failed", raw={"error": str(e)})
		refund_id = f"{payment_id}:{accepted.get('action_id')}"
		return RefundResult(
			status=self._refund_action_status(payment_id, accepted.get("action_id")),
			gateway_refund_id=refund_id,
			raw=accepted,
		)

	def get_refund_status(self, gateway_refund_id: str) -> str:
		payment_id, _, action_id = (gateway_refund_id or "").partition(":")
		return self._refund_action_status(payment_id, action_id)

	def get_transaction_status(self, gateway_txn_id: str) -> str:
		"""The payment's status in the words reconciliation reads."""
		try:
			payment = self._request("GET", f"/payments/{gateway_txn_id}")
		except CheckoutNotFound:
			return "unknown"
		return _STATUS.get(payment.get("status"), "unknown")

	# --- on-session payments -----------------------------------------------------

	def create_order(
		self, amount, currency: str, receipt: str, notes: dict | None = None, customer: str | None = None
	) -> dict:
		"""A Flow payment session for an invoice or a top-up the customer pays now.

		`order_id` is the session reference, which is `receipt`, so the webhook and
		reconciliation find the payment by it. When the team's card is held for a
		customer-present payment, the session stores the card again (Unscheduled), and
		that payment rearms the card."""
		notes = notes or {}
		team = notes.get("team")
		currency = (currency or DEFAULT_CURRENCY).upper()
		rearm = notes.get("purpose") == "invoice_payment" and self._has_held_card(team)
		session = self._payment_session(
			amount=to_minor(amount, currency),
			currency=currency,
			reference=_reference(receipt),
			payment_type=STORED_CARD_PAYMENT_TYPE if rearm else "Regular",
			team=team,
			customer_id=customer or self._customer_for(team),
			description=f"Payment {receipt}",
		)
		return {
			"order_id": _reference(receipt),
			"reference": _reference(receipt),
			**self._flow_handles(session),
		}

	def verify_payment(self, payment_id: str) -> VerifiedPayment:
		"""A payment read back by its id (`pay_...`), or by the reference Central gave it."""
		if str(payment_id or "").startswith("pay_"):
			payment = self._request("GET", f"/payments/{payment_id}")
		else:
			payment = self._latest_payment(payment_id)
			if not payment:
				raise GatewayError(f"Checkout.com has no payment with reference {payment_id}.")
		return _verified(payment)

	def find_order_payment(self, order_id: str) -> VerifiedPayment | None:
		"""The captured payment with this reference, or None while there is none."""
		for payment in self._payments_by_reference(order_id):
			if payment.get("status") in _CAPTURED:
				return _verified(payment)
		return None

	def checkout_payment(self, session_id: str) -> VerifiedPayment | None:
		return self.find_order_payment(session_id)

	# --- webhooks ----------------------------------------------------------------

	def verify_webhook_signature(self, payload: bytes, headers: dict) -> bool:
		"""`Cko-Signature` is the hex HMAC-SHA256 of the raw body, keyed with the
		workflow's signature key (the Webhook Secret)."""
		secret = self.get_credential("webhook_secret")
		received = str(header_value(headers, SIGNATURE_HEADER) or "").strip().lower()
		if not secret or not received:
			return False
		body = payload if isinstance(payload, bytes) else str(payload).encode()
		expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
		return hmac.compare_digest(expected, received)

	def parse_webhook_event(self, payload: dict, headers: dict | None = None) -> NormalisedEvent:
		return NormalisedEvent(
			gateway_event_id=str(payload.get("id") or ""),
			event_type=str(payload.get("type") or ""),
			payload=payload,
		)

	@staticmethod
	def payment_from_event(payload: dict) -> VerifiedPayment | None:
		if payload.get("type") not in GATEWAY_EVENTS or str(payload.get("type")).startswith("card_"):
			return None
		data = payload.get("data") or {}
		if not str(data.get("id") or "").startswith("pay_"):
			return None
		currency = str(data.get("currency") or "").upper()
		return VerifiedPayment(
			payment_id=data["id"],
			captured=payload.get("type") == "payment_captured",
			amount=from_minor(data.get("amount"), currency),
			currency=currency,
			# Central set the reference on the session or the payment; the payer cannot.
			order_id=data.get("reference") or None,
			receipt=data.get("reference") or None,
		)

	@staticmethod
	def failure_from_event(payload: dict) -> dict | None:
		if payload.get("type") not in ("payment_declined", "payment_capture_declined"):
			return None
		data = payload.get("data") or {}
		code = data.get("response_code")
		return {**failure_from_response(code, data.get("response_summary")), "raw": {"response_code": code}}

	@staticmethod
	def refund_from_event(payload: dict) -> dict | None:
		if payload.get("type") not in ("payment_refunded", "payment_refund_declined"):
			return None
		data = payload.get("data") or {}
		return {
			"id": f"{data.get('id')}:{data.get('action_id')}",
			"status": "Completed" if payload.get("type") == "payment_refunded" else "Failed",
		}

	@staticmethod
	def dispute_from_event(payload: dict) -> dict | None:
		event_type = payload.get("type")
		if event_type not in DISPUTE_EVENTS:
			return None
		data = payload.get("data") or {}
		status = {"dispute_evidence_required": "open", "dispute_lost": "lost", "dispute_won": "won"}.get(
			event_type, event_type.removeprefix("dispute_")
		)
		return {
			"id": data.get("id"),
			"payment_id": data.get("payment_id"),
			"amount": from_minor(data.get("amount"), str(data.get("currency") or "")),
			"reason": data.get("category") or data.get("reason_code"),
			"status": status,
		}

	# --- helpers -----------------------------------------------------------------

	def _payment_session(
		self,
		amount: int,
		currency: str,
		reference: str,
		payment_type: str,
		team: str | None,
		customer_id: str | None,
		description: str,
		return_url: str | None = None,
	) -> dict:
		back = return_url or f"{get_url()}/dashboard/billing"
		body = {
			"amount": amount,
			"currency": currency,
			"payment_type": payment_type,
			"reference": reference,
			"description": description,
			"billing": {"address": {"country": _country_code(team)}},
			"enabled_payment_methods": ["card"],
			"3ds": {"enabled": True},
			"success_url": back,
			"failure_url": back,
		}
		if customer_id:
			body["customer"] = {"id": customer_id}
		self._add_processing_channel(body)
		return self._request("POST", "/payment-sessions", json=body)

	def _flow_handles(self, session: dict) -> dict:
		"""What the browser needs to mount Flow, under `checkout` (the dashboard's
		`CheckoutSetup`). `payment_session` is Checkout.com's answer unchanged, as Flow
		requires."""
		return {
			"checkout": {
				"public_key": self.get_credential("api_key"),
				"environment": _FLOW_ENVIRONMENTS[self._environment()],
				"payment_session": session,
				"flow_script_url": FLOW_SCRIPT_URL,
			}
		}

	def _charge_result(self, payment: dict) -> PaymentResult:
		status = payment.get("status")
		if payment.get("approved") and status in ("Authorized", *_CAPTURED):
			return PaymentResult(
				success=True, status="Captured", gateway_transaction_id=payment.get("id"), raw=payment
			)
		if status in ("Pending", "Retry Scheduled") or (not status and payment.get("id")):
			# Accepted, outcome later (202): the webhook or reconciliation settles it.
			hold = frappe.utils.add_days(frappe.utils.now_datetime(), 1)
			return PaymentResult(
				success=False,
				status="Pending",
				gateway_transaction_id=payment.get("id"),
				hold_until=str(hold),
				raw=payment,
			)
		failure = failure_from_response(payment.get("response_code"), payment.get("response_summary"))
		return PaymentResult(
			success=False, status="Failed", gateway_transaction_id=payment.get("id"), raw=payment, **failure
		)

	def _refund_action_status(self, payment_id: str, action_id: str | None) -> str:
		"""Completed or Failed once the refund action has a response code, else Pending."""
		if not payment_id or not action_id:
			return "Pending"
		try:
			actions = self._request("GET", f"/payments/{payment_id}/actions")
		except CheckoutNotFound:
			return "Pending"
		rows = actions if isinstance(actions, list) else actions.get("data") or []
		action = next((row for row in rows if row.get("id") == action_id), None)
		if not action or not action.get("response_code"):
			return "Pending"
		return "Completed" if is_approved(action["response_code"]) else "Failed"

	def _payment_failure(self, payment: dict) -> dict:
		"""The decline of a payment, from its latest action's response code."""
		code, summary = payment.get("response_code"), payment.get("response_summary")
		if not code and payment.get("id"):
			try:
				actions = self._request("GET", f"/payments/{payment['id']}/actions")
			except GatewayError:
				actions = []
			rows = actions if isinstance(actions, list) else actions.get("data") or []
			declined = next((row for row in rows if row.get("response_code")), {})
			code, summary = declined.get("response_code"), declined.get("response_summary")
		return failure_from_response(code, summary)

	def _payments_by_reference(self, reference: str) -> list[dict]:
		"""Payments with this reference, newest first."""
		answer = self._request("GET", "/payments", params={"reference": reference, "limit": 100})
		rows = answer.get("data") or []
		return sorted(rows, key=lambda row: str(row.get("requested_on") or ""), reverse=True)

	def _payment_of_setup(self, reference: str, payment_id: str | None) -> dict | None:
		if str(payment_id or "").startswith("pay_"):
			try:
				payment = self._request("GET", f"/payments/{payment_id}")
			except CheckoutNotFound:
				payment = None
			if payment and payment.get("reference") == reference:
				return payment
		return self._latest_payment(reference)

	def _latest_payment(self, reference: str) -> dict | None:
		rows = self._payments_by_reference(reference)
		return rows[0] if rows else None

	def _has_held_card(self, team: str | None) -> bool:
		return bool(
			team
			and frappe.db.exists(
				"Payment Method",
				{"team": team, "gateway": self.gateway.name, "status": "Active", "reauth_required": 1},
			)
		)

	def _customer_for(self, team: str | None) -> str | None:
		if not team:
			return None
		return frappe.db.get_value(
			"Gateway Customer", {"team": team, "gateway": self.gateway.name}, "gateway_customer_id"
		)

	def _conditions(self, events: list[str]) -> list[dict]:
		conditions = [self._event_source_condition(events)]
		if self._processing_channel():
			conditions.append(
				{"type": "processing_channel", "processing_channels": [self._processing_channel()]}
			)
		return conditions

	@staticmethod
	def _event_source_condition(events: list[str]) -> dict:
		sources = {
			"gateway": [e for e in events if not e.startswith("dispute_")],
			"dispute": [e for e in events if e.startswith("dispute_")],
		}
		return {"type": "event", "events": {source: names for source, names in sources.items() if names}}

	def _add_processing_channel(self, body: dict) -> None:
		if self._processing_channel():
			body["processing_channel_id"] = self._processing_channel()

	def _environment(self) -> str:
		return LIVE if self.gateway.get("checkout_environment") == LIVE else SANDBOX

	def _processing_channel(self) -> str | None:
		return (
			frappe.conf.get("checkout_processing_channel_id")
			or self.gateway.get("processing_channel_id")
			or ""
		).strip() or None

	def _base_url(self) -> str:
		prefix = (self.gateway.get("checkout_api_prefix") or "").strip().strip(".")
		host = _HOSTS[self._environment()]
		return f"https://{prefix}.{host}" if prefix else f"https://{host}"

	def _request(
		self,
		method: str,
		path: str,
		json: dict | None = None,
		params: dict | None = None,
		idempotency_key: str | None = None,
	):
		"""One authenticated call. 401 is GatewayAuthError, 404 CheckoutNotFound, 403 and 422
		CheckoutRefused; a network failure, 409, 429 or 5xx is GatewayTimeout."""
		headers = {"Authorization": f"Bearer {self.get_credential('api_secret') or ''}"}
		if idempotency_key:
			headers["Cko-Idempotency-Key"] = idempotency_key
		try:
			response = requests.request(
				method, f"{self._base_url()}{path}", json=json, params=params, headers=headers, timeout=30
			)
		except requests.exceptions.RequestException as e:
			raise GatewayTimeout(f"Checkout.com did not answer {method} {path}: {e}") from e
		code = response.status_code
		if code == 401:
			raise GatewayAuthError("Checkout.com refused the secret key (401).")
		if code == 404:
			raise CheckoutNotFound(f"Checkout.com has no {path} (404).")
		body = _json(response)
		if code in (403, 422):
			raise CheckoutRefused(f"Checkout.com refused {method} {path} ({code}): {_errors(body)}", body)
		if code in (409, 429) or code >= 500:
			raise GatewayTimeout(f"Checkout.com answered {code} to {method} {path}.")
		if code >= 400:
			raise GatewayError(f"Checkout.com answered {code} to {method} {path}: {_errors(body)}")
		return body


def to_minor(amount, currency: str) -> int:
	"""Major units to the integer Checkout.com takes (AED 12.34 is 1234)."""
	digits = _minor_digits(currency)
	minor = Decimal(str(frappe.utils.flt(amount))).scaleb(digits)
	return int(minor.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def from_minor(amount, currency: str) -> float:
	return float(Decimal(frappe.utils.cint(amount)).scaleb(-_minor_digits(currency)))


def _minor_digits(currency: str) -> int:
	code = (currency or "").upper()
	if code in _ZERO_DECIMAL:
		return 0
	return 3 if code in _THREE_DECIMAL else 2


def _verified(payment: dict) -> VerifiedPayment:
	currency = str(payment.get("currency") or "").upper()
	return VerifiedPayment(
		payment_id=payment.get("id"),
		captured=payment.get("status") in _CAPTURED,
		amount=from_minor(payment.get("amount"), currency),
		currency=currency,
		order_id=payment.get("reference") or None,
		receipt=payment.get("reference") or None,
	)


def _event_condition(workflow: dict) -> dict:
	return next((c for c in workflow.get("conditions") or [] if c.get("type") == "event"), {})


def _is_sandbox_key(key: str) -> bool:
	return key.startswith(("sk_sbox_", "pk_sbox_", "sk_test_", "pk_test_"))


def _reference(value: str) -> str:
	return str(value or "")[:REFERENCE_LIMIT]


def _country_code(team: str | None) -> str:
	"""The team's billing country as ISO 3166 alpha-2, which Checkout.com requires on a
	payment session. A team with no country is billed from the UAE."""
	country = team and frappe.db.get_value("Billing Profile", team, "country")
	code = country and frappe.db.get_value("Country", country, "code")
	return (code or "ae").upper()


def _get(obj, key: str):
	if obj is None:
		return None
	if isinstance(obj, dict):
		return obj.get(key)
	return getattr(obj, key, None)


def _json(response) -> dict:
	try:
		return response.json() if response.content else {}
	except ValueError:
		return {}


def _errors(body) -> str:
	if not isinstance(body, dict):
		return "no detail"
	codes = body.get("error_codes") or []
	return ", ".join(str(c) for c in codes) or str(body.get("error_type") or "no detail")
