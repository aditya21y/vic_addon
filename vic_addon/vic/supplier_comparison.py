"""Perbandingan penawaran supplier dari sebuah Request for Quotation.

Satu RFQ dikirim ke beberapa supplier, dan tiap supplier bisa ngasih penawaran berkali-kali di
waktu yang beda. Yang dipakai buat perbandingan cuma **dua penawaran terakhir** tiap supplier:

	Lama = penawaran kedua terakhir
	Baru = penawaran paling akhir

Supplier yang baru ngasih sekali cuma punya satu kolom. Perbandingannya dua lapis:

1. Di dalam satu supplier: Lama lawan Baru - kelihatan hasil negonya turun berapa persen
2. Antar supplier: penawaran **Baru** masing-masing dibanding yang paling murah

Hasilnya file Excel yang bentuknya ngikutin format yang selama ini dipakai purchasing.
"""

import frappe
from frappe import _
from frappe.utils import flt

# tarif PPN yang dipakai di baris pajak tabel perbandingan
TAX_RATE = 11

# jumlah penawaran terakhir yang dibandingin per supplier
OFFERS_PER_SUPPLIER = 2

# awalan nama file PDF perbandingan - dipakai buat nyari lampiran lama waktu bikin yang baru
PDF_PREFIX = "Supplier-Comparison-"


def get_comparison(request_for_quotation):
	"""Data mentah tabel perbandingan: baris item, kolom penawaran, dan totalnya."""
	doc = frappe.get_doc("Request for Quotation", request_for_quotation)
	doc.check_permission("read")

	offers = get_offers(doc.name, [row.supplier for row in doc.suppliers])
	if not offers:
		frappe.throw(
			_("No Supplier Quotation has been created from {0} yet.").format(doc.name),
			title=_("Nothing to Compare"),
		)

	items = get_items(doc)
	rates = get_rates(offers, items)

	for row in items:
		row["prices"] = [
			{
				# `quoted` dibaca dari ADA-nya baris di penawaran, bukan dari nilainya. Baris yang
				# dihapus manual di SQTN beda artinya sama baris yang harganya kebetulan nol.
				"quoted": (offer["name"], row["name"]) in rates,
				"rate": rates.get((offer["name"], row["name"])),
				"amount": flt(rates.get((offer["name"], row["name"])) or 0) * flt(row["qty"]),
			}
			for offer in offers
		]

	set_coverage(offers, items)
	set_totals(offers, items)

	# key-nya sengaja bukan `items`: di `frappe._dict` itu ketabrak method `dict.items()`
	return frappe._dict(request_for_quotation=doc, offers=offers, item_rows=items)


def get_offers(request_for_quotation, supplier_order=None):
	"""Dua penawaran terakhir tiap supplier, diurutin dari yang paling lama ke paling baru.

	Urutan suppliernya ngikut daftar di RFQ biar kolomnya gak tuker-tukeran tiap kali di-download.
	"""
	quotations = frappe.get_all(
		"Supplier Quotation",
		filters={
			"docstatus": ["<", 2],
			"name": ["in", get_quotation_names(request_for_quotation)],
		},
		fields=["name", "supplier", "supplier_name", "transaction_date", "currency", "creation"],
		order_by="transaction_date desc, creation desc",
	)

	by_supplier = {}
	for quotation in quotations:
		by_supplier.setdefault(quotation.supplier, []).append(quotation)

	order = {supplier: index for index, supplier in enumerate(supplier_order or [])}
	suppliers = sorted(by_supplier, key=lambda supplier: (order.get(supplier, len(order)), supplier))

	offers = []
	for supplier in suppliers:
		rows = by_supplier[supplier]
		# `rows` udah urut dari yang terbaru; ambil dua, balik lagi biar Lama duluan
		latest = list(reversed(rows[:OFFERS_PER_SUPPLIER]))

		for index, quotation in enumerate(latest):
			offers.append(
				{
					"name": quotation.name,
					"supplier": supplier,
					"supplier_name": quotation.supplier_name or supplier,
					"transaction_date": quotation.transaction_date,
					"currency": quotation.currency,
					"label": get_offer_label(index, len(latest)),
					"is_latest": index == len(latest) - 1,
				}
			)

	return offers


