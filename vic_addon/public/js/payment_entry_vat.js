// DP ke supplier dengan PPN Masukan Belum Ditagih (lihat vic_addon/vic/dp_ppn.py): begitu faktur
// pajak supplier diterima, tombol ini bikin Journal Entry draft Dr PPN Masukan / Cr PPN Masukan
// Belum Ditagih. Kalau jurnalnya udah ada, tombolnya jadi buka jurnal itu.

frappe.ui.form.on("Payment Entry", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || !frm.doc.custom_vat_not_invoiced) return;

		frappe.call({
			method: "vic_addon.vic.dp_ppn.get_vat_reclass_journal",
			args: { payment_entry: frm.doc.name },
			callback({ message }) {
				if (message) {
					const label = message.docstatus ? __("PPN Reclass Journal") : __("PPN Reclass Journal (Draft)");
					frm.add_custom_button(label, () => frappe.set_route("Form", "Journal Entry", message.name), __("View"));
					return;
				}

				frm.add_custom_button(__("PPN Reclass Journal"), () => make_vat_reclass_journal(frm), __("Create"));
				frm.dashboard.set_headline_alert(
					__("PPN of this advance is still in PPN Masukan Belum Ditagih. Once the supplier's Faktur Pajak is received, use Create > PPN Reclass Journal."),
					"orange"
				);
			},
		});
	},
});

function make_vat_reclass_journal(frm) {
	frappe.confirm(__("Faktur Pajak from the supplier received? A draft Journal Entry will be created to move the PPN to PPN Masukan."), () =>
		frappe.call({
			method: "vic_addon.vic.dp_ppn.make_vat_reclass_journal",
			args: { payment_entry: frm.doc.name },
			freeze: true,
			callback({ message }) {
				if (message) frappe.set_route("Form", "Journal Entry", message);
			},
		})
	);
}
