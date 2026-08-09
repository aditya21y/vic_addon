"""Custom Sales Order: bikin PO per supplier, kepisah antara Reguler dan Dropship.

Supplier tiap item ikut turun dari Costing -> Quotation -> Sales Order lewat field
`custom_supplier` & `custom_supplier_quotation`, jadi PO ke supplier bisa dibikin
otomatis tanpa milih supplier manual lagi.
"""

import frappe
from frappe import _
from frappe.utils import flt

from vic_addon.vic.dropship import DROPSHIP, REGULER


@frappe.whitelist()
def make_purchase_orders(sales_order):
	"""Bikin draft PO dari Sales Order: item digrup per supplier + per tipe transaksi.

	Digrup per tipe juga karena satu SO bisa campur: sebagian dikirim ke gudang sendiri
	(Reguler), sebagian dikirim supplier langsung ke lapangan (Dropship). Dua-duanya beda
	alamat kirim dan beda alur dokumen, jadi PO-nya juga dipisah.

	Yang bikin dokumennya tetap `make_purchase_order` bawaan ERPNext (biar dapet handling
	currency dan exchange rate), kita yang nentuin suppliernya dari SQTN, ngisi harga beli,
	link SQTN, tipe transaksi, dan sisa qty yang beneran belum di-PO.
	"""
	from erpnext.selling.doctype.sales_order.sales_order import make_purchase_order

	doc = frappe.get_doc("Sales Order", sales_order)
	doc.check_permission("read")

	pending_qty = get_pending_qty(doc)
	items_by_type = get_items_by_transaction_type(doc, pending_qty)

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
		# `make_purchase_order` milih baris SO cuma dari item code, padahal item code yang sama
		# bisa muncul di baris Reguler dan Dropship sekaligus - jadi barisnya disaring lagi
		rows_of_type = {
			item.name
			for item in doc.items
			if (item.custom_transaction_type or REGULER) == transaction_type
		}

		for purchase_order in make_purchase_order(sales_order, selected_items) or []:
			set_supplier_quotation_details(purchase_order, doc)
			set_transaction_type_details(purchase_order, doc, transaction_type)

			if not set_pending_qty(purchase_order, pending_qty, rows_of_type):
				# semua barisnya udah ketutup PO lain, dokumennya gak usah ada
				purchase_order.delete()
				continue

			purchase_order.save()
			purchase_orders.append(purchase_order.name)

	return purchase_orders


def get_ordered_qty(sales_order):
	"""Qty tiap baris SO yang udah masuk PO aktif (draft + submitted).

	ERPNext cuma ngitung PO submitted lewat `Sales Order Item.ordered_qty`, jadi klik tombol
	dua kali bakal bikin PO draft dobel. Di sini draft ikut dihitung, sedangkan PO yang udah
	dibatalin (docstatus 2) sengaja gak dihitung - itu yang bikin item dari PO batal bisa
	dibikinin PO baru lagi.
	"""
	rows = frappe.get_all(
		"Purchase Order Item",
		filters={"sales_order": sales_order, "docstatus": ["<", 2]},
		fields=["sales_order_item", "stock_qty"],
	)

	ordered_qty = {}
	for row in rows:
		if row.sales_order_item:
			ordered_qty[row.sales_order_item] = (
				ordered_qty.get(row.sales_order_item, 0) + flt(row.stock_qty)
			)

	return ordered_qty


def get_pending_qty(doc):
	"""Sisa qty (stock uom) tiap baris SO yang belum ada PO aktifnya."""
	ordered_qty = get_ordered_qty(doc.name)
	pending_qty = {}
	ordered_items = []

	for item in doc.items:
		remaining = flt(item.stock_qty) - ordered_qty.get(item.name, 0)

		if remaining > 0:
			pending_qty[item.name] = remaining
		elif item.custom_supplier:
			ordered_items.append(item)

	if not pending_qty:
		frappe.throw(
			_(
				"Every item in this Sales Order already has an active Purchase Order ({0}). Cancel the Purchase Order first if it needs to be recreated."
			).format(", ".join(get_active_purchase_orders(doc.name))),
			title=_("Purchase Order Already Exists"),
		)

	if ordered_items:
		frappe.msgprint(
			_("These items already have an active Purchase Order and are skipped: {0}").format(
				", ".join(f"#{item.idx} {item.item_code}" for item in ordered_items)
			),
			title=_("Item Skipped"),
			indicator="orange",
		)

	return pending_qty


def get_active_purchase_orders(sales_order):
	return sorted(
		{
			row.parent
			for row in frappe.get_all(
				"Purchase Order Item",
				filters={"sales_order": sales_order, "docstatus": ["<", 2]},
				fields=["parent"],
			)
		}
	)


def set_pending_qty(purchase_order, pending_qty, rows_of_type):
	"""Potong PO ke sisa qty yang belum di-PO, baris yang udah ketutup dibuang.

	Balikin jumlah baris yang tersisa, biar PO kosong bisa dibatalin sama pemanggilnya.
	"""
	items = []

	for item in purchase_order.items:
		if not item.sales_order_item:
			# baris yang gak nempel ke baris SO (product bundle), biarin apa adanya
			items.append(item)
			continue

		if item.sales_order_item not in rows_of_type:
			continue

		remaining = pending_qty.get(item.sales_order_item, 0)
		if remaining <= 0:
			continue

		if flt(item.stock_qty) > remaining:
			item.qty = flt(remaining / (flt(item.conversion_factor) or 1), item.precision("qty"))

		items.append(item)

	purchase_order.items = items

	return len(items)


def get_items_by_transaction_type(doc, pending_qty):
	"""Supplier per item, dikelompokin dulu per tipe transaksi."""
	items_by_type = {}

	for item in doc.items:
		if not item.custom_supplier or item.name not in pending_qty:
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
