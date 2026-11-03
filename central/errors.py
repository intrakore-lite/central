from __future__ import annotations

import functools

import frappe
from frappe import _

from central.iam import is_managed_customer

# The message key the envelope rides on inside each _server_messages entry.
ENVELOPE_KEY = "action_error"


class ResourceActionError(frappe.ValidationError):
	"""A server-flow failure already shaped into a user-facing envelope."""


class AtlasConnectionError(frappe.ValidationError):
	"""A regional read or authentication/configuration check failed."""


class AtlasRejected(AtlasConnectionError):
	"""Atlas explicitly rejected a mutation before accepting it. `code` is Atlas's own
	error code, when the reply names one."""

	def __init__(self, message: str | None = None, code: str | None = None):
		super().__init__(message)
		self.code = code


# Atlas codes for "no host has room for this shape".
ATLAS_CAPACITY_CODES = frozenset({"out_of_capacity", "affinity_unsatisfied", "insufficient_capacity"})


class AtlasResourceGone(AtlasConnectionError):
	"""A correctly scoped regional resource was not found."""


class AtlasRequestUncertain(AtlasConnectionError):
	"""A remote mutation may have succeeded without a confirmed response."""


class CargoConnectionError(frappe.ValidationError):
	"""A regional Cargo health check or webhook configuration call failed."""


