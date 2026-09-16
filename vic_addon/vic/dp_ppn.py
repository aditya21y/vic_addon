"""PPN atas uang muka: akunnya dialihkan dulu, terus dipindahin waktu DP-nya kebayar.

Waktu bayar DP ke supplier, faktur pajaknya belum ada. Jadi PPN-nya gak boleh langsung masuk
PPN Masukan - ditampung dulu di akun "PPN Masukan Belum Ditagih". Begitu pembayaran DP-nya
disubmit, saldonya dipindah ke PPN Masukan lewat Journal Entry yang dibikin otomatis.

Dua-duanya dinyalain per company (tab Accounts, bagian "PPN Uang Muka (DP)"): ada centangan
buat sisi pembelian dan sisi penjualan, plus akun penampungnya masing-masing.

Alur lengkapnya:

1. DP Invoice (Payment Request) dibikin dari PO/SO. Baris PPN-nya ditarik dari dokumen
   referensi, terus akunnya diganti ke akun penampung. Akun aslinya disimpan di baris yang
   sama (`custom_original_account_head`) supaya gak perlu ditebak-tebak nanti.
2. Baris pajak itu kebawa ke Payment Entry apa adanya, jadi jurnal DP-nya kena akun penampung.
3. Payment Entry disubmit -> Journal Entry mindahin saldonya dari akun penampung ke akun asli.
   Payment Entry dibatalin -> jurnalnya ikut dibatalin.
"""

import frappe
from frappe import _
from frappe.utils import flt

# jenis DP -> (field centangan, field akun) di Company
COMPANY_SETTINGS = {
	"Purchase": ("custom_enable_purchase_dp_ppn", "custom_purchase_dp_ppn_account"),
	"Sales": ("custom_enable_sales_dp_ppn", "custom_sales_dp_ppn_account"),
}

ORIGINAL_ACCOUNT_FIELD = "custom_original_account_head"


def get_holding_account(company, dp_type):
	"""Akun penampung PPN uang muka, `None` kalau fiturnya gak dinyalain di company."""
	setting = COMPANY_SETTINGS.get(dp_type)
	if not (company and setting):
		return None

	enabled, account = frappe.db.get_value("Company", company, list(setting))

	return account if enabled and account else None


def is_vat_row(tax):
	"""Baris PPN = pajak yang nambah nilai bayar dan hitungannya persentase.

	PPh 23 kebedain dari sini: dia motong (`Deduct`), bukan nambah. Baris `Actual` - ongkos
	kirim dan sejenisnya - juga kelewat, karena bukan pajak yang perlu dipindah akunnya.
	"""
	return tax.get("charge_type") == "On Paid Amount" and tax.get("add_deduct_tax") != "Deduct"


def redirect_vat_account(doc):
	"""Alihin akun baris PPN di DP Invoice ke akun penampung company.

	Dipanggil sekali waktu tabel pajaknya baru diisi dari dokumen referensi. Baris yang akunnya
	udah pernah dialihin dilewat, jadi aman kalau kepanggil dua kali.
	"""
	account = get_holding_account(doc.company, doc.get("custom_dp_type"))
	if not account:
		return

	for tax in doc.get("custom_taxes") or []:
		if not is_vat_row(tax) or tax.get(ORIGINAL_ACCOUNT_FIELD):
			continue

		if tax.account_head and tax.account_head != account:
			tax.set(ORIGINAL_ACCOUNT_FIELD, tax.account_head)
			tax.account_head = account


def make_vat_reclass_entry(doc, method=None):
	"""Hook `on_submit` Payment Entry: pindahin PPN dari akun penampung ke akun aslinya."""
	rows = get_reclass_rows(doc)
	if not rows:
		return

	entry = frappe.new_doc("Journal Entry")
	entry.voucher_type = "Journal Entry"
	entry.company = doc.company
	entry.posting_date = doc.posting_date
	entry.custom_dp_ppn_payment_entry = doc.name
	entry.user_remark = _("PPN uang muka dipindahkan dari akun penampung, mengikuti {0}").format(
		doc.name
	)

	# DP pembelian: PPN-nya tadi didebit ke akun penampung, jadi sekarang penampungnya dikredit.
	# DP penjualan kebalikannya - PPN keluaran dikredit duluan, penampungnya yang didebit.
	from_holding_is_credit = doc.payment_type == "Pay"

	for account, holding, amount, cost_center in rows:
		entry.append(
			"accounts",
			{
				"account": account if from_holding_is_credit else holding,
				"debit_in_account_currency": amount,
				"cost_center": cost_center,
				"reference_type": "Payment Entry",
				"reference_name": doc.name,
			},
		)
		entry.append(
			"accounts",
			{
				"account": holding if from_holding_is_credit else account,
				"credit_in_account_currency": amount,
				"cost_center": cost_center,
				"reference_type": "Payment Entry",
				"reference_name": doc.name,
			},
		)

	entry.flags.ignore_permissions = True
	entry.insert()
	entry.submit()

	frappe.msgprint(
		_("PPN uang muka dipindahkan lewat Journal Entry {0}").format(
			frappe.utils.get_link_to_form("Journal Entry", entry.name)
		),
		title=_("PPN Uang Muka"),
		indicator="green",
	)


def get_reclass_rows(doc):
	"""Baris pajak yang akunnya pernah dialihin: (akun asli, akun penampung, nilai, cost center).

	Yang dipakai jejak di barisnya sendiri, bukan centangan di company. Kalau centangannya
	dimatiin setelah DP kebayar, saldonya tetap nyangkut di akun penampung dan tetap harus
	dipindahin.
	"""
	rows = []

	for tax in doc.get("taxes") or []:
		original = tax.get(ORIGINAL_ACCOUNT_FIELD)
		amount = flt(tax.get("base_tax_amount"))

		if not original or original == tax.account_head or not amount:
			continue

		rows.append((original, tax.account_head, abs(amount), tax.get("cost_center")))

	return rows


def cancel_vat_reclass_entry(doc, method=None):
	"""Hook `on_cancel` Payment Entry: jurnal pemindahan PPN-nya ikut dibatalin."""
	names = frappe.get_all(
		"Journal Entry",
		filters={"custom_dp_ppn_payment_entry": doc.name, "docstatus": 1},
		pluck="name",
	)

	for name in names:
		entry = frappe.get_doc("Journal Entry", name)
		entry.flags.ignore_permissions = True
		entry.cancel()
