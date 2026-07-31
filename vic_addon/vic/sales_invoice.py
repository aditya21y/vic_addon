"""Custom Sales Invoice: penanda customer WAPU.

WAPU (Wajib Pungut): PPN-nya dipungut dan disetor sendiri sama customer - biasanya instansi
pemerintah atau BUMN - bukan sama kita. Statusnya disimpan sekali di master Customer, terus
ditandai otomatis di tiap invoice biar gampang difilter dan dipakai di print / faktur pajak.
"""

import frappe

WAPU = "WAPU"


def set_customer_wapu(doc, method=None):
	"""Hook `validate`: tandai invoice kalau customernya berstatus WAPU."""
	doc.custom_customer_wapu = (
		1
		if doc.customer and frappe.db.get_value("Customer", doc.customer, "custom_wapu_status") == WAPU
		else 0
	)
