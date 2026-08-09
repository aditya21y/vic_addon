// DP Invoice (Payment Request): isi persentase -> DP Amount kehitung dari nilai dokumen
// referensi, plus tabel PPN/PPh atas DP yang nanti dibawa ke Payment Entry.

frappe.ui.form.on("Payment Request", {
	refresh(frm) {
		// tombol bawaan erpnext cuma nongol buat Outward + status Initiated/Partially Paid,
		// padahal DP dari customer (Inward) juga perlu bikin Payment Entry.
		// frappe nge-dedupe tombol per label, jadi ini gak bikin tombol dobel.
		if (frm.doc.docstatus !== 1 || ["Paid", "Cancelled"].includes(frm.doc.status)) return;

		frm.add_custom_button(__("Create Payment Entry"), () => {
			frappe.call({
				method: "erpnext.accounts.doctype.payment_request.payment_request.make_payment_entry",
				args: { docname: frm.doc.name },
				freeze: true,
				callback({ message }) {
					if (!message) return;

					frappe.model.sync(message);
					frappe.set_route("Form", message.doctype, message.name);
				},
			});
		}).addClass("btn-primary");
	},

	custom_dp_percentage(frm) {
		if (!flt(frm.doc.custom_dp_percentage)) return;

		get_reference_total(frm).then((reference_total) => {
			if (!reference_total) return;

			frm.set_value(
				"grand_total",
				flt(
					(reference_total * flt(frm.doc.custom_dp_percentage)) / 100,
					precision("grand_total")
				)
			);
		});
	},

	custom_purchase_taxes_and_charges_template(frm) {
		load_taxes(frm, "Purchase Taxes and Charges Template", frm.doc.custom_purchase_taxes_and_charges_template);
	},

	custom_sales_taxes_and_charges_template(frm) {
		load_taxes(frm, "Sales Taxes and Charges Template", frm.doc.custom_sales_taxes_and_charges_template);
	},
});

// DP dihitung dari Net Total dokumen referensi (belum kena PPN), karena PPN atas DP
// dicatat sendiri di tabel Advance Taxes and Charges - lihat vic_addon/vic/dp_invoice.py.
function get_reference_total(frm) {
	if (!frm.doc.reference_doctype || !frm.doc.reference_name) return Promise.resolve(0);

	return frappe.db
		.get_value(frm.doc.reference_doctype, frm.doc.reference_name, "net_total")
		.then(({ message }) => flt(message && message.net_total));
}

function load_taxes(frm, template_doctype, template) {
	if (!template) return;

	frappe.call({
		method: "erpnext.controllers.accounts_controller.get_taxes_and_charges",
		args: { master_doctype: template_doctype, master_name: template },
		callback({ message }) {
			frm.clear_table("custom_taxes");

			(message || []).forEach((row) => {
				const tax = frm.add_child("custom_taxes");
				Object.assign(tax, row, {
					// tabel pajak DP cuma kenal charge type ini
					charge_type: row.charge_type === "Actual" ? "Actual" : "On Paid Amount",
				});
			});

			frm.refresh_field("custom_taxes");
		},
	});
}
