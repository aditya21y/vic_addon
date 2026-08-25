"""Gudang default + nilai persediaan buat baris item.

Dipakai dokumen yang butuh nebak gudang stok sebuah item: Costing (harga barang stok) dan
Loan Memo (gudang asal barang pinjaman). Urutan gudangnya ngikut ERPNext: gudang default item
di company itu dulu, baru default di Stock Settings.
"""

import frappe
from frappe.utils import flt


@frappe.whitelist()
def get_default_warehouse(item_code, company):
	"""Gudang default item di company ini, jatuh ke default Stock Settings kalau item gak punya.

	Balikin `None` kalau dua-duanya gak diset, atau kalau gudang di Stock Settings punya company
	lain - gudang milik company lain gak boleh nyasar ke dokumen ini.
	"""
	if not (item_code and company):
		return None

	warehouse = frappe.db.get_value(
		"Item Default", {"parent": item_code, "company": company}, "default_warehouse"
	)
	if warehouse:
		return warehouse

	warehouse = frappe.db.get_single_value("Stock Settings", "default_warehouse")
	if warehouse and frappe.db.get_value("Warehouse", warehouse, "company") == company:
		return warehouse

	return None


@frappe.whitelist()
def get_valuation_rate(item_code, warehouse):
	"""Valuation rate item di gudang ini (dari Bin), `None` kalau gak ada nilainya.

	Dipakai buat barang stok yang gak dibeli lewat Supplier Quotation - harga pokoknya diambil
	dari nilai persediaan yang beneran ada di gudang itu, bukan dari penawaran supplier.
	"""
	if not (item_code and warehouse):
		return None

	rate = frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "valuation_rate")

	return flt(rate) or None
