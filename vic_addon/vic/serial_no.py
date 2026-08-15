"""Serial Number: penomoran sendiri, plus alirannya di skema dropship.

Dua kebutuhan yang dilayanin di sini:

1. **Barang masuk gudang (reguler).** User gak mau ngetik Serial No satu-satu. Begitu Purchase
   Receipt disimpan, Serial No dibikin sebanyak qty-nya pakai seri nomor dari master
   `Serial Number Settings`. Field `Serial No Series` di Item sengaja dikosongin, karena
   penomoran bawaan ERPNext gak bisa nyelipin nomor dan tanggal PO ke dalam serial number.

2. **Dropship.** Barang dikirim supplier langsung ke customer, lengkap dengan serial
   number-nya. Purchase Receipt-nya gak pernah dibikin manual - dokumennya kebuat otomatis
   tepat sebelum Delivery Note disubmit (lihat `dropship.py`). Jadi Serial No yang diketik
   user di Delivery Note dioper dulu ke Purchase Receipt itu, supaya barangnya "masuk" dengan
   nomor yang bener sebelum dikirim keluar. Kalau user gak ngisi, Purchase Receipt yang
   generate nomornya, terus nomornya ditarik balik ke Delivery Note.

Serial No-nya diisi ke field `serial_no` (bukan bikin Serial and Batch Bundle sendiri), jadi
ERPNext yang tetap ngurus pembuatan Serial No dan bundle-nya waktu dokumen disubmit.
"""

import re

import frappe
from frappe import _
from frappe.model.naming import getseries
from frappe.utils import cint, date_diff, getdate

SETTINGS = "Serial Number Settings"

# bagian nomor urut di seri nomor, contoh `############`
RUNNING_NUMBER = re.compile(r"#+")
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def set_serial_nos(doc, method=None):
	"""Hook `validate` Purchase Receipt: isi Serial No buat item yang belum ada nomornya."""
	settings = frappe.get_cached_doc(SETTINGS)
	if not settings.auto_create_serial_no or doc.get("is_return"):
		return

	for item in doc.items:
		if item.serial_no or item.serial_and_batch_bundle:
			continue

		if not frappe.get_cached_value("Item", item.item_code, "has_serial_no"):
			continue

		quantity = cint(item.stock_qty or item.qty)
		if quantity <= 0:
			continue

		item.serial_no = "\n".join(
			make_serial_nos(settings.serial_no_naming_series, doc, item, quantity)
		)
		item.use_serial_batch_fields = 1


def make_serial_nos(series, receipt, item, quantity):
	"""Bikin nomor sebanyak `quantity` dari seri nomor di master setting."""
	prefix, digits, suffix = split_series(series, get_context(receipt, item))

	return [f"{prefix}{getseries(prefix, digits)}{suffix}" for _ in range(quantity)]


def split_series(series, context):
	"""Pecah seri nomor jadi prefix (udah keisi variabel), jumlah digit, dan sisanya.

	Prefix-nya sekalian jadi kunci counter di tabel `Series`, jadi nomor urutnya jalan sendiri
	per item + per PO - persis kayak naming series bawaan frappe.
	"""
	running_number = RUNNING_NUMBER.search(series)
	if not running_number:
		frappe.throw(
			_("Serial No Naming Series in {0} has no running number ({1}).").format(
				frappe.bold(_(SETTINGS)), frappe.bold("#")
			),
			title=_("Invalid Naming Series"),
		)

	prefix = PLACEHOLDER.sub(lambda match: str(context.get(match.group(1), "")), series[: running_number.start()])

	return prefix, len(running_number.group()), series[running_number.end() :]


def get_context(receipt, item):
	"""Nilai tiap variabel di seri nomor, diambil dari PO-nya kalau ada."""
	purchase_order = item.get("purchase_order")
	date = None

	if purchase_order:
		date = frappe.db.get_value("Purchase Order", purchase_order, "transaction_date")

	# Purchase Receipt tanpa PO (pembelian langsung): pakai dokumen penerimaannya sendiri
	reference = purchase_order or receipt.name
	date = getdate(date or receipt.posting_date)

	return {
		"item_code": item.item_code,
		"po_no": reference,
		"po_date": date.strftime("%Y-%m-%d"),
		"po_month": date.strftime("%m"),
		"po_year": date.strftime("%y"),
		"supplier": receipt.get("supplier") or "",
	}


def get_unknown_placeholders(series):
	"""Variabel di seri nomor yang gak dikenal - dipakai buat validasi master setting."""
	known = {"item_code", "po_no", "po_date", "po_month", "po_year", "supplier"}

	return {name for name in PLACEHOLDER.findall(series or "") if name not in known}


def get_serial_nos_by_sales_order_item(delivery_note):
	"""Serial No yang diketik user di Delivery Note, dikunci ke baris Sales Order-nya."""
	serial_nos = {}

	for item in delivery_note.items:
		if not (item.serial_no and item.so_detail):
			continue

		numbers = split_serial_nos(item.serial_no)
		quantity = cint(item.stock_qty or item.qty)

		if len(numbers) != quantity:
			frappe.throw(
				_("Row #{0}: {1} Serial No entered for {2} qty of item {3}.").format(
					item.idx, len(numbers), quantity, item.item_code
				),
				title=_("Serial No Count Mismatch"),
			)

		serial_nos[item.so_detail] = numbers

	return serial_nos


