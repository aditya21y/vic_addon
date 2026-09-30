"""PPh atas uang muka diakui di Payment Entry.

ERPNext udah punya mesin PPh di Payment Entry: begitu `apply_tds` nyala dan kategorinya keisi,
`PaymentTaxWithholding` ngitung sendiri waktu dokumennya divalidasi, terus naruh hasilnya di
tabel pajak. Dasar hitungnya `unallocated_amount` plus alokasi ke dokumen uang muka (PO/SO) -
jadi pembayaran DP emang kasus yang dia dukung.

Yang bolong: **Payment Request gak kenal PPh sama sekali** (gak ada field, gak ada hook), dan
Payment Entry gak pernah nyalain `apply_tds` sendiri. Jadi DP yang dibayar lewat Advance Invoice
gak pernah motong PPh. Modul ini yang nyambungin: pas Payment Entry lahir dari Advance Invoice,
`apply_tds` dinyalain dan kategorinya diisi - sisanya ERPNext yang ngerjain.

Kategorinya dicari persis kayak cara ERPNext nyari buat baris invoice
(`stock/get_item_details.py`, `get_tax_withholding_category`): kategori di master **Item** dulu,
baru jatuh ke kategori di master Supplier/Customer.

Catatan: pelunasan **gak** ikut ke sini. Alokasi ke invoice sengaja gak diitung ERPNext sebagai
dasar PPh (`tax_withholding_entry.py`, `PaymentTaxWithholding._update_taxable_amounts`), karena
invoice-nya sendiri yang motong. PPh yang udah kepotong di DP otomatis dikurangin dari invoice,
asal Payment Entry DP-nya ditempelin di tabel Advances invoice itu.
"""

import frappe
from frappe import _
from frappe.utils import flt

# arah transaksi -> field kategori di master Item
ITEM_CATEGORY_FIELD = {
	"Customer": "sales_tax_withholding_category",
	"Supplier": "purchase_tax_withholding_category",
}


def resolve_category(doctype, name, party_type, party):
	"""Kategori & grup PPh buat satu dokumen sumber. `(None, None)` kalau gak kena PPh.

	Urutannya ngikut ERPNext: kategori di master Item menang duluan, baru kategori di master
	party. Grupnya selalu dari master party - itu yang nentuin baris tarif mana yang kepakai.
	"""
	field = ITEM_CATEGORY_FIELD.get(party_type)
	if not (field and party):
		return None, None

	group = frappe.db.get_value(party_type, party, "tax_withholding_group")

	for item_code in get_item_codes(doctype, name):
		category = frappe.db.get_value("Item", item_code, field)
		if category:
			return category, group

	return frappe.db.get_value(party_type, party, "tax_withholding_category"), group


def get_item_codes(doctype, name):
	"""Kode item di dokumen sumber, urut sesuai barisnya."""
	if not (doctype and name):
		return []

	table = f"{doctype} Item"
	if not frappe.db.exists("DocType", table):
		return []

	return frappe.get_all(table, filters={"parent": name}, pluck="item_code", order_by="idx")


def get_tax_rate(category, group, posting_date):
	"""Tarif PPh yang berlaku di tanggal itu, `0` kalau gak ada baris yang cocok.

	`get_applicable_tax_row` bawaan ERPNext ngelempar error kalau gak ketemu. Di sini errornya
	ditelen: fungsi ini cuma dipakai buat nampilin perkiraan di Advance Invoice, dan dokumen itu
	gak boleh gagal disimpan cuma gara-gara tabel tarifnya belum diisi.
	"""
	if not category:
		return 0

	try:
		row = frappe.get_cached_doc("Tax Withholding Category", category).get_applicable_tax_row(
			posting_date, group
		)
	except frappe.ValidationError:
		frappe.clear_last_message()
		return 0

	# nama field di baris tarifnya `tax_withholding_rate`; `tax_rate` itu nama hasil olahannya
	return flt(row.tax_withholding_rate)


def set_apply_tds(doc, method=None):
	"""Hook `before_validate` Payment Entry: nyalain PPh buat pembayaran uang muka.

	Cuma buat dokumen baru dan yang `apply_tds`-nya masih mati, biar pilihan user gak ketiban.
	"""
	if doc.get("apply_tds") or not doc.is_new():
		return

	from vic_addon.vic.dp_invoice import get_payment_request

	name = get_payment_request(doc)
	if not name:
		return

	request = frappe.db.get_value(
		"Payment Request",
		name,
		["reference_doctype", "reference_name", "custom_apply_tds"],
		as_dict=True,
	)
	if not (request and request.custom_apply_tds):
		return

	category, group = resolve_category(
		request.reference_doctype, request.reference_name, doc.party_type, doc.party
	)
	if not category:
		return

	doc.apply_tds = 1
	doc.tax_withholding_category = category
	if group:
		doc.tax_withholding_group = group


