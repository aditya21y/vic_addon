"""Purchase Request (Material Request): nomor PO customer ikut turun dari Sales Order.

Permintaan pembelian yang lahir dari Sales Order dicetak dengan nomor PO customer di kepalanya
(lihat print format Purchase Request), padahal Material Request bawaan ERPNext gak nyimpen nomor
itu. Di sini nomornya ditarik dari Sales Order yang nempel di baris item - kalau permintaannya
diketik manual, field-nya dibiarin buat diisi sendiri.
"""

import frappe


def set_customer_po_no(doc, method=None):
	"""Hook `before_validate` Material Request: isi Customer's Purchase Order dari Sales Order."""
	if doc.get("custom_po_no"):
		return

	sales_orders = get_sales_orders(doc)
	if not sales_orders:
		return

	po_numbers = frappe.get_all(
		"Sales Order", filters={"name": ["in", sales_orders]}, pluck="po_no", order_by="creation"
	)
	po_numbers = [number for number in po_numbers if number]

	if po_numbers:
		doc.custom_po_no = ", ".join(dict.fromkeys(po_numbers))


def get_sales_orders(doc):
	"""Sales Order yang nempel di baris-baris permintaan ini."""
	return list({item.sales_order for item in doc.get("items") or [] if item.get("sales_order")})
