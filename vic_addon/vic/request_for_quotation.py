"""Inquiry: permintaan penawaran ke supplier.

Print format `Inquiry` itu buat dicetak dan diisi tangan. Versi Excel-nya isinya sama persis -
supplier tinggal ngisi kolom Unit Price / Weight / Remarks di spreadsheet lalu dikirim balik,
jadi purchasing gak perlu ngetik ulang.

Di sini juga ada pengiriman ke supplier: user milih supplier, nyentang item mana aja yang mau
dimintain harga, terus kirim lewat email atau WhatsApp - atau diunduh sendiri. Barang sering
dipecah per jenis supplier, jadi jarang satu supplier dimintain semua item di dokumen.

Yang dikirim ikut lampir di dokumennya, biar kelihatan kapan dikirim ke siapa dan isinya apa.
File buat email disimpan privat; file buat WhatsApp mesti publik supaya bisa dibuka dari HP
tanpa akun, dan link-nya bisa dicabut dengan ngehapus lampirannya.
"""

import frappe
from frappe import _
from frappe.utils import flt

# kolom yang sengaja dikosongin buat diisi supplier
FILL_COLUMNS = ("Unit Price", "Weight", "Remarks")

# awalan nama file yang dikirim ke supplier - dipakai buat nyari lampiran lama
INQUIRY_PREFIX = "Inquiry-"

PRINT_FORMAT = "Inquiry"


def set_default_warehouse(doc, method=None):
	"""Hook `before_validate` Request for Quotation: warehouse kosong diisi gudang default.

	Gudangnya dari Stock Settings > Default Warehouse. Yang diisi cuma baris yang masih kosong -
	gudang yang udah dipilih user atau kebawa dari Material Request dibiarin.

	Sengaja `before_validate`, bukan `validate`: cek field wajib jalan di antara dua itu, jadi
	kalau warehouse-nya diwajibin, baris kosong udah keburu ditolak sebelum sempat diisi.
	"""
	warehouse = frappe.db.get_single_value("Stock Settings", "default_warehouse")
	if not warehouse:
		return

	for row in doc.get("items") or []:
		if not row.get("warehouse"):
			row.warehouse = warehouse


@frappe.whitelist()
def download_inquiry(request_for_quotation, items=None):
	"""Tombol unduh Excel: kirim file-nya ke browser, cuma item yang dipilih."""
	doc = get_inquiry_doc(request_for_quotation, items)

	frappe.response["filename"] = f"{doc.name} - Inquiry.xlsx"
	frappe.response["filecontent"] = build_workbook(doc).getvalue()
	frappe.response["type"] = "binary"


@frappe.whitelist()
def download_inquiry_pdf(request_for_quotation, items=None):
	"""Tombol unduh PDF: print format Inquiry, cuma item yang dipilih."""
	doc = get_inquiry_doc(request_for_quotation, items)

	frappe.response["filename"] = f"{doc.name} - Inquiry.pdf"
	frappe.response["filecontent"] = build_pdf(doc)
	frappe.response["type"] = "pdf"


def get_inquiry_doc(request_for_quotation, items=None):
	"""Dokumen RFQ dengan baris item disaring sesuai centangan user.

	Yang disaring salinan di memori doang - dokumen aslinya gak disentuh. Kalau gak ada yang
	dipilih, semua item kebawa.
	"""
	doc = frappe.get_doc("Request for Quotation", request_for_quotation)
	doc.check_permission("read")

	selected = frappe.parse_json(items) if isinstance(items, str) else items
	if not selected:
		return doc

	doc.items = [row for row in doc.items if row.name in set(selected)]
	if not doc.items:
		frappe.throw(_("No item selected."), title=_("Nothing to Send"))

	return doc


def build_pdf(doc):
	"""Print format Inquiry jadi PDF, pakai dokumen yang itemnya udah disaring."""
	return frappe.get_print(doc.doctype, doc.name, PRINT_FORMAT, doc=doc, as_pdf=True)


def get_supplier_row(doc, supplier):
	for row in doc.suppliers:
		if row.supplier == supplier:
			return row

	frappe.throw(
		_("Supplier {0} is not listed on {1}.").format(supplier, doc.name),
		title=_("Supplier Not Found"),
	)


def attach_inquiry(doc, supplier, file_format, is_private):
	"""Simpen file yang dikirim sebagai lampiran di dokumennya.

	Nama filenya dikasih kode acak di ujungnya - itu yang jadi kunci link WhatsApp, biar URL-nya
	gak bisa ditebak dari nomor dokumen.
	"""
	extension = "xlsx" if file_format == "Excel" else "pdf"
	content = build_workbook(doc).getvalue() if file_format == "Excel" else build_pdf(doc)

	return frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{INQUIRY_PREFIX}{doc.name}-{frappe.generate_hash(length=8)}.{extension}",
			"attached_to_doctype": doc.doctype,
			"attached_to_name": doc.name,
			"content": content,
			"is_private": 1 if is_private else 0,
		}
	).insert(ignore_permissions=True)


