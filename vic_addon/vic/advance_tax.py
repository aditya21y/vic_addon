"""Sisa PPN/PPh di invoice final setelah sebagian dibayar lewat DP.

Kalau DP-nya udah kena PPN/PPh (Payment Entry DP punya Advance Taxes and Charges), invoice
finalnya cuma boleh nagih sisanya. Baris pajak yang kena potongan diubah jadi charge type
`Actual` dengan nilai:

	tax amount = pajak penuh - pajak yang udah dibayar di DP

Potongannya diambil dari Payment Entry yang dialokasiin ke invoice ini (tabel Advances),
proporsional sama porsi yang dialokasiin.
"""

import frappe
from frappe import _
from frappe.utils import flt


def restore_tax_rows(doc, method=None):
	"""Hook `before_validate`: balikin baris pajak ke setelan aslinya.

	Wajib jalan sebelum ERPNext ngitung pajak, biar nilai penuhnya kehitung ulang dari awal.
	Kalau enggak, potongan DP bakal numpuk tiap dokumennya disimpan.
	"""
	for tax in doc.get("taxes") or []:
		if not tax.custom_original_charge_type:
			continue

		tax.charge_type = tax.custom_original_charge_type
		# ERPNext ngosongin rate tiap charge type-nya `Actual`, makanya disimpan terpisah
		tax.rate = tax.custom_original_rate
		tax.custom_original_charge_type = None
		tax.custom_original_rate = 0
		tax.custom_dp_tax_deducted = 0


def deduct_advance_taxes(doc, method=None):
	"""Hook `validate`: potong pajak yang udah dibayar di DP."""
	if not doc.get("custom_deduct_dp_taxes"):
		return

	taxes_paid_on_advances = get_taxes_paid_on_advances(doc)
	if not taxes_paid_on_advances:
		return

	deducted = False
	for tax in doc.get("taxes") or []:
		paid = flt(taxes_paid_on_advances.get(tax.account_head))
		if not paid:
			continue

		# nilai di Payment Entry disimpan dalam mata uang perusahaan
		paid = flt(paid / (flt(doc.conversion_rate) or 1), tax.precision("tax_amount"))
		full_tax_amount = flt(tax.tax_amount)

		if paid > full_tax_amount:
			frappe.msgprint(
				_(
					"Row #{0}: tax paid on DP ({1}) is bigger than the tax on this invoice ({2}). Deduction is capped at the invoice tax."
				).format(tax.idx, paid, full_tax_amount),
				title=_("Tax Paid on DP"),
				indicator="orange",
			)
			paid = full_tax_amount

		tax.custom_original_charge_type = tax.charge_type
		tax.custom_original_rate = tax.rate
		tax.custom_dp_tax_deducted = paid
		tax.charge_type = "Actual"
		tax.tax_amount = flt(full_tax_amount - paid, tax.precision("tax_amount"))
		deducted = True

	if deducted:
		doc.calculate_taxes_and_totals()


def get_taxes_paid_on_advances(doc):
	"""Total pajak per akun dari Payment Entry DP yang dialokasiin ke invoice ini.

	Dalam mata uang perusahaan, dan diprorata pakai porsi yang dialokasiin ke invoice ini
	(satu DP bisa dipakai buat beberapa invoice).
	"""
	taxes_paid = {}

	for advance in doc.get("advances") or []:
		if advance.reference_type != "Payment Entry" or not flt(advance.allocated_amount):
			continue

		payment_entry = frappe.get_cached_doc("Payment Entry", advance.reference_name)
		party_amount = flt(payment_entry.paid_amount) or flt(payment_entry.received_amount)
		if not party_amount:
			continue

		allocated_ratio = min(flt(advance.allocated_amount) / party_amount, 1)

		for tax in payment_entry.get("taxes") or []:
			if tax.add_deduct_tax == "Deduct":
				continue

			taxes_paid.setdefault(tax.account_head, 0)
			taxes_paid[tax.account_head] += flt(tax.base_tax_amount) * allocated_ratio

	return taxes_paid
