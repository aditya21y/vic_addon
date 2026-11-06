"""Deposit ke supplier (uang jaminan) yang ditagih lewat Purchase Order.

Nominalnya diisi di header PO (**Deposit Amount**, mata uang perusahaan, bisa diubah setelah
submit). Begitu PO disubmit, tombol **Pay Deposit** bikin Payment Entry:

	Dr  Vendor Deposit Account (setting Company)   <- akun aset, party supplier ikut kecatat di GL
	Cr  Bank / Kas dari Mode of Payment yang dipilih user

Paid Amount = sisa deposit yang belum dibayar (boleh dikurangin, bayar sebagian). Payment Entry-nya
ditandain lewat field **Deposit for Purchase Order** dan sengaja **gak** punya baris References:
deposit bukan uang muka barang, jadi gak boleh nambah Advance Paid PO atau ketarik "Get Advances"
di Purchase Invoice. Akun deposit bukan akun hutang, jadi ERPNext gak bikin Payment Ledger Entry -
saldo deposit per supplier dibaca dari General Ledger (filter akun deposit + party).

Tanpa PPN/PPh. Pengembalian deposit (penuh / sebagian) dicatat manual, mis. Payment Entry Receive
dari supplier dengan akun asal = akun deposit.

**Deposit Paid** di PO = total Payment Entry deposit yang submitted, dihitung ulang tiap Payment
Entry-nya disubmit / dibatalin.

Company yang nyalain *Book Advance Payments in Separate Party Account*: ERPNext nimpa akun party
Payment Entry ke akun uang muka waktu validate (`set_liability_account`), jalan sebelum hook apa pun.
Deposit bukan uang muka, jadi Payment Entry yang akun party-nya Vendor Deposit Account dilewatin -
baik bayar deposit maupun pengembaliannya. Lihat `VICPaymentEntry`.
"""

import frappe
from frappe import _
from frappe.utils import flt, today

from erpnext.accounts.doctype.payment_entry.payment_entry import PaymentEntry

PO_FIELD = "custom_deposit_purchase_order"
TOLERANCE = 0.005


class VICPaymentEntry(PaymentEntry):
	def set_liability_account(self):
		"""Akun deposit jangan ditimpa ke akun uang muka - Payment Entry lain tetap jalan bawaan."""
		account = get_deposit_account(self.company, throw=False) if self.company else None
		if account and self.party_account == account and self.docstatus == 0 and self.custom_deposit_purchase_order:
			self.book_advance_payments_in_separate_party_account = False
			self.is_opening = "No"
			return

		super().set_liability_account()


def get_deposit_account(company, throw=True):
	account = frappe.get_cached_value("Company", company, "custom_vendor_deposit_account")
	if not account and throw:
		frappe.throw(
			_("Set the Vendor Deposit Account in Company {0} first.").format(frappe.bold(company)),
			title=_("Vendor Deposit"),
		)
	return account


def get_paid(purchase_order, exclude=None):
	"""Deposit order ini yang udah dibayar lewat Payment Entry submitted (mata uang perusahaan)."""
	filters = {PO_FIELD: purchase_order, "docstatus": 1}
	if exclude:
		filters["name"] = ["!=", exclude]
	return sum(
		flt(row.base_received_amount)
		for row in frappe.get_all("Payment Entry", filters=filters, fields=["base_received_amount"])
	)


# ---------------------------------------------------------------------------------------------
# Tombol Pay Deposit di Purchase Order
# ---------------------------------------------------------------------------------------------