# ---------------------------------------------------------------------------------------------
# PPh atas pelunasan invoice
# ---------------------------------------------------------------------------------------------
#
# Mesin PPh bawaan Payment Entry gak bisa dipakai buat pelunasan: dasar hitungnya cuma uang yang
# belum dialokasi plus alokasi ke PO/SO - alokasi ke invoice dianggap nol, karena ERPNext ngira
# invoice-nya udah motong sendiri. Dan buat Customer arahnya dipaksa "Add" (skema TCS), padahal
# PPh 23 di sisi penjualan itu customer yang motong, uang masuk kita berkurang.
#
# Jadi di sini baris PPh-nya dibikin sendiri, sama kayak baris pajak di Advance Invoice:
#
#   PPh baris ini = (PPh penuh invoice - yang udah kepotong) x porsi yang dibayar sekarang
#
# - PPh penuh    = DPP invoice (`base_net_total`) x tarif kategori. Bukan dari uang yang dibayar:
#                  uang pelunasan udah termasuk PPN, dan PPh gak boleh kena PPN.
# - udah kepotong = PPh di Payment Entry uang muka yang ditempel di tabel Advances invoice, plus
#                  PPh pelunasan sebelumnya atas invoice yang sama (buat yang nyicil).
# - porsi        = alokasi sekarang / sisa tagihan sebelum pembayaran ini.
#
# Dua sisinya sama-sama "Deduct". Bedanya di akun: pembelian ngredit Utang PPh 23 (kewajiban),
# penjualan ndebit PPh 23 dibayar dimuka (aset) - makanya sisi penjualan butuh kategori sendiri.

INVOICE_PARTY = {"Purchase Invoice": "Supplier", "Sales Invoice": "Customer"}

TOGGLE_FIELD = "custom_apply_invoice_tds"
ROW_FLAG = "custom_invoice_withholding"
REFERENCE_AMOUNT = "custom_withholding_amount"


def apply_invoice_withholding(doc, method=None):
	"""Hook `before_validate` Payment Entry: susun ulang baris PPh atas pelunasan invoice.

	Tiap disimpan dihitung dari awal - baris yang kita pasang dibuang dulu - jadi kalau alokasi
	atau tanggalnya diganti, PPh-nya ikut. Baris pajak lain (PPN, baris ketikan user) gak disentuh.
	"""
	if doc.docstatus != 0:
		return

	keep = [row for row in doc.get("taxes") or [] if not row.get(ROW_FLAG)]
	if len(keep) != len(doc.get("taxes") or []):
		doc.set("taxes", keep)
		for index, row in enumerate(doc.taxes, start=1):
			row.idx = index

	for reference in doc.get("references") or []:
		reference.set(REFERENCE_AMOUNT, 0)

	if not doc.get(TOGGLE_FIELD):
		return

	per_account = {}
	for reference in get_invoice_references(doc):
		amount, account = get_reference_withholding(doc, reference)
		if not amount:
			continue

		reference.set(REFERENCE_AMOUNT, amount)
		per_account[account] = per_account.get(account, 0) + amount

	for account, amount in per_account.items():
		doc.append(
			"taxes",
			{
				"charge_type": "Actual",
				"account_head": account,
				"description": account,
				"add_deduct_tax": "Deduct",
				"tax_amount": flt(amount, doc.precision("paid_amount")),
				"cost_center": doc.get("cost_center") or erpnext_default_cost_center(doc.company),
				# sengaja gak pakai `is_tax_withholding_account`: baris yang ditandain itu
				# dinolin mesin PPh bawaan tiap validate
				ROW_FLAG: 1,
			},
		)


def get_invoice_references(doc):
	return [
		row
		for row in doc.get("references") or []
		if row.reference_doctype in INVOICE_PARTY and flt(row.allocated_amount)
	]


def get_reference_withholding(payment, reference):
	"""PPh atas satu baris alokasi ke invoice: `(nilai, akun)`, `(0, None)` kalau gak kena."""
	invoice = frappe.get_cached_doc(reference.reference_doctype, reference.reference_name)

	# invoice yang motong sendiri dilewat - kalau enggak, PPh-nya kepotong dua kali
	if invoice.get("apply_tds"):
		return 0, None

	party_type = INVOICE_PARTY[invoice.doctype]
	party = invoice.get(party_type.lower())

	category, group = resolve_category(invoice.doctype, invoice.name, party_type, party)
	if not category:
		return 0, None

	rate = get_tax_rate(category, group, payment.posting_date)
	if not rate:
		return 0, None

	account = frappe.get_cached_doc("Tax Withholding Category", category).get_company_account(
		payment.company
	)
	validate_account_side(account, party_type, category)

	full = flt(invoice.base_net_total) * rate / 100
	already = get_withheld_on_advances(invoice) + get_withheld_on_earlier_payments(
		invoice, exclude=payment.name
	)
	remaining = max(full - already, 0)

	outstanding = flt(reference.outstanding_amount)
	portion = min(flt(reference.allocated_amount) / outstanding, 1) if outstanding else 1

	return flt(remaining * portion, payment.precision("paid_amount")), account


