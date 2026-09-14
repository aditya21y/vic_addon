"""Bagian yang dipakai bareng semua file Excel yang dikeluarin app ini.

Tata letaknya ngikutin `RFQ Excel Template.xlsx` punya VIC: kolom A dipakai sebagai margin kiri,
isi dokumen mulai kolom B, logo di kiri atas, nama + alamat perusahaan rata kanan, terus judul
dokumen gede di tengah. Fontnya Aptos Narrow, sama kayak template.
"""

import frappe
from openpyxl.drawing.image import Image as ExcelImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

FONT_NAME = "Aptos Narrow"

THIN = Side(style="thin", color="000000")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
UNDERLINE = Border(bottom=THIN)
OVERLINE = Border(top=THIN)

BASE = Font(name=FONT_NAME, size=11)
BOLD = Font(name=FONT_NAME, size=11, bold=True)
SMALL = Font(name=FONT_NAME, size=9)
COMPANY_FONT = Font(name=FONT_NAME, size=14, bold=True)
TITLE_FONT = Font(name=FONT_NAME, size=20)

LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
RIGHT = Alignment(horizontal="right", vertical="center")
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
WRAP = Alignment(horizontal="left", vertical="top", wrap_text=True)
# buat tulisan yang mesti utuh sebaris - tanpa wrap, biar gak keperes jadi kolom kurus
LINE = Alignment(horizontal="left", vertical="center")
RIGHT_WRAP = Alignment(horizontal="right", vertical="center", wrap_text=True)

HEAD_FILL = PatternFill("solid", fgColor="F2F2F2")
FILL_FILL = PatternFill("solid", fgColor="FFF2CC")

# kolom A (dan kolom paling kanan) cuma jadi margin, kayak di template
MARGIN_WIDTH = 1.1
FIRST_COLUMN = 2

# tinggi logo di lembar Excel (px)
LOGO_HEIGHT = 66


def add_letterhead(sheet, company, last_column):
	"""Logo di kiri atas + nama & alamat perusahaan rata kanan. Balikin baris buat judul."""
	doc = frappe.get_cached_doc("Company", company)

	logo = get_logo()
	if logo:
		sheet.add_image(logo, f"{get_column_letter(FIRST_COLUMN)}1")

	# Blok alamat ngambil separuh kanan lembar - tiap barisnya di-merge biar rata kanan rapi.
	# Dibikin lebar soalnya ada company yang alamatnya sebaris panjang banget; di sel merge,
	# tulisan yang kepanjangan itu kepotong, gak numpuk keluar kayak sel biasa.
	start = max(last_column - 9, FIRST_COLUMN + 3)
	lines = [doc.company_name.upper(), *get_company_lines(company, doc)]

	for index, line in enumerate(lines, start=1):
		sheet.merge_cells(start_row=index, start_column=start, end_row=index, end_column=last_column)
		cell = sheet.cell(row=index, column=start, value=line)
		cell.font = COMPANY_FONT if index == 1 else SMALL
		cell.alignment = RIGHT_WRAP

		# tinggi baris alamat sengaja gak dipatok: kalau alamatnya sampai mecah dua baris,
		# Excel yang ngatur sendiri tingginya
		if index == 1:
			sheet.row_dimensions[index].height = 18

	# template naruh judul di baris 7, tepat di bawah blok alamat
	return max(len(lines), 6) + 1


def add_title(sheet, row, title, last_column):
	"""Judul dokumen gede di tengah, selebar isi dokumen - persis kayak template."""
	sheet.merge_cells(start_row=row, start_column=FIRST_COLUMN, end_row=row + 1, end_column=last_column)

	cell = sheet.cell(row=row, column=FIRST_COLUMN, value=title)
	cell.font, cell.alignment = TITLE_FONT, CENTER
	sheet.row_dimensions[row].height = 16
	sheet.row_dimensions[row + 1].height = 16

	return row + 2


def add_meta(sheet, row, entries, label_column, width=1, merge_to=None):
	"""Baris keterangan `Label : Isi` - titik dua di kolom sendiri biar sejajar.

	`merge_to` = kolom terakhir buat kolom isinya. Tanpa ini isinya cuma dapat satu kolom dan
	tulisan yang agak panjang keperes jadi kolom kurus ke bawah.
	"""
	for label, value in entries:
		if not value:
			continue

		text = sheet.cell(row=row, column=label_column, value=label)
		text.font, text.alignment = BASE, LEFT

		colon = sheet.cell(row=row, column=label_column + width, value=":")
		colon.font, colon.alignment = BASE, LEFT

		value_column = label_column + width + 1
		if merge_to and merge_to > value_column:
			sheet.merge_cells(
				start_row=row, start_column=value_column, end_row=row, end_column=merge_to
			)

		content = sheet.cell(row=row, column=value_column, value=value)
		content.font, content.alignment = BASE, LINE

		row += 1

	return row


def set_widths(sheet, widths, first_column=FIRST_COLUMN):
	"""Lebar kolom isi dokumen, plus margin tipis di kiri dan kanannya."""
	sheet.column_dimensions[get_column_letter(first_column - 1)].width = MARGIN_WIDTH

	for index, width in enumerate(widths):
		sheet.column_dimensions[get_column_letter(first_column + index)].width = width

	sheet.column_dimensions[get_column_letter(first_column + len(widths))].width = MARGIN_WIDTH


def get_logo():
	"""Logo VIC sebagai gambar Excel, `None` kalau filenya gak ada."""
	from pathlib import Path

	path = Path(frappe.get_app_path("vic_addon", "public", "img", "vic logo.png"))
	if not path.exists():
		return None

	image = ExcelImage(path)
	ratio = image.width / image.height
	image.height = LOGO_HEIGHT
	image.width = int(LOGO_HEIGHT * ratio)

	return image


def get_company_lines(company, doc=None):
	"""Alamat perusahaan buat kop surat - sumbernya sama kayak print format."""
	doc = doc or frappe.get_cached_doc("Company", company)

	address_name = frappe.db.get_value(
		"Dynamic Link",
		{"link_doctype": "Company", "link_name": company, "parenttype": "Address"},
		"parent",
	)
	address = (
		frappe.db.get_value(
			"Address",
			address_name,
			["address_line1", "address_line2", "city", "state", "pincode", "phone", "fax"],
			as_dict=True,
		)
		if address_name
		else frappe._dict()
	)

	lines = [address.address_line1, address.address_line2]
	lines.append(", ".join(part for part in (address.city, address.state, address.pincode) if part))

	phone = doc.phone_no or address.phone
	if phone:
		lines.append(f"Phone : {phone}")

	fax = doc.fax or address.fax
	if fax:
		lines.append(f"Fax : {fax}")

	return [line for line in lines if line]