def get_offer_label(index, total):
	"""Judul kolom kecil di atas harga: cuma dipakai kalau suppliernya nawar lebih dari sekali."""
	if total < 2:
		return None

	return _("Lama") if index == 0 else _("Baru")


def get_quotation_names(request_for_quotation):
	"""Supplier Quotation yang lahir dari RFQ ini, dibaca dari baris itemnya."""
	names = frappe.get_all(
		"Supplier Quotation Item",
		filters={"request_for_quotation": request_for_quotation},
		pluck="parent",
		distinct=True,
	)

	return names or [""]


def get_items(request_for_quotation):
	"""Baris item yang dibandingin - diambil dari RFQ, biar qty-nya satu acuan buat semua supplier."""
	return [
		{
			"idx": item.idx,
			# nama baris RFQ - ini kunci harga yang dipakai, bukan item_code
			"name": item.name,
			"item_code": item.item_code,
			"item_name": item.item_name or item.item_code,
			"description": item.description or item.item_name or item.item_code,
			"qty": flt(item.qty),
			"uom": item.uom,
		}
		for item in request_for_quotation.items
	]


def get_rates(offers, items):
	"""Harga satuan per BARIS RFQ, bukan per item code.

	Satu RFQ sering punya beberapa baris dengan item code yang sama - misalnya satu item jasa
	dipakai berkali-kali dan yang ngebedain cuma deskripsinya. Kalau dikunci pakai item code,
	baris-baris itu nabrak satu sama lain dan yang kesisa cuma harga baris terakhir.

	Yang dipakai `request_for_quotation_item`: link balik dari baris penawaran ke baris RFQ-nya,
	diisi ERPNext waktu Supplier Quotation dibikin dari RFQ. Buat baris penawaran lama yang
	link-nya kosong, harganya dicocokin lewat item code - tapi cuma kalau item code itu munculnya
	sekali doang di RFQ, biar gak nebak-nebak baris mana yang dimaksud.
	"""
	rows = frappe.get_all(
		"Supplier Quotation Item",
		filters={"parent": ["in", [offer["name"] for offer in offers]]},
		fields=["parent", "item_code", "rate", "net_rate", "request_for_quotation_item"],
	)

	unique_items = get_unique_item_rows(items)
	rates = {}

	for row in rows:
		rate = flt(row.net_rate) or flt(row.rate)
		key = row.request_for_quotation_item or unique_items.get(row.item_code)

		if key:
			rates[(row.parent, key)] = rate

	return rates


def get_unique_item_rows(items):
	"""Item code -> nama baris RFQ, cuma buat item code yang munculnya sekali."""
	counts = {}
	for row in items:
		counts.setdefault(row["item_code"], []).append(row["name"])

	return {code: names[0] for code, names in counts.items() if len(names) == 1}


def set_coverage(offers, items):
	"""Berapa item yang beneran ditawar tiap penawaran.

	Supplier boleh cuma nawar sebagian - barangnya emang dipecah per jenis. Yang gak boleh itu
	penawaran sebagian dibandingin totalnya lawan penawaran lengkap, soalnya isinya beda.
	"""
	for index, offer in enumerate(offers):
		offer["quoted_items"] = sum(1 for row in items if row["prices"][index]["quoted"])
		offer["item_count"] = len(items)
		offer["is_complete"] = offer["quoted_items"] == len(items)


def set_totals(offers, items):
	"""Total, PPN, grand total per penawaran, plus selisihnya."""
	for index, offer in enumerate(offers):
		total = sum(flt(row["prices"][index]["amount"]) for row in items)

		offer["total"] = total
		offer["tax"] = flt(total) * TAX_RATE / 100
		offer["grand_total"] = offer["total"] + offer["tax"]

	set_differences(offers)


