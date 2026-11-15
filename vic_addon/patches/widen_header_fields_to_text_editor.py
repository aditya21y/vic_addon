"""Header 1 & Header 2 (`custom_header`, `custom_pengerjaan`) diubah dari Data ke Text Editor, biar
user bisa atur font/warna sendiri dan style-nya kebawa ke print format.

Frappe cuma ngizinin ganti fieldtype dalam satu grup (ALLOWED_FIELDTYPE_CHANGE), jadi Data -> Text
Editor harus lewat Text dulu. Tiap langkah save-nya yang ngelebarin kolom DB dari varchar(140) ke
longtext - penting karena HTML ber-style gampang lewat 140 karakter. Idempoten: field yang udah
Text Editor dilewatin. Costing Item (app doctype) ikut model sync, gak lewat sini.
"""

import frappe

FIELDS = ("custom_header", "custom_pengerjaan")


def execute():
	for name in frappe.get_all("Custom Field", filters={"fieldname": ["in", FIELDS]}, pluck="name"):
		cf = frappe.get_doc("Custom Field", name)
		if cf.fieldtype == "Text Editor":
			continue
		# Data -> Text -> Text Editor (lompatan yang diizinin Frappe)
		for fieldtype in ("Text", "Text Editor"):
			cf.fieldtype = fieldtype
			cf.save()
