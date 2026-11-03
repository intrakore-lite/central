# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt

from datetime import datetime, time, timedelta

import frappe
from frappe import _
from frappe.utils import flt, get_last_day, getdate, nowdate

from central.billing.catalog.seats import SeatQuote, get_prorated_amount, get_seat_quote
from central.billing.platform.records import save_billing_record
from central.billing.states import transition

PREPAYMENT = "Prepayment"


def get_first_period(quote: SeatQuote, start_date) -> dict:
	"""The first payment of a site billed per seat: its seats from `start_date` to the end of
	that month, by the day as the billing run counts them, plus tax."""
	from central.billing.revenue.tax import resolve_tax

	start_date = getdate(start_date)
	period_end = get_last_day(start_date)
	net = get_prorated_amount(0, quote.monthly_rate, start_date)
	tax = resolve_tax(quote.team, net)
	return frappe._dict(
		period_start=start_date,
		period_end=period_end,
		days=(period_end - start_date).days + 1,
		net=net,
		tax_type=tax["output_tax_type"],
		tax_rate=flt(tax["output_tax_rate"]),
		tax=flt(tax["output_tax_amount"]),
		total=flt(net + flt(tax["output_tax_amount"]), 2),
		currency=quote.currency,
	)


def charge_first_payment(site: str) -> dict:
	"""Background job: charge the first period of a converted trial billed per seat to the card on
	file, now. The payment becomes wallet credit, so the first arrears invoice settles from it and
	nothing is billed twice. A failed charge is dunned like any unpaid invoice. Safe to repeat."""
	from central.billing.payments.collection import collect_invoice

	site_doc = frappe.db.get_value("Site", site, ["team", "trial_state"], as_dict=True)
	quote = get_seat_quote(site_doc.team) if site_doc and site_doc.trial_state == "Converted" else None
	if not quote:
		return {"charged": False, "reason": "not_billed_per_seat"}

	invoice = get_open_prepayment(quote.team) or create_prepayment(quote, nowdate()).name
	return collect_invoice(invoice)


def get_open_prepayment(team: str) -> str | None:
	return frappe.db.get_value(
		"Invoice", {"team": team, "invoice_type": PREPAYMENT, "status": ["in", ("Draft", "Open", "Overdue")]}
	)


def create_prepayment(quote: SeatQuote, start_date) -> frappe._dict:
	"""An Open Prepayment invoice for the first period. It is not a sale: the money it collects is
	an advance, booked as wallet credit with its tax kept for the invoices that use it."""
	period = get_first_period(quote, start_date)
	doc = frappe.get_doc(
		{
			"doctype": "Invoice",
			"team": quote.team,
			"invoice_type": PREPAYMENT,
			"status": "Draft",
			"period_start": period.period_start,
			"period_end": period.period_end,
			"currency": period.currency,
			"items": [
				{
					"subscription_resource": quote.server,
					"plan": _("{0} seats to {1}").format(
						quote.seats, frappe.utils.formatdate(period.period_end)
					),
					"resource_type": "Users",
					"unit": "seat",
					"quantity": quote.billed_seats,
					"rate": quote.seat_price,
					"days": period.days,
					"period_from": datetime.combine(period.period_start, time.min),
					"period_to": datetime.combine(period.period_end + timedelta(days=1), time.min),
					"amount": period.net,
				}
			],
			"subtotal": period.net,
			"output_tax_type": period.tax_type,
			"output_tax_rate": period.tax_rate,
			"output_tax_amount": period.tax,
			"total": period.total,
			"expected_collection": period.total,
			"due_date": period.period_start,
			"dunning_starts_on": period.period_start,
			"erpnext_sync_status": "Not Required",
		}
	)
	save_billing_record(doc)
	transition(doc, "Open", reason="first payment of a converted trial", actor="scheduler")
	save_billing_record(doc)
	return doc


def book_as_credit(inv, payment_id: str | None, adapter_key: str | None) -> None:
	"""Turn a paid Prepayment invoice into wallet credit: its subtotal is the credit and its tax
	is kept on the entry, as for a top-up. Booked once per payment."""
	from central.billing.revenue import credits

	credits.purchase(
		inv.team,
		inv.amount_paid,
		inv.currency,
		reference_name=inv.name,
		note=f"First payment {inv.name}",
		gateway_payment_id=payment_id or inv.name,
		gateway=adapter_key,
		credit=inv.subtotal,
	)


def cancel_unpaid_prepayments(team: str, period_end) -> list[str]:
	"""Cancel the team's unpaid Prepayment invoices that an arrears invoice to `period_end` now
	bills. A charge still in flight keeps its invoice: if it lands, it goes to the wallet."""
	from central.billing.payments.charges import in_flight_attempt
	from central.billing.revenue.invoicing.lifecycle import cancel_invoice

	cancelled = []
	for name in frappe.get_all(
		"Invoice",
		filters={
			"team": team,
			"invoice_type": PREPAYMENT,
			"status": ["in", ("Draft", "Open", "Overdue")],
			"period_end": ["<=", period_end],
		},
		pluck="name",
	):
		if not in_flight_attempt(name):
			cancelled.append(cancel_invoice(name, reason="The monthly invoice bills this period."))
	return cancelled
