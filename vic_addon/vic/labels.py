"""Label dokumen yang beda dari bawaan ERPNext.

Frappe gak nyediain cara ngeganti label doctype lewat Customize Form (yang bisa dicustom cuma
label field-nya). Tapi semua teks di desk lewat `__()`, jadi nama doctype bisa diganti lewat
record `Translation` di bahasa yang dipakai site.

Doctype-nya sendiri **gak** di-rename: nama aslinya tetap kepakai di kode, hooks, link field,
dan laporan. Yang diganti cuma tulisan yang kelihatan user.

Catatan: yang dicocokin itu teks persis, dan berlaku di seluruh desk - bukan cuma di judul
doctype-nya. Jadi field yang labelnya persis "Opportunity" di doctype lain (Quotation, Supplier
Quotation, Customer) ikut kebaca jadi label baru - itu emang dimau, soalnya field-nya emang
nunjuk ke dokumen yang sama.

Di tabel di bawah, "Request For Quotation" muncul dua kali: sebagai hasil terjemahan Opportunity,
dan sebagai teks asli yang diterjemahin jadi Inquiry. Itu gak muter-muter - Frappe nerjemahin
sekali, hasil terjemahan gak dilempar balik buat diterjemahin lagi.

Dijalanin lewat hook `after_install` & `after_migrate` - `Translation` gak punya field Module,
jadi gak bisa dijadiin fixture yang kefilter per app.
"""

import frappe

# teks asli -> teks yang dipakai di VIC
LABELS = {
	# Payment Request dipakai sebagai invoice uang muka (DP), bukan permintaan bayar biasa
	"Payment Request": "Advance Invoice",
	"Payment Requests": "Advance Invoices",
	"Payment Request Type": "Advance Invoice Type",
	# Di VIC, permintaan penawaran dari customer dicatat sebagai Opportunity, dan permintaan
	# harga ke supplier dicatat sebagai Request for Quotation. Istilah yang dipakai sehari-hari
	# beda: yang dari customer disebut Request For Quotation, yang ke supplier disebut Inquiry.
	"Opportunity": "Request For Quotation",
	"Opportunities": "Request For Quotations",
	"Opportunity Amount": "Request For Quotation Amount",
	"Opportunity Amount (Company Currency)": "Request For Quotation Amount (Company Currency)",
	"Opportunity Date": "Request For Quotation Date",
	"Opportunity From": "Request For Quotation From",
	"Opportunity Owner": "Request For Quotation Owner",
	"Opportunity Type": "Request For Quotation Type",
	"Opportunity Value": "Request For Quotation Value",
	"Request for Quotation": "Inquiry",
	"Request for Quotations": "Inquiries",
	# Tombol `Create > Request For Quotation` di Opportunity nulisnya pakai F besar - satu-satunya
	# tempat di ERPNext yang begitu. Dia bikin Request for Quotation, jadi ikut jadi Inquiry.
	"Request For Quotation": "Inquiry",
	"Request for Quotation Item": "Inquiry Item",
	"Request for Quotation Supplier": "Inquiry Supplier",
}


def setup_document_labels():
	from frappe.translate import clear_cache

	for language in get_languages():
		for source_text, translated_text in LABELS.items():
			set_translation(language, source_text, translated_text)

	clear_cache()


def get_languages():
	"""Bahasa site + bahasa tiap user, biar labelnya kelihatan sama buat semua orang."""
	languages = set(frappe.get_all("User", pluck="language"))
	languages.add(frappe.db.get_single_value("System Settings", "language"))
	languages.discard(None)
	languages.add("en")

	return sorted(languages)


def set_translation(language, source_text, translated_text):
	name = find_translation(language, source_text)

	if name:
		frappe.db.set_value("Translation", name, "translated_text", translated_text)
		return

	frappe.get_doc(
		{
			"doctype": "Translation",
			"language": language,
			"source_text": source_text,
			"translated_text": translated_text,
		}
	).insert(ignore_permissions=True)


def find_translation(language, source_text):
	"""Record Translation yang teks aslinya sama PERSIS, termasuk besar-kecil hurufnya.

	Pencarian di database gak bedain huruf besar-kecil (collation bawaan MySQL), padahal di sini
	bedanya penting: "Request for Quotation" (nama doctype) sama "Request For Quotation" (tulisan
	tombol Create di Opportunity) itu dua teks yang beda. Kalau ngandelin pencarian database,
	yang kedua bakal nimpa yang pertama dan salah satunya gak pernah kepasang. Jadi kandidatnya
	diambil dulu, baru dicocokin sendiri di sini.
	"""
	rows = frappe.get_all(
		"Translation",
		filters={"language": language, "source_text": source_text, "context": ("is", "not set")},
		fields=["name", "source_text"],
	)

	for row in rows:
		if row.source_text == source_text:
			return row.name

	return None
