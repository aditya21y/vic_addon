"""Buang field WAPU Status dari master Customer.

Status WAPU gak disimpan per customer lagi; penandanya diisi manual per invoice lewat checkbox
Customer WAPU di Sales Invoice.

Perlu patch tersendiri: sinkronisasi fixture cuma nambah dan memperbarui record, gak pernah
ngapus record yang dikeluarin dari file-nya. Kolom `custom_wapu_status` di tabel Customer
sengaja dibiarin - Frappe gak pernah ngedrop kolom, jadi datanya tetap ada kalau sewaktu-waktu
dibutuhin lagi.
"""

import frappe

FIELD = "Customer-custom_wapu_status"


def execute():
	if frappe.db.exists("Custom Field", FIELD):
		frappe.delete_doc("Custom Field", FIELD, force=1, ignore_permissions=True)

	# checkbox di Sales Invoice sekarang diisi tangan, jadi gak boleh read only lagi
	if frappe.db.exists("Custom Field", "Sales Invoice-custom_customer_wapu"):
		frappe.db.set_value("Custom Field", "Sales Invoice-custom_customer_wapu", "read_only", 0)
