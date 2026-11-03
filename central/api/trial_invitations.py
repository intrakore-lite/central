import builtins

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint

from central.iam import user_has_operator_bypass
from central.signups.doctype.trial_invitation import trial_invitation

# Each send is an email to any address, so the operator surface is capped per IP.
SENDS_PER_HOUR = 120
MAX_PAGE_LENGTH = 500


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=SENDS_PER_HOUR, seconds=60 * 60, methods="POST")
def invite(
	email: str,
	full_name: str,
	company: str,
	product: str | None = None,
	lead_reference: str | None = None,
) -> dict:
	"""Invite an email to Intrakore Cloud. Inviting an email again replaces its open link."""
	_require_operator()
	return trial_invitation.invite(email, full_name, company, product, lead_reference).get_summary()


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=SENDS_PER_HOUR, seconds=60 * 60, methods="POST")
def resend(name: str) -> dict:
	"""Email a new activation link. The earlier link stops working."""
	_require_operator()
	invitation = frappe.get_doc("Trial Invitation", name)
	invitation.resend()
	return invitation.get_summary()


@frappe.whitelist(methods=["POST"])
def revoke(name: str) -> dict:
	"""Withdraw an invitation. Its link stops working at once."""
	_require_operator()
	invitation = frappe.get_doc("Trial Invitation", name)
	invitation.revoke()
	return invitation.get_summary()


@frappe.whitelist(methods=["GET"])
def status(email: str | None = None, name: str | None = None) -> dict | None:
	"""The newest invitation for an email, or one invitation by name. None when the email has none."""
	_require_operator()
	if not (email or name):
		frappe.throw(_("Give an email or an invitation name."))

	if not name:
		name = frappe.db.get_value(
			"Trial Invitation", {"email": email.strip().lower()}, "name", order_by="creation desc"
		)
	return frappe.get_doc("Trial Invitation", name).get_summary() if name else None


@frappe.whitelist(methods=["GET"])
def list(
	status: str | None = None,
	email: str | None = None,
	lead_reference: str | None = None,
	start: int = 0,
	page_length: int = 50,
) -> builtins.list[dict]:
	"""Invitations, newest first, filtered by status, email or lead."""
	_require_operator()
	filters = {
		key: value
		for key, value in {
			"status": status,
			"email": email.strip().lower() if email else None,
			"lead_reference": lead_reference,
		}.items()
		if value
	}
	return frappe.get_list(
		"Trial Invitation",
		filters=filters,
		fields=[
			"name",
			"email",
			"full_name",
			"company",
			"product",
			"lead_reference",
			"status",
			"expires_on",
			"last_sent_at",
			"accepted_at",
			"team",
		],
		order_by="creation desc",
		start=cint(start),
		page_length=min(cint(page_length) or 50, MAX_PAGE_LENGTH),
	)


def _require_operator() -> None:
	if not user_has_operator_bypass():
		frappe.throw(_("Only an Intrakore operator can manage trial invitations."), frappe.PermissionError)
