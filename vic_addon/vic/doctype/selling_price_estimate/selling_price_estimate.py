"""Estimasi harga jual dari pembelian terakhir.

Tim Purchasing/Sales sering butuh ancer-ancer harga jual sebuah barang sebelum ada costing
resmi. Rumusnya:

	Estimasi Harga Jual = (Last Purchase Rate + Biaya Tambahan per Unit) / (1 - Margin %)

Contoh: (15.000 + 2.000) / (1 - 20%) = 21.250

Biaya tambahannya dua rasa, dipilih lewat checkbox **With Last LCV**:

- nyala  -> ambil biaya Landed Cost Voucher yang nempel di pembelian terakhir itu, per unit
- mati   -> diisi manual di tabel Additional Costs (pola yang sama kayak Costing)

Dokumen ini gak posting jurnal dan gak dipakai transaksi - murni alat hitung.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder import Order
from frappe.utils import flt


class SellingPriceEstimate(Document):
	def validate(self):
		self.set_last_purchase()
		self.set_additional_cost()
		self.calculate_estimate()

	def set_last_purchase(self):
		"""Harga beli terakhir item ini, dari Purchase Receipt yang udah disubmit."""
		purchase = get_last_purchase(self.item_code, self.warehouse)

		self.last_purchase_rate = flt(purchase.rate) if purchase else 0
		self.last_purchase_qty = flt(purchase.qty) if purchase else 0
		self.last_purchase_receipt = purchase.purchase_receipt if purchase else None
		self.last_purchase_date = purchase.posting_date if purchase else None

		if not purchase:
			frappe.msgprint(
				_("Item {0} has no submitted Purchase Receipt{1} yet, so Last Purchase Rate is empty.").format(
					self.item_code, _(" in warehouse {0}").format(self.warehouse) if self.warehouse else ""
				),
				title=_("No Purchase History"),
				indicator="orange",
			)

	def set_additional_cost(self):
		"""Biaya tambahan per unit: dari Landed Cost Voucher, atau dari tabel isian manual."""
		if self.with_last_lcv:
			self.set_landed_costs()
			self.total_additional_cost = flt(
				sum(flt(row.rate) for row in self.landed_costs),
				self.precision("total_additional_cost"),
			)
			return

		self.landed_costs = []
		self.total_additional_cost = flt(
			sum(flt(row.amount) for row in self.additional_costs),
			self.precision("total_additional_cost"),
		)

	def set_landed_costs(self):
		"""Tabel Landed Cost diisi ulang dari voucher yang nempel di pembelian terakhir."""
		self.landed_costs = []

		if not self.last_purchase_receipt:
			return

		for row in get_landed_costs(self.last_purchase_receipt, self.item_code):
			self.append("landed_costs", row)

		if not self.landed_costs:
			frappe.msgprint(
				_("Purchase Receipt {0} has no Landed Cost Voucher, so the additional cost is zero.").format(
					self.last_purchase_receipt
				),
				title=_("No Landed Cost"),
				indicator="orange",
			)

	def calculate_estimate(self):
		"""Harga pokok dibagi (1 - margin), jadi marginnya kehitung atas harga jual."""
		margin = flt(self.margin_percentage)

		if margin >= 100:
			frappe.throw(
				_("Margin % must be less than 100."),
				title=_("Invalid Margin"),
			)

		cost = flt(self.last_purchase_rate) + flt(self.total_additional_cost)

		self.estimated_selling_rate = flt(
			cost / (1 - margin / 100), self.precision("estimated_selling_rate")
		)


@frappe.whitelist()
def get_last_purchase(item_code, warehouse=None):
	"""Baris Purchase Receipt terakhir buat item ini, dibatesin ke gudangnya kalau diisi."""
	if not item_code:
		return None

	receipt = frappe.qb.DocType("Purchase Receipt")
	item = frappe.qb.DocType("Purchase Receipt Item")

	query = (
		frappe.qb.from_(item)
		.join(receipt)
		.on(item.parent == receipt.name)
		.select(
			receipt.name.as_("purchase_receipt"),
			receipt.posting_date,
			item.name.as_("purchase_receipt_item"),
			item.rate,
			item.qty,
			item.landed_cost_voucher_amount,
		)
		.where((receipt.docstatus == 1) & (item.item_code == item_code))
		.orderby(receipt.posting_date, order=Order.desc)
		.orderby(receipt.creation, order=Order.desc)
		.limit(1)
	)

	if warehouse:
		query = query.where(item.warehouse == warehouse)

	rows = query.run(as_dict=True)

	return rows[0] if rows else None


@frappe.whitelist()
def get_landed_costs(purchase_receipt, item_code):
	"""Biaya Landed Cost Voucher yang kena ke item ini di Purchase Receipt tersebut.

	`applicable_charges` itu porsi biaya buat baris penerimaan tadi (udah dialokasiin ERPNext),
	jadi tinggal dibagi qty biar ketemu biaya per unit.
	"""
	voucher = frappe.qb.DocType("Landed Cost Voucher")
	voucher_item = frappe.qb.DocType("Landed Cost Item")

	rows = (
		frappe.qb.from_(voucher_item)
		.join(voucher)
		.on(voucher_item.parent == voucher.name)
		.select(
			voucher.name.as_("landed_cost_voucher"),
			voucher.posting_date,
			voucher_item.qty,
			voucher_item.applicable_charges,
		)
		.where(
			(voucher.docstatus == 1)
			& (voucher_item.receipt_document == purchase_receipt)
			& (voucher_item.item_code == item_code)
		)
		.orderby(voucher.posting_date, order=Order.desc)
		.run(as_dict=True)
	)

	for row in rows:
		row["amount"] = flt(row.pop("applicable_charges"))
		row["rate"] = flt(row["amount"] / row["qty"]) if flt(row["qty"]) else 0
		row["description"] = get_charge_description(row["landed_cost_voucher"])

	return rows


def get_charge_description(landed_cost_voucher):
	"""Nama-nama biaya di voucher itu, digabung jadi satu baris."""
	charges = frappe.get_all(
		"Landed Cost Taxes and Charges",
		filters={"parent": landed_cost_voucher},
		pluck="description",
		order_by="idx",
	)

	return ", ".join(charge for charge in charges if charge)
