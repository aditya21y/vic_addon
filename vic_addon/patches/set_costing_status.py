"""Isi Status di Costing yang udah ada: Quoted kalau udah pernah dibikinin Quotation."""

import frappe

from vic_addon.vic.doctype.costing.costing import update_status


def execute():
	for costing in frappe.get_all("Costing", pluck="name"):
		update_status(costing)