# code -> user-facing copy. Templates are formatted with the call's context (action,
# region, resource_id, field); a missing placeholder renders empty rather than crashing
# the error path. `message` may be overridden when Central owns customer-safe copy.
# `managed` holds the copy a customer of a managed console reads, who sees sites, not servers.
ERROR_CATALOG: dict[str, dict] = {
	"PERMISSION_DENIED": {
		"title": "You don't have access",
		"message": "Your role on this team isn't allowed to {action} servers.",
		"remediation": "Ask a team admin to grant you server access, or switch to a team where you have it.",
		"retriable": False,
		"managed": {
			"message": "Your role on this team isn't allowed to {action} sites.",
			"remediation": "Ask a team admin to grant you site access, or switch to a team where you have it.",
		},
	},
	"INPUT_REQUIRED": {
		"title": "Missing information",
		"message": "{field} is required to continue.",
		"remediation": "",
		"retriable": False,
	},
	"SERVER_NOT_FOUND": {
		"title": "Server not found",
		"message": "We couldn't find the server '{resource_id}' on this team.",
		"remediation": "It may have been terminated, or it belongs to another team. Refresh your server list and try again.",
		"retriable": False,
		"managed": {
			"title": "Site not found",
			"message": "We couldn't find the site '{resource_id}' on this team.",
			"remediation": "It may have been terminated, or it belongs to another team. Refresh your site list and try again.",
		},
	},
	"SERVER_BUSY_RESIZING": {
		"title": "Server is resizing",
		"message": "This server is resizing right now. You can {action} it as soon as the resize finishes.",
		"remediation": "",
		"retriable": True,
		"managed": {
			"title": "Site is changing plan",
			"message": "This site is changing plan right now. You can {action} it as soon as the change finishes.",
		},
	},
	"REGION_UNAVAILABLE": {
		"title": "This region is temporarily unavailable",
		"message": "We couldn't reach the selected region.",
		"remediation": "Try again in a few minutes. If the problem continues, contact support.",
		"retriable": True,
	},
	"ATLAS_REJECTED": {
		"title": "This request couldn't be completed",
		"message": "The selected region couldn't complete this request.",
		"remediation": "Review your selections and try again. If the problem continues, contact support.",
		"retriable": False,
	},
	"REGION_AT_CAPACITY": {
		"title": "No room for this size",
		"message": "The selected region has no room for this server size right now.",
		"remediation": "Choose a smaller size, or try again later.",
		"retriable": True,
		"managed": {
			"message": "The selected region has no room for this site's plan right now.",
			"remediation": "Choose a smaller plan, or try again later.",
		},
	},
	"RESOURCE_GONE": {
		"title": "This server is no longer available",
		"message": "The server may already have been removed.",
		"remediation": "Refresh your server list to see the current state.",
		"retriable": False,
		"managed": {
			"title": "This site is no longer available",
			"message": "The site may already have been removed.",
			"remediation": "Refresh your site list to see the current state.",
		},
	},
	"ACTION_FAILED": {
		"title": "The {action} didn't complete",
		"message": "Your server reported a failure while trying to {action}, and it's now in a failed state.",
		"remediation": "Review the existing server and contact support before submitting another operation.",
		"retriable": False,
		"managed": {
			"message": "Your site reported a failure while trying to {action}, and it's now in a failed state.",
			"remediation": "Contact support before you submit another operation.",
		},
	},
	"ACTION_TIMED_OUT": {
		"title": "The {action} is taking too long",
		"message": "We haven't heard back that the {action} finished. It may still complete on its own.",
		"remediation": "Refresh your server list in a few minutes. If it still looks stuck, contact support.",
		"retriable": False,
		"managed": {
			"remediation": "Refresh your site list in a few minutes. If it still looks stuck, contact support.",
		},
	},
	"CREATE_NOT_ACCEPTED": {
		"title": "The server wasn't created",
		"message": "The selected region did not accept the request. No server was created.",
		"remediation": "Try again, or select another region if the problem continues.",
		"retriable": True,
		"managed": {
			"title": "The site wasn't created",
			"message": "The selected region did not accept the request. No site was created.",
		},
	},
	"SNAPSHOT_FAILED": {
		"title": "The final snapshot didn't complete",
		"message": "The snapshot failed, so the server was not removed. The server is stopped.",
		"remediation": "Start the server again, or terminate it without a snapshot.",
		"retriable": True,
	},
	"OUTCOME_UNKNOWN": {
		"title": "We're still confirming this request",
		"message": "We couldn't confirm whether the selected region accepted it.",
		"remediation": "We'll keep checking. Don't submit the request again.",
		"retriable": False,
	},
	"REFRESH_FAILED": {
		"title": "Progress isn't available yet",
		"message": "Your request was accepted, but we couldn't load its latest status.",
		"remediation": "We'll check again automatically. Don't submit another request.",
		"retriable": False,
	},
	"FINALIZATION_FAILED": {
		"title": "Setup needs support",
		"message": "The selected region accepted the request, but setup did not finish.",
		"remediation": "Don't submit another request. Contact support with this action ID.",
		"retriable": False,
	},
	"VALIDATION_ERROR": {
		"title": "Check the request details",
		"message": "The request could not be completed with these details.",
		"remediation": "Review the information you entered. Contact support if you cannot resolve the problem.",
		"retriable": False,
	},
	"PAYMENT_METHOD_REQUIRED": {
		"title": "Add a payment method to create servers",
		"message": "Your credit does not cover this server, and your team has no payment method.",
		"remediation": "Open Billing to add your billing details and a payment method. Ask a team admin if you cannot manage billing.",
		"retriable": False,
		"managed": {
			"title": "Add a payment method to create sites",
			"message": "Your credit does not cover this site, and your team has no payment method.",
		},
	},
	"PAYMENT_OVERDUE": {
		"title": "Pay what your team owes to continue",
		"message": "Your team has an unpaid invoice that is overdue, or its account is past due or suspended.",
		"remediation": "Open Billing and pay the unpaid invoice. Ask a team admin if you cannot manage billing.",
		"retriable": False,
	},
	"TRIAL_IN_PROGRESS": {
		"title": "You already have a free trial",
		"message": "Your {product} trial at {address} is still open.",
		"remediation": "Use that site, or delete it to start a new trial.",
		"retriable": False,
	},
	"TRUST_TIER_LIMIT": {
		"title": "Your trust tier limit is reached",
		"message": "Your trust tier allows {limit} servers, and your team already has {count}.",
		"remediation": "Terminate a server you no longer need, or contact support to review your trust tier.",
		"retriable": False,
		"managed": {
			"message": "Your trust tier allows {limit} sites, and your team already has {count}.",
			"remediation": "Terminate a site you no longer need, or contact support to review your trust tier.",
		},
	},
	"MAILBOX_POOL_EMPTY": {
		"title": "The server wasn't created",
		"message": "This region has no mailbox ready for a new server. No server was created.",
		"remediation": "Try again in a few minutes.",
		"retriable": True,
		"managed": {
			"title": "The site wasn't created",
			"message": "This region has no mailbox ready for a new site. No site was created.",
		},
	},
	"UNEXPECTED": {
		"title": "We couldn't complete that",
		"message": "Something went wrong while we were processing your request.",
		"remediation": "Check its status before trying again. If the result is unclear, contact support.",
		"retriable": False,
	},
}


class _SafeContext(dict):
	"""format_map source that renders a missing placeholder as empty, so building an
	error message can never itself raise."""

	def __missing__(self, key: str) -> str:
		return ""


