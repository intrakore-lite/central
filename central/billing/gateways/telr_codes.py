# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt
"""What Telr's response codes and advice fields mean to billing.

The codes are Telr's "Response codes" table (docs.telr.com, General > Response codes):
status A (authorised), H (authorised, on hold), D (declined), E (error), C (cancelled),
X (expired), each with a numeric code. The no-retry lists are Telr's "Retry
guidelines" for Visa and Mastercard recurring transactions."""

# Telr answered, but whether money moved is not known: a duplicate cart id (the first
# request may have gone through), or a failure at Telr or its processor.
AMBIGUOUS_CODES = {56, 58, 59, 78, 98, 99}

# E01 hides a bad key and a live request from an IP Telr has not whitelisted; E04 is a
# wrong store ID.
CREDENTIAL_CODES = {1, 4}

# A Visa or Mastercard recurring decline with one of these must not be retried.
NO_RETRY_CODES = {11, 12, 66, 67, 91, 109, 110, 112, 113}

# The code -> Central failure code. Anything unlisted is a decline (D) or a refused
# request (E), by its status.
_FAILURE_CODES = {
	57: "continuous_authority_unavailable",  # "Continuous authority not available on referenced transaction"
	22: "reference_invalid",  # "Invalid transaction reference"
	25: "reference_invalid",  # "Original transaction not authorised"
	39: "request_refused",  # "Invalid transaction class": cont is not enabled on the store
	21: "request_refused",  # "Card/Currency/Class combination not supported"
	41: "card_declined",  # "Insufficient funds"
	11: "incorrect_number",
	12: "expired_card",
	38: "expired_card",
	15: "incorrect_cvc",
	42: "incorrect_cvc",
	46: "authentication_failed",
	47: "authentication_failed",
	65: "card_not_supported",
	67: "card_not_supported",
}

_DECLINE_CODES = {41: "insufficient_funds", 62: "do_not_honor"}

# The hosted-page order status (`check`), as the words reconciliation reads.
ORDER_STATUS = {
	1: "pending",
	2: "authorised",
	3: "paid",
	4: "payment_requested",
	-1: "expired",
	-2: "cancelled",
	-3: "declined",
	-4: "replaced",
}

# The fields `tran_check` is the SHA1 of, after the secret, joined with ":".
# Telr's Magento 2 and WooCommerce plugins verify the order callback (ivp_update_url)
# with the first; Telr's Transaction Advice Service samples use the second, and the
# older sample the third. Telr is to confirm which one each service sends.
ADVICE_SIGNATURE_LAYOUTS = (
	(
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
	),
	(
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
	),
	(
		"tran_store",
		"tran_type",
		"tran_class",
		"tran_test",
		"tran_ref",
		"tran_prevref",
		"tran_firstref",
		"tran_currency",
		"tran_amount",
		"tran_cartid",
		"tran_desc",
		"tran_status",
		"tran_authcode",
		"tran_authmessage",
	),
)

# Advices name the type as a word or, in the order callback, as a number. The numbers
# follow Telr's Magento 2 plugin (1, 4, 7 complete an order; 3 refunds; 2, 6, 8 cancel).
_ADVICE_TYPES = {
	"1": "sale",
	"2": "void",
	"3": "refund",
	"4": "capture",
	"6": "release",
	"7": "sale",
	"8": "void",
}
_KNOWN_TYPES = {"sale", "auth", "refund", "capture", "void", "release"}
_STATUS_WORDS = {
	"A": "approved",
	"H": "held",
	"D": "declined",
	"E": "error",
	"C": "cancelled",
	"X": "expired",
}


def code_number(code) -> int | None:
	text = str(code or "").strip()
	return int(text) if text.isdigit() else None


def is_credential_error(code) -> bool:
	return code_number(code) in CREDENTIAL_CODES


def is_ambiguous(auth: dict) -> bool:
	"""Whether a Remote API answer leaves the outcome unknown."""
	status = auth.get("status")
	if status not in ("A", "H", "D", "E", "C", "X"):
		return True
	return status == "E" and code_number(auth.get("code")) in AMBIGUOUS_CODES


def failure_from_auth(auth: dict) -> dict:
	"""`{failure_code, decline_code, failure_reason}` of a refused Telr transaction.

	An approved transaction carries the issuer's authorisation code in `code`, so this is
	only read for a status other than A or H."""
	status = auth.get("status") or "E"
	number = code_number(auth.get("code"))
	failure_code = _FAILURE_CODES.get(number) or ("request_refused" if status == "E" else "card_declined")
	# Telr's code says where to point the decline: no retry, a bucket we word, or itself.
	if number in NO_RETRY_CODES:
		decline_code = "do_not_try_again"
	else:
		decline_code = _DECLINE_CODES.get(number) or (f"telr_{number}" if number is not None else None)
	return {
		"failure_code": failure_code,
		"decline_code": decline_code,
		"failure_reason": f"Telr {status}{str(auth.get('code') or '').strip()}: {auth.get('message') or ''}".strip(),
	}


def advice_status(advice: dict) -> str:
	return str(advice.get("tran_status") or advice.get("tran_authstatus") or "").strip().upper()[:1]


def advice_type(advice: dict) -> str:
	raw = str(advice.get("tran_type") or "").strip().lower()
	if raw in _KNOWN_TYPES:
		return raw
	return _ADVICE_TYPES.get(raw, "unknown")


def advice_event_type(advice: dict) -> str:
	"""`telr.<type>.<outcome>`, such as `telr.sale.approved`."""
	return f"telr.{advice_type(advice)}.{_STATUS_WORDS.get(advice_status(advice), 'unknown')}"