def set_differences(offers):
	"""Dua lapis selisih: hasil nego per supplier, dan posisi tiap supplier lawan yang termurah."""
	previous = {}
	for offer in offers:
		earlier = previous.get(offer["supplier"])

		# (Lama - Baru) / Baru: turun berapa persen dari penawaran sebelumnya
		offer["negotiated"] = (
			(earlier["grand_total"] - offer["grand_total"]) / offer["grand_total"]
			if earlier and offer["grand_total"]
			else None
		)
		previous[offer["supplier"]] = offer

	# Cuma penawaran LENGKAP yang diadu totalnya. Kalau yang sebagian ikut, dia menang gampang -
	# totalnya kecil bukan karena murah, tapi karena itemnya kurang.
	latest = [
		offer
		for offer in offers
		if offer["is_latest"] and offer["grand_total"] and offer.get("is_complete", True)
	]

	for offer in offers:
		offer["cheapest"] = False
		offer["vs_cheapest"] = None

	if not latest:
		return

	cheapest = min(latest, key=lambda offer: offer["grand_total"])

	for offer in latest:
		offer["cheapest"] = offer is cheapest
		offer["vs_cheapest"] = (
			(offer["grand_total"] - cheapest["grand_total"]) / cheapest["grand_total"]
			if cheapest["grand_total"]
			else None
		)


@frappe.whitelist()
def download_comparison(request_for_quotation):
	"""Tombol `Download Comparison` di Request for Quotation: kirim file Excel-nya ke browser."""
	comparison = get_comparison(request_for_quotation)

	frappe.response["filename"] = f"{request_for_quotation} - Supplier Comparison.xlsx"
	frappe.response["filecontent"] = build_workbook(comparison).getvalue()
	frappe.response["type"] = "binary"


