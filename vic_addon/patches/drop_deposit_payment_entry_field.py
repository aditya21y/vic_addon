"""Buang field Deposit Payment Entry di Purchase Order - diganti indikator + tombol JS.

Link ke PE deposit sekarang ditampilin lewat dashboard JS (public/js/vendor_deposit.js), jadi custom
field-nya gak dipakai lagi. Fixtures cuma nambah/ngubah, jadi penghapusannya lewat patch.
"""

import frappe


def execute():
	frappe.delete_doc_if_exists("Custom Field", "Purchase Order-custom_deposit_payment_entry")
	frappe.clear_cache(doctype="Purchase Order")
