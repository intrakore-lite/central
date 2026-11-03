from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime, set_request
from frappe.website.serve import get_response

from central.api import trial_invitations
from central.api.auth import activate, get_activation, send_code, verify_code
from central.identity.email_code import EmailCode
from central.signups.doctype.trial_invitation.trial_invitation import hash_token
from central.tests.test_team_management import create_user
from central.tests.utils import central_limit
from central.users import InviteOnlyError

SENDMAIL = "central.signups.doctype.trial_invitation.trial_invitation.frappe.sendmail"
CODE_MAIL = "central.identity.email_code.frappe.sendmail"


class TestTrialInvitation(IntegrationTestCase):
	"""Intrakore Cloud is invite-only: a new email needs a live Trial Invitation, and its link works once."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.email = f"invitee.{frappe.generate_hash(length=8)}@example.test"
		self.addCleanup(EmailCode(self.email).discard)
		self.enterContext(central_limit("invite_only", 1))

	def tearDown(self):
		frappe.set_user("Administrator")

	def invite(self, email: str | None = None) -> tuple[dict, str]:
		"""Invite as an operator and return the summary and the emailed token."""
		with patch(SENDMAIL) as sendmail:
			summary = trial_invitations.invite(email or self.email, "Invited Person", "Acme Contracting LLC")
		return summary, self.token_from(sendmail)

	def token_from(self, sendmail) -> str:
		url = sendmail.call_args.kwargs["args"]["activation_url"]
		self.assertTrue(urlsplit(url).path.endswith("/dashboard/activate"))
		return parse_qs(urlsplit(url).query)["token"][0]

	def activate_as_guest(self, token: str) -> dict:
		frappe.set_user("Guest")
		with patch("frappe.local.login_manager", create=True) as login_manager:
			login_manager.login_as.side_effect = frappe.set_user
			return activate(token)

	def test_the_gate_refuses_an_unknown_email_with_the_invite_only_message(self):
		frappe.set_user("Guest")
		with patch(CODE_MAIL) as code_mail, self.assertRaises(InviteOnlyError) as refused:
			send_code(self.email, "Stranger")

		self.assertEqual(refused.exception.envelope["code"], "INVITE_ONLY")
		self.assertEqual(
			frappe.message_log[-1]["message"],
			"Intrakore Cloud is invite-only. Ask your Intrakore contact for an invitation.",
		)
		code_mail.assert_not_called()

	def test_an_existing_user_keeps_signing_in(self):
		create_user(self.email)
		frappe.set_user("Guest")

		with patch(CODE_MAIL) as code_mail:
			send_code(self.email)

		self.assertIn("sign-in code", code_mail.call_args.kwargs["subject"])

	def test_an_invited_email_can_sign_up_with_a_code(self):
		self.invite()
		frappe.set_user("Guest")

		with patch(CODE_MAIL):
			send_code(self.email, "Invited Person")
		with patch("frappe.local.login_manager", create=True) as login_manager:
			login_manager.login_as.side_effect = frappe.set_user
			result = verify_code(self.email, EmailCode(self.email).pending["code"])

		self.assertEqual(result["next"], "/dashboard/onboarding/profile")
		self.assertEqual(trial_invitations_status(self.email)["status"], "Accepted")

	def test_the_link_creates_the_account_signs_in_and_works_once(self):
		summary, token = self.invite()
		frappe.set_user("Guest")
		self.assertEqual(get_activation(token)["email"], self.email)

		result = self.activate_as_guest(token)

		self.assertEqual(result["user"], self.email)
		self.assertEqual(result["next"], "/dashboard/onboarding/profile")
		self.assertEqual(frappe.session.user, self.email)
		self.assertEqual(frappe.db.get_value("User", self.email, "full_name"), "Invited Person")
		invitation = frappe.get_doc("Trial Invitation", summary["name"])
		self.assertEqual(invitation.status, "Accepted")
		self.assertIsNotNone(invitation.accepted_at)
		self.assertIsNone(invitation.token_hash)

		with self.assertRaises(frappe.DoesNotExistError):
			self.activate_as_guest(token)

	def test_only_the_hash_of_the_token_is_stored(self):
		summary, token = self.invite()

		stored = frappe.db.get_value("Trial Invitation", summary["name"], "token_hash")
		self.assertEqual(stored, hash_token(token))
		self.assertNotIn(token, frappe.as_json(frappe.get_doc("Trial Invitation", summary["name"]).as_dict()))

	def test_an_expired_link_is_refused_and_no_longer_opens_the_gate(self):
		summary, token = self.invite()
		frappe.db.set_value(
			"Trial Invitation", summary["name"], "expires_on", add_to_date(now_datetime(), hours=-1)
		)

		with self.assertRaisesRegex(frappe.ValidationError, "expired"):
			self.activate_as_guest(token)
		with patch(CODE_MAIL), self.assertRaises(InviteOnlyError):
			send_code(self.email, "Late Person")
		self.assertFalse(frappe.db.exists("User", self.email))

	def test_a_revoked_invitation_closes_the_link_and_the_gate(self):
		summary, token = self.invite()

		trial_invitations.revoke(summary["name"])

		with self.assertRaises(frappe.DoesNotExistError):
			self.activate_as_guest(token)
		with patch(CODE_MAIL), self.assertRaises(InviteOnlyError):
			send_code(self.email, "Revoked Person")

	def test_resend_and_a_second_invite_replace_the_earlier_link(self):
		summary, first = self.invite()
		with patch(SENDMAIL) as sendmail:
			trial_invitations.resend(summary["name"])
		second = self.token_from(sendmail)
		again, third = self.invite()

		self.assertEqual(again["name"], summary["name"])
		self.assertEqual(frappe.db.count("Trial Invitation", {"email": self.email}), 1)
		for spent in (first, second):
			with self.assertRaises(frappe.DoesNotExistError):
				self.activate_as_guest(spent)
		self.assertEqual(self.activate_as_guest(third)["user"], self.email)

	def test_an_existing_account_signs_in_before_the_link_is_spent(self):
		create_user(self.email)
		summary, token = self.invite()

		self.assertEqual(self.activate_as_guest(token), {"needs_sign_in": True, "email": self.email})
		self.assertEqual(frappe.session.user, "Guest")
		self.assertEqual(frappe.db.get_value("Trial Invitation", summary["name"], "status"), "Sent")

		frappe.set_user(self.email)
		self.assertEqual(activate(token)["user"], self.email)
		self.assertEqual(frappe.db.get_value("Trial Invitation", summary["name"], "status"), "Accepted")

	def test_a_link_opened_in_another_session_is_refused(self):
		_summary, token = self.invite()
		other = create_user(f"other.{frappe.generate_hash(length=8)}@example.test")
		frappe.set_user(other)

		with self.assertRaises(frappe.PermissionError):
			activate(token)

	def test_only_an_operator_manages_invitations(self):
		customer = create_user(f"customer.{frappe.generate_hash(length=8)}@example.test")
		frappe.set_user(customer)

		with patch(SENDMAIL), self.assertRaises(frappe.PermissionError):
			trial_invitations.invite(self.email, "Invited Person", "Acme Contracting LLC")
		with self.assertRaises(frappe.PermissionError):
			trial_invitations.list()

	def test_the_try_link_opens_the_sign_in_page(self):
		set_request(method="GET", path="/try?utm_source=ads")
		response = get_response()

		self.assertEqual(response.status_code, 302)
		self.assertEqual(urlsplit(response.headers["Location"]).path, "/dashboard/login")


def trial_invitations_status(email: str) -> dict:
	frappe.set_user("Administrator")
	return trial_invitations.status(email=email)
