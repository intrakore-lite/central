import frappe

from central.signups.trial_offer import get_trial_signup_url

no_cache = 1


def get_context(context):
	"""The short link for the marketing site: a temporary redirect to the trial signup, so a
	change of the Default Trial Product applies at once."""
	frappe.local.flags.redirect_location = get_trial_signup_url(frappe.request.args.to_dict())
	raise frappe.Redirect(302)
