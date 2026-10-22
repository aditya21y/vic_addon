"""PPN atas uang muka: ditampung dulu di akun penampung, dipindah ke akun aslinya belakangan.

Waktu bayar DP ke supplier, faktur pajaknya sering belum terbit - PPN-nya belum bisa dikreditkan.
Jadi PPN-nya dicatat dulu di akun "PPN Masukan Belum Ditagih". Begitu faktur pajak dari supplier
datang, saldonya dipindah ke PPN Masukan lewat Journal Entry: Dr PPN Masukan / Cr PPN Masukan
Belum Ditagih.

Setting per company (tab Accounts, bagian "PPN Uang Muka (DP)"): akun penampung buat sisi
pembelian & penjualan, plus centangan yang bikin DP Invoice langsung ngalihin PPN-nya.

**Pembelian (Payment Entry Pay ke Supplier, referensi Purchase Order):**

1. Centangan **PPN Masukan Belum Ditagih** (`custom_vat_not_invoiced`) di Payment Entry yang
   nentuin: dicentang -> baris PPN dialihin ke akun penampung (akun aslinya disimpan di
   `custom_original_account_head`), gak dicentang -> balik ke akun aslinya. Payment Entry dari DP
   Invoice yang PPN-nya udah dialihin langsung kecentang.
2. Submit **gak** bikin jurnal apa-apa - PPN-nya nunggu di akun penampung.
3. Faktur pajak datang -> tombol **Create > PPN Reclass Journal** di Payment Entry bikin Journal
   Entry **draft** (Dr akun asli / Cr penampung). Tanggalnya hari ini, bisa diubah ke tanggal
   faktur; user yang submit.

**Penjualan:** masih otomatis - PPN dari DP Invoice dialihin, terus Journal Entry pemindahannya
dibikin & disubmit begitu Payment Entry-nya disubmit (fakturnya diterbitin VIC sendiri).

Payment Entry dibatalin -> jurnal pemindahan yang udah submit ikut dibatalin, yang masih draft
dihapus.
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


def get_holding_account(company, dp_type, require_enabled=True):
	"""Akun penampung PPN uang muka, `None` kalau gak di-set (atau fiturnya gak dinyalain)."""
	setting = COMPANY_SETTINGS.get(dp_type)
	if not (company and setting):
		return None

	enabled, account = frappe.db.get_value("Company", company, list(setting))

	return account if account and (enabled or not require_enabled) else None


def is_vat_row(tax):
	"""Baris PPN = pajak yang nambah nilai bayar dan hitungannya persentase.

	PPh kebedain dua lapis: baris yang dibikin mesin PPh ERPNext ketandain
	`is_tax_withholding_account`, dan PPh yang diketik tangan biasanya motong (`Deduct`).
	Dua-duanya dilewat - arah Add/Deduct doang gak cukup, soalnya ERPNext maksa arah "Add" buat
	PPh sisi customer. Baris `Actual` - ongkos kirim dan sejenisnya - juga kelewat, karena bukan
	pajak yang perlu dipindah akunnya.
	"""
	if tax.get("is_tax_withholding_account"):
		return False

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


# ---------------------------------------------------------------------------------------------
# Pembelian: centangan PPN Masukan Belum Ditagih di Payment Entry
# ---------------------------------------------------------------------------------------------


def set_vat_holding_account(doc, method=None):
	"""Hook `before_validate` Payment Entry: akun baris PPN ngikut centangan Belum Ditagih.

	Cuma Payment Entry bayar ke supplier. Dicentang -> PPN ke akun penampung; gak dicentang ->
	baris yang sempat dialihin dibalikin ke akun aslinya.
	"""
	if doc.docstatus != 0 or doc.payment_type != "Pay" or doc.party_type != "Supplier":
		return

	if not doc.get("custom_vat_not_invoiced"):
		for tax in doc.get("taxes") or []:
			original = tax.get(ORIGINAL_ACCOUNT_FIELD)
			if original:
				tax.account_head = original
				tax.set(ORIGINAL_ACCOUNT_FIELD, None)
		return

	if not any(row.reference_doctype == "Purchase Order" for row in doc.get("references") or []):
		frappe.throw(
			_("PPN Masukan Belum Ditagih is only for advance payments against a Purchase Order."),
			title=_("PPN Masukan Belum Ditagih"),
		)

	account = get_holding_account(doc.company, "Purchase", require_enabled=False)
	if not account:
		frappe.throw(
			_("Set the PPN Masukan Belum Ditagih account in Company {0} (tab Accounts, PPN Uang Muka) first.").format(
				frappe.bold(doc.company)
			),
			title=_("PPN Masukan Belum Ditagih"),
		)

	vat_rows = [tax for tax in doc.get("taxes") or [] if is_vat_row(tax)]
	if not vat_rows:
		frappe.throw(
			_("This Payment Entry has no VAT row to record under PPN Masukan Belum Ditagih."),
			title=_("PPN Masukan Belum Ditagih"),
		)

	for tax in vat_rows:
		if tax.account_head and tax.account_head != account:
			tax.set(ORIGINAL_ACCOUNT_FIELD, tax.account_head)
			tax.account_head = account


@frappe.whitelist()
def get_vat_reclass_journal(payment_entry):
	"""Buat tombol di form: jurnal pemindahan yang udah ada (draft/submit), atau `None`."""
	doc = frappe.get_doc("Payment Entry", payment_entry)
	doc.check_permission("read")

	return frappe.db.get_value(
		"Journal Entry",
		{"custom_dp_ppn_payment_entry": doc.name, "docstatus": ["<", 2]},
		["name", "docstatus"],
		as_dict=True,
	)


@frappe.whitelist()
def make_vat_reclass_journal(payment_entry):
	"""Tombol Create > PPN Reclass Journal: Journal Entry draft Dr PPN Masukan / Cr penampung."""
	doc = frappe.get_doc("Payment Entry", payment_entry)
	doc.check_permission("read")
	frappe.has_permission("Journal Entry", "create", throw=True)

	if doc.docstatus != 1 or not doc.get("custom_vat_not_invoiced"):
		frappe.throw(_("Only for a submitted Payment Entry with PPN Masukan Belum Ditagih checked."))

	existing = get_vat_reclass_journal(doc.name)
	if existing:
		frappe.throw(
			_("PPN of {0} is already reclassified in {1}.").format(
				doc.name, frappe.utils.get_link_to_form("Journal Entry", existing.name)
			),
			title=_("Already Reclassified"),
		)

	entry = build_reclass_entry(doc, frappe.utils.today())
	if not entry:
		frappe.throw(_("{0} has no PPN recorded under PPN Masukan Belum Ditagih.").format(doc.name))

	entry.user_remark = _(
		"Faktur Pajak diterima: PPN uang muka {0} dipindahkan dari PPN Masukan Belum Ditagih ke PPN Masukan"
	).format(doc.name)
	entry.insert()
	return entry.name


# ---------------------------------------------------------------------------------------------
# Penjualan: jurnal pemindahan otomatis waktu Payment Entry disubmit
# ---------------------------------------------------------------------------------------------


def make_vat_reclass_entry(doc, method=None):
	"""Hook `on_submit` Payment Entry: pindahin PPN dari akun penampung ke akun aslinya.

	Cuma sisi penjualan. Sisi pembelian nunggu faktur pajak supplier - jurnalnya dibikin manual
	lewat tombol (`make_vat_reclass_journal`).
	"""
	if doc.payment_type == "Pay":
		return

	entry = build_reclass_entry(doc, doc.posting_date)
	if not entry:
		return

	entry.user_remark = _("PPN uang muka dipindahkan dari akun penampung, mengikuti {0}").format(
		doc.name
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


def build_reclass_entry(doc, posting_date):
	"""Journal Entry (belum disimpan) yang mindahin PPN dari akun penampung ke akun aslinya."""
	rows = get_reclass_rows(doc)
	if not rows:
		return None

	entry = frappe.new_doc("Journal Entry")
	entry.voucher_type = "Journal Entry"
	entry.company = doc.company
	entry.posting_date = posting_date
	entry.custom_dp_ppn_payment_entry = doc.name

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

	return entry


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
	"""Hook `on_cancel` Payment Entry: jurnal pemindahan PPN yang udah submit ikut dibatalin, yang
	masih draft dihapus (gak ada gunanya lagi tanpa Payment Entry-nya)."""
	entries = frappe.get_all(
		"Journal Entry",
		filters={"custom_dp_ppn_payment_entry": doc.name, "docstatus": ["<", 2]},
		fields=["name", "docstatus"],
	)

	for row in entries:
		if row.docstatus == 0:
			frappe.delete_doc("Journal Entry", row.name, ignore_permissions=True)
			continue
		entry = frappe.get_doc("Journal Entry", row.name)
		entry.flags.ignore_permissions = True
		entry.cancel()
