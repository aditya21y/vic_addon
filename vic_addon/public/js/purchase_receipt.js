// Form Purchase Receipt cuma buat nyatet barang + qty yang diterima, harga gak ditampilin.
// Section harga & Accounting Dimensions disembunyiin lewat property setter (fixtures), tapi tiga
// total di bawah tabel item dimunculin lagi sama ERPNext (`change_form_labels`, jalan tiap
// refresh dan ganti currency) - jadi abis itu kelar, disembunyiin lagi di sini. Total Quantity
// di section yang sama tetap kelihatan. Net Total (Company Currency) cuma disembunyiin di sini:
// field itu wajib tanpa default, jadi Frappe nolak property setter `hidden` buat dia.

const PRICE_TOTALS = ["base_total", "base_net_total", "net_total"];

const change_form_labels = cur_frm.cscript.change_form_labels;

cur_frm.cscript.change_form_labels = function (...args) {
	change_form_labels.apply(this, args);
	this.frm.toggle_display(PRICE_TOTALS, false);
};

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
