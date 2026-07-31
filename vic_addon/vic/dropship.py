"""Skema dropship: barang dikirim supplier langsung ke lapangan, dokumennya tetap lengkap.

ERPNext punya dropship bawaan (`delivered_by_supplier`), tapi itu justru ngecualiin item
dropship dari Purchase Receipt dan Delivery Note, dan nganggep SO udah terkirim begitu PO
disubmit. Di sini dua dokumen itu tetap harus ada, jadi dropship diperlakukan sebagai
atribut pengiriman doang - rantai dokumennya tetap standar:

	PO (alamat kirim ke customer/proyek)
	  -> Delivery Note
	       -> tepat sebelum DN disubmit, Purchase Receipt dibuat & disubmit otomatis

Barangnya lewat gudang transit dropship: masuk lewat Purchase Receipt, keluar lewat Delivery
Note di tanggal yang sama, jadi saldonya nol tapi stock ledger dan valuasinya tetap kecatat.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

DROPSHIP = "Dropship"
REGULER = "Reguler"
MIXED = "Mixed"

# dokumen dropship pakai seri nomor sendiri biar gak ganggu penomoran transaksi reguler
DROPSHIP_NAMING_SERIES = {
	"Delivery Note": "MAT-DN-DS-.YYMM.-",
	"Purchase Receipt": "MAT-PRE-DS-.YYMM.-",
}


def set_transaction_type(doc, method=None):
	"""Ringkasan tipe di header, diambil dari tipe baris itemnya."""
	types = {(item.get("custom_transaction_type") or REGULER) for item in doc.get("items") or []}

	if not types:
		return

	doc.custom_transaction_type = types.pop() if len(types) == 1 else MIXED


def set_dropship_naming_series(doc, method=None):
	"""Hook `before_naming`: dokumen dropship pakai naming series sendiri."""
	series = DROPSHIP_NAMING_SERIES.get(doc.doctype)
	if not series or doc.name or not doc.meta.get_field("naming_series"):
		return

	# tipe header belum dihitung waktu penamaan, jadi dihitung duluan di sini
	set_transaction_type(doc)

	if doc.custom_transaction_type == DROPSHIP:
		doc.naming_series = series


def set_dropship_warehouse_on_items(doc, method=None):
	"""Item dropship keluar/masuk lewat gudang transit dropship."""
	warehouse = None

	for item in doc.get("items") or []:
		if item.get("custom_transaction_type") != DROPSHIP:
			continue

		warehouse = warehouse or get_dropship_warehouse(doc.company)
		item.warehouse = warehouse


def get_dropship_warehouse(company):
	"""Gudang transit dropship. Diambil dari Company, dibuatin kalau belum ada."""
	warehouse = frappe.db.get_value("Company", company, "custom_dropship_warehouse")
	if warehouse:
		return warehouse

	abbreviation = frappe.db.get_value("Company", company, "abbr")
	warehouse = f"Dropship - {abbreviation}"

	if not frappe.db.exists("Warehouse", warehouse):
		parent = f"All Warehouses - {abbreviation}"
		frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": "Dropship",
				"company": company,
				"parent_warehouse": parent if frappe.db.exists("Warehouse", parent) else None,
				"is_group": 0,
			}
		).insert(ignore_permissions=True)

	frappe.db.set_value("Company", company, "custom_dropship_warehouse", warehouse)

	return warehouse


@frappe.whitelist()
def make_delivery_note(source_name, target_doc=None):
	"""Bikin Delivery Note dari Purchase Order dropship.

	DN-nya tetap dibikin dari Sales Order (dokumen ke customer), cuma isinya dibatasi ke item
	yang ada di PO ini, dan barangnya keluar dari gudang transit dropship.
	"""
	from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note as make_dn

	purchase_order = frappe.get_doc("Purchase Order", source_name)
	purchase_order.check_permission("read")

	dropship_items = [
		item for item in purchase_order.items if item.custom_transaction_type == DROPSHIP
	]
	if not dropship_items:
		frappe.throw(_("No Dropship item in this Purchase Order."), title=_("Not a Dropship PO"))

	sales_orders = {item.sales_order for item in dropship_items if item.sales_order}
	if not sales_orders:
		frappe.throw(
			_("Dropship items in this Purchase Order are not linked to any Sales Order."),
			title=_("Sales Order Not Found"),
		)

	if len(sales_orders) > 1:
		frappe.throw(
			_("This Purchase Order covers more than one Sales Order ({0}). Create the Delivery Note from each Sales Order instead.").format(
				", ".join(sorted(sales_orders))
			)
		)

	sales_order_items = {item.sales_order_item for item in dropship_items}
	delivery_note = make_dn(sales_orders.pop(), target_doc)
	delivery_note.items = [
		item for item in delivery_note.items if item.so_detail in sales_order_items
	]

	warehouse = get_dropship_warehouse(delivery_note.company)
	for item in delivery_note.items:
		item.custom_transaction_type = DROPSHIP
		item.warehouse = warehouse

	set_transaction_type(delivery_note)

	return delivery_note


def make_dropship_purchase_receipt(doc, method=None):
	"""Hook `before_submit` Delivery Note: terima barangnya dulu baru dikirim.

	Barang dropship gak pernah mampir ke gudang fisik, tapi stoknya harus ada sebelum DN
	disubmit. Jadi Purchase Receipt atas PO-nya dibuat & disubmit otomatis di tanggal yang
	sama dengan DN.
	"""
	if doc.custom_transaction_type != DROPSHIP or doc.custom_dropship_purchase_receipt:
		return

	quantity_by_sales_order_item = {
		item.so_detail: flt(item.qty)
		for item in doc.items
		if item.custom_transaction_type == DROPSHIP and item.so_detail
	}
	if not quantity_by_sales_order_item:
		return

	if getdate(doc.posting_date) > getdate():
		frappe.throw(
			_(
				"Posting Date {0} is in the future. Purchase Receipt for a dropship delivery cannot be dated in the future, so set the Delivery Note date to today or earlier."
			).format(frappe.format(doc.posting_date, {"fieldtype": "Date"})),
			title=_("Dropship Purchase Receipt"),
		)

	purchase_receipts = []
	for purchase_order in get_purchase_orders_to_receive(quantity_by_sales_order_item):
		receipt = create_purchase_receipt(doc, purchase_order, quantity_by_sales_order_item)
		if receipt:
			purchase_receipts.append(receipt.name)

	if not purchase_receipts:
		return

	doc.custom_dropship_purchase_receipt = purchase_receipts[0]
	frappe.msgprint(
		_("Purchase Receipt {0} created automatically for this dropship delivery.").format(
			", ".join(purchase_receipts)
		),
		title=_("Dropship Purchase Receipt"),
		indicator="green",
		alert=True,
	)


def get_purchase_orders_to_receive(quantity_by_sales_order_item):
	"""Purchase Order submitted yang barangnya belum diterima, buat baris DN ini."""
	rows = frappe.get_all(
		"Purchase Order Item",
		filters={
			"sales_order_item": ["in", list(quantity_by_sales_order_item)],
			"docstatus": 1,
		},
		fields=["parent", "qty", "received_qty"],
	)

	return sorted({row.parent for row in rows if flt(row.qty) > flt(row.received_qty)})


def create_purchase_receipt(delivery_note, purchase_order, quantity_by_sales_order_item):
	from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt

	receipt = make_purchase_receipt(purchase_order)
	receipt.posting_date = delivery_note.posting_date
	receipt.posting_time = delivery_note.posting_time
	receipt.set_posting_time = 1

	warehouse = get_dropship_warehouse(delivery_note.company)
	items = []

	for item in receipt.items:
		delivered_qty = quantity_by_sales_order_item.get(item.sales_order_item)
		if not delivered_qty:
			continue

		# terima sebanyak yang dikirim, gak lebih dari sisa PO
		item.qty = min(flt(item.qty), delivered_qty)
		item.received_qty = item.qty
		item.warehouse = warehouse
		item.custom_transaction_type = DROPSHIP
		items.append(item)

	if not items:
		return None

	receipt.items = items
	set_transaction_type(receipt)
	receipt.insert(ignore_permissions=True)
	receipt.submit()

	return receipt
