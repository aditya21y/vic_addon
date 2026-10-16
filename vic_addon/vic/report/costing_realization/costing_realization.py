# Copyright (c) 2026, aditya and contributors
# For license information, please see license.txt

"""Costing Realization: rencana Costing vs realisasi Sales Order & Purchase Order, per item.

Tampilannya pohon: baris Costing (total) di atas, baris item di bawahnya. Hitungannya dipakai bareng
section Realization di form Costing - lihat vic_addon/vic/costing_realization.py.
"""

import frappe
from frappe import _

from vic_addon.vic.costing_realization import get_realization


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_data(filters):
	data = []

	for costing in get_costings(filters):
		result = get_realization(frappe.get_doc("Costing", costing.name))
		if filters.get("only_with_sales_order") and not result.sales_orders:
			continue

		data.append(
			dict(
				result.total,
				id=costing.name,
				parent_id=None,
				indent=0,
				costing=costing.name,
				customer=costing.customer,
				item_code=None,
				item_name=_("{0} item").format(len(result.rows)),
				sales_orders=", ".join(result.sales_orders),
				purchase_orders=", ".join(result.purchase_orders),
			)
		)
		for index, row in enumerate(result.rows):
			data.append(
				dict(row, id=f"{costing.name}::{index}", parent_id=costing.name, indent=1, costing=costing.name)
			)

	return data


def get_costings(filters):
	conditions = {"company": filters.company}
	if filters.get("from_date") and filters.get("to_date"):
		conditions["posting_date"] = ["between", [filters.from_date, filters.to_date]]
	for field in ("customer", "project"):
		if filters.get(field):
			conditions[field] = filters[field]
	if filters.get("costing"):
		conditions["name"] = filters.costing

	return frappe.get_all(
		"Costing",
		filters=conditions,
		fields=["name", "customer", "posting_date"],
		order_by="posting_date desc, name desc",
	)


def get_columns():
	def col(fieldname, label, fieldtype="Currency", width=120, options=None):
		column = {"fieldname": fieldname, "label": _(label), "fieldtype": fieldtype, "width": width}
		if options:
			column["options"] = options
		return column

	return [
		col("costing", "Costing", "Link", 150, "Costing"),
		col("customer", "Customer", "Link", 140, "Customer"),
		col("item_code", "Item", "Link", 120, "Item"),
		col("item_name", "Item Name", "Data", 150),
		col("po_status", "PO Status", "Data", 100),
		col("plan_qty", "Qty Costing", "Float", 90),
		col("so_qty", "Qty SO", "Float", 80),
		col("po_qty", "Qty PO", "Float", 80),
		col("plan_sell_rate", "Harga Jual Rencana"),
		col("so_rate", "Harga Jual SO"),
		col("plan_sell_amount", "Nilai Jual Rencana", width=130),
		col("so_amount", "Nilai Jual SO", width=130),
		col("sell_variance", "Selisih Jual", width=120),
		col("plan_buy_rate", "Harga Beli Rencana"),
		col("po_rate", "Harga Beli PO"),
		col("plan_buy_amount", "Nilai Beli Rencana", width=130),
		col("po_amount", "Nilai Beli PO", width=130),
		col("real_buy_amount", "Biaya Beli Realisasi", width=140),
		col("buy_variance", "Selisih Beli", width=120),
		col("plan_profit", "Profit Rencana", width=130),
		col("real_profit", "Profit Realisasi", width=130),
		col("profit_variance", "Selisih Profit", width=120),
		col("plan_margin", "Margin Rencana %", "Percent", 110),
		col("real_margin", "Margin Realisasi %", "Percent", 120),
		col("sales_orders", "Sales Order", "Data", 180),
		col("purchase_orders", "Purchase Order", "Data", 180),
	]
