"""Custom Sales Order: bikin PO per supplier, kepisah antara Reguler dan Dropship.

Supplier tiap item ikut turun dari Costing -> Quotation -> Sales Order lewat field
`custom_supplier` & `custom_supplier_quotation`, jadi PO ke supplier bisa dibikin
otomatis tanpa milih supplier manual lagi.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from vic_addon.vic.dropship import DROPSHIP, REGULER


@frappe.whitelist()
def get_items_for_purchase_order(sales_order):
	"""Baris SO yang masih bisa di-PO, buat isi tabel di modal `Purchase Order (per Supplier)`.

	Supplier-nya diisi dari SQTN yang nempel di baris item, tapi di modal masih bisa diganti -
	kasus barang habis di supplier pertama (R&C ke-6 di sheet Costing). Baris yang gak punya
	supplier tetap dibalikin dengan kolom supplier kosong, biar user yang milih di modal.
	"""
	doc = frappe.get_doc("Sales Order", sales_order)
	doc.check_permission("read")

	pending_qty = get_pending_qty(doc)
	rows = []

	for item in doc.items:
		remaining = pending_qty.get(item.name)
		if not remaining:
			continue

		rows.append(
			{
				"sales_order_item": item.name,
				"item_code": item.item_code,
				"item_name": item.item_name,
				"uom": item.uom,
				"pending_qty": flt(
					remaining / (flt(item.conversion_factor) or 1), item.precision("qty")
				),
				"transaction_type": item.custom_transaction_type or REGULER,
				"supplier": item.custom_supplier,
				"supplier_quotation": item.custom_supplier_quotation,
			}
		)

	return rows


@frappe.whitelist()
def make_purchase_orders(sales_order, selected_items=None):
	"""Bikin draft PO dari Sales Order: item digrup per supplier + per tipe transaksi.

	Digrup per tipe juga karena satu SO bisa campur: sebagian dikirim ke gudang sendiri
	(Reguler), sebagian dikirim supplier langsung ke lapangan (Dropship). Dua-duanya beda
	alamat kirim dan beda alur dokumen, jadi PO-nya juga dipisah.

	`selected_items` itu isian dari modal: baris mana aja yang mau di-PO plus suppliernya.
	Kalau gak dikasih (dipanggil dari script), suppliernya diambil dari SQTN di baris item.

	Yang bikin dokumennya tetap `make_purchase_order` bawaan ERPNext (biar dapet handling
	currency dan exchange rate), kita yang nentuin suppliernya, ngisi harga beli, link SQTN,
	tipe transaksi, dan sisa qty yang beneran belum di-PO.
	"""
	from erpnext.selling.doctype.sales_order.sales_order import make_purchase_order

	doc = frappe.get_doc("Sales Order", sales_order)
	doc.check_permission("read")

	pending_qty = get_pending_qty(doc)
	validate_pending_qty(doc, pending_qty)

	supplier_by_row = get_supplier_by_row(doc, pending_qty, selected_items)
	groups = get_rows_by_group(doc, supplier_by_row)

	if not groups:
		frappe.throw(
			_("No item in this Sales Order has a Supplier. Fill Supplier Quotation info first."),
			title=_("Supplier Not Found"),
		)

	purchase_orders = []
	for (transaction_type, supplier), rows in groups.items():
		selected = [
			{"item_code": item_code, "supplier": supplier}
			for item_code in {row.item_code for row in rows}
		]
		# `make_purchase_order` milih baris SO cuma dari item code, padahal item code yang sama
		# bisa muncul di beberapa baris dengan supplier atau tipe transaksi beda - jadi barisnya
		# disaring lagi ke baris punya grup ini
		rows_of_group = {row.name for row in rows}

		# `make_purchase_order` nge-insert dokumennya di dalam sana, jadi penyesuaian tanggalnya
		# nebeng hook `before_validate` lewat flag ini
		frappe.flags.purchase_order_from_sales_order = True
		try:
			created = make_purchase_order(sales_order, selected) or []
		finally:
			frappe.flags.purchase_order_from_sales_order = False

		for purchase_order in created:
			set_supplier_quotation_details(purchase_order, doc)
			set_transaction_type_details(purchase_order, doc, transaction_type)

			if not set_pending_qty(purchase_order, pending_qty, rows_of_group):
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

	for item in doc.items:
		remaining = flt(item.stock_qty) - ordered_qty.get(item.name, 0)
		if remaining > 0:
			pending_qty[item.name] = remaining

	return pending_qty


def validate_pending_qty(doc, pending_qty):
	"""Tolak kalau semua item udah ada PO-nya, dan kasih tau baris mana yang dilewatin."""
	if not pending_qty:
		frappe.throw(
			_(
				"Every item in this Sales Order already has an active Purchase Order ({0}). Cancel the Purchase Order first if it needs to be recreated."
			).format(", ".join(get_active_purchase_orders(doc.name))),
			title=_("Purchase Order Already Exists"),
		)

	ordered_items = [
		item for item in doc.items if item.name not in pending_qty and item.custom_supplier
	]
	if ordered_items:
		frappe.msgprint(
			_("These items already have an active Purchase Order and are skipped: {0}").format(
				", ".join(f"#{item.idx} {item.item_code}" for item in ordered_items)
			),
			title=_("Item Skipped"),
			indicator="orange",
		)


def get_supplier_by_row(doc, pending_qty, selected_items=None):
	"""Supplier per baris SO: dari modal kalau ada, kalau enggak dari SQTN di baris itemnya."""
	if isinstance(selected_items, str):
		selected_items = frappe.parse_json(selected_items)

	if not selected_items:
		return {
			item.name: item.custom_supplier
			for item in doc.items
			if item.custom_supplier and item.name in pending_qty
		}

	supplier_by_row = {}
	for row in selected_items:
		row = frappe._dict(row)
		if row.supplier and row.sales_order_item in pending_qty:
			supplier_by_row[row.sales_order_item] = row.supplier

	return supplier_by_row


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


def set_pending_qty(purchase_order, pending_qty, rows_of_group):
	"""Potong PO ke sisa qty yang belum di-PO, baris yang udah ketutup dibuang.

	Balikin jumlah baris yang tersisa, biar PO kosong bisa dibatalin sama pemanggilnya.
	"""
	items = []

	for item in purchase_order.items:
		if not item.sales_order_item:
			# baris yang gak nempel ke baris SO (product bundle), biarin apa adanya
			items.append(item)
			continue

		if item.sales_order_item not in rows_of_group:
			continue

		remaining = pending_qty.get(item.sales_order_item, 0)
		if remaining <= 0:
			continue

		if flt(item.stock_qty) > remaining:
			item.qty = flt(remaining / (flt(item.conversion_factor) or 1), item.precision("qty"))

		items.append(item)

	purchase_order.items = items

	return len(items)


def set_schedule_date(doc, method=None):
	"""Hook `before_validate` Purchase Order: Required By minimal sama dengan tanggal PO.

	Tanggalnya ngikut delivery date Sales Order, dan buat SO yang tanggal kirimnya udah lewat
	ERPNext bakal nolak PO-nya (`Required By cannot be before Date`). Jadi yang udah lewat
	dimajuin ke tanggal PO - user tinggal ganti manual di draft-nya kalau perlu.

	Cuma jalan buat PO yang lahir dari tombol Create > Purchase Order (per Supplier), jadi PO
	yang diisi manual tetap divalidasi apa adanya sama ERPNext.
	"""
	if not (doc.is_new() and frappe.flags.get("purchase_order_from_sales_order")):
		return

	purchase_order = doc
	transaction_date = getdate(purchase_order.transaction_date)

	for item in purchase_order.items:
		if not item.schedule_date or getdate(item.schedule_date) < transaction_date:
			item.schedule_date = transaction_date

	purchase_order.schedule_date = min(getdate(item.schedule_date) for item in purchase_order.items)


def get_rows_by_group(doc, supplier_by_row):
	"""Baris Sales Order dikelompokin per supplier + tipe transaksi - satu grup satu PO.

	Item yang sama boleh nongol di beberapa baris. Selama supplier dan tipe transaksinya sama,
	barisnya digabung ke PO yang sama. Kalau suppliernya beda - misalnya sebagian dibeli dari
	Common Supplier, sebagian dari Electrical Supplier - PO-nya kepisah sendiri-sendiri, gitu
	juga kalau tipe transaksinya beda (Reguler dikirim ke gudang, Dropship langsung ke lapangan).
	"""
	groups = {}

	for item in doc.items:
		supplier = supplier_by_row.get(item.name)
		if not supplier:
			continue

		key = (item.custom_transaction_type or REGULER, supplier)
		groups.setdefault(key, []).append(item)

	return groups


def set_transaction_type_details(purchase_order, sales_order, transaction_type):
	"""Tandai tipe transaksi di PO, dan buat dropship alamat kirimnya ke customer/proyek."""
	for item in purchase_order.items:
		item.custom_transaction_type = transaction_type

	purchase_order.custom_transaction_type = transaction_type

	if transaction_type != DROPSHIP:
		return

	# barangnya dikirim supplier langsung ke lapangan, jadi alamat kirim PO ikut customer
	# (ERPNext-nya sendiri nolak alamat non-Company di sini, lihat `dropship.stash_customer_shipping_address`)
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

	Baris yang suppliernya diganti di modal dilewatin: penawaran itu punya supplier lain, jadi
	harga maupun link-nya gak nyambung lagi.
	"""
	sales_order_items = {item.name: item for item in sales_order.items}

	for item in purchase_order.items:
		sales_order_item = sales_order_items.get(item.sales_order_item)
		if not (sales_order_item and sales_order_item.custom_supplier_quotation):
			continue

		if sales_order_item.custom_supplier and sales_order_item.custom_supplier != purchase_order.supplier:
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
