import frappe


def execute() -> None:
	"""Turn Managed SaaS Mode on, the field's default, so customers keep only their sites."""
	frappe.db.set_single_value("Central Settings", "managed_saas_mode", 1)
