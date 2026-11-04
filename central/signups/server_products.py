import re

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
		"apps": get_image_apps(image.get("tags") or {}, product),
	}


# Apps every bundle carries for the others to run on. The console shows them as "Core".
CORE_APPS = frozenset({"frappe", "intrakore_master", "intrakore_ui"})
# Words a person reads as an acronym, not as a capitalised word.
ACRONYMS = frozenset({"ai", "boq", "crm", "hr", "ui", "vat"})
APP_TAG_PREFIX = "app_"
# Apps a bundle carries for its feature apps to post to. They follow the feature apps.
FOUNDATION_APPS = frozenset({"intrakore_accounting", "intrakore_inventory"})
# The assistant works across every app, so it closes the list.
ASSISTANT_APPS = frozenset({"intrakore_ai"})


def get_image_apps(tags: dict[str, str], product: Product | None = None) -> list[dict]:
	"""The apps an image carries, from its `app_<name>=<version>` tags, in the order a person
	reads the bundle: see `app_order`. The core apps come last."""
	apps = [
		{
			"app": tag.removeprefix(APP_TAG_PREFIX),
			"title": get_app_title(tag.removeprefix(APP_TAG_PREFIX)),
			"version": version or None,
			"is_core": tag.removeprefix(APP_TAG_PREFIX) in CORE_APPS,
		}
		for tag, version in tags.items()
		if tag.startswith(APP_TAG_PREFIX) and len(tag) > len(APP_TAG_PREFIX)
	]
	return sorted(apps, key=lambda app: app_order(app, product))


def app_order(app: dict, product: Product | None = None) -> tuple:
	"""Sort key of an image app: the bundle's own apps first, what they run on after.

	1. The product's signup app.
	2. The apps the product title names, in title order: "CRM + Estimation".
	3. The other feature apps, by title.
	4. The apps the feature apps depend on (Accounting, Inventory), by title.
	5. The AI assistant.
	6. The core apps.
	"""
	title = app["title"]
	if app["is_core"]:
		return (6, 0, title)
	if product and app["app"] == product.signup_app:
		return (1, 0, title)
	# A product named after a dependency or the assistant still lists it first.
	if (position := _title_position(title, product)) is not None:
		return (2, position, title)
	if app["app"] in ASSISTANT_APPS:
		return (5, 0, title)
	if app["app"] in FOUNDATION_APPS:
		return (4, 0, title)
	return (3, 0, title)


def _title_position(app_title: str, product: Product | None) -> int | None:
	"""Where the product title names an app, as a whole word: "CRM + Estimation" names CRM at 0."""
	if not product or not product.title:
		return None
	match = re.search(rf"\b{re.escape(app_title)}\b", product.title, re.IGNORECASE)
	return match.start() if match else None


def get_app_title(app: str) -> str:
	"""A friendly name for an app: `intrakore_crm` reads CRM, `intrakore_fixed_assets` Fixed Assets."""
	words = app.removeprefix("intrakore_").split("_")
	return " ".join(word.upper() if word in ACRONYMS else word.capitalize() for word in words if word)


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
