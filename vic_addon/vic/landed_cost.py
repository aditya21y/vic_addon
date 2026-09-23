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
