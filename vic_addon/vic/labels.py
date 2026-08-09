"""Label dokumen yang beda dari bawaan ERPNext.

Frappe gak nyediain cara ngeganti label doctype lewat Customize Form (yang bisa dicustom cuma
label field-nya). Tapi semua teks di desk lewat `__()`, jadi nama doctype bisa diganti lewat
record `Translation` di bahasa yang dipakai site.

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
	name = frappe.db.get_value(
		"Translation", {"language": language, "source_text": source_text, "context": ("is", "not set")}
	)

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
