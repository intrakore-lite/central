import frappe


def execute() -> None:
	"""Telr is replaced by Checkout.com (OPS-217): remove the Telr Payment Gateway row.

	Telr never had a live account, so its row holds no money. Its Gateway Customer rows go
	with it. A Payment Method or Payment Attempt that still names Telr is listed in the
	Error Log for an operator, and is not deleted."""
	if not frappe.db.exists("Payment Gateway", "Telr"):
		return
	left = {
		doctype: frappe.get_all(doctype, filters={"gateway": "Telr"}, pluck="name")
		for doctype in ("Payment Method", "Payment Attempt", "Top-up Order")
	}
	if any(left.values()):
		frappe.log_error(
			title="Telr records left after the Telr gateway was removed",
			message=frappe.as_json(left),
		)
	frappe.db.delete("Gateway Customer", {"gateway": "Telr"})
	frappe.delete_doc("Payment Gateway", "Telr", force=True, ignore_permissions=True)
