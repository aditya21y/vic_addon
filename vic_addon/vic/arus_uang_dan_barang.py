"""Kertas Kerja Pemeriksaan - Arus Uang dan Barang, versi Excel.

Bentuknya ngikut kertas kerja yang dipakai pemeriksa pajak: kotak identitas PKP di kanan atas,
terus dua blok berdampingan - PENYERAHAN di kiri, PEMBELIAN di kanan - dengan judul kolom
bertingkat. Bentuk kayak gini gak bisa dibikin report bawaan Frappe (judul kolomnya gak bisa
di-merge), makanya file Excel-nya disusun sendiri.

Datanya dipakai bareng sama report di desk (`vic/report/arus_uang_dan_barang/`) - yang beda
cuma cara nyajiinnya.
"""

from io import BytesIO

import frappe
from frappe import _
from frappe.utils import flt, formatdate
from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from vic_addon.vic.excel import BASE, BOLD, BOX, CENTER, LEFT, LINE, RIGHT, MARGIN_WIDTH
from vic_addon.vic.report.arus_uang_dan_barang.arus_uang_dan_barang import (
	flatten_purchases,
	flatten_sales,
	get_data,
)

# kolom B..E buat PENYERAHAN yang sebelah kiri, dst - angkanya lebar kolom Excel
COLUMN_WIDTHS = (
	5,    # B  No
	26,   # C  Nama Pembeli
	20,   # D  NPWP
	38,   # E  Rincian Barang
	20,   # F  Nomor Seri
	12,   # G  Tanggal
	15,   # H  DPP
	14,   # I  PPN
	26,   # J  Nama PKP Penjual
	20,   # K  NPWP
	20,   # L  Nomor Seri
	12,   # M  Tanggal
	38,   # N  Jenis Barang
	10,   # O  Quantity
	7,    # P  UOM
	14,   # Q  @ Hrg Satuan
	15,   # R  DPP PPN
	14,   # S  PPN
)

FIRST_COLUMN = 2
MONEY_FORMAT = "#,##0.00"


@frappe.whitelist()
def download(filters=None):
	"""Endpoint tombol Download Excel di report."""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	filters = frappe._dict(filters)

	frappe.has_permission("Sales Invoice", throw=True)

	company = filters.get("company") or frappe.defaults.get_user_default("Company")
	stream = build_workbook(filters, company)

	frappe.local.response.filename = "Arus Uang dan Barang.xlsx"
	frappe.local.response.filecontent = stream.getvalue()
	frappe.local.response.type = "binary"


def build_workbook(filters, company):
	workbook = Workbook()
	sheet = workbook.active
	sheet.title = "Arus Uang dan Barang"

	set_widths(sheet)
	row = add_heading(sheet, filters, company)
	row = add_column_titles(sheet, row)
	add_rows(sheet, row, filters)

	stream = BytesIO()
	workbook.save(stream)

	return stream


def set_widths(sheet):
	sheet.column_dimensions[get_column_letter(FIRST_COLUMN - 1)].width = MARGIN_WIDTH

	for index, width in enumerate(COLUMN_WIDTHS):
		sheet.column_dimensions[get_column_letter(FIRST_COLUMN + index)].width = width


def last_column():
	return FIRST_COLUMN + len(COLUMN_WIDTHS) - 1


def add_heading(sheet, filters, company):
	"""Judul kertas kerja + kotak identitas PKP di sebelah kanannya."""
	merge(sheet, 1, FIRST_COLUMN, 1, last_column())
	title = sheet.cell(row=1, column=FIRST_COLUMN, value="KERTAS KERJA PEMERIKSAAN")
	title.font, title.alignment = BOLD, CENTER

	merge(sheet, 3, FIRST_COLUMN, 5, FIRST_COLUMN + 7)
	subtitle = sheet.cell(row=3, column=FIRST_COLUMN, value="ARUS UANG DAN BARANG")
	subtitle.font, subtitle.alignment = BOLD, CENTER
	box(sheet, 3, FIRST_COLUMN, 5, FIRST_COLUMN + 7)

	doc = frappe.get_cached_doc("Company", company) if company else frappe._dict()
	periode = ""
	if filters.get("from_date") and filters.get("to_date"):
		periode = f"{formatdate(filters.from_date, 'd MMMM yyyy')} - {formatdate(filters.to_date, 'd MMMM yyyy')}"

	identitas = (
		("Nama PKP", doc.get("company_name") or ""),
		("NPWP", doc.get("tax_id") or ""),
		("Masa/Th Pajak", periode),
	)
	for index, (label, value) in enumerate(identitas):
		line = 3 + index
		text = sheet.cell(row=line, column=FIRST_COLUMN + 9, value=label)
		text.font, text.alignment = BASE, LINE
		content = sheet.cell(row=line, column=FIRST_COLUMN + 11, value=f": {value}")
		content.font, content.alignment = BASE, LINE
		merge(sheet, line, FIRST_COLUMN + 11, line, last_column())

	box(sheet, 3, FIRST_COLUMN + 9, 5, last_column())

	return 7


