"""Isi print format ditulis di file `.html` biar enak diedit dan di-review.

Frappe cuma baca file `.json` waktu migrate, dan di situ HTML-nya kesimpan sebagai satu string
panjang - gampang basi kalau ada yang ngedit file `.html`-nya doang. Jadi isi `.html` disalin ke
dokumen Print Format tiap install & migrate: **file `.html` yang jadi acuan**, `.json`-nya cuma
buat bikin dokumennya waktu install pertama.
"""

from pathlib import Path

import frappe

# nama Print Format -> nama folder di vic_addon/vic/print_format/
PRINT_FORMATS = {
	"Goods Received": "goods_received",
	"Serial No Label": "serial_no_label",
	"Delivery Order": "delivery_order",
	# Delivery Order versi gudang: barang stok aja, tanpa Pengerjaan / Pengiriman
	"Delivery Order (Stock Only)": "delivery_order_stock",
	"Quotation (VIC)": "quotation",
	"Purchase Order (VIC)": "purchase_order",
	"Purchase Request": "purchase_request",
	"Purchase Request (Sales Order)": "purchase_request_sales_order",
	"Inquiry": "inquiry",
	"Request For Quotation (Customer)": "opportunity_rfq",
	"Costing (Sales)": "costing_sales",
	"Costing (Import)": "costing_import",
	"Kwitansi": "kwitansi",
	"Kwitansi (Progress)": "kwitansi_progress",
	"Receipt Note": "receipt_note",
	# Proforma Invoice dari Sales Order
	"Proforma Invoice": "proforma_invoice",
}


def sync_print_formats():
	folder = Path(frappe.get_app_path("vic_addon", "vic", "print_format"))

	for name, slug in PRINT_FORMATS.items():
		path = folder / slug / f"{slug}.html"

		if not (path.exists() and frappe.db.exists("Print Format", name)):
			continue

		html = path.read_text()
		if frappe.db.get_value("Print Format", name, "html") != html:
			frappe.db.set_value("Print Format", name, "html", html)
