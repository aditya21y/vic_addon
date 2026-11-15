// PR dropship dibatalin lewat Delivery Note-nya (server nolak cancel langsung, lihat
// `block_direct_cancel` di vic/dropship.py). DN-nya gak ditawarin di dialog "Cancel All" - urutan
// batal dari sana kebalik dan PR-nya keburu dibatalin duluan sama DN.
frappe.ui.form.on("Purchase Receipt", {
	refresh(frm) {
		if (!frm.doc.custom_dropship_delivery_note) return;

		frm.ignore_doctypes_on_cancel_all = [
			...new Set([...(frm.ignore_doctypes_on_cancel_all || []), "Delivery Note"]),
		];
	},
});
