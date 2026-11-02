import frappe
from frappe import _

from central.integrations.images import validate_catalog_access
from central.signups.doctype.product.product import Product
from central.site_provisioning import (
	SIGNUP_FLOW,
	preferred_image,
	product_image_tags,
	signup_offering,
	trial_images,
)


def list_server_products(team: str, region: str) -> list[dict]:
	"""The products a team can create a server of in a region, each with the image it boots.

	1. Require server view access in the Team.
	2. Return enabled products marked Available on New Server.
	3. Leave out a product that has no image in the region.
	"""
	validate_catalog_access(team, "Server")

	# Product is an operator DocType. A customer reads only its public branding, as signup does.
	names = frappe.get_all(
		"Product",
		filters={"enabled": 1, "available_on_new_server": 1},
		pluck="name",
		order_by="title asc",
	)
	if not names:
		return []

	offering = signup_offering()
	choices = []
	for name in names:
		product = frappe.get_cached_doc("Product", name)
		if images := trial_images(team, region, offering, product):
			choices.append(_get_choice(product, offering, preferred_image(images)))

	return choices


def _get_choice(product: Product, offering: str, image: dict) -> dict:
	return {
		"name": product.name,
		"title": product.title,
		"logo": product.logo,
		"description": product.subtitle,
		"offering": offering,
		"image_id": image["id"],
	}


def get_new_server_product(product: str) -> Product:
	"""The enabled product a new server names, or a refusal the customer can read."""
	if not frappe.db.exists("Product", {"name": product, "enabled": 1, "available_on_new_server": 1}):
		frappe.throw(_("This product is not available for new servers."))

	return frappe.get_cached_doc("Product", product)


def get_product_image_selector(product: str | None) -> dict:
	"""The flow and tags the image of a product server must match. They narrow the signup
	offering to images with the product's app installed. A server without a product adds none."""
	if not product:
		return {}

	return {"flow": SIGNUP_FLOW, "extra_tags": product_image_tags(get_new_server_product(product))}
