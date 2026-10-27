"""SPP / SPK No. kwitansi gak disimpan di Sales Order lagi - kwitansi ngambil Customer's Purchase Order.

Field SPP / SPK No. & Tanggal SPP / SPK di Sales Order dibuang. Isian yang terlanjur ada dipindah dulu
ke Customer's Purchase Order (`po_no` / `po_date`) - cuma kalau field itu masih kosong, isian user
gak ditimpa.

Perlu patch karena sinkronisasi fixture gak pernah ngapus record. Kolom lamanya dibiarin - Frappe gak
ngedrop kolom.
"""

import frappe

FIELDS = {
	"custom_kwitansi_spp_no": "po_no",
	"custom_kwitansi_spp_date": "po_date",
}


def execute():
	columns = frappe.db.get_table_columns("Sales Order")

	for source, target in FIELDS.items():
		if source in columns:
			frappe.db.sql(
				f"""update `tabSales Order` set `{target}` = `{source}`
				where ifnull(`{source}`, '') != '' and ifnull(`{target}`, '') = ''"""
			)

		name = f"Sales Order-{source}"
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, force=1, ignore_permissions=True)

	frappe.clear_cache(doctype="Sales Order")
