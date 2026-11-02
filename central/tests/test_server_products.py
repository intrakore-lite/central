import json
from unittest.mock import patch

import frappe
import requests
from frappe.tests import IntegrationTestCase

from central.api.images import eligible_plans, list_server_products
from central.api.servers import create_server
from central.errors import AtlasConnectionError
from central.integrations.images import selected_image
from central.resource_actions import submit_request
from central.signups.server_products import get_product_image_selector
from central.tests.test_iam import ensure_user

COMPOSITION = [
	{"resource_type": "Compute", "quantity": 1, "unit": "vCPU"},
	{"resource_type": "Memory", "quantity": 2, "unit": "GB"},
]


class TestServerProducts(IntegrationTestCase):
	"""A customer starts a server with a product's apps from the product's newest signup image."""

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, "Administrator")
		self.addCleanup(frappe.db.rollback)
		frappe.db.set_single_value("Central Settings", "signup_image_minimum_age_minutes", 0)
		frappe.db.delete("Image Offering")
		frappe.db.delete("Product")
		self.region = frappe.get_doc(
			{
				"doctype": "Region",
				"region": frappe.generate_hash(length=8),
				"base_url": "https://atlas.example.test",
				"atlas_region_id": "43",
				"status": "Active",
			}
		).insert()
		self.team = frappe.get_doc(
			{"doctype": "Team", "team_name": "Products", "owner_user": "Administrator"}
		).insert()
		self.offering = frappe.get_doc(
			{
				"doctype": "Image Offering",
				"offering_key": "pilot",
				"title": "Intrakore Apps",
				"enabled": 1,
				"available_in": "Signup",
				"required_tags": [{"key": "purpose", "value": "pilot"}],
			}
		).insert()
		self.product("crm", "intrakore_crm")
		self.enterContext(patch("central.integrations.atlas.mint_atlas_token", return_value="test-token"))
		self.request = self.enterContext(patch("central.integrations.atlas.requests.request"))
		self.request.side_effect = self.regional_page

	def product(self, key: str, app: str, **values):
		return frappe.get_doc(
			{
				"doctype": "Product",
				"product_key": key,
				"title": key.upper(),
				"subtitle": f"{key} for contractors",
				"signup_app": app,
				**values,
			}
		).insert()

	def image(self, image_id: str, app: str, created_at: int = 1789000000) -> dict:
		return {
			"id": image_id,
			"title": image_id,
			"image_type": "system",
			"enabled": True,
			"status": "available",
			"architecture": "amd64",
			"rootfs_size_mib": 20 * 1024,
			"created_at": created_at,
			"tags": {"purpose": "pilot", "has_site": "1", "frappe_version": "develop", "app": app},
		}

	def regional_page(self, method, url, **request):
		"""The region has two builds of the CRM app and none of any other app."""
		items = []
		if "app:intrakore_crm" in request["params"]["tag"]:
			items = [self.image("crm-old", "intrakore_crm", 1), self.image("crm-new", "intrakore_crm", 2)]

		response = requests.Response()
		response.status_code = 200
		response._content = json.dumps(
			{"items": items, "has_more": False, "offset": 0, "limit": 100}
		).encode()
		return response

	def test_lists_enabled_products_with_their_newest_regional_image(self):
		self.product("off", "intrakore_crm", enabled=0)
		self.product("hidden", "intrakore_crm", available_on_new_server=0)
		self.product("unbuilt", "intrakore_estimation")

		choices = list_server_products(self.team.name, self.region.name)

		self.assertEqual(
			choices,
			[
				{
					"name": "crm",
					"title": "CRM",
					"logo": None,
					"description": "crm for contractors",
					"offering": "pilot",
					"image_id": "crm-new",
				}
			],
		)
		self.assertIn("has_site:1", self.request.call_args_list[0].kwargs["params"]["tag"])

	def test_another_team_cannot_list_or_create_from_a_product(self):
		user = ensure_user(f"products-{frappe.generate_hash(length=8)}@example.test")
		own = frappe.get_doc({"doctype": "Team", "team_name": "Customer", "owner_user": user}).insert()
		frappe.set_user(user)

		self.assertEqual([row["name"] for row in list_server_products(own.name, self.region.name)], ["crm"])
		self.request.reset_mock()
		with self.assertRaises(frappe.PermissionError):
			list_server_products(self.team.name, self.region.name)
		with self.assertRaises(frappe.PermissionError):
			create_server(
				team=self.team.name,
				region=self.region.name,
				title="CRM",
				request_key="product-request-0001",
				plan="any-plan",
				offering="pilot",
				image_id="crm-new",
				product="crm",
			)
		self.request.assert_not_called()

	def test_the_image_must_carry_an_available_product_app(self):
		selector = get_product_image_selector("crm")
		with patch(
			"central.integrations.atlas.AtlasClient.get_image",
			return_value=self.image("crm-new", "intrakore_crm"),
		):
			image = selected_image(self.team.name, self.region.name, "pilot", "crm-new", **selector)
			self.assertEqual(image["tags"]["app"], "intrakore_crm")

			# The raw signup offering is not a server choice without a product.
			with self.assertRaises(frappe.ValidationError):
				selected_image(self.team.name, self.region.name, "pilot", "crm-new")

		self.product("estimation", "intrakore_estimation")
		with (
			patch(
				"central.integrations.atlas.AtlasClient.get_image",
				return_value=self.image("crm-new", "intrakore_crm"),
			),
			self.assertRaises(AtlasConnectionError),
		):
			selected_image(
				self.team.name,
				self.region.name,
				"pilot",
				"crm-new",
				**get_product_image_selector("estimation"),
			)

		frappe.db.set_value("Product", "crm", "available_on_new_server", 0)
		with self.assertRaises(frappe.ValidationError):
			get_product_image_selector("crm")

	def test_plans_fit_the_product_image_disk(self):
		def plan(name: str, disk_gib: int) -> dict:
			return {
				"plan": name,
				"includes": [*COMPOSITION, {"resource_type": "Disk", "quantity": disk_gib, "unit": "GB"}],
			}

		catalog = {"plans": {"Standard": [plan("small", 10), plan("large", 40)]}, "profiles": []}
		with (
			patch(
				"central.integrations.atlas.AtlasClient.get_image",
				return_value=self.image("crm-new", "intrakore_crm"),
			),
			patch("central.billing.catalog.server_plans.get_server_plans", return_value=catalog),
		):
			menu = eligible_plans(self.team.name, self.region.name, "pilot", "crm-new", product="crm")

		self.assertEqual([row["plan"] for row in menu["plans"]["Standard"]], ["large"])

	def test_server_creation_resolves_the_product_image(self):
		with (
			patch("central.resource_actions.selected_image", side_effect=frappe.ValidationError) as image,
			self.assertRaises(frappe.ValidationError),
		):
			submit_request(
				team=self.team.name,
				region=self.region.name,
				title="CRM",
				offering="pilot",
				image_id="crm-new",
				request_key="product-request-0002",
				plan="any-plan",
				product="crm",
			)

		self.assertEqual(
			image.call_args.kwargs,
			{
				"flow": "Signup",
				"extra_tags": {"has_site": "1", "frappe_version": "develop", "app": "intrakore_crm"},
			},
		)
