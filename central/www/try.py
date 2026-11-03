import frappe

from central.signups.trial_offer import get_trial_signup_url
from central.users import is_invite_only

no_cache = 1
LOGIN_PATH = "/dashboard/login"


def get_context(context):
	"""The short link for the marketing site: a temporary redirect to the trial signup, so a
	change of the Default Trial Product applies at once. While Central is invite-only there is
	no public signup, so the link opens the sign-in page."""
	if is_invite_only():
		frappe.local.flags.redirect_location = LOGIN_PATH
	else:
		frappe.local.flags.redirect_location = get_trial_signup_url(frappe.request.args.to_dict())
	raise frappe.Redirect(302)
