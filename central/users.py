from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import frappe
from frappe import _
from frappe.utils import cint, escape_html, random_string, today
from frappe.utils.telemetry import capture

from central.branding import get_brand_name
from central.errors import throw_action_error
from central.geo import warm_country_cache
from central.identity.email_code import EmailCode
from central.signups.doctype.trial_invitation import trial_invitation

if TYPE_CHECKING:
	from central.signups.doctype.product.product import Product

CENTRAL_USER_ROLE = "Central User"
# Where a newly activated invitee starts: the invited onboarding.
INVITED_ONBOARDING_PATH = "/dashboard/onboarding/profile"


class InviteOnlyError(frappe.ValidationError):
	"""A new email has no invitation while Intrakore Cloud is invite-only."""


def send_sign_in_code(email: str, full_name: str | None = None, product: str | None = None) -> None:
	"""Email a code to an address. A new address gets an account when the code is verified.

	While Central is invite-only, a new address needs a live invitation. A disabled account gets
	a notice instead of a code, so the caller cannot tell it apart. `product` labels the signup
	funnel event, and its branding replaces the platform's."""
	from central.signups.doctype.product.product import get_email_product

	user = _find_user(email)
	if not user:
		require_invitation(email)
	if user and not user.enabled:
		EmailCode(email).hold()
		_send_disabled_notice(email)
		return

	subject, heading, brand = get_code_email(get_email_product(product), is_new_user=not user)
	EmailCode(email).send(subject, heading, None if user else full_name, brand)
	if not user:
		capture("signup_code_sent", "central", user=email, properties={"product": product})
		warm_country_cache()


def get_code_email(
	product: Product | None, is_new_user: bool
) -> tuple[Callable[[str], str], str, dict | None]:
	"""The subject builder, heading and header branding of a code email. A product with its own
	branding names itself instead of the platform."""
	brand = product.get_email_brand() if product else None
	name = product.title if brand else get_brand_name()
	if is_new_user:
		return (
			lambda code: _("{0} is your {1} signup code").format(code, name),
			_("Create your {0} account").format(escape_html(name)),
			brand,
		)

	return (
		lambda code: _("{0} is your {1} sign-in code").format(code, name),
		_("Sign in to {0}").format(escape_html(name)),
		brand,
	)


def sign_in_with_code(
	email: str, code: str, full_name: str | None = None, product: str | None = None
) -> dict:
	"""Sign in with a verified code, creating the account for a new address.

	A new address needs a name. Without one the code stays valid, so the person can add it."""
	email_code = EmailCode(email)
	with email_code.lock():
		pending = email_code.verify(code)
		user = _find_user(email)
		if user and not user.enabled:
			_throw_disabled()

		full_name = full_name or pending.get("full_name")
		if not user and not full_name:
			return {"needs_name": True}

		name = user.name if user else create_user(email, full_name).name
		email_code.discard()

	frappe.local.login_manager.login_as(name)
	if not user:
		capture("signup_verified", "central", user=name, properties={"product": product})
		is_trial_invitee = trial_invitation.accept_for_new_user(name)
		for invitation in get_pending_invitations(name):
			frappe.get_doc("Team Invitation", invitation).accept()
		if is_trial_invitee:
			return {"user": name, "next": INVITED_ONBOARDING_PATH}

	return {"user": name}


def activate_trial_invitation(token: str) -> dict:
	"""Spend an activation link. It proves the invited mailbox the same way an emailed code does,
	so a new invitee gets an account and a session without a second code.

	1. The link must be live: sent, not expired, not used. Using it clears its hash.
	2. An email that already has an account must sign in first, so a link cannot open an
	   existing account.
	3. A session for another email is refused."""
	invitation = trial_invitation.get_invitation_by_token(token, for_update=True)
	if not invitation.is_live:
		frappe.throw(
			_("This activation link has expired. Ask your Intrakore contact to send it again."),
			frappe.ValidationError,
		)

	session_user = frappe.session.user
	if session_user not in ("Guest", invitation.email):
		frappe.throw(
			_("This link is for {0}. Sign out, then open the link again.").format(invitation.email),
			frappe.PermissionError,
		)

	user = _find_user(invitation.email)
	if user and not user.enabled:
		_throw_disabled()
	if user and session_user != user.name:
		return {"needs_sign_in": True, "email": invitation.email}

	name = user.name if user else create_user(invitation.email, invitation.full_name).name
	invitation.accept(name)
	if not user:
		frappe.local.login_manager.login_as(name)
		capture("signup_verified", "central", user=name, properties={"product": invitation.product})

	return {"user": name, "next": INVITED_ONBOARDING_PATH}


