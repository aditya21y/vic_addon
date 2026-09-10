"""Inquiry: permintaan penawaran ke supplier, versi Excel.

Print format `Inquiry` itu buat dicetak dan diisi tangan. Yang ini isinya sama persis, cuma
bentuknya file Excel - supplier tinggal ngisi kolom Unit Price / Weight / Remarks di
spreadsheet lalu dikirim balik, jadi purchasing gak perlu ngetik ulang.
"""

import frappe
from frappe import _
from frappe.utils import flt

# kolom yang sengaja dikosongin buat diisi supplier
FILL_COLUMNS = ("Unit Price", "Weight", "Remarks")


@frappe.whitelist()
def download_inquiry(request_for_quotation):
	"""Tombol `Download Inquiry` di Request for Quotation: kirim file Excel-nya ke browser."""
	doc = frappe.get_doc("Request for Quotation", request_for_quotation)
	doc.check_permission("read")

	frappe.response["filename"] = f"{doc.name} - Inquiry.xlsx"
	frappe.response["filecontent"] = build_workbook(doc).getvalue()
	frappe.response["type"] = "binary"


def build_workbook(doc):
	"""Susun Excel-nya ngikutin `RFQ Excel Template.xlsx`.

	Tata letaknya: margin kolom A, logo kiri atas, alamat perusahaan rata kanan, judul INQUIRY
	gede di tengah, keterangan nomor & tanggal di kanan, terus tabel yang cuma bergaris di bawah
	judul kolomnya. Tiga kolom terakhir dibiarin kosong buat diisi supplier.
	"""
	from io import BytesIO

	from openpyxl import Workbook

	from vic_addon.vic.excel import (
		BASE,
		CENTER,
		FIRST_COLUMN,
		LEFT,
		RIGHT,
		OVERLINE,
		UNDERLINE,
		WRAP,
		add_letterhead,
		add_meta,
		add_title,
		set_widths,
	)

	# kolom isi dokumen: B..N, sama kayak template
	item, description, qty, unit_price, weight, remarks = 2, 3, 8, 9, 11, 13
	last_column = 14

	workbook = Workbook()
	sheet = workbook.active
	sheet.title = "Inquiry"

	row = add_letterhead(sheet, doc.company, last_column)
	row = add_title(sheet, row, "INQUIRY", last_column)

	# nomor & tanggal ditaruh di kanan, sejajar kolom Qty ke kanan
	row = add_meta(
		sheet,
		row,
		(
			(_("Inquiry No."), doc.name),
			(_("Date"), frappe.utils.formatdate(doc.transaction_date, "d MMMM yyyy")),
		),
		label_column=7,
	)

	row += 4
	row = add_meta(sheet, row, ((_("Subject"), doc.get("custom_subject")),), label_column=FIRST_COLUMN)

	intro = sheet.cell(
		row=row,
		column=FIRST_COLUMN,
		value=_("Please quote us your best price & delivery time as follows :"),
	)
	intro.font, intro.alignment = BASE, LEFT
	row += 1

	# ---- judul kolom: dua baris tinggi, cuma bergaris di bawahnya ----
	headers = (
		(item, item, _("Item"), RIGHT),
		(description, description + 2, _("Description"), LEFT),
		(qty, qty, _("Qty"), CENTER),
		(unit_price, weight - 1, _("Unit Price"), CENTER),
		(weight, remarks - 1, _("Weight"), CENTER),
		(remarks, last_column, _("Remarks"), CENTER),
	)

	for start, end, title, alignment in headers:
		sheet.merge_cells(start_row=row, start_column=start, end_row=row + 1, end_column=end)
		cell = sheet.cell(row=row, column=start, value=title)
		cell.font, cell.alignment = BASE, alignment

	# blok judul kolom diapit dua garis melintang - gak ada garis tegak, sama kayak template
	for column in range(FIRST_COLUMN, last_column + 1):
		sheet.cell(row=row, column=column).border = OVERLINE
		sheet.cell(row=row + 1, column=column).border = UNDERLINE

	sheet.row_dimensions[row].height = 15
	sheet.row_dimensions[row + 1].height = 15
	row += 2

	# ---- baris item; tiga kolom terakhir sengaja dikosongin ----
	for index, item_row in enumerate(doc.items, start=1):
		size = frappe.db.get_value("Item", item_row.item_code, "custom_size")
		text = item_row.item_name or item_row.item_code
		if size:
			text = f"{text}\nSize : {size}"

		number = sheet.cell(row=row, column=item, value=index)
		number.font, number.alignment = BASE, RIGHT

		sheet.merge_cells(start_row=row, start_column=description, end_row=row, end_column=qty - 1)
		name = sheet.cell(row=row, column=description, value=text)
		name.font, name.alignment = BASE, WRAP

		amount = sheet.cell(
			row=row,
			column=qty,
			value=f"{flt(item_row.qty):g} {item_row.uom}",
		)
		amount.font, amount.alignment = BASE, CENTER

		for start, end in ((unit_price, weight - 1), (weight, remarks - 1), (remarks, last_column)):
			sheet.merge_cells(start_row=row, start_column=start, end_row=row, end_column=end)

		sheet.row_dimensions[row].height = 26 if size else 18
		row += 1

	# tabelnya ditutup garis melintang di bawah baris terakhir
	for column in range(FIRST_COLUMN, last_column + 1):
		sheet.cell(row=row - 1, column=column).border = UNDERLINE

	# ---- penutup ----
	row += 2
	closing = sheet.cell(row=row, column=FIRST_COLUMN, value=_("Wait for your reply immediately"))
	closing.font, closing.alignment = BASE, LEFT

	row += 2
	regards = sheet.cell(row=row, column=FIRST_COLUMN, value=_("Best regards,"))
	regards.font, regards.alignment = BASE, LEFT

	set_widths(sheet, (5, 9, 8.5, 8.5, 8.5, 9, 8.5, 9, 8.5, 8.5, 8.5, 9, 9))

	stream = BytesIO()
	workbook.save(stream)

	return stream
