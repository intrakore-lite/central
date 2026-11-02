from urllib.parse import urlencode

import frappe

from central.signups.trial import TrialSettings

SIGNUP_PATH = "/dashboard/signup"


def get_trial_offer() -> dict | None:
	"""The free trial that the sign-in page offers: the Default Trial Product of Central Settings,
	its title and its trial days. None when the setting is empty or the product is disabled."""
	product = frappe.get_cached_doc("Central Settings").default_trial_product
	if not product:
		return None

	title = frappe.db.get_value("Product", {"name": product, "enabled": 1}, "title")
	if not title:
		return None
	return {"product": product, "title": title, "days": TrialSettings(product).days}


def get_trial_signup_url(query: dict[str, str]) -> str:
	"""The signup page for the /try link. The visitor's query, such as the UTM tags, goes along,
	because the console records it as the team's first touch. A `product` in the query wins."""
	offer = get_trial_offer()
	carried = dict(query)
	if offer:
		carried.setdefault("product", offer["product"])
	return f"{SIGNUP_PATH}?{urlencode(carried)}" if carried else SIGNUP_PATH
