"""Buang semua field WAPU: Customer WAPU di Sales Invoice (dan WAPU Status di Customer kalau masih ada).

Penanda WAPU gak dipakai lagi sama sekali. WAPU Status di Customer sebenernya udah dibuang duluan
(patch `drop_customer_wapu_status`), di sini ikut dicek buat site yang kelewat.

Perlu patch karena sinkronisasi fixture gak pernah ngapus record. Kolomnya dibiarin - Frappe gak
ngedrop kolom.
"""

import frappe

FIELDS = (
	"Sales Invoice-custom_customer_wapu",
	"Customer-custom_wapu_status",
)


def execute():
	for name in FIELDS:
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, force=1, ignore_permissions=True)

	for doctype in ("Sales Invoice", "Customer"):
		frappe.clear_cache(doctype=doctype)
