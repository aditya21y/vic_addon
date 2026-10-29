"""Retur dropship: customer balikin barang dropship -> barangnya balik ke supplier juga.

Alur maju dropship (lihat dropship.py): Delivery Note disubmit -> Purchase Receipt dibikin otomatis
lewat gudang transit dropship. Kebalikannya, waktu **retur Delivery Note** (Create > Return dari DN
dropship) disubmit:

1. Barangnya masuk lagi ke gudang transit lewat retur DN itu (bawaan ERPNext).
2. **Retur Purchase Receipt** dibikin & disubmit otomatis atas PR dropship-nya - barang keluar dari
   gudang transit, balik ke supplier. Serial No yang diretur customer ikut dibalikin.
3. Kalau baris PR itu **udah ditagih** (ada Purchase Invoice-nya), **retur Purchase Invoice** (debit
   note) dibikin & disubmit juga, sebanyak qty yang diretur.

Gak ada Payment Entry yang dibikin, walaupun invoice-nya udah dibayar: debit note-nya nyimpen
outstanding sendiri (piutang ke supplier), dibereskan manual.

Dibikin di `on_submit` (bukan `before_submit` kayak alur maju): stoknya baru masuk gudang transit
setelah retur DN-nya kecatat, dan retur PR baru bisa ngeluarin stok yang udah ada.

Retur PR & PI yang dibikin nyimpen nomor retur DN-nya (`custom_dropship_delivery_note`). Retur DN
dibatalin -> retur PI & PR-nya ikut dibatalin duluan.
"""

import frappe
from frappe import _
from frappe.utils import flt

from vic_addon.vic.dropship import DROPSHIP, get_dropship_warehouse
from vic_addon.vic.serial_no import get_serial_nos

LINK_FIELD = "custom_dropship_delivery_note"


def make_dropship_returns(doc, method=None):
	"""Hook `on_submit` Delivery Note: retur DN dropship -> retur PR (+ retur PI kalau udah ditagih)."""
	if not doc.get("is_return"):
		return

	rows = [item for item in doc.items if item.get("custom_transaction_type") == DROPSHIP and item.so_detail]
	if not rows:
		return

	receipt_rows = allocate_receipt_rows(doc, rows)
	if not receipt_rows:
		frappe.msgprint(
			_("No dropship Purchase Receipt found to return for this Delivery Note. Return the goods to the supplier manually."),
			title=_("Dropship Return"),
			indicator="orange",
		)
		return

	receipts = [
		make_receipt_return(doc, receipt, allocations)
		for receipt, allocations in group_by_parent(receipt_rows).items()
	]

	invoice_rows = allocate_invoice_rows(receipt_rows)
	invoices = [
		make_invoice_return(doc, invoice, allocations)
		for invoice, allocations in group_by_parent(invoice_rows).items()
	]

	doc.db_set("custom_dropship_purchase_receipt", receipts[0])

	message = _("Purchase Receipt return {0} created for this dropship return.").format(", ".join(receipts))
	if invoices:
		message += " " + _("Debit Note {0} created (no Payment Entry is made).").format(", ".join(invoices))
	frappe.msgprint(message, title=_("Dropship Return"), indicator="green", alert=True)


def allocate_receipt_rows(delivery_note, rows):
	"""Baris PR dropship yang diretur: list `(baris PR, qty, serial no)`.

	Qty retur tiap baris DN dibagi ke baris PR dropship atas baris SO yang sama, sebatas sisa yang
	belum diretur. PR yang dibikin buat DN asalnya didahuluin, sisanya dari yang terbaru.
	"""
	warehouse = get_dropship_warehouse(delivery_note.company)
	needed = {}
	serials = {}
	for item in rows:
		needed[item.so_detail] = needed.get(item.so_detail, 0) + abs(flt(item.qty))
		serials.setdefault(item.so_detail, []).extend(get_serial_nos(item))

	purchase_order_items = {
		row.name: row.sales_order_item
		for row in frappe.get_all(
			"Purchase Order Item",
			filters={"sales_order_item": ["in", list(needed)], "docstatus": 1},
			fields=["name", "sales_order_item"],
		)
	}
	if not purchase_order_items:
		return []

	candidates = frappe.get_all(
		"Purchase Receipt Item",
		filters={
			"purchase_order_item": ["in", list(purchase_order_items)],
			"warehouse": warehouse,
			"docstatus": 1,
			"qty": [">", 0],
		},
		fields=["name", "parent", "purchase_order_item", "qty", "returned_qty"],
		order_by="creation desc",
	)
	# PR dari DN asal retur ini duluan (PR dropship lama yang belum nyimpen nomor DN-nya: dari yang terbaru)
	origin = set(
		frappe.get_all(
			"Purchase Receipt",
			filters={LINK_FIELD: delivery_note.return_against, "docstatus": 1},
			pluck="name",
		)
	) if frappe.get_meta("Purchase Receipt").has_field(LINK_FIELD) else set()
	candidates.sort(key=lambda row: row.parent not in origin)

	allocations = []
	for row in candidates:
		sales_order_item = purchase_order_items[row.purchase_order_item]
		need = needed.get(sales_order_item, 0)
		available = flt(row.qty) - flt(row.returned_qty)
		if need <= 0 or available <= 0:
			continue

		qty = min(need, available)
		needed[sales_order_item] = need - qty
		taken, serials[sales_order_item] = serials[sales_order_item][: int(qty)], serials[sales_order_item][int(qty) :]
		allocations.append(frappe._dict(name=row.name, parent=row.parent, qty=qty, serial_nos=taken))

	short = {key: left for key, left in needed.items() if left > 0.0001}
	if short:
		frappe.throw(
			_("Returned qty is more than what was received through dropship Purchase Receipts for Sales Order item {0}.").format(
				", ".join(short)
			),
			title=_("Dropship Return"),
		)

	return allocations