def build_workbook(comparison):
	"""Susun file Excel-nya: satu blok kolom per penawaran, nama supplier ngepalain blok itu."""
	from io import BytesIO

	from openpyxl import Workbook
	from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
	from openpyxl.utils import get_column_letter

	offers = comparison.offers
	items = comparison.item_rows

	workbook = Workbook()
	sheet = workbook.active
	sheet.title = "Comparison"

	bold = Font(bold=True)
	center = Alignment(horizontal="center", vertical="center", wrap_text=True)
	thin = Side(style="thin", color="999999")
	box = Border(left=thin, right=thin, top=thin, bottom=thin)
	head_fill = PatternFill("solid", fgColor="F2F2F2")
	cheap_fill = PatternFill("solid", fgColor="FFF2CC")
	# abu-abu buat baris yang gak ditawar supplier itu
	blank_fill = PatternFill("solid", fgColor="EDEDED")
	money = "#,##0"
	percent = "0.00%"

	# ---- kepala tabel: baris 1 nama supplier, baris 2 Lama/Baru, baris 3 judul kolom ----
	fixed = [_("Item"), _("Description"), _("Qty"), _("UOM")]
	for column, title in enumerate(fixed, start=1):
		cell = sheet.cell(row=3, column=column, value=title)
		cell.font, cell.alignment, cell.border, cell.fill = bold, center, box, head_fill

	first_offer_column = len(fixed) + 1
	supplier_start = {}

	for index, offer in enumerate(offers):
		column = first_offer_column + index * 2

		if offer["label"]:
			label = sheet.cell(row=2, column=column, value=offer["label"])
			label.font, label.alignment, label.border, label.fill = bold, center, box, head_fill
			sheet.merge_cells(start_row=2, start_column=column, end_row=2, end_column=column + 1)

		# nama supplier ngepalain semua kolom miliknya, jadi awalnya diinget dulu
		supplier_start.setdefault(offer["supplier"], column)

		for offset, title in enumerate((_("Unit Price"), _("Total Price"))):
			cell = sheet.cell(row=3, column=column + offset, value=title)
			cell.font, cell.alignment, cell.border, cell.fill = bold, center, box, head_fill

	for supplier, start in supplier_start.items():
		columns = [
			first_offer_column + index * 2 for index, offer in enumerate(offers) if offer["supplier"] == supplier
		]
		end = max(columns) + 1
		name = next(offer["supplier_name"] for offer in offers if offer["supplier"] == supplier)

		cell = sheet.cell(row=1, column=start, value=name)
		cell.font, cell.alignment, cell.border, cell.fill = bold, center, box, head_fill

		# supplier yang cuma nawar sekali gak punya baris Lama/Baru, jadi namanya turun ke baris 2.
		# Merge-nya sekali doang - dua merge yang tumpang tindih bikin file Excel-nya rusak.
		labelled = any(offer["label"] for offer in offers if offer["supplier"] == supplier)
		sheet.merge_cells(
			start_row=1, start_column=start, end_row=1 if labelled else 2, end_column=end
		)

	# ---- baris item ----
	row_number = 4
	for item in items:
		sheet.cell(row=row_number, column=1, value=item["idx"]).border = box
		sheet.cell(row=row_number, column=2, value=item["description"]).border = box
		sheet.cell(row=row_number, column=3, value=item["qty"]).border = box
		sheet.cell(row=row_number, column=4, value=item["uom"]).border = box

		cheapest_rate = min(
			(flt(price["rate"]) for price, offer in zip(item["prices"], offers) if offer["is_latest"] and price["rate"]),
			default=None,
		)

		for index, price in enumerate(item["prices"]):
			column = first_offer_column + index * 2

			if not price["quoted"]:
				# ditandain jelas: sel kosong gampang kebaca sebagai harga nol
				for offset in (0, 1):
					cell = sheet.cell(row=row_number, column=column + offset, value="\u2014")
					cell.alignment, cell.border, cell.fill = center, box, blank_fill
				continue

			rate = sheet.cell(row=row_number, column=column, value=price["rate"])
			amount = sheet.cell(row=row_number, column=column + 1, value=price["amount"] or None)
			rate.number_format = amount.number_format = money
			rate.border = amount.border = box

			# harga termurah di antara penawaran terakhir ditandain, biar gampang dilihat
			if cheapest_rate and offers[index]["is_latest"] and flt(price["rate"]) == cheapest_rate:
				rate.fill = amount.fill = cheap_fill
				rate.font = bold

		row_number += 1

	# ---- total, PPN, grand total ----
	for title, key in ((_("Total"), "total"), (_("PPn {0}%").format(TAX_RATE), "tax"), (_("Grand Total"), "grand_total")):
		cell = sheet.cell(row=row_number, column=1, value=title)
		cell.font = bold
		sheet.merge_cells(start_row=row_number, start_column=1, end_row=row_number, end_column=4)

		for index, offer in enumerate(offers):
			column = first_offer_column + index * 2 + 1
			total = sheet.cell(row=row_number, column=column, value=offer[key])
			total.number_format, total.border = money, box
			if key == "grand_total":
				total.font = bold

		row_number += 1

	# ---- berapa item yang ditawar ----
	cell = sheet.cell(row=row_number, column=1, value=_("Item Ditawar"))
	cell.font = bold
	sheet.merge_cells(start_row=row_number, start_column=1, end_row=row_number, end_column=4)

	for index, offer in enumerate(offers):
		column = first_offer_column + index * 2 + 1
		value = sheet.cell(
			row=row_number, column=column, value=f"{offer['quoted_items']} / {offer['item_count']}"
		)
		value.alignment, value.border = center, box
		if not offer["is_complete"]:
			value.fill, value.font = blank_fill, bold

	row_number += 2

	# ---- dua lapis selisih ----
	for title, key, note in (
		(_("Lama vs Baru"), "negotiated", _("turun dari penawaran sebelumnya")),
		(_("vs Termurah"), "vs_cheapest", _("selisih ke penawaran terakhir termurah")),
	):
		cell = sheet.cell(row=row_number, column=1, value=f"{title} — {note}")
		cell.font = bold
		sheet.merge_cells(start_row=row_number, start_column=1, end_row=row_number, end_column=4)

		for index, offer in enumerate(offers):
			if offer.get(key) is None:
				continue

			column = first_offer_column + index * 2 + 1
			value = sheet.cell(row=row_number, column=column, value=offer[key])
			value.number_format, value.border = percent, box

			if key == "vs_cheapest" and offer.get("cheapest"):
				value.fill = cheap_fill
				value.font = bold

		row_number += 1

	# ---- catatan kaki ----
	if any(not offer["is_complete"] for offer in offers):
		row_number += 1
		note = sheet.cell(
			row=row_number,
			column=1,
			value=_(
				"Tanda \u2014 berarti supplier tidak menawar barang tersebut. Penawaran yang tidak "
				"lengkap tidak diikutkan dalam penentuan termurah, karena totalnya tidak sebanding."
			),
		)
		note.font = Font(italic=True)
		note.alignment = Alignment(wrap_text=True, vertical="top")
		sheet.merge_cells(
			start_row=row_number, start_column=1, end_row=row_number,
			end_column=first_offer_column + len(offers) * 2 - 1,
		)
		sheet.row_dimensions[row_number].height = 28

	# ---- lebar kolom secukupnya ----
	sheet.column_dimensions["A"].width = 6
	sheet.column_dimensions["B"].width = 42
	sheet.column_dimensions["C"].width = 9
	sheet.column_dimensions["D"].width = 7
	for index in range(len(offers) * 2):
		sheet.column_dimensions[get_column_letter(first_offer_column + index)].width = 16

	sheet.freeze_panes = sheet.cell(row=4, column=first_offer_column)

	stream = BytesIO()
	workbook.save(stream)

	return stream