@frappe.whitelist()
def make_deposit_payment(purchase_order):
	"""Payment Entry deposit (belum disimpan) buat dibuka di form."""
	order = frappe.get_doc("Purchase Order", purchase_order)
	order.check_permission("read")

	if order.docstatus != 1:
		frappe.throw(_("Submit the Purchase Order first."))

	remaining = flt(order.get("custom_deposit_amount")) - get_paid(order.name)
	if remaining <= TOLERANCE:
		frappe.throw(_("The deposit of {0} is already fully paid.").format(order.name))

	from erpnext.accounts.doctype.journal_entry.journal_entry import get_default_bank_cash_account

	deposit_account = get_deposit_account(order.company)
	bank = get_default_bank_cash_account(order.company, "Bank") or {}
	currency = frappe.get_cached_value("Company", order.company, "default_currency")

	doc = frappe.new_doc("Payment Entry")
	doc.update(
		{
			"payment_type": "Pay",
			"company": order.company,
			"posting_date": today(),
			"party_type": "Supplier",
			"party": order.supplier,
			"party_name": order.supplier_name,
			PO_FIELD: order.name,
			"paid_from": bank.get("account"),
			"paid_from_account_currency": bank.get("account_currency") or currency,
			"paid_to": deposit_account,
			"paid_to_account_currency": currency,
			"paid_amount": remaining,
			"received_amount": remaining,
			"source_exchange_rate": 1,
			"target_exchange_rate": 1,
			"project": order.get("project"),
			"cost_center": order.get("cost_center"),
			"remarks": _("Deposit for Purchase Order {0}").format(order.name),
		}
	)
	# party_account dibaca dari paid_to (akun deposit), jadi set_missing_values gak nimpa pakai
	# akun hutang supplier
	doc.setup_party_account_field()
	doc.set_missing_values()
	return doc.as_dict()


# ---------------------------------------------------------------------------------------------
# Hook
# ---------------------------------------------------------------------------------------------


def validate_deposit_payment(doc, method=None):
	"""Hook `validate` Payment Entry: Payment Entry deposit harus nyocok sama PO-nya."""
	if not doc.get(PO_FIELD):
		return

	order = frappe.db.get_value(
		"Purchase Order",
		doc.get(PO_FIELD),
		["supplier", "company", "docstatus", "custom_deposit_amount"],
		as_dict=True,
	)
	if not order or order.docstatus != 1:
		frappe.throw(_("Purchase Order {0} must be submitted.").format(doc.get(PO_FIELD)))

	if doc.payment_type != "Pay" or doc.party_type != "Supplier" or doc.party != order.supplier:
		frappe.throw(_("A deposit payment must be a Pay to supplier {0}.").format(frappe.bold(order.supplier)))
	if doc.company != order.company:
		frappe.throw(_("Purchase Order {0} belongs to another company.").format(doc.get(PO_FIELD)))

	account = get_deposit_account(doc.company)
	if doc.paid_to != account:
		frappe.throw(_("The account paid to must be the Vendor Deposit Account {0}.").format(frappe.bold(account)))
	if doc.get("references"):
		frappe.throw(
			_("A deposit payment cannot have references: a deposit is not an advance for the goods."),
			title=_("Vendor Deposit"),
		)
	if doc.get("taxes") or doc.get("deductions"):
		frappe.throw(_("A deposit payment has no taxes or deductions."), title=_("Vendor Deposit"))

	paid = get_paid(doc.get(PO_FIELD), exclude=doc.name) + flt(doc.base_received_amount)
	if paid > flt(order.custom_deposit_amount) + TOLERANCE:
		frappe.throw(
			_("Total deposit paid for {0} would be {1}, more than its Deposit Amount {2}.").format(
				doc.get(PO_FIELD),
				frappe.format(paid, {"fieldtype": "Currency"}),
				frappe.format(order.custom_deposit_amount, {"fieldtype": "Currency"}),
			),
			title=_("Vendor Deposit"),
		)


def update_deposit_paid(doc, method=None):
	"""Hook `on_submit` / `on_cancel` Payment Entry: Deposit Paid di PO dihitung ulang."""
	if doc.get(PO_FIELD):
		frappe.db.set_value(
			"Purchase Order", doc.get(PO_FIELD), "custom_deposit_paid", get_paid(doc.get(PO_FIELD))
		)


def validate_deposit_amount(doc, method=None):
	"""Hook PO: Deposit Amount gak boleh minus, dan setelah submit gak boleh di bawah yang udah dibayar."""
	amount = flt(doc.get("custom_deposit_amount"))
	if amount < 0:
		frappe.throw(_("Deposit Amount cannot be negative."))

	if doc.docstatus == 1:
		paid = get_paid(doc.name)
		if amount < paid - TOLERANCE:
			frappe.throw(
				_("Deposit Amount cannot be less than the deposit already paid ({0}).").format(
					frappe.format(paid, {"fieldtype": "Currency"})
				)
			)