def build_envelope(
	code: str,
	*,
	message: str | None = None,
	remediation: str | None = None,
	managed: bool | None = None,
	**context,
) -> dict:
	"""Shape one catalog entry into an envelope, filling templates from `context`.
	`message`/`remediation` override the catalog copy when the caller has better words
	(e.g. the region's own error sentence). `managed` picks the managed customer copy; it
	defaults to the session user, so a background job that stores the envelope passes it."""
	entry = ERROR_CATALOG.get(code, ERROR_CATALOG["UNEXPECTED"])
	if managed is None:
		managed = is_managed_customer()
	if entry.get("managed") and managed:
		entry = {**entry, **entry["managed"]}
	source = _SafeContext(context)

	return {
		"code": code if code in ERROR_CATALOG else "UNEXPECTED",
		"title": _(entry["title"]).format_map(source),
		"message": message if message is not None else _(entry["message"]).format_map(source),
		"remediation": remediation if remediation is not None else _(entry["remediation"]).format_map(source),
		"retriable": entry["retriable"],
	}


def throw_action_error(code: str, *, exc: type[Exception] = ResourceActionError, **context) -> None:
	"""Raise a known server-flow failure as a clean, structured error. Pass `exc` to keep
	the right HTTP status (e.g. frappe.PermissionError for 403); pass `message`/`remediation`
	in `context` to override the catalog copy."""
	envelope = build_envelope(code, **context)
	_carry(envelope)

	error = exc(envelope["message"])
	error.envelope = envelope
	raise error


def to_error_response(exc: Exception, *, managed: bool | None = None) -> dict:
	"""Shape an already-raised exception into a customer-safe envelope. `managed` is passed
	on to `build_envelope`."""
	if getattr(exc, "envelope", None):
		return exc.envelope

	envelope = functools.partial(build_envelope, managed=managed)

	if isinstance(exc, AtlasRequestUncertain):
		return envelope("OUTCOME_UNKNOWN")
	if isinstance(exc, AtlasResourceGone):
		return envelope("RESOURCE_GONE")
	if isinstance(exc, AtlasRejected):
		return envelope("REGION_AT_CAPACITY" if exc.code in ATLAS_CAPACITY_CODES else "ATLAS_REJECTED")
	if isinstance(exc, AtlasConnectionError):
		return envelope("REGION_UNAVAILABLE")

	if isinstance(exc, frappe.PermissionError):
		return envelope("PERMISSION_DENIED", message=str(exc) or None)

	if isinstance(exc, frappe.DoesNotExistError):
		return envelope("SERVER_NOT_FOUND", message=str(exc) or None)

	if isinstance(exc, frappe.ValidationError):
		return envelope("VALIDATION_ERROR", message=str(exc) or None)

	return envelope("UNEXPECTED")


def handle_resource_operation(func):
	"""Return customer-safe errors from a resource endpoint: a catalog envelope with a stable
	`code` the console switches on, never a bare exception or a traceback."""

	@functools.wraps(func)
	def wrapper(*args, **kwargs):
		try:
			return func(*args, **kwargs)
		except Exception as exc:
			if getattr(exc, "envelope", None):
				raise

			envelope = to_error_response(exc)
			# The user sees only generic copy, so keep the traceback for the operator.
			if envelope["code"] == "UNEXPECTED":
				# No frame locals: a remote call's frames hold its bearer token.
				frappe.log_error(title="Unexpected server-action error", message=frappe.get_traceback())
			_reraise_with_envelope(exc, envelope)

	return wrapper


def _reraise_with_envelope(exc: Exception, envelope: dict) -> None:
	"""Attach the envelope to what the client receives. A frappe exception already logged
	its message, so enrich that entry and keep the original type (and status); anything
	else gets a fresh message and is re-raised as a ResourceActionError."""
	if isinstance(exc, (frappe.ValidationError, frappe.PermissionError)) and frappe.message_log:
		frappe.message_log[-1]["message"] = _display_message(envelope)
		frappe.message_log[-1][ENVELOPE_KEY] = envelope
		exc.envelope = envelope
		raise exc

	_carry(envelope)

	error = ResourceActionError(envelope["message"])
	error.envelope = envelope
	raise error from exc


def _display_message(envelope: dict) -> str:
	"""What the user reads: what happened, then how to resolve it. frappe-ui surfaces only
	this line and drops the structured envelope, so the remediation has to ride here too."""
	remediation = envelope.get("remediation")
	return f"{envelope['message']} {remediation}".strip() if remediation else envelope["message"]


def _carry(envelope: dict) -> None:
	"""Append the message-log entry that carries this envelope to the client."""
	frappe.message_log.append(
		frappe._dict(
			message=_display_message(envelope),
			title=envelope["title"],
			indicator="red",
			raise_exception=1,
			**{ENVELOPE_KEY: envelope},
		)
	)
