"""Trial figures for operators: how many trials run, end, convert, what they cost, and how
invitations turn into teams. (OPS-222)

`summary` is the one call Pulse makes, with an operator's API key (`Authorization: token
<api_key>:<api_secret>`). The other routes feed the number cards of the Trials workspace.
Every route is for operators only: the figures cross every team.
"""

from __future__ import annotations

import frappe
from frappe.query_builder.functions import Count, Sum
from frappe.utils import add_days, flt, now_datetime, nowdate

from central.billing.authz import require_operator
from central.services.trial_ai_budget import TO_USD, get_budget_usd

TRIAL_STATES = ("Active", "Ended", "Converted", "Deleted")
ENDING_SOON_DAYS = 7
INVITATION_DOCTYPE = "Trial Invitation"


@frappe.whitelist(methods=["GET"])
def summary() -> dict:
	"""Every trial figure in one answer, for Pulse."""
	require_operator()
	return {
		"as_of": str(now_datetime()),
		"trials": get_trial_counts(),
		"trial_cost": get_trial_cost(),
		"free_trial_subsidy_usd": get_free_trial_subsidy(),
		"invitations": get_invitation_funnel(),
		"ai_budget_usd_per_site": get_budget_usd(),
	}


def get_trial_counts() -> dict:
	"""Trial sites by state, the active ones that end within a week, and the share that converted
	of the trials that are over."""
	site = frappe.qb.DocType("Site")
	# A cross-team count for an operator: require_operator gates every caller.
	rows = (
		frappe.qb.from_(site)
		.select(site.trial_state, Count("*").as_("sites"))
		.where(site.trial_state.isin(TRIAL_STATES))
		.groupby(site.trial_state)
	).run(as_dict=True)
	counts = {state.lower(): 0 for state in TRIAL_STATES}
	counts.update({row.trial_state.lower(): row.sites for row in rows})

	counts["ending_in_7_days"] = frappe.db.count(
		"Site",
		{
			"trial_state": "Active",
			"trial_ends_on": ["between", [nowdate(), add_days(nowdate(), ENDING_SOON_DAYS)]],
		},
	)
	over = counts["converted"] + counts["ended"] + counts["deleted"]
	counts["conversion_rate"] = flt(counts["converted"] / over * 100, 1) if over else 0.0
	return counts


def get_trial_cost() -> dict:
	"""What trial sites cost so far, by currency, and the USD and AED part in USD."""
	site = frappe.qb.DocType("Site")
	rows = (
		frappe.qb.from_(site)
		.select(site.trial_currency, Sum(site.trial_cost).as_("cost"))
		.where(site.trial_state.isin(TRIAL_STATES))
		.groupby(site.trial_currency)
	).run(as_dict=True)
	by_currency = {(row.trial_currency or "USD"): flt(row.cost, 2) for row in rows if flt(row.cost)}
	usd = sum(cost * TO_USD[currency] for currency, cost in by_currency.items() if currency in TO_USD)
	return {"by_currency": by_currency, "usd_total": flt(usd, 2)}


def get_free_trial_subsidy() -> float | None:
	"""The billing module's true cost of free trials (Cost Report invoices). None when it fails:
	the other figures still answer."""
	from central.billing.api.admin.revenue import get_free_trial_costs

	try:
		return get_free_trial_costs()["total_subsidy"]
	except Exception:
		frappe.log_error(title="Trial metrics: free trial subsidy failed")
		return None


def get_invitation_funnel() -> dict | None:
	"""Invitations by status, and how many of the accepted ones made a team whose trial
	converted. None while the site has no Trial Invitation doctype (OPS-215)."""
	if not frappe.db.exists("DocType", INVITATION_DOCTYPE):
		return None

	invitation = frappe.qb.DocType(INVITATION_DOCTYPE)
	rows = (
		frappe.qb.from_(invitation)
		.select(invitation.status, Count("*").as_("count"))
		.groupby(invitation.status)
	).run(as_dict=True)
	funnel = {"sent": sum(row.count for row in rows)}
	funnel.update({(row.status or "Sent").lower(): row.count for row in rows})

	teams = frappe.get_all(
		INVITATION_DOCTYPE, filters={"status": "Accepted", "team": ["is", "set"]}, pluck="team"
	)
	funnel["converted"] = (
		frappe.db.count("Site", {"team": ["in", teams], "trial_state": "Converted"}) if teams else 0
	)
	return funnel


# The number cards of the Trials workspace. Frappe posts the card's filters; none are used.


@frappe.whitelist()
def ending_soon_card(filters: str | dict | None = None) -> dict:
	require_operator()
	return {"value": get_trial_counts()["ending_in_7_days"], "fieldtype": "Int"}


@frappe.whitelist()
def trial_cost_card(filters: str | dict | None = None) -> dict:
	require_operator()
	return {"value": get_trial_cost()["usd_total"], "fieldtype": "Currency"}


@frappe.whitelist()
def conversion_rate_card(filters: str | dict | None = None) -> dict:
	require_operator()
	return {"value": get_trial_counts()["conversion_rate"], "fieldtype": "Percent"}


@frappe.whitelist()
def invitations_accepted_card(filters: str | dict | None = None) -> dict:
	require_operator()
	funnel = get_invitation_funnel()
	return {"value": funnel.get("accepted", 0) if funnel else 0, "fieldtype": "Int"}