def set_serial_nos_on_receipt(receipt, serial_nos_by_sales_order_item):
	"""Oper Serial No dari Delivery Note ke Purchase Receipt dropship yang lagi dibikin."""
	for item in receipt.items:
		numbers = serial_nos_by_sales_order_item.get(item.sales_order_item)
		if not numbers:
			continue

		item.serial_no = "\n".join(numbers[: cint(item.stock_qty or item.qty)])
		item.use_serial_batch_fields = 1


def set_serial_nos_on_delivery_note(delivery_note, receipt):
	"""Tarik Serial No hasil generate Purchase Receipt balik ke Delivery Note.

	Cuma buat baris yang Serial No-nya masih kosong - kalau user udah ngetik sendiri, itu yang
	dipakai (dan nomornya emang yang barusan dioper ke Purchase Receipt).
	"""
	serial_nos = {
		item.sales_order_item: item.serial_no
		for item in receipt.items
		if item.serial_no and item.sales_order_item
	}

	for item in delivery_note.items:
		if item.serial_no or not serial_nos.get(item.so_detail):
			continue

		item.serial_no = serial_nos[item.so_detail]
		item.use_serial_batch_fields = 1


def split_serial_nos(serial_no):
	return [number.strip() for number in re.split(r"[\n,]", serial_no or "") if number.strip()]


def set_warranty_dates(doc, method=None):
	"""Hook `validate` Delivery Note: rapihin tanggal garansi di baris item.

	Sesuai bispro, garansi mulai jalan pas barang dikirim ke customer - jadi kalau user cuma
	ngisi tanggal berakhirnya, tanggal mulainya ngikut posting date Delivery Note.
	"""
	for item in doc.items:
		start = item.get("custom_warranty_start_date")
		end = item.get("custom_warranty_end_date")

		if not (start or end):
			continue

		if not start:
			start = item.custom_warranty_start_date = doc.posting_date

		if end and getdate(end) < getdate(start):
			frappe.throw(
				_("Row #{0}: Warranty End Date {1} is before Warranty Start Date {2}.").format(
					item.idx,
					frappe.format(end, {"fieldtype": "Date"}),
					frappe.format(start, {"fieldtype": "Date"}),
				),
				title=_("Invalid Warranty Period"),
			)


def update_serial_no_warranty(doc, method=None):
	"""Hook `on_submit` Delivery Note: turunin tanggal garansi ke tiap Serial No.

	`warranty_period` (hari) ikut diisi biar hitungan bawaan ERPNext tetap nyambung sama dua
	tanggal ini.
	"""
	updated = 0

	for item in doc.items:
		start = item.get("custom_warranty_start_date")
		end = item.get("custom_warranty_end_date")

		if not (start or end):
			continue

		values = {"custom_warranty_start_date": start, "warranty_expiry_date": end}
		if start and end:
			values["warranty_period"] = date_diff(end, start)

		for serial_no in get_serial_nos(item):
			frappe.db.set_value("Serial No", serial_no, values)
			updated += 1

	if updated:
		frappe.msgprint(
			_("Warranty dates updated on {0} Serial No.").format(updated),
			title=_("Serial No Warranty"),
			indicator="green",
			alert=True,
		)


def get_row_serial_nos(item):
	"""Versi buat print format (didaftarin sebagai jinja method di hooks)."""
	return get_serial_nos(item)


def get_qr_code(text, scale=4):
	"""QR code sebagai data URI, dipakai di print format label Serial No.

	Digambar sendiri pakai `pyqrcode` (udah kebawa frappe buat 2FA), jadi labelnya tetap bisa
	dicetak tanpa internet dan gak nitip ke layanan QR luar.
	"""
	import pyqrcode

	if not text:
		return ""

	code = pyqrcode.create(str(text), error="M")

	return "data:image/png;base64," + code.png_as_base64_str(scale=cint(scale) or 4, quiet_zone=1)


def get_label_rows(doc):
	"""Satu baris per Serial No di dokumen - dipakai print format label."""
	rows = []

	for item in doc.items:
		for serial_no in get_serial_nos(item):
			rows.append(
				frappe._dict(
					{
						"serial_no": serial_no,
						"item_code": item.item_code,
						"item_name": item.item_name,
					}
				)
			)

	return rows


def get_serial_nos(item):
	"""Serial No di satu baris dokumen, dari field `serial_no` atau dari bundle-nya."""
	if item.get("serial_no"):
		return split_serial_nos(item.serial_no)

	if item.get("serial_and_batch_bundle"):
		return frappe.get_all(
			"Serial and Batch Entry",
			filters={"parent": item.serial_and_batch_bundle},
			pluck="serial_no",
		)

	return []
