# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt
"""What the customer picks, on which surface, and which rail it lands on (ADR 0023).

Two rules run this module.

**Stripe takes everything it can.** We are a Stripe India merchant, and Razorpay is
consulted only where that account cannot serve the instrument or the network at
all: it carries no UPI, Stripe has no netbanking product anywhere, and Stripe
registers India card mandates on Visa and Mastercard only. So the split is
mechanical, and a Stripe product change moves a rail without re-opening anything.

**Recharge is not the mandate surface.** Topping up a wallet happens once with the
customer present and no ceiling. A mandate debits later with nobody present, under
the ₹15,000 rule. They offer different instruments, because different instruments
can be saved — netbanking pays once and saves nothing, so it belongs to one surface
and not the other.

We never detect the card network. Stripe Elements iframes the PAN, so the digits
never reach the server. Instead each surface says which networks its rail accepts,
and the customer's own choice is the signal. Once a Payment Method exists its own
`gateway` settles it for life; nothing here is consulted at charge time.
"""

import frappe

RECHARGE = "recharge"
MANDATE = "mandate"

CARD = "Card"
RUPAY_CARD = "RuPay Card"
UPI = "UPI"
UPI_AUTOPAY = "UPI Autopay"
NETBANKING = "Netbanking"

# `currencies = None` means every currency the adapter settles. A tile is never
# labelled "Other cards": a customer holding an unusual Visa would read that as
# theirs and land on a rail that cannot take it, so every tile names its networks.
CATALOGUE = (
	{
		"surface": RECHARGE,
		"instrument": CARD,
		"label": "Card",
		"description": "Visa, Mastercard or Amex",
		"adapter": "Stripe",
		"method_type": None,
		"currencies": None,
		"fallback_reason": None,
	},
	{
		"surface": RECHARGE,
		"instrument": RUPAY_CARD,
		"label": "RuPay or Diners card",
		"description": "These run on a different rail from other cards",
		"adapter": "Razorpay",
		"method_type": None,
		"currencies": ("INR",),
		"fallback_reason": None,
	},
	{
		"surface": RECHARGE,
		"instrument": UPI,
		"label": "UPI",
		"description": "Pay from your bank account",
		"adapter": "Razorpay",
		"method_type": None,
		"currencies": ("INR",),
		"fallback_reason": None,
	},
	{
		"surface": RECHARGE,
		"instrument": NETBANKING,
		"label": "Netbanking",
		"description": "Pay through your bank's own site",
		"adapter": "Razorpay",
		"method_type": None,
		"currencies": ("INR",),
		"fallback_reason": None,
	},
	{
		"surface": MANDATE,
		"instrument": CARD,
		"label": "Card",
		"description": "Visa or Mastercard, charged automatically each month",
		"adapter": "Stripe",
		"method_type": "Card",
		"currencies": None,
		"fallback_reason": None,
	},
	{
		"surface": MANDATE,
		"instrument": RUPAY_CARD,
		"label": "RuPay card",
		"description": "RuPay is saved on a different rail from other cards",
		"adapter": "Razorpay",
		"method_type": "Card",
		"currencies": ("INR",),
		"fallback_reason": "Network Unsupported",
	},
	{
		"surface": MANDATE,
		"instrument": UPI_AUTOPAY,
		"label": "UPI",
		"description": "Authorise a UPI mandate once; we debit it each month",
		"adapter": "Razorpay",
		"method_type": "UPI Autopay",
		"currencies": ("INR",),
		"fallback_reason": None,
	},
)

BY_KEY = {(entry["surface"], entry["instrument"]): entry for entry in CATALOGUE}

# Networks that can pay but cannot be saved: no rail we use registers a mandate on
# them (Stripe does Visa and Mastercard; Razorpay's standing instructions add
# RuPay). A customer holding one tops up a wallet or pays each invoice, and the
# auto-pay surface has to say so — an absence they have to infer is how someone
# taps the nearest card tile, fails at registration, and hears about it from a
# dunning email.
NO_MANDATE_NETWORKS = ("Amex", "Diners")

# One line that carries the limit and the way out of it. The reason a customer
# needs is "my card isn't here and this says why"; the paragraph that explained
# which bank rails register mandates was answering a question nobody asked.
MANDATE_GAP_NOTE = "Amex or Diners can't auto-pay — top up a wallet"


def mandate_gap_note(currency: str) -> str | None:
	"""The one line the auto-pay surface owes a customer whose card cannot be saved.

	It doubles as the label of the control that takes them to the wallet, so it has
	to read as a route rather than a warning.
	"""
	return MANDATE_GAP_NOTE if currency == "INR" else None


def get(instrument: str, surface: str = MANDATE) -> dict:
	entry = BY_KEY.get((surface, instrument))
	if not entry:
		frappe.throw(frappe._("{0} is not a payment option here.").format(instrument), frappe.ValidationError)
	return entry


# Gateways that save a card in-app and charge it off-session. Stripe is the card rail
# everywhere it is enabled, except where the currency's default gateway is another card
# rail: AED defaults to Checkout.com.
CARD_ADAPTERS = ("Stripe", "Checkout")


def card_gateway(currency: str) -> str | None:
	"""The enabled gateway that saves and charges cards in this currency, if any.

	The currency's default gateway wins when it is a card rail, so an AED team saves its
	card on Checkout.com. Otherwise Stripe, as before."""
	from central.billing.api.dashboard._shared import _enabled_gateway_for_currency
	from central.billing.gateways.registry import GatewayNotFound, resolve_gateway_for_currency

	try:
		default = resolve_gateway_for_currency(currency)
	except GatewayNotFound:
		default = None
	if default and frappe.db.get_value("Payment Gateway", default, "adapter_key") in CARD_ADAPTERS:
		return default
	return _enabled_gateway_for_currency(currency, "Stripe")


def gateway_for(instrument: str, currency: str, surface: str = MANDATE) -> str | None:
	"""The enabled gateway that carries this instrument in this currency, if any."""
	from central.billing.api.dashboard._shared import _enabled_gateway_for_currency

	entry = get(instrument, surface)
	if entry["currencies"] and currency not in entry["currencies"]:
		return None
	# The console saves a Checkout.com card in Flow. A Checkout.com top-up has no console
	# form yet, so the recharge card stays on Stripe.
	if instrument == CARD and surface == MANDATE:
		return card_gateway(currency)
	return _enabled_gateway_for_currency(currency, entry["adapter"])


def available(currency: str, surface: str = MANDATE) -> list[dict]:
	"""The instruments a team billed in `currency` can be offered on this surface.

	An instrument whose gateway is disabled, or which does not exist in the
	currency, is left out rather than shown and refused.
	"""
	offered = []
	for entry in CATALOGUE:
		if entry["surface"] != surface:
			continue
		gateway = gateway_for(entry["instrument"], currency, surface)
		if not gateway:
			continue
		offered.append(
			{
				"instrument": entry["instrument"],
				"label": entry["label"],
				"description": entry["description"],
				"gateway": gateway,
				# A gateway row is named after its adapter (ADR 0021).
				"adapter_key": gateway,
				"surface": surface,
			}
		)
	return offered
