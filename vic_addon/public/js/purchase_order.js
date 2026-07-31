// PO dropship: barangnya dikirim supplier langsung ke lapangan, tapi dokumennya tetap
// lengkap. Purchase Receipt-nya gak dibikin manual - kebuat otomatis pas Delivery Note
// disubmit (lihat vic_addon/vic/dropship.py).

frappe.ui.form.on("Purchase Order", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || frm.doc.custom_transaction_type !== "Dropship") return;

		frm.remove_custom_button(__("Purchase Receipt"), __("Create"));

		frm.add_custom_button(
			__("Delivery Note"),
			() =>
				frappe.model.open_mapped_doc({
					method: "vic_addon.vic.dropship.make_delivery_note",
					frm: frm,
				}),
			__("Create")
		);
	},
});