def add_column_titles(sheet, row):
	"""Judul kolom tiga tingkat, sama kayak kertas kerjanya."""
	left, right = FIRST_COLUMN, FIRST_COLUMN + 8

	merge(sheet, row, left, row, right - 1)
	title(sheet, row, left, "PENYERAHAN")
	merge(sheet, row, right, row, last_column())
	title(sheet, row, right, "PEMBELIAN")

	# tingkat 2: yang gak punya anak di-merge ke bawah sampai tingkat 3
	tegak = (
		(left + 0, "No"), (left + 1, "Nama Pembeli"), (left + 2, "NPWP"), (left + 3, "Rincian Barang"),
		(right + 0, "Nama PKP Penjual BKP/JKP"), (right + 1, "NPWP"),
		(right + 8, "DPP PPN"), (right + 9, "PPN"),
	)
	for column, text in tegak:
		merge(sheet, row + 1, column, row + 2, column)
		title(sheet, row + 1, column, text)

	# yang punya anak: judul induk di tingkat 2, anaknya di tingkat 3
	induk = (
		(left + 4, left + 7, "Faktur Pajak", ("Nomor Seri", "Tanggal", "DPP", "PPN")),
		(right + 2, right + 3, "Faktur Pajak/Nota Retur", ("Nomor Seri", "Tanggal")),
		(right + 4, right + 7, "Uraian Barang", ("Jenis Barang", "Quantity", "UOM", "@ Hrg Satuan")),
	)
	for mulai, selesai, teks, anak in induk:
		merge(sheet, row + 1, mulai, row + 1, selesai)
		title(sheet, row + 1, mulai, teks)
		for index, nama in enumerate(anak):
			title(sheet, row + 2, mulai + index, nama)

	sheet.row_dimensions[row].height = 16

	return row + 3


def add_rows(sheet, row, filters):
	for group in get_data(filters):
		merge(sheet, row, FIRST_COLUMN, row, last_column())
		judul = sheet.cell(row=row, column=FIRST_COLUMN, value=group.project_label)
		judul.font, judul.alignment = BOLD, LINE
		box(sheet, row, FIRST_COLUMN, row, last_column())
		row += 1

		sales = flatten_sales(group.sales)
		purchases = flatten_purchases(group.purchases)

		for index in range(max(len(sales), len(purchases))):
			kiri = sales[index] if index < len(sales) else {}
			kanan = purchases[index] if index < len(purchases) else {}
			write_row(sheet, row, kiri, kanan)
			row += 1

	return row


def write_row(sheet, row, kiri, kanan):
	nilai = (
		(kiri.get("no"), LEFT, None),
		(kiri.get("buyer"), LINE, None),
		(kiri.get("buyer_npwp"), LINE, None),
		(kiri.get("sales_item"), LINE, None),
		(kiri.get("sales_faktur_no"), LINE, None),
		(tanggal(kiri.get("sales_faktur_date")), CENTER, None),
		(kiri.get("sales_dpp"), RIGHT, MONEY_FORMAT),
		(kiri.get("sales_ppn"), RIGHT, MONEY_FORMAT),
		(kanan.get("seller"), LINE, None),
		(kanan.get("seller_npwp"), LINE, None),
		(kanan.get("purchase_faktur_no"), LINE, None),
		(tanggal(kanan.get("purchase_faktur_date")), CENTER, None),
		(kanan.get("purchase_item"), LINE, None),
		(kanan.get("qty"), RIGHT, "#,##0.##"),
		(kanan.get("uom"), CENTER, None),
		(kanan.get("rate"), RIGHT, MONEY_FORMAT),
		(kanan.get("purchase_dpp"), RIGHT, MONEY_FORMAT),
		(kanan.get("purchase_ppn"), RIGHT, MONEY_FORMAT),
	)

	for index, (value, alignment, number_format) in enumerate(nilai):
		cell = sheet.cell(row=row, column=FIRST_COLUMN + index, value=value)
		cell.font, cell.alignment, cell.border = BASE, alignment, BOX
		if number_format and value not in (None, ""):
			cell.number_format = number_format


def tanggal(value):
	return formatdate(value, "dd/MM/yyyy") if value else ""


def title(sheet, row, column, text):
	cell = sheet.cell(row=row, column=column, value=text)
	cell.font, cell.alignment, cell.border = BOLD, CENTER, BOX


def merge(sheet, row, column, end_row, end_column):
	if (end_row, end_column) != (row, column):
		sheet.merge_cells(start_row=row, start_column=column, end_row=end_row, end_column=end_column)


def box(sheet, row, column, end_row, end_column):
	for line in range(row, end_row + 1):
		for index in range(column, end_column + 1):
			sheet.cell(row=line, column=index).border = BOX
