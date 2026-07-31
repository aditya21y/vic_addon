"""Kunci harga ke dokumen sumbernya, jangan ketiban Item Price.

Tiap dokumen baru kebuka di form, ERPNext jalanin trigger `currency` -> `apply_price_list()`
yang narik ulang harga semua item dari Item Price, terus **maksa** `rate = price_list_rate`
(lihat `transaction.js` di `_set_values_for_item_list`). Buat alur VIC harganya bukan dari
price list:

	harga jual  -> Quotation Rate di Costing   (Quotation, Sales Order)
	harga beli  -> net rate di Supplier Quotation  (Purchase Order)

Makanya tiap dokumen disimpan, harganya dipasang lagi dari sumbernya. Nego harga tetap bisa
lewat kolom diskon per item (dan diskon atas total), yang dihitung dari harga sumber ini.
"""

import frappe
from frappe.utils import flt


def set_selling_rate_from_costing(doc, method=None):
	"""Hook `before_validate` Quotation & Sales Order: harga jual balik ke Costing."""
	if not doc.get("custom_costing"):
		return

	rates = get_costing_rates(doc.custom_costing)
	if not rates:
		return

	for item in doc.items:
		rate = rates.get((item.item_code, item.get("custom_supplier_quotation")))
		if rate is None:
			rate = rates.get((item.item_code, None))

		apply_rate(item, rate)


def set_buying_rate_from_supplier_quotation(doc, method=None):
	"""Hook `before_validate` Purchase Order: harga beli balik ke SQTN-nya.

	Kalau harga belinya beda dari penawaran supplier, yang bener itu revisi SQTN lalu hitung
	ulang costing - bukan diubah diam-diam di PO. Potongan tetap bisa lewat kolom diskon.
	"""
	for item in doc.items:
		if not item.get("custom_supplier_quotation"):
			continue

		apply_rate(item, get_supplier_quotation_rate(item, doc.currency))


def apply_rate(item, rate):
	"""Pasang harga sumber ke `price_list_rate`, rate-nya biar ERPNext yang hitung."""
	if rate is None or flt(item.price_list_rate) == flt(rate):
		return

	item.price_list_rate = flt(rate, item.precision("price_list_rate"))
	item.discount_amount = 0
	# kalau ada diskon, rate dikosongin biar dihitung ulang ERPNext (pembulatannya ikut dia)
	item.rate = 0 if flt(item.discount_percentage) else item.price_list_rate


def get_costing_rates(costing):
	"""Quotation Rate per item di costing, dikunci sama SQTN-nya kalau itemnya kembar."""
	rates = {}

	for row in frappe.get_all(
		"Costing Item",
		filters={"parent": costing},
		fields=["item_code", "supplier_quotation", "quotation_rate"],
	):
		rates[(row.item_code, row.supplier_quotation)] = flt(row.quotation_rate)
		rates.setdefault((row.item_code, None), flt(row.quotation_rate))

	return rates


def get_supplier_quotation_rate(item, currency):
	"""Net rate item di SQTN, cuma dipakai kalau mata uangnya sama."""
	quotation = item.custom_supplier_quotation

	if frappe.db.get_value("Supplier Quotation", quotation, "currency") != currency:
		return None

	return frappe.db.get_value(
		"Supplier Quotation Item",
		item.get("custom_supplier_quotation_item")
		or {"parent": quotation, "item_code": item.item_code},
		"net_rate",
	)
