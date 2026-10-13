"""Helper Jinja buat print format VIC."""

from frappe.utils import strip_html


def get_item_description(item):
	"""Isi kolom Description di tabel item: description dulu, kalau kosong baru item name.

	Description itu Text Editor (HTML), jadi dicetak apa adanya - format tebal/baris barunya ikut.
	Editor sering nyimpen tag kosong (`<p></p>`, `<br>`) waktu isinya dihapus; yang kayak gitu
	dianggap kosong. Doctype yang barisnya gak punya description (mis. Costing Item) langsung jatuh
	ke item name.
	"""
	description = item.get("description") or ""
	if strip_html(description).replace("&nbsp;", " ").strip():
		return description

	return item.get("item_name") or item.get("item_code") or ""


# ---------------------------------------------------------------------------------------------
# Kwitansi (Sales Invoice)
# ---------------------------------------------------------------------------------------------

BULAN = (
	"Januari", "Februari", "Maret", "April", "Mei", "Juni",
	"Juli", "Agustus", "September", "Oktober", "November", "Desember",
)


def terbilang(amount, upper=False):
	"""Angka -> kata bahasa Indonesia + "Rupiah": 17760000000 -> "Tujuh Belas Miliar ... Rupiah"."""
	from num2words import num2words
	from frappe.utils import flt

	words = num2words(int(round(flt(amount))), lang="id") + " rupiah"
	return words.upper() if upper else words.title()


def tanggal(date, upper=False):
	"""Tanggal bahasa Indonesia: 2026-07-06 -> "06 Juli 2026"."""
	from frappe.utils import getdate

	if not date:
		return ""
	date = getdate(date)
	text = f"{date.day:02d} {BULAN[date.month - 1]} {date.year}"
	return text.upper() if upper else text


def get_kwitansi(doc):
	"""Semua isian kwitansi Sales Invoice, dipakai print format Kwitansi & Kwitansi (Progress).

	Yang diketik user ada di tab Kwitansi (bisa diisi setelah submit); sisanya diambil dari invoice,
	Company, dan Bank Account-nya.
	"""
	import frappe
	from frappe.utils import flt

	company = frappe.get_cached_doc("Company", doc.company)

	# nilai yang beneran ditagih: total dikurangi DP yang dibalik & uang muka yang udah dialokasiin
	amount = flt(doc.get("custom_kwitansi_amount")) or (
		flt(doc.rounded_total or doc.grand_total)
		- flt(doc.get("custom_total_dp_allocated"))
		- flt(doc.get("total_advance"))
	)

	bank = frappe._dict()
	if doc.get("custom_kwitansi_bank_account"):
		bank = frappe.db.get_value(
			"Bank Account",
			doc.custom_kwitansi_bank_account,
			["bank", "bank_account_no", "branch_code"],
			as_dict=True,
		) or frappe._dict()

	delivery_notes = sorted({row.delivery_note for row in doc.get("items") or [] if row.get("delivery_note")})
	project = (frappe.db.get_value("Project", doc.project, "project_name") or doc.project) if doc.get("project") else ""

	return frappe._dict(
		no=doc.get("custom_kwitansi_no") or "",
		date=doc.get("custom_kwitansi_date") or doc.posting_date,
		city=company.get("custom_kwitansi_city") or "Jakarta",
		amount=amount,
		received_from=doc.customer_name or doc.customer,
		project=project,
		payment_for=(doc.get("custom_kwitansi_payment_for") or "").strip(),
		invoice_no=doc.name,
		delivery_notes=delivery_notes,
		faktur_no=doc.get("custom_faktur_pajak_no") or "",
		spp_no=doc.get("custom_kwitansi_spp_no") or "",
		spp_date=doc.get("custom_kwitansi_spp_date"),
		period_from=doc.get("custom_kwitansi_period_from"),
		period_to=doc.get("custom_kwitansi_period_to"),
		bank=bank.get("bank") or "",
		bank_branch=bank.get("branch_code") or "",
		account_no=bank.get("bank_account_no") or "",
		account_name=company.company_name,
		signer=company.get("custom_kwitansi_signer") or "",
		signer_title=company.get("custom_kwitansi_signer_title") or "",
		currency=doc.currency,
	)
