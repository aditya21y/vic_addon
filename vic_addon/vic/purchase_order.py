"""Validasi Purchase Order terhadap Supplier Quotation-nya.

PO yang dibikin dari Sales Order bawa link SQTN di tiap baris (`custom_supplier_quotation` +
`custom_supplier_quotation_item`). Link itu yang jadi jaminan harga beli PO sama dengan harga
yang udah dinego di SQTN, makanya sebelum PO disimpan dicek dulu:

- SQTN-nya beneran ada, udah disubmit, dan suppliernya sama dengan supplier PO
- barisnya beneran baris SQTN itu dan item code-nya sama
Qty PO **gak** dibatesin qty yang ditawarin di SQTN: penawaran supplier sering ditulis buat 1
unit sebagai patokan harga, sedangkan pesanannya bisa lebih banyak.
"""

import frappe
from frappe import _


def sync_supplier_quotation(doc, method=None):
	"""Hook `before_validate` Purchase Order: samain link SQTN sama supplier PO-nya.

	Supplier di PO boleh diganti - barang habis di supplier pertama itu kasus normal (R&C ke-6
	di sheet Costing). Yang gak boleh, link SQTN-nya ketinggalan nunjuk ke penawaran supplier
	lama: harga belinya bakal ditarik balik dari penawaran itu tiap PO disimpan (lihat
	`rate_lock.py`), dan angkanya jadi harga supplier yang salah.

	Jadi tiap PO disimpan:

	- supplier PO beda dari supplier SQTN -> link SQTN dilepas, harga bebas diisi sesuai
	  penawaran supplier baru
	- baris dari Sales Order yang belum punya link (misal dibikin lewat modal bawaan) dan
	  suppliernya sama -> link SQTN-nya diambil dari baris Sales Order

	Jalan duluan sebelum `rate_lock`, biar harga yang kepasang udah ngikut link yang bener.
	"""
	drop_rows_of_other_suppliers(doc)

	released = []

	for item in doc.items:
		quotation = item.get("custom_supplier_quotation")

		if quotation:
			supplier = frappe.db.get_value("Supplier Quotation", quotation, "supplier")
			if supplier and supplier != doc.supplier:
				item.custom_supplier_quotation = None
				item.custom_supplier_quotation_item = None
				released.append((item.idx, item.item_code, quotation, supplier))
			continue

		set_supplier_quotation_from_sales_order(doc, item)

	# Pas PO dibikin dari tombol `Purchase Order (per Supplier)`, mapper bawaan sempat narik baris
	# punya supplier lain (dia milihnya dari item code) - baris itu dibuang lagi habis ini, jadi
	# gak usah diributin ke user.
	if released and not frappe.flags.get("purchase_order_from_sales_order"):
		frappe.msgprint(
			_("Supplier Quotation link removed on row {0} because it belongs to {1}. Fill the buying rate from {2}'s offer.").format(
				", ".join(f"#{row[0]}" for row in released),
				", ".join(sorted({row[3] for row in released})),
				doc.supplier,
			),
			title=_("Supplier Changed"),
			indicator="orange",
		)


def drop_rows_of_other_suppliers(doc):
	"""PO baru dari Sales Order: buang baris yang jatahnya supplier lain.

	`make_purchase_order` bawaan ERPNext milih baris Sales Order dari **item code**, bukan dari
	barisnya. Jadi kalau item yang sama muncul di dua baris SO dengan supplier beda - misalnya
	sebagian dibeli dari Common Supplier, sebagian dari Electrical Supplier - PO buat supplier
	yang satu ikut kebawa baris punya supplier satunya, lengkap sama link SQTN yang salah.

	Baris kayak gitu dibuang di sini, bukan cuma dilepas link SQTN-nya, biar PO-nya bener-bener
	cuma isi barang yang emang dipesan ke supplier ini. Kalau ternyata semua barisnya punya
	supplier lain, gak ada yang dibuang - biar dokumennya gak jadi kosong dan user bisa lihat
	sendiri apa yang kejadian.

	Gak jalan buat PO yang lahir dari tombol `Purchase Order (per Supplier)`: di sana barisnya
	udah disaring per baris (bukan per item code), dan suppliernya boleh sengaja diganti di modal
	- kalau dibuang di sini malah baris yang bener yang ilang.
	"""
	if not doc.is_new() or frappe.flags.get("purchase_order_from_sales_order"):
		return

	keep, dropped = [], []

	for item in doc.items:
		supplier = (
			frappe.db.get_value("Sales Order Item", item.sales_order_item, "custom_supplier")
			if item.get("sales_order_item")
			else None
		)

		if supplier and supplier != doc.supplier:
			dropped.append((item, supplier))
		else:
			keep.append(item)

	if not (dropped and keep):
		return

	doc.items = keep
	for idx, item in enumerate(doc.items, start=1):
		item.idx = idx

	frappe.msgprint(
		_("{0} removed: in {1} those rows are ordered from {2}, not {3}.").format(
			", ".join(sorted({item.item_code for item, _supplier in dropped})),
			", ".join(sorted({item.sales_order for item, _supplier in dropped if item.sales_order})),
			", ".join(sorted({supplier for _item, supplier in dropped})),
			doc.supplier,
		),
		title=_("Rows of Another Supplier Removed"),
		indicator="orange",
	)


