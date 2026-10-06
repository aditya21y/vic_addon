"""Biaya yang nambah nilai barang, ditarik dari Journal Entry ke Landed Cost Voucher.

Biaya impor (ongkos kapal, bea masuk, jasa forwarder) biasanya udah kecatat duluan lewat
Journal Entry. Yang belum kejadian: biaya itu masih nangkring di akun biaya, belum nempel ke
nilai barangnya. Landed Cost Voucher yang mindahin - tapi bawaannya biayanya mesti diketik
ulang satu-satu.

Di sini baris jurnalnya ditandain dulu lewat centangan **Biaya yang masuk nilai barang**, terus
ditarik ke Landed Cost Voucher lewat tombol `Get Expenses From > Journal Entry`. Yang ketarik
cuma baris bercentang, jadi jurnal yang isinya campur (biaya barang + biaya lain) tetap aman.

Centangannya ditaruh di dua tempat dengan nama field yang sama persis: di Journal Entry Template
Account (dicentang sekali di templatenya) dan di Journal Entry Account. Waktu template dipilih
di Journal Entry, ERPNext nyalin semua field baris templatenya apa adanya - jadi centangannya
kebawa sendiri, gak perlu kode tambahan.

Yang ditarik cuma sisi **debit**: itu yang nunjukin biaya keluar. Baris kredit di jurnal yang
sama (kas/hutang) bukan biaya, jadi dilewat.

Satu Journal Entry cuma boleh dipakai di **satu** Landed Cost Voucher yang masih aktif (draft atau
submit) - kalau kepakai dua kali, biayanya nempel dua kali ke nilai barang. Dicek di tiga tempat:
daftar pilihan jurnal, tombol tarik, dan validasi waktu disimpan/disubmit (yang terakhir ini yang
nangkep jalur di luar form - import, API, atau dua draft yang disubmit barengan). Voucher yang
dicancel ngelepas jurnalnya lagi.
"""

import frappe
from frappe import _
from frappe.utils import flt

LANDED_COST_FIELD = "custom_is_landed_cost"


@frappe.whitelist()
def get_expenses_from_journal_entry(journal_entry):
	"""Baris biaya bercentang di satu Journal Entry, siap dimasukin ke tabel Landed Cost."""
	doc = frappe.get_doc("Journal Entry", journal_entry)
	doc.check_permission("read")

	if used_in := get_vouchers_using(journal_entry):
		throw_already_used(journal_entry, used_in)

	rows = []

	for row in doc.get("accounts") or []:
		if not row.get(LANDED_COST_FIELD):
			continue

		# biaya ada di sisi debit; baris kredit di jurnal yang sama itu kas/hutangnya
		amount = flt(row.debit_in_account_currency)
		if amount <= 0:
			continue

		rows.append(
			{
				"expense_account": row.account,
				"amount": amount,
				"description": row.user_remark or doc.user_remark or doc.name,
				"custom_journal_entry": doc.name,
			}
		)

	if not rows:
		frappe.msgprint(
			_("No account in {0} is marked as {1}.").format(
				frappe.utils.get_link_to_form("Journal Entry", doc.name), frappe.bold(_("Biaya yang masuk nilai barang"))
			),
			title=_("Nothing to Pull"),
			indicator="orange",
		)

	return rows


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def journal_entry_query(doctype, txt, searchfield, start, page_len, filters):
	"""Jurnal yang punya minimal satu baris bercentang - biar pilihannya gak kebanyakan."""
	journal_entry = frappe.qb.DocType("Journal Entry")
	account = frappe.qb.DocType("Journal Entry Account")

	query = (
		frappe.qb.from_(journal_entry)
		.inner_join(account)
		.on(account.parent == journal_entry.name)
		.select(journal_entry.name, journal_entry.posting_date, journal_entry.total_debit)
		.where((journal_entry.docstatus == 1) & (account[LANDED_COST_FIELD] == 1))
		# jurnal yang udah kepakai di voucher lain gak ditawarin lagi
		.where(journal_entry.name.notin(get_used_journal_entries_query()))
		.groupby(journal_entry.name)
		.orderby(journal_entry.posting_date, order=frappe.qb.desc)
		.limit(page_len)
		.offset(start)
	)

	if filters.get("company"):
		query = query.where(journal_entry.company == filters["company"])

	if txt:
		query = query.where(journal_entry.name.like(f"%{txt}%"))

	return query.run()


def validate_journal_entries(doc, method=None):
	"""Hook `validate` Landed Cost Voucher: jurnal yang udah dipakai voucher lain ditolak."""
	journal_entries = {row.custom_journal_entry for row in doc.get("taxes") or [] if row.get("custom_journal_entry")}

	for journal_entry in sorted(journal_entries):
		if used_in := get_vouchers_using(journal_entry, exclude=doc.name):
			throw_already_used(journal_entry, used_in)


def get_vouchers_using(journal_entry, exclude=None):
	"""Landed Cost Voucher aktif (draft/submit) yang udah narik biaya dari jurnal ini."""
	charge = frappe.qb.DocType("Landed Cost Taxes and Charges")
	voucher = frappe.qb.DocType("Landed Cost Voucher")

	query = (
		frappe.qb.from_(charge)
		.inner_join(voucher)
		.on(voucher.name == charge.parent)
		.select(voucher.name)
		.distinct()
		.where((charge.custom_journal_entry == journal_entry) & (voucher.docstatus < 2))
	)
	if exclude:
		query = query.where(voucher.name != exclude)

	return [row[0] for row in query.run()]


def get_used_journal_entries_query():
	charge = frappe.qb.DocType("Landed Cost Taxes and Charges")
	voucher = frappe.qb.DocType("Landed Cost Voucher")

	return (
		frappe.qb.from_(charge)
		.inner_join(voucher)
		.on(voucher.name == charge.parent)
		.select(charge.custom_journal_entry)
		.where(charge.custom_journal_entry.isnotnull() & (voucher.docstatus < 2))
	)


def throw_already_used(journal_entry, vouchers):
	frappe.throw(
		_("Journal Entry {0} is already used in Landed Cost Voucher {1}. Cancel that voucher first, or remove the expenses from it.").format(
			frappe.bold(journal_entry),
			", ".join(frappe.utils.get_link_to_form("Landed Cost Voucher", name) for name in vouchers),
		),
		title=_("Journal Entry Already Used"),
	)
