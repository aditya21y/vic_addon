"""Custom Sales Order: bikin PO per supplier, kepisah antara Reguler dan Dropship.

Supplier tiap item ikut turun dari Costing -> Quotation -> Sales Order lewat field
`custom_supplier` & `custom_supplier_quotation`, jadi PO ke supplier bisa dibikin
otomatis tanpa milih supplier manual lagi.
"""

import frappe
from frappe import _

from vic_addon.vic.dropship import DROPSHIP, REGULER


@frappe.whitelist()
def make_purchase_orders(sales_order):
	"""Bikin draft PO dari Sales Order: item digrup per supplier + per tipe transaksi.

	Digrup per tipe juga karena satu SO bisa campur: sebagian dikirim ke gudang sendiri
	(Reguler), sebagian dikirim supplier langsung ke lapangan (Dropship). Dua-duanya beda
	alamat kirim dan beda alur dokumen, jadi PO-nya juga dipisah.

	Yang bikin dokumennya tetap `make_purchase_order` bawaan ERPNext (biar dapet handling
	currency, exchange rate, dan sisa qty yang belum di-PO), kita cuma nentuin suppliernya
	dari SQTN terus ngisi harga beli, link SQTN, dan tipe transaksinya.
	"""
	from erpnext.selling.doctype.sales_order.sales_order import make_purchase_order

	doc = frappe.get_doc("Sales Order", sales_order)
	doc.check_permission("read")

	items_by_type = get_items_by_transaction_type(doc)
	if not items_by_type:
		frappe.throw(
			_("No item in this Sales Order has a Supplier. Fill Supplier Quotation info first."),
			title=_("Supplier Not Found"),
		)

	purchase_orders = []
	for transaction_type, supplier_by_item in items_by_type.items():
		selected_items = [
			{"item_code": item_code, "supplier": supplier}
			for item_code, supplier in supplier_by_item.items()
		]

		for purchase_order in make_purchase_order(sales_order, selected_items) or []:
			set_supplier_quotation_details(purchase_order, doc)
			set_transaction_type_details(purchase_order, doc, transaction_type)
			purchase_order.save()
			purchase_orders.append(purchase_order.name)

	return purchase_orders


def get_items_by_transaction_type(doc):
	"""Supplier per item, dikelompokin dulu per tipe transaksi."""
	items_by_type = {}

	for item in doc.items:
		if not item.custom_supplier:
			continue

		transaction_type = item.custom_transaction_type or REGULER
		supplier_by_item = items_by_type.setdefault(transaction_type, {})

		existing_supplier = supplier_by_item.get(item.item_code)
		if existing_supplier and existing_supplier != item.custom_supplier:
			frappe.throw(
				_(
					"Item {0} comes from two different suppliers ({1} and {2}). Use separate Sales Orders for each supplier."
				).format(item.item_code, existing_supplier, item.custom_supplier)
			)

		supplier_by_item[item.item_code] = item.custom_supplier

	return items_by_type


def set_transaction_type_details(purchase_order, sales_order, transaction_type):
	"""Tandai tipe transaksi di PO, dan buat dropship alamat kirimnya ke customer/proyek."""
	for item in purchase_order.items:
		item.custom_transaction_type = transaction_type

	purchase_order.custom_transaction_type = transaction_type

	if transaction_type != DROPSHIP:
		return

	# barangnya dikirim supplier langsung ke lapangan, jadi alamat kirim PO ikut customer
	shipping_address = sales_order.shipping_address_name or sales_order.customer_address
	if shipping_address:
		purchase_order.shipping_address = shipping_address
		purchase_order.shipping_address_display = (
			sales_order.shipping_address or sales_order.address_display
		)

	purchase_order.customer = sales_order.customer
	purchase_order.customer_name = sales_order.customer_name
	purchase_order.customer_contact_person = sales_order.contact_person
	purchase_order.customer_contact_display = sales_order.contact_display




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