@frappe.whitelist()
def send_inquiry(request_for_quotation, supplier, items=None, subject=None, message=None, file_format="Excel"):
	"""Kirim inquiry ke satu supplier lewat email, lengkap sama lampirannya."""
	from frappe.core.doctype.communication.email import make

	doc = get_inquiry_doc(request_for_quotation, items)
	row = get_supplier_row(doc, supplier)

	if not row.email_id:
		frappe.throw(
			_("Supplier {0} has no email address on this document.").format(supplier),
			title=_("Email Address Missing"),
		)

	file = attach_inquiry(doc, supplier, file_format, is_private=True)

	make(
		subject=subject or _("Inquiry {0}").format(doc.name),
		content=message or "",
		recipients=row.email_id,
		attachments=[file.name],
		send_email=True,
		doctype=doc.doctype,
		name=doc.name,
	)

	return {"email": row.email_id, "file_name": file.file_name, "items": len(doc.items)}


@frappe.whitelist()
def share_inquiry(request_for_quotation, supplier, items=None, file_format="Excel"):
	"""Bikin file publik + link-nya, buat dibagi lewat WhatsApp."""
	doc = get_inquiry_doc(request_for_quotation, items)
	get_supplier_row(doc, supplier)

	file = attach_inquiry(doc, supplier, file_format, is_private=False)

	return {
		"file_name": file.file_name,
		"url": frappe.utils.get_url(
			f"/api/method/vic_addon.vic.request_for_quotation.view_inquiry?key={get_share_key(file.file_name)}"
		),
		"items": len(doc.items),
	}


def get_share_key(file_name):
	"""Kode acak di ujung nama file - itu yang jadi kunci link."""
	return file_name.rsplit("-", 1)[-1].rsplit(".", 1)[0]


@frappe.whitelist(allow_guest=True)
def view_inquiry(key):
	"""Buka file inquiry dari link yang dibagiin - tanpa perlu login.

	Sama kayak link perbandingan supplier: yang dicari cuma lampiran inquiry di Request for
	Quotation, jadi endpoint ini gak bisa dipakai buat narik file lain. Nama site dibaca dari
	header yang dipasang nginx, jadi jalurnya gak lewat `/files/...` yang bisa 404 di server
	multi-domain.
	"""
	if not (key and key.isalnum()):
		raise frappe.DoesNotExistError

	name = frappe.db.get_value(
		"File",
		{
			"file_name": ["like", f"{INQUIRY_PREFIX}%-{key}.%"],
			"attached_to_doctype": "Request for Quotation",
		},
		"name",
	)
	if not name:
		raise frappe.DoesNotExistError

	file = frappe.get_doc("File", name)

	frappe.response["filename"] = file.file_name
	frappe.response["filecontent"] = file.get_content()
	frappe.response["type"] = "pdf" if file.file_name.endswith(".pdf") else "binary"


def build_workbook(doc):
	"""Susun Excel-nya ngikutin `RFQ Excel Template.xlsx`.

	Tata letaknya: margin kolom A, logo kiri atas, alamat perusahaan rata kanan, judul INQUIRY
	gede di tengah, keterangan nomor & tanggal di kanan, terus tabel yang cuma bergaris di bawah
	judul kolomnya. Tiga kolom terakhir dibiarin kosong buat diisi supplier.
	"""
	from io import BytesIO

	from openpyxl import Workbook

	from vic_addon.vic.print_utils import get_inquiry_signatory
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
		merge_to=last_column,
	)

	row += 4
	row = add_meta(
		sheet,
		row,
		((_("Subject"), doc.get("custom_subject")),),
		label_column=FIRST_COLUMN,
		merge_to=last_column,
	)

	row = add_line(sheet, row, _("Please quote us your best price & delivery time as follows :"), last_column)

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
	row = add_line(sheet, row, _("Wait for your reply immediately"), last_column)

	row += 1
	row = add_line(sheet, row, _("Best regards,"), last_column)

	# ruang tanda tangan, terus namanya - sama kayak print format
	row += 3
	row = add_line(sheet, row, get_inquiry_signatory(doc), last_column)

	set_widths(sheet, (5, 9, 8.5, 8.5, 8.5, 9, 8.5, 9, 8.5, 8.5, 8.5, 9, 9))

	stream = BytesIO()
	workbook.save(stream)

	return stream


def add_line(sheet, row, text, last_column):
	"""Satu kalimat utuh selebar isi dokumen.

	Di-merge sampai kolom terakhir: kalau ditaruh di satu sel doang, lebar kolom B cuma muat
	beberapa huruf dan kalimatnya keperes jadi kolom kurus memanjang ke bawah.
	"""
	from vic_addon.vic.excel import BASE, FIRST_COLUMN, LINE

	sheet.merge_cells(start_row=row, start_column=FIRST_COLUMN, end_row=row, end_column=last_column)

	cell = sheet.cell(row=row, column=FIRST_COLUMN, value=text)
	cell.font, cell.alignment = BASE, LINE

	return row + 1
