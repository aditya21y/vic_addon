"""Pengelompokan baris item dua tingkat: Pengerjaan, lalu Pengiriman.

- **Pengerjaan** (`custom_pengerjaan`) - kelompok paling atas. Ada di Opportunity (RFQ), Request
  for Quotation (Inquiry), Costing, Quotation, Sales Order, Delivery Note, Sales Invoice.
- **Pengiriman** (`custom_header`, dulu labelnya "Header") - kelompok di dalam Pengerjaan. Ada di
  doctype di atas plus Purchase Order, Purchase Receipt, Purchase Invoice.

Dua-duanya cukup diisi di baris pertama tiap kelompok: baris yang dikosongin ikut baris di
atasnya. Pengiriman mulai dari nol lagi tiap ganti Pengerjaan - baris pertama Pengerjaan baru gak
ngewarisin Pengiriman dari Pengerjaan sebelumnya. Yang gak boleh:

- Pengerjaan dipakai, tapi baris pertama dokumen kosong (gak ada baris di atasnya buat diikutin)
- di satu kelompok Pengerjaan ada Pengiriman, tapi baris pertama kelompok itu kosong

Nilai yang diwarisin ditulis balik ke barisnya waktu dokumen disimpan. Jadi isi tabelnya selalu
eksplisit, dan waktu dokumen diturunin (Quotation -> Sales Order -> Delivery Note, Invoice)
kelompoknya ikut kebawa sendiri - field-nya senama di semua doctype, dan mapper bawaan Frappe
nyalin field senama.

Di print format Pengerjaan dicetak paling atas (tebal + garis bawah), Pengiriman di bawahnya
(tebal), dan item menjorok di bawah keduanya.
"""

import frappe
from frappe import _

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
	"""Nurunin Pengerjaan & Pengiriman ke baris-baris di bawahnya, sekalian jaga baris pertamanya."""
	rows = doc.get(HEADER_TABLES[doc.doctype]) or []
	if not rows:
		return

	meta = frappe.get_meta(rows[0].doctype)

	if meta.has_field(PENGERJAAN) and any(get_value(row, PENGERJAAN) for row in rows):
		fill_down(rows, PENGERJAAN, _("Pengerjaan"))
		segments = split_by(rows, PENGERJAAN)
	else:
		segments = [rows]

	# Dokumen / kelompok yang emang gak pakai Pengiriman dibiarin apa adanya - yang dijaga cuma
	# jangan sampai ada baris nyangkut tanpa induk di kelompok yang pakai.
	if meta.has_field(FIELDNAME):
		for segment in segments:
			if any(get_value(row, FIELDNAME) for row in segment):
				fill_down(segment, FIELDNAME, _("Pengiriman"))


def fill_down(rows, fieldname, label):
	value = ""

	for row in rows:
		own = get_value(row, fieldname)

		if not own and not value:
			frappe.throw(
				_(
					"Row #{0}: {1} is required on the first item of the group, because the rows below it follow the row above them."
				).format(row.idx, label),
				title=_("{0} Required").format(label),
			)

		value = own or value
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

	Tiap kelompok: `pengerjaan` (judul Pengerjaan, cuma diisi di kelompok pertama Pengerjaan itu
	biar judulnya kecetak sekali), `header` (judul Pengiriman), `header_indent` (class menjorok
	judul Pengiriman), `indent` (class menjorok baris item), dan `rows`.

	Dokumen tanpa Pengerjaan & Pengiriman balik jadi satu kelompok tanpa judul, jadi print format
	tetap kecetak kayak biasa.
	"""
	tree = {}

	for row in items or []:
		pengerjaan = get_value(row, PENGERJAAN)
		tree.setdefault(pengerjaan, {}).setdefault(get_header(row), []).append(row)

	groups = []
	for pengerjaan, headers in tree.items():
		for i, (header, rows) in enumerate(headers.items()):
			depth = (1 if pengerjaan else 0) + (1 if header else 0)
			groups.append(
				frappe._dict(
					pengerjaan=pengerjaan if i == 0 else "",
					header=header,
					header_indent="indent" if pengerjaan else "",
					indent={0: "", 1: "indent", 2: "indent-2"}[depth],
					rows=rows,
				)
			)

	return groups


def group_items_by_header(items):
	"""Baris item -> [(pengiriman, [baris, ...]), ...] - versi satu tingkat, buat print format
	doctype yang gak punya Pengerjaan (Purchase Order, Purchase Receipt)."""
	groups = {}

	for row in items or []:
		groups.setdefault(get_header(row), []).append(row)

	return list(groups.items())