@frappe.whitelist()
def share_comparison(request_for_quotation):
	"""Tombol `Share to WhatsApp`: bikin PDF perbandingan, simpen jadi file publik, balikin link.

	File-nya sengaja publik supaya penerimanya (misalnya direksi) bisa buka langsung dari HP
	tanpa punya akun. Nama filenya diberi kode acak biar URL-nya gak bisa ditebak, dan link-nya
	bisa dicabut kapan saja dengan menghapus lampirannya dari Request for Quotation.

	Tiap kali dipencet, PDF lama di RFQ ini dihapus - biar lampirannya gak numpuk dan cuma ada
	satu link yang hidup. Konsekuensinya link yang udah terlanjur dibagi jadi mati begitu yang
	baru dibikin.
	"""
	comparison = get_comparison(request_for_quotation)

	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": get_pdf_name(request_for_quotation),
			"attached_to_doctype": "Request for Quotation",
			"attached_to_name": request_for_quotation,
			"content": build_pdf(comparison),
			"is_private": 0,
		}
	).insert(ignore_permissions=True)

	# dihapusnya setelah yang baru jadi: kalau bikin PDF-nya gagal, link lama masih kepakai
	removed = remove_previous_pdf(request_for_quotation, keep=file.name)

	return {
		"removed": removed,
		"file_name": file.file_name,
		"url": get_share_url(file.file_name),
		"supplier": get_cheapest_supplier(comparison),
	}


def get_share_url(file_name):
	"""Link yang dibagiin ke luar.

	Sengaja gak pakai URL `/files/...` langsung: Frappe nyari folder site buat file statis dari
	**nama host** (lihat `StaticDataMiddleware`), padahal di server kita satu site diakses lewat
	domain yang beda dari nama foldernya - jadi link `/files/...` bakal 404. Lewat endpoint ini
	permintaannya masuk ke alur biasa, di mana nama site dibaca dari header yang dipasang nginx.
	"""
	key = get_share_key(file_name)

	return frappe.utils.get_url(
		f"/api/method/vic_addon.vic.supplier_comparison.view_comparison?key={key}"
	)


def get_share_key(file_name):
	"""Kode acak di ujung nama file - itu yang jadi kunci link."""
	return file_name.rsplit("-", 1)[-1].removesuffix(".pdf")


