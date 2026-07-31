// Penanda customer WAPU, diambil dari WAPU Status di master Customer.
// Server tetap nge-set ulang pas simpan (vic_addon/vic/sales_invoice.py), ini biar
// centangnya langsung kelihatan waktu customer dipilih.

frappe.ui.form.on("Sales Invoice", {
	customer(frm) {
		if (!frm.doc.customer) {
			frm.set_value("custom_customer_wapu", 0);
			return;
		}

		frappe.db
			.get_value("Customer", frm.doc.customer, "custom_wapu_status")
			.then(({ message }) =>
				frm.set_value("custom_customer_wapu", message?.custom_wapu_status === "WAPU" ? 1 : 0)
			);
	},
});
