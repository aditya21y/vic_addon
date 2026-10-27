"""Skema DP pakai Item DP dicabut dari sisi pembelian - DP ke supplier cukup advance payment di PO.

Yang dibuang: field Invoice DP & tabel DP Invoices di Purchase Invoice, plus akun Uang Muka
Pembelian di Company. Sisi penjualan (Sales Invoice) gak berubah.

Perlu patch karena sinkronisasi fixture gak pernah ngapus record. Kolom & baris DP Allocation lama
dibiarin - Frappe gak ngedrop kolom, dan jurnal yang udah kebentuk tetap utuh.
"""

import frappe

FIELDS = (
	"Purchase Invoice-custom_dp_section",
	"Purchase Invoice-custom_is_dp",
	"Purchase Invoice-custom_dp_order",
	"Purchase Invoice-custom_dp_column",
	"Purchase Invoice-custom_dp_term",
	"Purchase Invoice-custom_dp_percentage",
	"Purchase Invoice-custom_dp_allocation_section",
	"Purchase Invoice-custom_dp_allocations",
	"Purchase Invoice-custom_total_dp_allocated",
	"Company-custom_purchase_dp_account",
)


def execute():
	for name in FIELDS:
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, force=1, ignore_permissions=True)

	for doctype in ("Purchase Invoice", "Company"):
		frappe.clear_cache(doctype=doctype)