def require_invitation(email: str) -> None:
	"""Refuse a new email that has no live invitation while Central is invite-only.

	A live Trial Invitation or a pending Team Invitation counts as an invitation."""
	if not is_invite_only():
		return
	if trial_invitation.has_live_invitation(email) or get_pending_invitations(email):
		return

	throw_action_error("INVITE_ONLY", exc=InviteOnlyError, brand=get_brand_name(), managed=False)


def is_invite_only() -> bool:
	return bool(cint(frappe.get_cached_value("Central Settings", "Central Settings", "invite_only")))


def create_user(email: str, full_name: str):
	"""Create a Website User whose email is already verified."""
	require_invitation(email)
	_enforce_signup_limit()
	roles = {CENTRAL_USER_ROLE, frappe.get_single_value("Portal Settings", "default_role")}
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": escape_html(full_name),
			"enabled": 1,
			"new_password": random_string(10),
			"user_type": "Website User",
			"roles": [{"role": role} for role in roles if role],
		}
	)
	user.flags.ignore_password_policy = True
	user.flags.no_welcome_mail = True
	# A guest creates the account, and a guest has no User create permission.
	user.insert(ignore_permissions=True)

	return user


def grant_central_user_role(doc, method: str | None = None) -> None:
	"""Give a newly created user the Central User role.

	A new user gets no team here. An invited user joins the invited team when the
	signup accepts the invitation. Anyone else creates a team in console onboarding."""
	if _should_skip_role_grant(doc):
		return

	if CENTRAL_USER_ROLE not in {row.role for row in doc.roles}:
		doc.add_roles(CENTRAL_USER_ROLE)


def validate_user_image(doc, method: str | None = None) -> None:
	"""A profile photo must be a file uploaded to that user's photo field, not any URL."""
	if not doc.user_image or not doc.has_value_changed("user_image"):
		return

	is_uploaded = frappe.db.exists(
		"File",
		{
			"file_url": doc.user_image,
			"attached_to_doctype": "User",
			"attached_to_name": doc.name,
			"attached_to_field": "user_image",
		},
	)
	if not is_uploaded:
		frappe.throw(_("Upload the image again."))


def get_pending_invitations(user: str) -> list[str]:
	return frappe.get_all(
		"Team Invitation",
		filters={"email": user, "status": "Pending", "expires_on": [">=", today()]},
		pluck="name",
		order_by="creation asc",
	)


def _find_user(email: str):
	return frappe.db.get_value("User", {"email": email}, ["name", "enabled"], as_dict=True)


def _send_disabled_notice(email: str) -> None:
	frappe.sendmail(
		recipients=[email],
		subject=_("Your {0} account is disabled").format(get_brand_name()),
		template="notification",
		args={
			"title": _("Your account is disabled"),
			"body": _(
				"Someone tried to sign in to {0} with this email. Contact support to restore access."
			).format(get_brand_name()),
		},
	)


def _throw_disabled() -> None:
	frappe.throw(_("This account is disabled. Contact support to restore access."), frappe.ValidationError)


def _enforce_signup_limit() -> None:
	limit = cint(frappe.get_system_settings("max_signups_allowed_per_hour") or 300)
	if frappe.db.get_creation_count("User", 60) >= limit:
		frappe.throw(
			_("Too many users signed up recently. Please try again in an hour."),
			frappe.TooManyRequestsError,
		)


def _should_skip_role_grant(doc) -> bool:
	if not doc.enabled:
		return True
	if frappe.flags.in_install or frappe.flags.in_migrate:
		return True
	if not frappe.db.exists("Role", CENTRAL_USER_ROLE):
		return True

	return False
