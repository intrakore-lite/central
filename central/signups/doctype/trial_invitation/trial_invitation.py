# Copyright (c) 2026, frappe and contributors
# For license information, please see license.txt

from __future__ import annotations

import hashlib
import secrets

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, get_datetime, now_datetime, validate_email_address

from central.branding import get_brand_name
from central.sso import central_url

DEFAULT_EXPIRY_DAYS = 7
ACTIVATION_PATH = "/dashboard/activate"


class TrialInvitation(Document):
	"""An operator's invitation to try Intrakore Cloud, with a one-time activation link.

	Only the SHA-256 of the link's token is stored. Accepting or revoking clears it, so a link works once."""

	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		accepted_at: DF.Datetime | None
		company: DF.Data
		email: DF.Data
		expires_on: DF.Datetime | None
		full_name: DF.Data
		last_sent_at: DF.Datetime | None
		lead_reference: DF.Data | None
		product: DF.Link | None
		sent_by: DF.Link | None
		status: DF.Literal["Sent", "Accepted", "Expired", "Revoked"]
		team: DF.Link | None
		token_hash: DF.Data | None
	# end: auto-generated types

	def before_insert(self) -> None:
		self.status = "Sent"
		self.accepted_at = None
		self.team = None
		self._issue_token()

	def validate(self) -> None:
		self.email = (self.email or "").strip().lower()
		validate_email_address(self.email, throw=True)
		self.full_name = (self.full_name or "").strip()
		self.company = (self.company or "").strip()
		if self.is_new():
			self._validate_no_live_duplicate()

	def after_insert(self) -> None:
		self.send_email()

	@property
	def is_live(self) -> bool:
		return self.status == "Sent" and not self.is_expired

	@property
	def is_expired(self) -> bool:
		return bool(self.expires_on and get_datetime(self.expires_on) <= now_datetime())

	def get_summary(self) -> dict:
		"""What the operator API and the activation page show. Never the token or its hash."""
		return {
			"name": self.name,
			"email": self.email,
			"full_name": self.full_name,
			"company": self.company,
			"product": self.product,
			"lead_reference": self.lead_reference,
			"status": "Expired" if self.status == "Sent" and self.is_expired else self.status,
			"expires_on": self.expires_on,
			"last_sent_at": self.last_sent_at,
			"accepted_at": self.accepted_at,
			"team": self.team,
			"has_account": bool(frappe.db.exists("User", {"email": self.email})),
		}

	def resend(self) -> None:
		"""Send a fresh link. The new token replaces the old one, so the earlier email stops working."""
		if self.status not in ("Sent", "Expired"):
			frappe.throw(_("Only a sent or expired invitation can be resent. Send a new invitation instead."))

		self.status = "Sent"
		self._issue_token()
		self.save()
		self.send_email()

	def revoke(self) -> bool:
		if self.status == "Revoked":
			return False
		if self.status == "Accepted":
			frappe.throw(_("This invitation was already accepted, so it cannot be revoked."))

		self.status = "Revoked"
		self.token_hash = None
		self.save()
		return True

	def accept(self, user: str) -> None:
		"""Spend the link for `user`, the invited email. The caller holds the row lock."""
		self.status = "Accepted"
		self.accepted_at = now_datetime()
		self.token_hash = None
		self.team = _first_owned_team(user)
		# The invitee is a guest or a Central User, and only an operator can write invitations.
		self.save(ignore_permissions=True)

	def send_email(self) -> None:
		token = self.flags.get("activation_token")
		if not token:
			frappe.throw(_("The activation link is only known when it is issued. Resend the invitation."))

		brand = get_brand_name()
		frappe.sendmail(
			recipients=[self.email],
			subject=_("Your {0} invitation").format(brand),
			template="trial_invitation",
			args={
				"full_name": self.full_name,
				"company": self.company,
				"activation_url": f"{central_url()}{ACTIVATION_PATH}?token={token}",
				"expires_on": frappe.format(self.expires_on, "Datetime"),
			},
			reference_doctype=self.doctype,
			reference_name=self.name,
		)

	def _issue_token(self) -> None:
		# The raw token lives only in this request, long enough to email it.
		token = secrets.token_urlsafe(32)
		self.flags.activation_token = token
		self.token_hash = hash_token(token)
		self.expires_on = add_days(now_datetime(), get_expiry_days())
		self.sent_by = frappe.session.user
		self.last_sent_at = now_datetime()

	def _validate_no_live_duplicate(self) -> None:
		if frappe.db.exists("Trial Invitation", {"email": self.email, "status": "Sent"}):
			frappe.throw(_("This email already has an open invitation. Resend it instead."))


