import frappe

from central.iam import can


def get_default_trial_product() -> str | None:
	"""The product a free trial starts when nothing names one.

	1. Central Settings > Default Trial Product, once that field exists and its product is enabled.
	2. Else the oldest enabled product that takes signups, which is the only one on a new Central."""
	settings = frappe.get_cached_doc("Central Settings")
	configured = settings.get("default_trial_product")
	if configured and frappe.db.exists("Product", {"name": configured, "enabled": 1}):
		return configured

	return frappe.db.get_value(
		"Product", {"enabled": 1, "signup_app": ["is", "set"]}, "name", order_by="creation asc"
	)


def resolve_trial_product(product: str | None) -> str | None:
	"""The product a signup link names when it is enabled, else the default trial product."""
	if product and frappe.db.exists("Product", {"name": product, "enabled": 1}):
		return product

	return get_default_trial_product()


def get_trial_offer(team: str) -> dict | None:
	"""The free trial the console offers this team, or None.

	1. There must be a default trial product.
	2. A new site of that product must be a free trial for the team (`is_free_trial_creation`).
	3. The team's owner must have no open trial: an owner gets one free site.
	4. The caller must be able to create sites in the team."""
	from central.signups.eligibility import get_open_trial_of_owner, is_free_trial_creation
	from central.signups.trial import get_product_branding

	product = get_default_trial_product()
	if not product or not can(frappe.session.user, team, "server:create"):
		return None
	if not is_free_trial_creation(team, product) or get_open_trial_of_owner(team):
		return None

	branding = get_product_branding(product)
	return {"product": product, "title": branding["product_title"], "logo": branding["product_logo"]}
