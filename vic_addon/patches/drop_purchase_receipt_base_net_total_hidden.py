"""Buang property setter `hidden` di Net Total (Company Currency) Purchase Receipt.

Field itu wajib tanpa default, jadi Frappe nolak disembunyiin lewat property setter - dan selama
record-nya masih ada, tiap property setter Purchase Receipt lain yang diimpor ikut gagal
(`HiddenAndMandatoryWithoutDefaultError`). Field-nya sekarang cuma disembunyiin lewat JS
(`public/js/purchase_receipt.js`).

Jalan sebelum fixture disinkronin, jadi sinkronisasinya gak kepentok record ini lagi.
"""

import frappe

NAME = "Purchase Receipt-base_net_total-hidden"


def execute():
	if frappe.db.exists("Property Setter", NAME):
		frappe.db.delete("Property Setter", NAME)
		frappe.clear_cache(doctype="Purchase Receipt")
