"""Buang fitur Target Grand Total di Purchase Invoice (field + property setter-nya).

Fitur-nya (rate item disesuaikan ke Target Grand Total tagihan supplier) dicabut. Custom field
`custom_target_grand_total` dihapus - fixtures cuma nambah/ngubah, jadi lewat patch. Hook & mixin-nya
udah dicopot di kode.
"""

import frappe


def execute():
	frappe.delete_doc_if_exists("Custom Field", "Purchase Invoice-custom_target_grand_total")
	frappe.clear_cache(doctype="Purchase Invoice")
