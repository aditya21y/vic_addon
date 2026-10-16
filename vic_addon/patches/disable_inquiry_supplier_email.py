"""Matiin Send Email di baris supplier Inquiry (Request for Quotation) yang masih draft.

Field Send Email sekarang disembunyiin dan default-nya 0 (property setter). Centangan itu yang
bikin ERPNext ngirim email portal ke supplier waktu Inquiry di-submit (`send_to_supplier`).
Draft lama masih kecentang 1 dari default bawaan, dan karena field-nya udah gak kelihatan, user
gak bisa ngilangin centangnya lagi - jadi dinolin di sini. Inquiry yang udah submitted dibiarin:
emailnya kalau ada udah terkirim.
"""

import frappe


def execute():
	frappe.db.sql(
		"""
		update `tabRequest for Quotation Supplier` supplier
		join `tabRequest for Quotation` rfq on rfq.name = supplier.parent
		set supplier.send_email = 0
		where rfq.docstatus = 0 and supplier.send_email = 1
		"""
	)