def set_supplier_quotation_from_sales_order(doc, item):
	"""Ambil link SQTN dari baris Sales Order-nya, kalau suppliernya emang sama."""
	if not item.get("sales_order_item"):
		return

	sales_order_item = frappe.db.get_value(
		"Sales Order Item",
		item.sales_order_item,
		["custom_supplier", "custom_supplier_quotation"],
		as_dict=True,
	)
	if not (sales_order_item and sales_order_item.custom_supplier_quotation):
		return

	if sales_order_item.custom_supplier != doc.supplier:
		return

	item.custom_supplier_quotation = sales_order_item.custom_supplier_quotation
	item.custom_supplier_quotation_item = frappe.db.get_value(
		"Supplier Quotation Item",
		{"parent": sales_order_item.custom_supplier_quotation, "item_code": item.item_code},
		"name",
	)


def validate_supplier_quotation(doc, method=None):
	"""Link SQTN-nya dicek masih nyambung, tapi qty PO gak dibatesin qty yang ditawarin.

	Dulu qty PO dibandingin sama qty di SQTN dan ditolak kalau lewat. Aturan itu dicabut:
	penawaran supplier sering ditulis buat 1 unit sebagai patokan harga, sedangkan pesanannya
	bisa lebih banyak - dan urusan sanggup atau enggaknya supplier itu dibereskan di lapangan,
	bukan diblokir sistem.
	"""
	for item in doc.items:
		if not item.custom_supplier_quotation:
			warn_if_quotation_missing(doc, item)
			continue

		validate_quotation(doc, item)
		get_quotation_item(item)


def validate_quotation(doc, item):
	quotation = frappe.db.get_value(
		"Supplier Quotation", item.custom_supplier_quotation, ["supplier", "docstatus"], as_dict=True
	)

	if not quotation:
		frappe.throw(
			_("Row #{0}: Supplier Quotation {1} does not exist.").format(
				item.idx, item.custom_supplier_quotation
			),
			title=_("Supplier Quotation Not Found"),
		)

	if quotation.docstatus != 1:
		frappe.throw(
			_("Row #{0}: Supplier Quotation {1} is not submitted.").format(
				item.idx, item.custom_supplier_quotation
			),
			title=_("Supplier Quotation Not Submitted"),
		)

	if quotation.supplier != doc.supplier:
		frappe.throw(
			_(
				"Row #{0}: Supplier Quotation {1} belongs to supplier {2}, but this Purchase Order is for {3}."
			).format(item.idx, item.custom_supplier_quotation, quotation.supplier, doc.supplier),
			title=_("Supplier Mismatch"),
		)


def get_quotation_item(item):
	"""Baris SQTN yang jadi acuan baris PO ini."""
	filters = {"parent": item.custom_supplier_quotation, "item_code": item.item_code}
	if item.custom_supplier_quotation_item:
		filters["name"] = item.custom_supplier_quotation_item

	quotation_item = frappe.db.get_value("Supplier Quotation Item", filters, "name", as_dict=True)

	if not quotation_item:
		frappe.throw(
			_("Row #{0}: Item {1} is not in Supplier Quotation {2}.").format(
				item.idx, item.item_code, item.custom_supplier_quotation
			),
			title=_("Item Not Quoted"),
		)

	item.custom_supplier_quotation_item = quotation_item.name

	return quotation_item


def warn_if_quotation_missing(doc, item):
	"""Baris Sales Order-nya punya SQTN tapi barisnya di PO kosong - kasih tau, gak diblokir.

	Gak diomelin kalau suppliernya emang beda dari yang di Sales Order: itu tandanya user sengaja
	pindah supplier, dan link SQTN-nya udah dilepas di `sync_supplier_quotation`.
	"""
	if not item.sales_order_item:
		return

	sales_order_item = frappe.db.get_value(
		"Sales Order Item",
		item.sales_order_item,
		["custom_supplier", "custom_supplier_quotation"],
		as_dict=True,
	)
	if not (sales_order_item and sales_order_item.custom_supplier_quotation):
		return

	if sales_order_item.custom_supplier and sales_order_item.custom_supplier != doc.supplier:
		return

	quotation = sales_order_item.custom_supplier_quotation

	frappe.msgprint(
		_("Row #{0}: Item {1} is quoted in Supplier Quotation {2}, but this row is not linked to it.").format(
			item.idx, item.item_code, quotation
		),
		title=_("Supplier Quotation Not Linked"),
		indicator="orange",
	)


def get_dashboard_data(data=None):
	"""Hook `override_doctype_dashboards`: Delivery Note dropship nongol di Connections PO.

	Link-nya dari `purchase_order` di baris Delivery Note (diisi
	`dropship.set_purchase_order_on_items`), jadi dari PO dropship langsung kelihatan barangnya
	udah dikirim lewat DN mana.
	"""
	data = frappe._dict(data or {})
	data.setdefault("transactions", []).append({"label": _("Dropship"), "items": ["Delivery Note"]})

	return data
