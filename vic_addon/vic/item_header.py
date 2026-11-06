"""Pengelompokan baris item dua tingkat: Header 1, lalu Header 2.

- **Header 1** (`custom_header`) - kelompok paling atas. Ada di Opportunity (RFQ), Request for
  Quotation (Inquiry), Costing, Quotation, Sales Order, Delivery Note, Sales Invoice, plus Purchase
  Order, Purchase Receipt, Purchase Invoice.
- **Header 2** (`custom_pengerjaan`) - kelompok di dalam Header 1. Ada di doctype di atas kecuali
  Purchase Order, Purchase Receipt, Purchase Invoice.

Labelnya dulu Pengiriman (Header 1) dan Pengerjaan (Header 2). Yang diganti cuma label: fieldname
dan nama internal di kode & print format (`group.pengiriman`, `group.pengerjaan`) tetap.

Dua-duanya opsional dan cukup diisi di baris pertama tiap kelompok: baris yang dikosongin ikut baris
di atasnya. Header 2 mulai dari nol lagi tiap ganti Header 1 - baris pertama Header 1 baru gak
ngewarisin Header 2 dari Header 1 sebelumnya. Baris yang di atasnya belum ada nilai (mis. baris
pertama dokumen) boleh kosong dan tetap kosong: dicetak tanpa judul.

Nilai yang diwarisin ditulis balik ke barisnya waktu dokumen disimpan. Jadi isi tabelnya selalu
eksplisit, dan waktu dokumen diturunin (Quotation -> Sales Order -> Delivery Note, Invoice)
kelompoknya ikut kebawa sendiri - field-nya senama di semua doctype, dan mapper bawaan Frappe
nyalin field senama.

Di print format Header 1 dicetak paling atas (tebal + garis bawah), Header 2 di bawahnya
(tebal), terus itemnya - gak ada yang menjorok.
"""

import frappe

FIELDNAME = "custom_header"
PENGERJAAN = "custom_pengerjaan"

# doctype induk -> nama child table yang barisnya dikelompokin
HEADER_TABLES = {
	# Opportunity (RFQ) -> Request for Quotation (Inquiry): kelompoknya ikut kebawa lewat field senama
	"Opportunity": "items",
	"Request for Quotation": "items",
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
	"""Nurunin Header 1 & Header 2 ke baris-baris di bawahnya."""
	rows = doc.get(HEADER_TABLES[doc.doctype]) or []
	if not rows:
		return

	meta = frappe.get_meta(rows[0].doctype)

	if meta.has_field(FIELDNAME):
		fill_down(rows, FIELDNAME)

	if meta.has_field(PENGERJAAN):
		for segment in split_by(rows, FIELDNAME):
			fill_down(segment, PENGERJAAN)


def fill_down(rows, fieldname):
	"""Baris kosong ikut nilai di atasnya; yang di atasnya belum ada nilai dibiarin kosong."""
	value = ""

	for row in rows:
		value = get_value(row, fieldname) or value
		if value:
			row.set(fieldname, value)


def split_by(rows, fieldname):
	"""Baris berurutan -> potongan tiap kali nilai field-nya ganti."""
	segments = []

	for row in rows:
		if not segments or get_value(row, fieldname) != get_value(segments[-1][-1], fieldname):
			segments.append([])
		segments[-1].append(row)

	return segments


def get_value(row, fieldname):
	return (row.get(fieldname) or "").strip()


def get_header(row):
	return get_value(row, FIELDNAME)


def group_items(items):
	"""Baris item -> daftar kelompok buat print format, urutannya ngikut kemunculan pertama.

	Tiap kelompok: `pengiriman` (judul Header 1, cuma diisi di kelompok pertama Header 1 itu
	biar judulnya kecetak sekali), `pengerjaan` (judul Header 2), dan `rows`.

	Dokumen tanpa Header 1 & Header 2 balik jadi satu kelompok tanpa judul, jadi print format
	tetap kecetak kayak biasa.
	"""
	tree = {}

	for row in items or []:
		tree.setdefault(get_header(row), {}).setdefault(get_value(row, PENGERJAAN), []).append(row)

	groups = []
	for pengiriman, pengerjaan_groups in tree.items():
		for i, (pengerjaan, rows) in enumerate(pengerjaan_groups.items()):
			groups.append(
				frappe._dict(
					pengiriman=pengiriman if i == 0 else "",
					pengerjaan=pengerjaan,
					rows=rows,
				)
			)

	return groups


def group_items_by_header(items):
	"""Baris item -> [(header 1, [baris, ...]), ...] - versi satu tingkat, buat print format
	doctype yang gak punya Header 2 (Purchase Order, Purchase Receipt)."""
	groups = {}

	for row in items or []:
		groups.setdefault(get_header(row), []).append(row)

	return list(groups.items())
