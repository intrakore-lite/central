# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt

import frappe

from central.billing import authz
from central.billing.api.dashboard._shared import _resolve_team
from central.billing.catalog import seats


@frappe.whitelist()
def get_seats(team: str | None = None, seat_count: int | None = None) -> dict:
	"""The Seats card: the team's seats and their monthly price. With `seat_count`, the price of
	that many seats and what the change adds to this month's bill."""
	team = _resolve_team(team)
	return seats.get_seat_summary(team, frappe.utils.cint(seat_count) or None)


@frappe.whitelist(methods=["POST"])
def change_seats(seat_count: int, team: str | None = None) -> dict:
	"""Set the team's seats. A paid site bills the change by the day from today."""
	team = _resolve_team(team, authz.MANAGE)
	return seats.change_seats(team, seat_count, changed_by=frappe.session.user)


@frappe.whitelist(methods=["POST"])
def set_subscription_cancelled(cancelled: bool, team: str | None = None) -> dict:
	"""Cancel the seat subscription at the end of the trial or of this month, or keep it."""
	team = _resolve_team(team, authz.MANAGE)
	return seats.set_cancellation(team, frappe.utils.sbool(cancelled))
