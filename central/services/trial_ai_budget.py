"""The free AI a trial or managed site gets each month, and the site config that carries it.

Intrakore sites meter their own AI in AI Usage Settings (intrakore_ai). Central writes the budget
into the site config at creation, and the site refuses new AI calls once it is used up. The pool's
Grove trial keys are minted with the same cap, so both stop at the same figure. (OPS-222)

The budget comes from Central Settings' Trial AI Cap, in its Seat Price Currency, when both are
set (OPS-216). Otherwise from AI Settings' Trial Key Cap, in USD.
"""

from __future__ import annotations

import math

import frappe
from frappe.utils import flt

from central import iam

# The UAE dirham is pegged to the US dollar at this rate.
AED_PER_USD = 3.6725
TO_USD = {"USD": 1.0, "AED": 1 / AED_PER_USD}

# The site config keys intrakore_ai reads (intrakore_ai/ai/usage.py).
BUDGET_KEY = "intrakore_ai_monthly_budget_usd"
ACTION_KEY = "intrakore_ai_over_budget_action"
STOP = "stop"


def get_budget_usd() -> float:
	"""The free AI budget of one site for a month, in USD. 0 when none is set."""
	settings = frappe.get_cached_doc("Central Settings")
	# Read with .get: the field arrives with OPS-216 and a site without it falls back.
	cap = flt(settings.get("trial_ai_cap"))
	if cap > 0:
		currency = settings.get("seat_price_currency") or "AED"
		if currency in TO_USD:
			return flt(cap * TO_USD[currency], 2)
		frappe.log_error(
			title="Trial AI cap ignored",
			message=f"Trial AI Cap is in {currency}; only USD and AED convert. Trial Key Cap applies.",
		)

	return flt(frappe.db.get_single_value("AI Settings", "trial_key_cap"), 2)


def get_trial_key_cap() -> int:
	"""The cap a new Grove trial key is minted with: the budget in whole USD, rounded up, so the
	site's own refusal comes first and Grove's cap is the backstop."""
	return math.ceil(get_budget_usd())


def gets_free_ai(action) -> bool:
	"""Whether a creation's site gets the free AI budget.

	1. A free-trial creation does.
	2. A creation for a team of a managed console does (Managed SaaS mode, team not an operator's).
	3. Any other creation does not: the team brings its own AI.
	"""
	return bool(action.is_free_trial) or iam.is_managed_team(action.team)


def get_site_config(action) -> dict:
	"""The common_site_config keys that cap a creation's AI, or none when it gets no free AI."""
	if not gets_free_ai(action):
		return {}

	budget = get_budget_usd()
	if budget <= 0:
		return {}

	return {BUDGET_KEY: budget, ACTION_KEY: STOP}
