// Deposit ke supplier - lihat vic_addon/vic/vendor_deposit.py.
// PO: tombol Pay Deposit selama deposit belum lunas. Payment Entry deposit: Account Paid To
// disaring ke akun deposit (bawaannya cuma akun hutang).

frappe.ui.form.on("Purchase Order", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;
		if (flt(frm.doc.custom_deposit_amount) - flt(frm.doc.custom_deposit_paid) <= 0.005) return;

		frm.add_custom_button(__("Pay Deposit"), () =>
			frappe.call({
				method: "vic_addon.vic.vendor_deposit.make_deposit_payment",
				args: { purchase_order: frm.doc.name },
				freeze: true,
				callback({ message }) {
					if (!message) return;
					const doc = frappe.model.sync(message)[0];
					frappe.set_route("Form", doc.doctype, doc.name);
				},
			})
		);
	},
});

frappe.ui.form.on("Payment Entry", {
	refresh(frm) {
		if (!frm.doc.custom_deposit_purchase_order) return;

		frm.set_query("paid_to", () => ({
			filters: { company: frm.doc.company, is_group: 0, root_type: "Asset" },
		}));
	},
});
