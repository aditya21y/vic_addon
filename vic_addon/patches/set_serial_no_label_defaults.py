"""Isi default ukuran label di Serial Number Settings yang udah kebikin duluan.

Default di doctype cuma kepakai waktu dokumennya pertama dibikin, sedangkan Single ini udah ada
sebelum field labelnya ditambahin - jadi nilainya kosong dan harus diisi sekali di sini.
"""

import frappe

DEFAULTS = {
	"label_width": 50,
	"label_height": 30,
	"label_font_size": 7,
	"label_show_item_name": 1,
}


def execute():
	settings = frappe.get_single("Serial Number Settings")
	changed = False

	for fieldname, value in DEFAULTS.items():
		if settings.get(fieldname) in (None, "", 0.0):
			settings.set(fieldname, value)
			changed = True

	if changed:
		settings.flags.ignore_permissions = True
		settings.save()
