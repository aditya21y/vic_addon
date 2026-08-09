"""Validasi Purchase Order terhadap Supplier Quotation-nya.

PO yang dibikin dari Sales Order bawa link SQTN di tiap baris (`custom_supplier_quotation` +
`custom_supplier_quotation_item`). Link itu yang jadi jaminan harga beli PO sama dengan harga
yang udah dinego di SQTN, makanya sebelum PO disimpan dicek dulu:

- SQTN-nya beneran ada, udah disubmit, dan suppliernya sama dengan supplier PO
- barisnya beneran baris SQTN itu dan item code-nya sama
- baris SQTN-nya sama dengan yang nempel di baris Sales Order-nya
- total qty yang di-PO (termasuk PO lain yang masih aktif) gak lewat dari qty di SQTN
"""

import frappe
from frappe import _
from frappe.utils import flt


def validate_supplier_quotation(doc, method=None):
	ordered_qty = get_ordered_qty_by_quotation_item(doc)

	for item in doc.items:
		if not item.custom_supplier_quotation:
			warn_if_quotation_missing(item)
			continue

		validate_quotation(doc, item)
		quotation_item = get_quotation_item(item)
		validate_sales_order_link(item)
		validate_qty(doc, item, quotation_item, ordered_qty)


def validate_quotation(doc, item):
	quotation = frappe.db.get_value(
		"Supplier Quotation", item.custom_supplier_quotation, ["supplier", "docstatus"], as_dict=True
	)

	if not quotation:
		frappe.throw(
			_("Row #{0}: Supplier Quotation {1} does not exist.").format(
				item.idx, item.custom_supplier_quotation
			),
			title=_("Supplier Quotation Not Found"),
		)

	if quotation.docstatus != 1:
		frappe.throw(
			_("Row #{0}: Supplier Quotation {1} is not submitted.").format(
				item.idx, item.custom_supplier_quotation
			),
			title=_("Supplier Quotation Not Submitted"),
		)

	if quotation.supplier != doc.supplier:
		frappe.throw(
			_(
				"Row #{0}: Supplier Quotation {1} belongs to supplier {2}, but this Purchase Order is for {3}."
			).format(item.idx, item.custom_supplier_quotation, quotation.supplier, doc.supplier),
			title=_("Supplier Mismatch"),
		)


def get_quotation_item(item):
	"""Baris SQTN yang jadi acuan baris PO ini."""
	filters = {"parent": item.custom_supplier_quotation, "item_code": item.item_code}
	if item.custom_supplier_quotation_item:
		filters["name"] = item.custom_supplier_quotation_item

	quotation_item = frappe.db.get_value(
		"Supplier Quotation Item", filters, ["name", "stock_qty", "uom"], as_dict=True
	)

	if not quotation_item:
		frappe.throw(
			_("Row #{0}: Item {1} is not in Supplier Quotation {2}.").format(
				item.idx, item.item_code, item.custom_supplier_quotation
			),
			title=_("Item Not Quoted"),
		)

	item.custom_supplier_quotation_item = quotation_item.name

	return quotation_item


def validate_sales_order_link(item):
	"""Baris SQTN di PO harus sama dengan yang dipilih di baris Sales Order-nya."""
	if not item.sales_order_item:
		return

	quotation = frappe.db.get_value(
		"Sales Order Item", item.sales_order_item, "custom_supplier_quotation"
	)

	if quotation and quotation != item.custom_supplier_quotation:
		frappe.throw(
			_(
				"Row #{0}: Sales Order {1} quotes this item from Supplier Quotation {2}, not {3}."
			).format(item.idx, item.sales_order, quotation, item.custom_supplier_quotation),
			title=_("Supplier Quotation Mismatch"),
		)


def validate_qty(doc, item, quotation_item, ordered_qty):
	"""Total qty yang di-PO gak boleh lewat dari qty yang ditawarin di SQTN."""
	quoted_qty = flt(quotation_item.stock_qty)
	if not quoted_qty:
		return

	total_qty = flt(item.stock_qty) + ordered_qty.get(quotation_item.name, 0)
	precision = item.precision("stock_qty")

	if flt(total_qty, precision) > flt(quoted_qty, precision):
		frappe.throw(
			_(
				"Row #{0}: Item {1} would be ordered {2} in total against Supplier Quotation {3}, more than the quoted {4}."
			).format(
				item.idx,
				item.item_code,
				flt(total_qty, precision),
				item.custom_supplier_quotation,
				flt(quoted_qty, precision),
			),
			title=_("Qty More Than Quoted"),
		)


def get_ordered_qty_by_quotation_item(doc):
	"""Qty per baris SQTN yang udah kepakai di PO lain yang masih aktif (draft + submitted)."""
	quotation_items = [
		item.custom_supplier_quotation_item for item in doc.items if item.custom_supplier_quotation_item
	]
	if not quotation_items:
		return {}

	rows = frappe.get_all(
		"Purchase Order Item",
		filters={
			"custom_supplier_quotation_item": ["in", quotation_items],
			"docstatus": ["<", 2],
			"parent": ["!=", doc.name or ""],
		},
		fields=["custom_supplier_quotation_item", "stock_qty"],
	)

	ordered_qty = {}
	for row in rows:
		ordered_qty[row.custom_supplier_quotation_item] = (
			ordered_qty.get(row.custom_supplier_quotation_item, 0) + flt(row.stock_qty)
		)

	return ordered_qty


def warn_if_quotation_missing(item):
	"""Baris Sales Order-nya punya SQTN tapi barisnya di PO kosong - kasih tau, gak diblokir."""
	if not item.sales_order_item:
		return

	quotation = frappe.db.get_value(
		"Sales Order Item", item.sales_order_item, "custom_supplier_quotation"
	)
	if not quotation:
		return

	frappe.msgprint(
		_("Row #{0}: Item {1} is quoted in Supplier Quotation {2}, but this row is not linked to it.").format(
			item.idx, item.item_code, quotation
		),
		title=_("Supplier Quotation Not Linked"),
		indicator="orange",
	)