@frappe.whitelist(allow_guest=True)
def view_comparison(key):
	"""Buka PDF perbandingan dari link yang dibagiin - tanpa perlu login.

	Kuncinya kode acak 8 karakter di nama file. Yang dicari cuma lampiran PDF perbandingan di
	Request for Quotation, jadi endpoint ini gak bisa dipakai buat narik file lain.
	"""
	if not (key and key.isalnum()):
		raise frappe.DoesNotExistError

	name = frappe.db.get_value(
		"File",
		{
			"file_name": ["like", f"{PDF_PREFIX}%-{key}.pdf"],
			"attached_to_doctype": "Request for Quotation",
		},
		"name",
	)
	if not name:
		raise frappe.DoesNotExistError

	file = frappe.get_doc("File", name)

	frappe.response["filename"] = file.file_name
	frappe.response["filecontent"] = file.get_content()
	# `pdf` bikin browser nampilin isinya langsung, gak maksa download
	frappe.response["type"] = "pdf"


def remove_previous_pdf(request_for_quotation, keep):
	"""Hapus PDF perbandingan lama yang nempel di RFQ ini. Balikin jumlah yang kehapus."""
	names = frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "Request for Quotation",
			"attached_to_name": request_for_quotation,
			"file_name": ["like", f"{PDF_PREFIX}%"],
			"name": ["!=", keep],
		},
		pluck="name",
	)

	for name in names:
		frappe.delete_doc("File", name, ignore_permissions=True, delete_permanently=True)

	return len(names)


def get_pdf_name(request_for_quotation):
	"""Nama file: nomor RFQ + tanggal, ditutup kode acak biar URL-nya gak ketebak."""
	stamp = frappe.utils.now_datetime().strftime("%Y%m%d-%H%M")

	return f"{PDF_PREFIX}{request_for_quotation}-{stamp}-{frappe.generate_hash(length=8)}.pdf"


def get_cheapest_supplier(comparison):
	"""Nama supplier dengan penawaran terakhir termurah - dipakai di teks pesan WhatsApp."""
	for offer in comparison.offers:
		if offer.get("cheapest"):
			return offer["supplier_name"]

	return None


def build_pdf(comparison):
	"""Render tabel perbandingan jadi PDF."""
	from frappe.utils.pdf import get_pdf

	html = frappe.render_template("vic_addon/templates/supplier_comparison.html", get_context(comparison))

	return get_pdf(html, {"orientation": "Landscape"})


def get_context(comparison):
	"""Bahan buat template PDF: kop surat, kolom supplier, baris item, dan baris totalnya."""
	doc = comparison.request_for_quotation
	offers = comparison.offers

	# harga termurah per baris item ditandain, sama kayak di Excel-nya
	for row in comparison.item_rows:
		rates = [
			flt(price["rate"])
			for price, offer in zip(row["prices"], offers)
			if offer["is_latest"] and price["rate"]
		]
		cheapest = min(rates) if rates else None

		for price, offer in zip(row["prices"], offers):
			price["cheapest"] = bool(cheapest and offer["is_latest"] and flt(price["rate"]) == cheapest)

	suppliers = []
	for offer in offers:
		if suppliers and suppliers[-1]["name"] == offer["supplier_name"]:
			suppliers[-1]["span"] += 2
			continue

		suppliers.append({"name": offer["supplier_name"], "span": 2})

	company = frappe.get_cached_doc("Company", doc.company)

	return {
		"request_for_quotation": doc,
		"subject": doc.get("custom_subject"),
		"offers": offers,
		"item_rows": comparison.item_rows,
		"suppliers": suppliers,
		"company_name": company.company_name,
		"company_lines": get_company_lines(doc.company, company),
		"logo": get_logo(),
		"totals": [
			(_("Total"), "total"),
			(_("PPn {0}%").format(TAX_RATE), "tax"),
			(_("Grand Total"), "grand_total"),
		],
		"differences": [
			(_("Lama vs Baru"), "negotiated"),
			(_("Selisih ke penawaran termurah"), "vs_cheapest"),
		],
	}


def get_company_lines(company, doc):
	"""Alamat perusahaan buat kop surat PDF."""
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


def get_logo():
	"""Logo ditanam langsung ke HTML-nya, biar wkhtmltopdf gak perlu narik file lewat jaringan."""
	import base64
	from pathlib import Path

	path = Path(frappe.get_app_path("vic_addon", "public", "img", "vic logo.png"))
	if not path.exists():
		return None

	return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()
