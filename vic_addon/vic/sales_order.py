"""Custom Sales Order: skema dropship dan bikin PO per supplier.

Supplier tiap item ikut turun dari Costing -> Quotation -> Sales Order lewat field
`custom_supplier` & `custom_supplier_quotation`, jadi PO ke supplier bisa dibikin
otomatis tanpa milih supplier manual lagi.
"""

import frappe
from frappe import _


def set_dropship_details(doc, method=None):
	"""Tandai item sesuai tipe transaksi.

	Kalau Dropship, semua item ditandai `delivered_by_supplier` + suppliernya diisi dari
	SQTN, jadi flow drop ship bawaan ERPNext jalan (alamat kirim PO ke customer, item
	dropship gak ikut Delivery Note). Kalau Reguler, tandanya dilepas.
	"""
	dropship = doc.custom_transaction_type == "Dropship"

	for item in doc.items:
		item.delivered_by_supplier = 1 if dropship else 0
		item.supplier = item.custom_supplier if dropship else None


@frappe.whitelist()
def make_purchase_orders(sales_order):
	"""Bikin draft PO dari Sales Order: item digrup per supplier, satu PO per supplier.

	Yang bikin dokumennya tetap `make_purchase_order` bawaan ERPNext (biar dapet handling
	currency, exchange rate, alamat kirim buat dropship, dan sisa qty yang belum di-PO),
	kita cuma nentuin suppliernya dari SQTN terus ngisi harga beli + link SQTN-nya.
	"""
	from erpnext.selling.doctype.sales_order.sales_order import make_purchase_order

	doc = frappe.get_doc("Sales Order", sales_order)
	doc.check_permission("read")

	supplier_by_item = get_supplier_by_item(doc)
	if not supplier_by_item:
		frappe.throw(
			_("No item in this Sales Order has a Supplier. Fill Supplier Quotation info first."),
			title=_("Supplier Not Found"),
		)

	selected_items = [
		{"item_code": item_code, "supplier": supplier}
		for item_code, supplier in supplier_by_item.items()
	]

	purchase_orders = []
	for purchase_order in make_purchase_order(sales_order, selected_items) or []:
		set_supplier_quotation_details(purchase_order, doc)
		purchase_order.save()
		purchase_orders.append(purchase_order.name)

	return purchase_orders


def get_supplier_by_item(doc):
	"""Supplier per item_code, sekalian mastiin satu item gak dateng dari dua supplier."""
	supplier_by_item = {}

	for item in doc.items:
		if not item.custom_supplier:
			continue

		existing_supplier = supplier_by_item.get(item.item_code)
		if existing_supplier and existing_supplier != item.custom_supplier:
			frappe.throw(
				_(
					"Item {0} comes from two different suppliers ({1} and {2}). Use separate Sales Orders for each supplier."
				).format(item.item_code, existing_supplier, item.custom_supplier)
			)

		supplier_by_item[item.item_code] = item.custom_supplier

	return supplier_by_item


def set_supplier_quotation_details(purchase_order, sales_order):
	"""Isi harga beli + link SQTN di PO, diambil dari baris Sales Order-nya.

	Link SQTN-nya ditaruh di custom field, bukan di field bawaan `supplier_quotation`.
	Field bawaan bikin ERPNext maksa PO item sama persis dengan SQTN (project, uom,
	conversion factor), padahal project di PO ngikut Sales Order, bukan SQTN.
	"""
	sales_order_items = {item.name: item for item in sales_order.items}

	for item in purchase_order.items:
		sales_order_item = sales_order_items.get(item.sales_order_item)
		if not (sales_order_item and sales_order_item.custom_supplier_quotation):
			continue

		quotation = sales_order_item.custom_supplier_quotation
		quotation_item = frappe.db.get_value(
			"Supplier Quotation Item",
			{"parent": quotation, "item_code": item.item_code},
			["name", "net_rate"],
			as_dict=True,
		)
		if not quotation_item:
			continue

		item.custom_supplier_quotation = quotation
		item.custom_supplier_quotation_item = quotation_item.name

		# harga cuma diambil kalau mata uangnya sama, biar gak ketuker kurs
		if frappe.db.get_value("Supplier Quotation", quotation, "currency") == purchase_order.currency:
			item.rate = quotation_item.net_rate
