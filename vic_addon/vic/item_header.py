"""Pengelompokan baris item lewat field Header.

User ngetik Header di baris item buat nandain kelompok pekerjaan. Baris yang Header-nya
dikosongin ikut kelompok baris di atasnya, jadi cukup diisi di baris pertama tiap kelompok -
mau diisi semua juga boleh, hasilnya sama. Yang gak boleh cuma baris pertama kosong, karena
gak ada baris di atasnya buat diikutin.

Header yang diwarisin ditulis balik ke barisnya waktu dokumen disimpan. Jadi isi tabelnya
selalu eksplisit, dan waktu dokumen diturunin (Quotation -> Sales Order -> Purchase Order,
Delivery Note, Invoice) kelompoknya ikut kebawa sendiri - field-nya senama di semua doctype,
dan mapper bawaan Frappe nyalin field senama.

Di print format tiap Header dicetak jadi baris sendiri (tebal) dan item di bawahnya menjorok
ke dalam.
"""

import frappe
from frappe import _

FIELDNAME = "custom_header"

# doctype induk -> nama child table yang barisnya dikelompokin
HEADER_TABLES = {
	"Costing": "items",
	"Quotation": "items",
	"Sales Order": "items",
	"Purchase Order": "items",
	"Purchase Receipt": "items",
	"Purchase Invoice": "items",
	"Delivery Note": "items",
	"Sales Invoice": "items",
}

ITEM_HEADER_DOCTYPES = tuple(HEADER_TABLES)


def set_item_headers(doc, method=None):
	"""Nurunin Header ke baris-baris di bawahnya, sekalian jaga baris pertama gak kosong."""
	rows = doc.get(HEADER_TABLES[doc.doctype]) or []

	if not rows or not has_header_field(rows[0].doctype):
		return

	# Dokumen yang emang gak pakai pengelompokan dibiarin apa adanya - yang dijaga cuma jangan
	# sampai ada baris nyangkut tanpa induk di dokumen yang pakai.
	if not any(get_header(row) for row in rows):
		return

	header = ""

	for row in rows:
		value = get_header(row)

		if not value and not header:
			frappe.throw(
				_(
					"Row #{0}: Header is required on the first item, because the rows below it follow the header above them."
				).format(row.idx),
				title=_("Header Required"),
			)

		header = value or header
		row.set(FIELDNAME, header)


def has_header_field(doctype):
	return frappe.get_meta(doctype).has_field(FIELDNAME)


def get_header(row):
	return (row.get(FIELDNAME) or "").strip()


def group_items_by_header(items):
	"""Baris item -> [(header, [baris, ...]), ...], urutan kelompok ngikut kemunculan pertamanya.

	Dipakai print format. Dokumen tanpa Header balik jadi satu kelompok berjudul kosong, biar
	print format lama tetap kecetak seperti biasa.
	"""
	groups = {}

	for row in items or []:
		groups.setdefault(get_header(row), []).append(row)

	return list(groups.items())
