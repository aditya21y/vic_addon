# Copyright (c) 2026, aditya and contributors
# For license information, please see license.txt

"""Costing: hitung HPP dari harga Supplier Quotation + distribusi additional cost, terus
tentuin harga jual dari margin. Rumusnya ngikut sheet "5a. COSTING" di source of truth:

	Total Buying Amount        = sum(Rate x Qty)
	Total Additional Costs     = sum(Additional Costs)
	Additional Cost Percentage = Total Additional Costs / Total Buying Amount x 100

	per item:
	Distributed Cost Rate = Rate x Additional Cost Percentage x (1 + Additional Percentage)
	HPP Rate              = Rate + Distributed Cost Rate
	Selling Rate          = HPP Rate / (1 - Margin %)
	Profit Amount         = Selling Amount - HPP Amount

Additional cost dibagi proporsional lewat rate tiap item, jadi total distributed cost
= Total Additional Costs x (1 + Additional Percentage).
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class Costing(Document):
	def validate(self):
		self.validate_margin_percentage()
		self.calculate()

	def validate_margin_percentage(self):
		for item in self.items:
			if flt(item.margin_percentage) >= 100:
				frappe.throw(
					_("Row #{0}: Margin % must be less than 100").format(item.idx),
					title=_("Invalid Margin"),
				)

	def calculate(self):
		self.calculate_buying_amount()
		self.calculate_additional_cost_percentage()
		self.calculate_items()
		self.calculate_totals()

	def calculate_buying_amount(self):
		for item in self.items:
			item.amount = flt(flt(item.rate) * flt(item.qty), item.precision("amount"))

		self.total_buying_amount = flt(
			sum(flt(item.amount) for item in self.items), self.precision("total_buying_amount")
		)

	def calculate_additional_cost_percentage(self):
		self.total_additional_costs = flt(
			sum(flt(cost.amount) for cost in self.additional_costs),
			self.precision("total_additional_costs"),
		)

		self.additional_cost_percentage = (
			flt(
				self.total_additional_costs / self.total_buying_amount * 100,
				self.precision("additional_cost_percentage"),
			)
			if self.total_buying_amount
			else 0
		)

	def calculate_items(self):
		# additional cost yang dibebankan ke tiap rupiah harga beli
		cost_factor = (
			flt(self.additional_cost_percentage) / 100 * (1 + flt(self.additional_percentage) / 100)
		)

		for item in self.items:
			item.distributed_cost_rate = flt(
				flt(item.rate) * cost_factor, item.precision("distributed_cost_rate")
			)
			item.distributed_cost_amount = flt(
				flt(item.distributed_cost_rate) * flt(item.qty),
				item.precision("distributed_cost_amount"),
			)

			item.hpp_rate = flt(
				flt(item.rate) + flt(item.distributed_cost_rate), item.precision("hpp_rate")
			)
			item.hpp_amount = flt(flt(item.hpp_rate) * flt(item.qty), item.precision("hpp_amount"))

			item.selling_rate = flt(
				flt(item.hpp_rate) / (1 - flt(item.margin_percentage) / 100),
				item.precision("selling_rate"),
			)
			item.margin_rate = flt(
				flt(item.selling_rate) - flt(item.hpp_rate), item.precision("margin_rate")
			)
			item.margin_amount = flt(
				flt(item.margin_rate) * flt(item.qty), item.precision("margin_amount")
			)
			item.selling_amount = flt(
				flt(item.selling_rate) * flt(item.qty), item.precision("selling_amount")
			)

			# quotation rate default ngikut selling rate, kecuali user isi manual
			if not item.quotation_rate_manually_set:
				item.quotation_rate = item.selling_rate

			item.quotation_amount = flt(
				flt(item.quotation_rate) * flt(item.qty), item.precision("quotation_amount")
			)

			item.profit_amount = flt(
				flt(item.selling_amount) - flt(item.hpp_amount), item.precision("profit_amount")
			)
			item.profit_percentage = (
				flt(item.profit_amount / item.hpp_amount * 100, item.precision("profit_percentage"))
				if item.hpp_amount
				else 0
			)

	def calculate_totals(self):
		totals = {
			"total_distributed_cost_amount": "distributed_cost_amount",
			"total_hpp_amount": "hpp_amount",
			"total_selling_amount": "selling_amount",
			"total_quotation_amount": "quotation_amount",
			"total_profit_amount": "profit_amount",
		}

		for total_field, item_field in totals.items():
			self.set(
				total_field,
				flt(
					sum(flt(item.get(item_field)) for item in self.items),
					self.precision(total_field),
				),
			)

		self.total_profit_percentage = (
			flt(
				self.total_profit_amount / self.total_hpp_amount * 100,
				self.precision("total_profit_percentage"),
			)
			if self.total_hpp_amount
			else 0
		)


@frappe.whitelist()
def make_costing(source_name, target_doc=None):
	"""Bikin Costing dari satu Supplier Quotation (tombol Create di form SQTN)."""
	from frappe.model.mapper import get_mapped_doc

	def update_item(source_item, target_item, source_parent):
		# net_rate = rate setelah diskon bertingkat per item + diskon tambahan atas net total
		target_item.rate = flt(source_item.net_rate) or flt(source_item.rate)
		target_item.supplier_quotation = source_parent.name
		target_item.supplier = source_parent.supplier
		target_item.supplier_quotation_item = source_item.name

	return get_mapped_doc(
		"Supplier Quotation",
		source_name,
		{
			"Supplier Quotation": {
				"doctype": "Costing",
				"validation": {"docstatus": ["=", 1]},
			},
			"Supplier Quotation Item": {
				"doctype": "Costing Item",
				"postprocess": update_item,
			},
		},
		target_doc,
	)


@frappe.whitelist()
def get_supplier_quotation_items(supplier_quotations):
	"""Ambil item dari satu atau beberapa Supplier Quotation buat tabel Costing."""
	if isinstance(supplier_quotations, str):
		supplier_quotations = frappe.parse_json(supplier_quotations)

	if isinstance(supplier_quotations, str):
		supplier_quotations = [supplier_quotations]

	items = []
	for name in supplier_quotations:
		quotation = frappe.get_doc("Supplier Quotation", name)
		quotation.check_permission("read")

		for item in quotation.items:
			items.append(
				{
					"item_code": item.item_code,
					"item_name": item.item_name,
					"uom": item.uom,
					"qty": item.qty,
					# net_rate = rate setelah diskon bertingkat per item + diskon tambahan atas net total
					"rate": flt(item.net_rate) or flt(item.rate),
					"supplier_quotation": quotation.name,
					"supplier": quotation.supplier,
					"supplier_quotation_item": item.name,
				}
			)

	return items
