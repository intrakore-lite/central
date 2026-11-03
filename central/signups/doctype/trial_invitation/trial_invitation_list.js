frappe.listview_settings["Trial Invitation"] = {
	add_fields: ["status", "expires_on"],
	get_indicator(doc) {
		const isExpired = doc.status === "Sent" && doc.expires_on && frappe.datetime.str_to_obj(doc.expires_on) <= new Date();
		if (isExpired) return [__("Expired"), "gray", "status,=,Sent"];

		const colors = { Sent: "blue", Accepted: "green", Expired: "gray", Revoked: "red" };
		return [__(doc.status), colors[doc.status], `status,=,${doc.status}`];
	},
};
