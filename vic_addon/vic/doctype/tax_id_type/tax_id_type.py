# Copyright (c) 2026, aditya and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

# Jenis ID pembeli/penjual yang dikenal Coretax (e-Faktur)
DEFAULT_TYPES = (
	("TIN", "NPWP (Tax Identification Number)"),
	("NIK", "Nomor Induk Kependudukan"),
	("Passport", "Nomor paspor (WNA)"),
	("Other ID", "Identitas lain"),
)


class TaxIDType(Document):
	pass


def setup_tax_id_types():
	"""Isian awal master Tax ID Type, cuma kalau masih kosong.

	Jalan tiap install & migrate. Kalau udah ada isinya (termasuk yang udah diubah/dihapus user),
	gak disentuh - biar pilihan user gak muncul lagi diam-diam.
	"""
	if frappe.db.count("Tax ID Type"):
		return

	for name, description in DEFAULT_TYPES:
		frappe.get_doc({"doctype": "Tax ID Type", "tax_id_type": name, "description": description}).insert(
			ignore_permissions=True
		)
