"""Nyalain "Show Project in Print" di Costing lama yang Project-nya udah keisi.

Dulu nama Project selalu dicetak di print format Costing (dengan label Subject). Sekarang Project
dan Subject cuma dicetak kalau centangannya nyala, default-nya mati - tanpa patch ini Project di
Costing lama mendadak ilang dari kertasnya. Subject gak perlu: field-nya baru, belum ada isinya.
"""

import frappe


def execute():
	frappe.reload_doc("vic", "doctype", "costing")

	frappe.db.sql(
		"""
		update `tabCosting`
		set show_project_in_print = 1
		where ifnull(project, '') != ''
		"""
	)
