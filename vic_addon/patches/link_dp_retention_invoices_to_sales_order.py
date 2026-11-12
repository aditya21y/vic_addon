"""Baris Item DP / RETENSI invoice lama diisi nomor SO-nya, biar invoice DP & retensi muncul di tab
Connections Sales Order. Cuma field link `sales_order` - `so_detail` tetap kosong, jadi billed SO
gak berubah. SO Closed / On Hold dilewatin (ERPNext nolak cancel invoice yang barisnya nunjuk SO
begitu) - sama kayak invoice retensi baru (`append_retention_row`)."""

import frappe


def execute():
	frappe.db.sql(
		"""
		update `tabSales Invoice Item` item
		join `tabSales Invoice` invoice on invoice.name = item.parent
		join `tabSales Order` sales_order on sales_order.name = invoice.custom_dp_order
		set item.sales_order = invoice.custom_dp_order
		where ifnull(item.sales_order, '') = ''
			and ifnull(invoice.custom_dp_order, '') != ''
			and (invoice.custom_is_dp = 1 or invoice.custom_is_retention = 1)
			and sales_order.status not in ('Closed', 'On Hold')
		"""
	)
