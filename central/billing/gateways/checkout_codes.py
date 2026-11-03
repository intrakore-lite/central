# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt
"""What Checkout.com's response codes mean to billing.

The codes are Checkout.com's "API response codes" table: 10xxx approved, 20xxx soft
declines (a later attempt can succeed), 30xxx hard declines (the issuer or the
cardholder must act first), 4xxxx risk responses and 50xxx payout and refund
declines. Some codes carry letters (200N7, 200R1), so a code is a string here."""

from central.billing.payments.decline import (
	CUSTOMER_AUTHENTICATION_REQUIRED,
	REQUEST_REFUSED,
	STORED_CREDENTIAL_INVALID,
)

APPROVED_CODES = {"10000", "10100", "10200"}

# The code -> (Central failure code, decline code). A decline code from
# `decline.HARD_DECLINE_CODES` stops every later retry on the card.
_CODES = {
	# The card needs the cardholder: 3DS is required, or the stored source is no longer
	# usable. The customer pays once in the card form, and that payment rearms the card.
	"20154": (CUSTOMER_AUTHENTICATION_REQUIRED, "authentication_required"),
	"43401": (CUSTOMER_AUTHENTICATION_REQUIRED, "authentication_required"),
	"20101": (STORED_CREDENTIAL_INVALID, "invalid_account"),
	"20114": (STORED_CREDENTIAL_INVALID, None),
	"20108": (STORED_CREDENTIAL_INVALID, None),  # "Declined - Updated cardholder available"
	# The cardholder stopped the standing payment at the bank.
	"200R1": ("card_declined", "revocation_of_authorization"),
	"200R3": ("card_declined", "revocation_of_all_authorizations"),
	# The card itself.
	"20005": ("card_declined", "do_not_honor"),
	"20051": ("card_declined", "insufficient_funds"),
	"20061": ("card_declined", "insufficient_funds"),
	"200P1": ("card_declined", "insufficient_funds"),
	"20054": ("expired_card", None),
	"30033": ("expired_card", "pickup_card"),
	"20100": ("expired_card", None),
	"20014": ("incorrect_number", None),
	"30015": ("incorrect_number", "invalid_account"),
	"20087": ("incorrect_cvc", None),
	"200N7": ("incorrect_cvc", None),
	"20124": ("incorrect_cvc", None),
	"20150": ("authentication_failed", None),
	"20151": ("authentication_failed", None),
	"20155": ("authentication_failed", None),
	"20057": ("card_not_supported", None),
	"20103": ("card_not_supported", None),
	"20059": ("card_declined", "fraudulent"),
	"20062": ("card_declined", "restricted_card"),
	"30004": ("card_declined", "pickup_card"),
	"30007": ("card_declined", "pickup_card"),
	"30041": ("card_declined", "lost_card"),
	"30043": ("card_declined", "stolen_card"),
	"30046": ("card_declined", "invalid_account"),
	# Our request or our account set-up: an operator fixes it.
	"20003": (REQUEST_REFUSED, None),
	"20102": (REQUEST_REFUSED, None),
	"20106": (REQUEST_REFUSED, None),
	"20113": (REQUEST_REFUSED, None),
	"20117": (REQUEST_REFUSED, None),
	"20121": (REQUEST_REFUSED, None),
	"20156": (REQUEST_REFUSED, None),
	"20157": (REQUEST_REFUSED, None),
	# Our own risk rules blocked the card.
	"41201": ("card_declined", "merchant_blacklist"),
}


def failure_from_response(response_code, response_summary: str | None = None) -> dict:
	"""`{failure_code, decline_code, failure_reason}` for a declined Checkout.com payment.

	An unlisted soft decline (20xxx) is a plain card decline that may clear later. An
	unlisted hard decline (30xxx) or risk response (4xxxx) must not be retried."""
	code = str(response_code or "").strip().upper()
	failure_code, decline_code = _CODES.get(code, (None, None))
	if not failure_code:
		failure_code = "card_declined"
		decline_code = "do_not_try_again" if code[:1] in ("3", "4") else (f"cko_{code}" if code else None)
	reason = f"{code} {response_summary or ''}".strip() or "Declined"
	return {"failure_code": failure_code, "decline_code": decline_code, "failure_reason": reason[:140]}


def is_approved(response_code) -> bool:
	return str(response_code or "").strip() in APPROVED_CODES
