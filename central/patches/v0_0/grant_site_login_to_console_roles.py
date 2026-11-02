import frappe

SITE_LOGIN = "server:site-login"


def execute() -> None:
	"""Give `server:site-login` to every team-defined role that can open the console, so its
	members still sign in to their sites. The fixtures give it to the system roles."""
	console_roles = frappe.get_all(
		"Role Capability",
		filters={"parenttype": "Team Role", "parentfield": "capabilities", "capability": "server:console"},
		pluck="parent",
	)
	for role in set(console_roles):
		if frappe.db.get_value("Team Role", role, "is_system"):
			continue
		if frappe.db.exists(
			"Role Capability", {"parenttype": "Team Role", "parent": role, "capability": SITE_LOGIN}
		):
			continue

		last = frappe.db.count("Role Capability", {"parenttype": "Team Role", "parent": role})
		frappe.get_doc(
			{
				"doctype": "Role Capability",
				"parent": role,
				"parenttype": "Team Role",
				"parentfield": "capabilities",
				"capability": SITE_LOGIN,
				"idx": last + 1,
			}
		).db_insert()