def validate_account_side(account, party_type, category):
	"""Sisi penjualan wajib pakai akun aset, bukan kewajiban.

	Customer yang motong PPh-nya, jadi potongannya hak kita (PPh dibayar dimuka). Kalau yang
	kepakai akun Utang PPh, Payment Entry-nya bakal ndebit utang - kelihatan kayak kita udah nyetor
	PPh ke kantor pajak. Dicegah di sini biar gak salah posting diem-diem.
	"""
	if party_type != "Customer":
		return

	if frappe.db.get_value("Account", account, "root_type") == "Liability":
		frappe.throw(
			_(
				"Tax Withholding Category {0} posts to {1}, which is a liability account. On the sales side the customer withholds the tax, so it must go to an asset account (prepaid tax). Use a separate category for sales in the Item's Sales Tax Withholding Category."
			).format(frappe.bold(category), frappe.bold(account)),
			title=_("Wrong Account for Sales Withholding"),
		)


def get_withheld_on_advances(invoice):
	"""PPh yang udah kepotong di Payment Entry uang muka yang ditempel ke invoice ini.

	Diprorata sesuai porsi uang mukanya yang dipakai di invoice ini - satu uang muka bisa kebagi
	ke beberapa invoice.
	"""
	total = 0.0

	for advance in invoice.get("advances") or []:
		if advance.reference_type != "Payment Entry" or not flt(advance.allocated_amount):
			continue

		payment = frappe.get_cached_doc("Payment Entry", advance.reference_name)
		party_amount = flt(payment.paid_amount) or flt(payment.received_amount)
		if not party_amount:
			continue

		withheld = sum(
			flt(row.base_tax_amount)
			for row in payment.get("taxes") or []
			if row.get("is_tax_withholding_account") or row.get(ROW_FLAG)
		)
		total += withheld * min(flt(advance.allocated_amount) / party_amount, 1)

	return total


def get_withheld_on_earlier_payments(invoice, exclude=None):
	"""PPh pelunasan yang udah dipotong di Payment Entry lain atas invoice yang sama."""
	reference = frappe.qb.DocType("Payment Entry Reference")
	payment = frappe.qb.DocType("Payment Entry")

	query = (
		frappe.qb.from_(reference)
		.inner_join(payment)
		.on(payment.name == reference.parent)
		.select(reference[REFERENCE_AMOUNT])
		.where(
			(reference.reference_doctype == invoice.doctype)
			& (reference.reference_name == invoice.name)
			& (payment.docstatus == 1)
		)
	)
	if exclude:
		query = query.where(payment.name != exclude)

	return sum(flt(row[0]) for row in query.run())


def erpnext_default_cost_center(company):
	return frappe.get_cached_value("Company", company, "cost_center")


@frappe.whitelist()
def get_payment_entry(
	dt,
	dn,
	party_amount=None,
	bank_account=None,
	bank_amount=None,
	party_type=None,
	payment_type=None,
	reference_date=None,
	created_from_payment_request=False,
):
	"""Tombol `Create > Payment` di Purchase / Sales Invoice.

	Sama kayak versi ERPNext, cuma centangan Potong PPh atas Invoice langsung dinyalain kalau
	invoice-nya kena PPh, dan barisnya udah keisi - biar kelihatan di form sebelum disimpan.

	Argumennya sengaja ditulis satu-satu, sama persis kayak versi ERPNext - jangan diganti
	`*args, **kwargs`. Frappe nyaring isi request sesuai argumen fungsinya; kalau fungsinya nerima
	`**kwargs`, semuanya ikut kelempar (termasuk `cmd`), dan versi ERPNext-nya bakal nolak.
	"""
	from erpnext.accounts.doctype.payment_entry.payment_entry import (
		get_payment_entry as get_erpnext_payment_entry,
	)

	doc = get_erpnext_payment_entry(
		dt,
		dn,
		party_amount=party_amount,
		bank_account=bank_account,
		bank_amount=bank_amount,
		party_type=party_type,
		payment_type=payment_type,
		reference_date=reference_date,
		created_from_payment_request=created_from_payment_request,
	)

	if any(get_reference_withholding(doc, row)[0] for row in get_invoice_references(doc)):
		doc.set(TOGGLE_FIELD, 1)
		apply_invoice_withholding(doc)

	return doc