def hash_token(token: str) -> str:
	return hashlib.sha256(token.encode()).hexdigest()


def get_expiry_days() -> int:
	"""Days an activation link stays open, from Central Settings."""
	days = cint(frappe.get_cached_value("Central Settings", "Central Settings", "trial_invitation_days"))
	return days or DEFAULT_EXPIRY_DAYS


def invite(
	email: str,
	full_name: str,
	company: str,
	product: str | None = None,
	lead_reference: str | None = None,
) -> TrialInvitation:
	"""Invite an email. An open invitation for the same email gets the new details and a new link."""
	email = (email or "").strip().lower()
	details = {
		"full_name": full_name,
		"company": company,
		"product": product or None,
		"lead_reference": lead_reference or None,
	}
	name = frappe.db.get_value("Trial Invitation", {"email": email, "status": "Sent"})
	if not name:
		return frappe.get_doc({"doctype": "Trial Invitation", "email": email, **details}).insert()

	invitation = frappe.get_doc("Trial Invitation", name)
	invitation.update(details)
	invitation.resend()
	return invitation


def has_live_invitation(email: str) -> bool:
	return bool(
		frappe.db.exists(
			"Trial Invitation",
			{"email": email, "status": "Sent", "expires_on": (">", now_datetime())},
		)
	)


def get_invitation_by_token(token: str, for_update: bool = False) -> TrialInvitation:
	name = (
		frappe.db.get_value("Trial Invitation", {"token_hash": hash_token(token)}, for_update=for_update)
		if token
		else None
	)
	if not name:
		frappe.throw(
			_(
				"This activation link is not valid or was already used. Open the link in your latest invitation email, or sign in."
			),
			frappe.DoesNotExistError,
		)

	return frappe.get_doc("Trial Invitation", name)


def accept_for_new_user(user: str) -> bool:
	"""Accept the live invitation of a user who signed up with an emailed code instead of the link."""
	name = frappe.db.get_value(
		"Trial Invitation",
		{"email": user, "status": "Sent", "expires_on": (">", now_datetime())},
		for_update=True,
	)
	if not name:
		return False

	frappe.get_doc("Trial Invitation", name).accept(user)
	return True


def link_team(user: str, team: str) -> None:
	"""Record the first team an invitee creates on their accepted invitation."""
	name = frappe.db.get_value(
		"Trial Invitation", {"email": user, "status": "Accepted", "team": ("is", "not set")}
	)
	if name:
		frappe.db.set_value("Trial Invitation", name, "team", team)


def expire_invitations() -> None:
	for name in frappe.get_all(
		"Trial Invitation",
		filters={"status": "Sent", "expires_on": ("<=", now_datetime())},
		pluck="name",
	):
		frappe.db.set_value("Trial Invitation", name, {"status": "Expired", "token_hash": None})


def on_doctype_update() -> None:
	frappe.db.add_unique("Trial Invitation", ["token_hash"])
	frappe.db.add_index("Trial Invitation", ["email", "status"])


def _first_owned_team(user: str) -> str | None:
	return frappe.db.get_value("Team", {"owner_user": user}, "name", order_by="creation asc")
