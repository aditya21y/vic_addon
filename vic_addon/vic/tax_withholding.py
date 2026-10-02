"""PPh diakui di Payment Entry - uang muka maupun pelunasan - dan dihitung per baris item.

Semua baris PPh di Payment Entry dihitung sendiri di modul ini; mesin PPh bawaan ERPNext
(`apply_tds`) dimatiin total. Alasannya:

- Mesin bawaan ngambil dasar dari **seluruh uang** yang dialokasi ke PO/SO (plus yang belum
  dialokasi), gak lihat item. DP 20% dari PO yang cuma satu itemnya jasa jadi kepotong PPh atas
  seluruh DP - termasuk barang, dan PPN-nya kalau ada.
- Alokasi ke invoice dianggap nol, karena ERPNext ngira invoice-nya udah motong sendiri.
- Buat Customer arahnya dipaksa "Add" (skema TCS), kebalikan PPh 23.

Kategorinya dicari persis kayak cara ERPNext ngisi baris invoice
(`stock/get_item_details.py`, `get_tax_withholding_category`): kategori di master **Item** dulu,
baru jatuh ke kategori di master Supplier/Customer. Baris tanpa kategori gak kena.

Semua centangan PPh **otomatis dan read only** - user gak milih. Di Purchase / Sales Invoice
centangannya dipaksa mati, karena PPh selalu diakui waktu dibayar.
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


# ---------------------------------------------------------------------------------------------
# Baris PPh di Payment Entry
# ---------------------------------------------------------------------------------------------
#
# PPh penuh satu dokumen (PO/SO/PI/SI) = Σ per kategori: DPP baris item berkategori x tarif.
# Dasarnya DPP, bukan uang yang dibayar - uang itu bisa udah termasuk PPN, dan PPh gak boleh kena
# PPN. Tiap baris alokasi di PE motong sebagian dari PPh penuh itu:
#
# - alokasi ke PO/SO (uang muka):  PPh penuh x porsi DP
#       porsi = alokasi / Net Total kalau lewat Advance Invoice (DP-nya dihitung dari Net Total,
#               PPN-nya jadi baris pajak sendiri), selain itu alokasi / Grand Total.
# - alokasi ke PI/SI (pelunasan):  (PPh penuh - yang udah kepotong) x alokasi / sisa tagihan
#       yang udah kepotong = PPh di PE uang muka yang ditempel di tabel Advances invoice, plus
#       PPh pelunasan sebelumnya atas invoice yang sama (buat yang nyicil).
# - uang yang belum dialokasi:     uang itu x tarif kategori master party - gak ada item yang
#       bisa dilihat, jadi ikut cara ERPNext.
#
# Dua sisinya sama-sama "Deduct". Bedanya di akun: pembelian ngredit Utang PPh 23 (kewajiban),
# penjualan ndebit PPh 23 dibayar dimuka (aset) - makanya sisi penjualan butuh kategori sendiri.

INVOICE_PARTY = {"Purchase Invoice": "Supplier", "Sales Invoice": "Customer"}
ADVANCE_DOCTYPES = ("Purchase Order", "Sales Order")

# centangan read only "Potong PPh" - nama field-nya peninggalan waktu cuma buat pelunasan invoice
TOGGLE_FIELD = "custom_apply_invoice_tds"
ROW_FLAG = "custom_invoice_withholding"
REFERENCE_AMOUNT = "custom_withholding_amount"


def apply_withholding(doc, method=None):
	"""Hook `before_validate` Payment Entry: susun ulang semua baris PPh.

	Tiap disimpan dihitung dari awal - baris PPh dibuang dulu - jadi kalau alokasi atau tanggalnya
	diganti, PPh-nya ikut. Baris pajak lain (PPN, baris ketikan user) gak disentuh. Centangan
	Potong PPh (read only) cuma penanda: nyala kalau ada baris yang kepasang.
	"""
	if doc.docstatus != 0:
		return

	# mesin bawaan dimatiin; baris bertanda `is_tax_withholding_account` itu sisa draft lama
	doc.apply_tds = 0
	doc.tax_withholding_category = None
	doc.tax_withholding_group = None
	doc.set("tax_withholding_entries", [])

	taxes = doc.get("taxes") or []
	keep = [row for row in taxes if not (row.get(ROW_FLAG) or row.get("is_tax_withholding_account"))]
	if len(keep) != len(taxes):
		doc.set("taxes", keep)
		for index, row in enumerate(doc.taxes, start=1):
			row.idx = index

	for reference in doc.get("references") or []:
		reference.set(REFERENCE_AMOUNT, 0)

	doc.set(TOGGLE_FIELD, 0)

	if doc.party_type not in ITEM_CATEGORY_FIELD:
		return

	per_account = {}

	def add(amounts):
		for account, amount in amounts.items():
			per_account[account] = per_account.get(account, 0) + amount

	for reference in doc.get("references") or []:
		if not flt(reference.allocated_amount):
			continue

		if reference.reference_doctype in INVOICE_PARTY:
			amounts = get_reference_withholding(doc, reference)
		elif reference.reference_doctype in ADVANCE_DOCTYPES:
			amounts = get_order_withholding(doc, reference)
		else:
			continue

		reference.set(REFERENCE_AMOUNT, sum(amounts.values()))
		add(amounts)

	add(get_unallocated_withholding(doc))

	precision = doc.precision("paid_amount")
	per_account = {account: flt(amount, precision) for account, amount in per_account.items()}
	per_account = {account: amount for account, amount in per_account.items() if amount}
	if per_account:
		doc.set(TOGGLE_FIELD, 1)

	for account, amount in per_account.items():
		doc.append(
			"taxes",
			{
				"charge_type": "Actual",
				"account_head": account,
				"description": account,
				"add_deduct_tax": "Deduct",
				"tax_amount": amount,
				"cost_center": doc.get("cost_center") or erpnext_default_cost_center(doc.company),
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
	"""PPh atas satu baris alokasi ke invoice: `{akun: nilai}`, kosong kalau gak kena."""
	invoice = frappe.get_cached_doc(reference.reference_doctype, reference.reference_name)

	# invoice yang motong sendiri dilewat - kalau enggak, PPh-nya kepotong dua kali
	if invoice.get("apply_tds"):
		return {}

	party_type = INVOICE_PARTY[invoice.doctype]
	full = get_full_withholding(invoice, party_type, invoice.get(party_type.lower()), payment)
	total = sum(full.values())
	if not total:
		return {}

	already = get_withheld_on_advances(invoice) + get_withheld_on_earlier_payments(
		invoice, exclude=payment.name
	)
	remaining = max(total - already, 0)

	outstanding = flt(reference.outstanding_amount)
	portion = min(flt(reference.allocated_amount) / outstanding, 1) if outstanding else 1

	# yang udah kepotong gak kecatat per kategori, jadi sisanya dibagi ke tiap akun sebanding
	# PPh penuhnya
	return {account: remaining * portion * amount / total for account, amount in full.items()}


def get_order_withholding(payment, reference):
	"""PPh uang muka atas satu baris alokasi ke PO/SO: `{akun: nilai}`."""
	order = frappe.get_cached_doc(reference.reference_doctype, reference.reference_name)
	party_type = "Supplier" if order.doctype == "Purchase Order" else "Customer"

	full = get_full_withholding(order, party_type, order.get(party_type.lower()), payment)
	if not full:
		return {}

	# lewat Advance Invoice yang dialokasi DP net (PPN-nya baris pajak sendiri), jadi porsinya
	# dari Net Total; bayar langsung dari PO/SO dialokasi dari tagihan penuh, jadi dari Grand Total
	base = flt(order.net_total) if reference.get("payment_request") else flt(order.grand_total)
	if not base:
		return {}

	portion = flt(reference.allocated_amount) / base
	return {account: amount * portion for account, amount in full.items()}


def get_unallocated_withholding(payment):
	"""PPh atas uang yang belum dialokasi ke dokumen mana pun - pakai kategori master party."""
	references = payment.get("references") or []
	party_amount = (
		flt(payment.paid_amount) if payment.payment_type == "Receive" else flt(payment.received_amount)
	)
	# `unallocated_amount` baru dihitung ulang di validate, jadi di sini dihitung sendiri
	unallocated = party_amount - sum(flt(row.allocated_amount) for row in references)
	if unallocated <= 0.005:
		return {}

	category = frappe.db.get_value(payment.party_type, payment.party, "tax_withholding_category")
	if not category:
		return {}

	group = frappe.db.get_value(payment.party_type, payment.party, "tax_withholding_group")
	rate = get_tax_rate(category, group, payment.posting_date)
	if not rate:
		warn_missing_rate(category, group, payment.posting_date)
		return {}

	account = get_category_account(category, payment.company, payment.party_type)
	return {account: unallocated * rate / 100}


def get_full_withholding(source, party_type, party, payment):
	"""PPh penuh satu dokumen per akun: Σ per kategori (DPP baris berkategori x tarif)."""
	# grup tarif: yang kesimpan di dokumen dulu (ERPNext ngisinya dari master party), baru master
	group = source.get("tax_withholding_group") or frappe.db.get_value(
		party_type, party, "tax_withholding_group"
	)

	full = {}
	for category, taxable in get_taxable_by_category(source, party_type, party).items():
		rate = get_tax_rate(category, group, payment.posting_date)
		if not rate:
			warn_missing_rate(category, group, payment.posting_date)
			continue

		account = get_category_account(category, payment.company, party_type)
		full[account] = full.get(account, 0) + taxable * rate / 100

	return full


def get_category_account(category, company, party_type):
	account = frappe.get_cached_doc("Tax Withholding Category", category).get_company_account(company)
	validate_account_side(account, party_type, category)
	return account


def get_taxable_by_category(invoice, party_type, party):
	"""Dasar PPh dokumen per kategori, dijumlah dari baris item - sama kayak ERPNext.

	Kategorinya diambil dari yang kesimpan di baris item (`tax_withholding_category`, diisi
	ERPNext waktu item dipilih di invoice: master Item dulu, kalau kosong master Supplier/Customer).
	Baris PO/SO gak nyimpen kategori, jadi dicari pakai urutan yang sama. Baris invoice yang
	`apply_tds`-nya mati dilewat, kayak di ERPNext (`TaxWithholdingController._update_amount_for_item`);
	baris PO/SO gak punya field itu.
	"""
	field = ITEM_CATEGORY_FIELD[party_type]
	party_category = frappe.db.get_value(party_type, party, "tax_withholding_category")

	taxable = {}
	for item in invoice.get("items") or []:
		if item.get("apply_tds") == 0:
			continue

		category = (
			item.get("tax_withholding_category")
			or frappe.db.get_value("Item", item.item_code, field)
			or party_category
		)
		if not category:
			continue

		amount = flt(item.base_net_amount)
		if get_deduction_basis(category) == "Gross Total" and flt(invoice.base_net_total):
			# ERPNext nambahin pajak baris itu; di sini dibagi rata sebanding DPP-nya
			amount += amount / flt(invoice.base_net_total) * flt(invoice.base_total_taxes_and_charges)

		taxable[category] = taxable.get(category, 0) + amount

	return taxable


def get_deduction_basis(category):
	return frappe.get_cached_value("Tax Withholding Category", category, "tax_deduction_basis")


def warn_missing_rate(category, group, posting_date):
	"""Kasih tau user kalau invoice-nya kena PPh tapi gak ada baris tarif yang cocok.

	Baris tarif cocok kalau tanggalnya masuk **dan** grupnya persis sama dengan grup party - party
	tanpa grup cuma cocok sama baris yang grupnya juga kosong. Dua-duanya disebut di pesan, soalnya
	penyebab yang sering kejadian dua: `to_date` udah lewat, atau party-nya belum dikasih grup.
	Tanpa peringatan ini PE kesimpen tanpa PPh diem-diem. Sekali per kategori per request.
	"""
	key = (category, group, str(posting_date))
	warned = frappe.flags.setdefault("vic_missing_withholding_rate", set())
	if key in warned:
		return
	warned.add(key)

	frappe.msgprint(
		_(
			"Tax Withholding Category {0} has no rate row for date {1} and Tax Withholding Group {2}, so no tax is withheld on this payment. A rate row must match both the date range and the group exactly. Set the group on the Supplier / Customer, or add a matching rate row in the category, then save again."
		).format(
			frappe.bold(category),
			frappe.bold(frappe.format(posting_date, "Date")),
			frappe.bold(group or _("(empty)")),
		),
		title=_("Tax Withholding Rate Not Found"),
		indicator="orange",
	)


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
	"""Tombol `Create > Payment` di PO / SO / Purchase Invoice / Sales Invoice.

	Sama kayak versi ERPNext, cuma PPh-nya langsung dihitung - biar barisnya udah kelihatan di form
	sebelum disimpan. Waktu disimpan dihitung ulang lagi di hook `before_validate`.

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

	apply_withholding(doc)

	return doc


def turn_off_invoice_tds(doc, method=None):
	"""Hook `before_validate` Purchase / Sales Invoice: PPh gak pernah dipotong di invoice.

	Centangannya disembunyiin, tapi ERPNext tetap nyalainnya sendiri dari kategori supplier /
	customer (juga lewat jalur tanpa form: mapper, import, API) - jadi dimatiin di server juga.
	"""
	if doc.docstatus == 0 and doc.get("apply_tds"):
		doc.apply_tds = 0
