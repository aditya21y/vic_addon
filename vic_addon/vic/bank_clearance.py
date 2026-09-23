"""Tanggal jurnal ikut pindah ke tanggal cair di bank.

Bank Clearance bawaan cuma nulis Clearance Date ke dokumennya - tanggal posting sama jurnalnya
gak kesentuh, jadi kas tetap kecatat di tanggal dokumen dibikin, bukan tanggal duitnya beneran
cair. Di sini tanggal postingnya digeser ikut Clearance Date, terus jurnalnya ditulis ulang
lewat Repost Accounting Ledger bawaan ERPNext.

Urutannya gak boleh kebalik: tanggal dokumennya diganti dulu, baru di-repost. Repost bikin
jurnal baru dari nilai dokumen yang sekarang, jadi kalau repost duluan, jurnalnya cuma
ketulis ulang di tanggal yang lama.

Tanggal semula disimpan di `custom_original_posting_date`. Jadi kalau Clearance Date-nya
dikosongin lagi - salah isi, misalnya - tanggalnya bisa balik ke asal.

Yang digeser cuma Payment Entry sama Journal Entry, dan cuma kalau doctype-nya kedaftar di
Accounts Settings > Repost > Allowed DocTypes. Invoice sengaja gak ikut walau kedaftar di situ:
geser tanggal invoice itu mindahin pengakuan pendapatan/biaya, bukan cuma tanggal kas.

Pengaman periode gak perlu dibikin sendiri - ERPNext ngecek dua-duanya: periode asal dicek
waktu jurnal lama dibalikin, periode tujuan dicek waktu jurnal baru ditulis. Kalau salah satu
ketutup (Accounting Period, Period Closing Voucher, atau tanggal beku), semuanya dibatalin -
gak ada yang setengah jalan.
"""

import frappe
from frappe import _
from frappe.utils import getdate

from erpnext.accounts.doctype.bank_clearance.bank_clearance import BankClearance

# cuma dokumen kas yang tanggalnya boleh ngikut tanggal cair
SHIFTABLE_DOCTYPES = ("Payment Entry", "Journal Entry")

ORIGINAL_DATE_FIELD = "custom_original_posting_date"


class VICBankClearance(BankClearance):
	"""Bank Clearance bawaan + penggeseran tanggal jurnal."""

	@frappe.whitelist()
	def update_clearance_date(self):
		# Isian user dicatat duluan: method bawaan nutup kerjaannya dengan `get_payment_entries()`
		# yang nyusun ulang tabelnya, jadi Clearance Date yang diketik tadi udah gak kebaca lagi
		# dari `self` sesudah ini.
		requested = [
			(row.payment_document, row.payment_entry, row.clearance_date)
			for row in self.get("payment_entries") or []
			if row.payment_document and row.payment_entry
		]

		super().update_clearance_date()

		for doctype, name, clearance_date in requested:
			sync_posting_date(doctype, name, clearance_date)


def sync_posting_date(doctype, name, clearance_date):
	"""Samain tanggal posting dokumen sama Clearance Date-nya, terus tulis ulang jurnalnya."""
	if doctype not in SHIFTABLE_DOCTYPES or doctype not in get_allowed_types():
		return

	document = frappe.db.get_value(
		doctype,
		name,
		["docstatus", "company", "posting_date", "clearance_date", ORIGINAL_DATE_FIELD],
		as_dict=True,
	)
	if not document or document.docstatus != 1:
		return

	# Method bawaan bisa berhenti di tengah jalan kalau ada baris yang gak valid. Yang dipakai
	# acuan di sini apa yang beneran kesimpan, bukan apa yang tadi diketik.
	if not same_date(document.clearance_date, clearance_date):
		return

	if clearance_date:
		shift_posting_date(doctype, name, document)
	else:
		restore_posting_date(doctype, name, document)


def shift_posting_date(doctype, name, document):
	if same_date(document.posting_date, document.clearance_date):
		return

	values = {"posting_date": document.clearance_date}
	# tanggal asli cuma dicatat sekali; penggeseran kedua kalinya gak boleh nimpa
	if not document.get(ORIGINAL_DATE_FIELD):
		values[ORIGINAL_DATE_FIELD] = document.posting_date

	apply_posting_date(doctype, name, document, values["posting_date"])
	frappe.db.set_value(doctype, name, values, update_modified=False)
	repost_ledger(doctype, name, document.company)


def restore_posting_date(doctype, name, document):
	"""Clearance Date dikosongin: tanggalnya balik ke tanggal semula."""
	original = document.get(ORIGINAL_DATE_FIELD)
	if not original or same_date(document.posting_date, original):
		return

	apply_posting_date(doctype, name, document, original)
	frappe.db.set_value(
		doctype, name, {"posting_date": original, ORIGINAL_DATE_FIELD: None}, update_modified=False
	)
	repost_ledger(doctype, name, document.company)


def apply_posting_date(doctype, name, document, posting_date):
	frappe.get_doc(doctype, name).add_comment(
		"Comment",
		_("Posting date changed from {0} to {1} via Bank Clearance Tool").format(
			frappe.format(document.posting_date, {"fieldtype": "Date"}),
			frappe.format(getdate(posting_date), {"fieldtype": "Date"}),
		),
	)


def repost_ledger(doctype, name, company):
	"""Tulis ulang jurnal dokumen ini lewat Repost Accounting Ledger bawaan.

	Satu dokumen satu Repost: ERPNext ngelempar repost ke background kalau isinya lebih dari
	lima dokumen, dan kalau di background errornya gak kelihatan user. Jejak jurnal lamanya
	sengaja gak dihapus (`delete_cancelled_entries` dibiarin mati) - barisnya tetap ada dengan
	tanda cancelled, gak keitung di laporan tapi masih bisa ditelusuri.
	"""
	repost = frappe.new_doc("Repost Accounting Ledger")
	repost.company = company
	repost.delete_cancelled_entries = 0
	repost.append("vouchers", {"voucher_type": doctype, "voucher_no": name})
	repost.flags.ignore_permissions = True
	repost.insert()
	repost.submit()


def get_allowed_types():
	from erpnext.accounts.doctype.repost_accounting_ledger.repost_accounting_ledger import (
		get_allowed_types_from_settings,
	)

	return get_allowed_types_from_settings()


def same_date(left, right):
	if not left and not right:
		return True

	if not left or not right:
		return False

	return getdate(left) == getdate(right)
