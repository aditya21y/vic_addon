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
