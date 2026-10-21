// Form Purchase Receipt cuma buat nyatet barang + qty yang diterima, harga gak ditampilin.
// Section harga & Accounting Dimensions disembunyiin lewat property setter (fixtures), tapi tiga
// total di bawah tabel item dimunculin lagi sama ERPNext (`change_form_labels`, jalan tiap
// refresh dan ganti currency) - jadi abis itu kelar, disembunyiin lagi di sini. Total Quantity
// di section yang sama tetap kelihatan.

const PRICE_TOTALS = ["base_total", "base_net_total", "net_total"];

const change_form_labels = cur_frm.cscript.change_form_labels;

cur_frm.cscript.change_form_labels = function (...args) {
	change_form_labels.apply(this, args);
	this.frm.toggle_display(PRICE_TOTALS, false);
};