def allocate_invoice_rows(receipt_rows):
	"""Baris Purchase Invoice yang ikut diretur: yang nagih baris PR tadi (`pr_detail`), sebatas qty
	yang belum diretur di invoice itu."""
	qty_by_receipt_row = {row.name: row.qty for row in receipt_rows}
	invoice_rows = frappe.get_all(
		"Purchase Invoice Item",
		filters={"pr_detail": ["in", list(qty_by_receipt_row)], "docstatus": 1},
		fields=["name", "parent", "pr_detail", "qty"],
		order_by="creation asc",
	)
	returns = set(
		frappe.get_all(
			"Purchase Invoice",
			filters={"name": ["in", list({row.parent for row in invoice_rows})], "is_return": 1},
			pluck="name",
		)
	) if invoice_rows else set()
	invoice_rows = [row for row in invoice_rows if row.parent not in returns]

	allocations = []
	for row in invoice_rows:
		need = qty_by_receipt_row.get(row.pr_detail, 0)
		available = flt(row.qty) - get_invoice_returned_qty(row.name)
		if need <= 0 or available <= 0:
			continue

		qty = min(need, available)
		qty_by_receipt_row[row.pr_detail] = need - qty
		allocations.append(frappe._dict(name=row.name, parent=row.parent, qty=qty))

	return allocations


def get_invoice_returned_qty(invoice_item):
	returned = frappe.get_all(
		"Purchase Invoice Item",
		filters={"purchase_invoice_item": invoice_item, "docstatus": 1},
		pluck="qty",
	)
	return abs(sum(flt(qty) for qty in returned))


def group_by_parent(rows):
	groups = {}
	for row in rows:
		groups.setdefault(row.parent, []).append(row)
	return groups


def make_receipt_return(delivery_note, receipt, allocations):
	from erpnext.controllers.sales_and_purchase_return import make_return_doc

	by_row = {row.name: row for row in allocations}
	doc = make_return_doc("Purchase Receipt", receipt)
	set_return_dates(doc, delivery_note)

	items = []
	for item in doc.items:
		row = by_row.get(item.purchase_receipt_item)
		if not row:
			continue

		item.qty = item.received_qty = -flt(row.qty, item.precision("qty"))
		item.stock_qty = item.qty * flt(item.conversion_factor or 1)
		item.rejected_qty = 0
		# Serial No yang diretur customer, bukan semua nomor di baris PR-nya
		item.serial_and_batch_bundle = None
		item.serial_no = "\n".join(row.serial_nos) if row.serial_nos else None
		item.use_serial_batch_fields = 1 if row.serial_nos else item.use_serial_batch_fields
		items.append(item)

	doc.items = items
	doc.set(LINK_FIELD, delivery_note.name)
	doc.insert(ignore_permissions=True)
	doc.submit()

	return doc.name


def make_invoice_return(delivery_note, invoice, allocations):
	from erpnext.controllers.sales_and_purchase_return import make_return_doc

	by_row = {row.name: row for row in allocations}
	doc = make_return_doc("Purchase Invoice", invoice)
	set_return_dates(doc, delivery_note)
	doc.update_stock = 0

	items = []
	for item in doc.items:
		row = by_row.get(item.purchase_invoice_item)
		if not row:
			continue

		item.qty = -flt(row.qty, item.precision("qty"))
		items.append(item)

	doc.items = items
	doc.set(LINK_FIELD, delivery_note.name)
	doc.insert(ignore_permissions=True)
	doc.submit()

	return doc.name


def set_return_dates(doc, delivery_note):
	doc.posting_date = delivery_note.posting_date
	doc.posting_time = delivery_note.posting_time
	doc.set_posting_time = 1


def cancel_dropship_returns(doc, method=None):
	"""Hook `before_cancel` Delivery Note: retur PI & PR dropship yang dibikin retur DN ini ikut
	dibatalin duluan - kalau enggak, stok gudang transit minus dan link-nya ngunci pembatalan."""
	if not doc.get("is_return") or not frappe.get_meta("Purchase Receipt").has_field(LINK_FIELD):
		return

	for doctype in ("Purchase Invoice", "Purchase Receipt"):
		for name in frappe.get_all(doctype, filters={LINK_FIELD: doc.name, "docstatus": 1}, pluck="name"):
			returned = frappe.get_doc(doctype, name)
			returned.flags.ignore_permissions = True
			# retur DN ini sendiri nge-link ke retur PR-nya (Dropship Purchase Receipt) - DN-nya lagi
			# dibatalin juga, jadi link itu gak boleh ngunci
			returned.flags.ignore_links = True
			returned.cancel()
