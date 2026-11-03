frappe.ui.form.on("Trial Invitation", {
	refresh(frm) {
		if (frm.is_new()) {
			frm.set_intro(__("Saving sends the invitation email with a one-time activation link."));
			return;
		}

		if (["Sent", "Expired"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Resend"), () =>
				frappe.confirm(__("Send a new activation link? The link in the earlier email stops working."), () =>
					frappe
						.call("central.api.trial_invitations.resend", { name: frm.doc.name })
						.then(() => {
							frappe.show_alert({ message: __("Invitation sent"), indicator: "green" });
							frm.reload_doc();
						})
				)
			);
		}
		if (frm.doc.status === "Sent") {
			frm.add_custom_button(__("Revoke"), () =>
				frappe.confirm(__("Revoke this invitation? Its activation link stops working at once."), () =>
					frappe
						.call("central.api.trial_invitations.revoke", { name: frm.doc.name })
						.then(() => frm.reload_doc())
				)
			);
		}
	},
});
