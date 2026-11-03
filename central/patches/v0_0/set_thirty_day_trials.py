import frappe


def execute() -> None:
	"""Run every trial for 30 days: Central Settings holds the length, and each Product inherits it.
	A trial that is already open keeps its end date."""
	frappe.db.set_single_value("Central Settings", "trial_days", 30)
	frappe.db.set_value("Product", {"trial_days": ["!=", 0]}, "trial_days", 0, update_modified=False)
