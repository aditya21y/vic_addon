"""PPN Masukan Tertunda: PPN pembelian yang faktur pajaknya belum diterima.

Selama faktur pajaknya belum ada, PPN-nya gak boleh langsung masuk PPN Masukan. Jadi:

1. Di Purchase Invoice user nyentang **PPN Tertunda**, terus milih manual akun
   PPN Masukan Tertunda di baris PPN tabel pajak. Waktu submit dicek: kalau dicentang, harus ada
   baris yang pakai akun itu.
2. Begitu fakturnya dateng, tombol **Create > Reklas PPN Tertunda** di invoice yang udah submit
   bikin **draft** Journal Entry:

	Dr PPN Masukan            xxx
	    Cr PPN Masukan Tertunda   xxx

   Sengaja draft: tanggal posting (tanggal faktur diterima) dan akunnya masih bisa dicek/diubah
   sebelum disubmit.

Dua akunnya diset per company (tab Accounts, bagian "PPN Masukan Tertunda"). Jurnalnya nyimpen
link ke invoice-nya (`custom_ppn_tertunda_invoice`), jadi satu invoice cuma dapat satu jurnal
reklas, dan invoice-nya gak bisa dibatalin selama jurnal reklasnya masih submitted.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_link_to_form, nowdate

INVOICE_LINK_FIELD = "custom_ppn_tertunda_invoice"


def get_accounts(company):
	"""(akun PPN Masukan Tertunda, akun PPN Masukan) dari Company."""
	return frappe.db.get_value(
		"Company", company, ["custom_ppn_masukan_tertunda_account", "custom_ppn_masukan_account"]
	) or (None, None)


def get_deferred_amounts(doc, deferred_account):
	"""Nilai PPN tertunda per cost center, persis yang dijurnal invoice-nya ke akun itu.

	Nilainya `base_tax_amount_after_discount_amount` - angka yang dipakai ERPNext waktu bikin GL
	pajak. Baris `Add` nambah saldo debit, `Deduct` ngurangin.
	"""
	amounts = {}

	for tax in doc.get("taxes") or []:
		if tax.account_head != deferred_account:
			continue

		amount = flt(tax.base_tax_amount_after_discount_amount)
		if tax.add_deduct_tax == "Deduct":
			amount = -amount

		amounts[tax.cost_center] = amounts.get(tax.cost_center, 0) + amount

	return {cost_center: amount for cost_center, amount in amounts.items() if flt(amount, 2)}


def validate_ppn_tertunda(doc, method=None):
	"""Hook `before_submit` Purchase Invoice: yang dicentang PPN Tertunda wajib punya baris
	PPN Masukan Tertunda - kalau enggak, gak ada yang bisa direklas nanti.

	Dicek waktu submit, bukan waktu simpan, biar draft-nya bebas disimpan sambil tabel pajaknya
	dilengkapi.
	"""
	if not doc.get("custom_ppn_tertunda"):
		return

	deferred_account, vat_account = get_accounts(doc.company)
	if not (deferred_account and vat_account):
		frappe.throw(
			_("Set COA PPN Masukan Tertunda and COA PPN Masukan in Company {0} (Accounts tab) first.").format(
				get_link_to_form("Company", doc.company)
			),
			title=_("PPN Tertunda Not Set Up"),
		)

	if not get_deferred_amounts(doc, deferred_account):
		frappe.throw(
			_("PPN Tertunda is checked, but no row in Purchase Taxes and Charges uses account {0}. Select it as the Account Head of the PPN row, or uncheck PPN Tertunda.").format(
				frappe.bold(deferred_account)
			),
			title=_("PPN Masukan Tertunda Missing"),
		)


@frappe.whitelist()
def make_reclass_entry(purchase_invoice):
	"""Tombol Reklas PPN Tertunda: bikin draft Journal Entry, balikin namanya.

	Kalau invoice-nya udah punya jurnal reklas (draft atau submitted), yang dibalikin jurnal itu -
	gak dibikin dobel.
	"""
	doc = frappe.get_doc("Purchase Invoice", purchase_invoice)
	doc.check_permission("read")
	frappe.has_permission("Journal Entry", "create", throw=True)

	if doc.docstatus != 1 or not doc.get("custom_ppn_tertunda"):
		frappe.throw(
			_("Only a submitted Purchase Invoice with PPN Tertunda checked can be reclassified."),
			title=_("Cannot Reclassify"),
		)

	existing = frappe.db.get_value(
		"Journal Entry", {INVOICE_LINK_FIELD: doc.name, "docstatus": ["<", 2]}, "name"
	)
	if existing:
		return {"journal_entry": existing, "existing": 1}

	deferred_account, vat_account = get_accounts(doc.company)
	if not (deferred_account and vat_account):
		frappe.throw(
			_("Set COA PPN Masukan Tertunda and COA PPN Masukan in Company {0} (Accounts tab) first.").format(
				get_link_to_form("Company", doc.company)
			),
			title=_("PPN Tertunda Not Set Up"),
		)

	amounts = get_deferred_amounts(doc, deferred_account)
	if not amounts:
		frappe.throw(
			_("No PPN Masukan Tertunda ({0}) on this invoice.").format(frappe.bold(deferred_account)),
			title=_("Nothing to Reclassify"),
		)

	entry = frappe.new_doc("Journal Entry")
	entry.voucher_type = "Journal Entry"
	entry.company = doc.company
	entry.posting_date = nowdate()
	entry.set(INVOICE_LINK_FIELD, doc.name)
	entry.user_remark = _("Reklas PPN Masukan Tertunda ke PPN Masukan atas {0} ({1})").format(
		doc.name, doc.get("bill_no") or doc.supplier_name or doc.supplier
	)

	for cost_center, amount in amounts.items():
		# nilai minus (mis. debit note) = arahnya kebalik
		debit_account, credit_account = (vat_account, deferred_account) if amount > 0 else (deferred_account, vat_account)

		entry.append(
			"accounts",
			{"account": debit_account, "debit_in_account_currency": abs(amount), "cost_center": cost_center},
		)
		entry.append(
			"accounts",
			{"account": credit_account, "credit_in_account_currency": abs(amount), "cost_center": cost_center},
		)

	entry.insert()

	return {"journal_entry": entry.name, "existing": 0}
