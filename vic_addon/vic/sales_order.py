"""Custom Sales Order: bikin PO per supplier, kepisah antara Reguler dan Dropship.

Supplier tiap item ikut turun dari Costing -> Quotation -> Sales Order lewat field
`custom_supplier` & `custom_supplier_quotation`, jadi PO ke supplier bisa dibikin
otomatis tanpa milih supplier manual lagi.
"""

import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.utils import flt, get_link_to_form, getdate

from vic_addon.vic.dropship import DROPSHIP, MIXED, REGULER, set_transaction_type

TRANSACTION_TYPES = (REGULER, DROPSHIP, MIXED)


@frappe.whitelist()
def get_items_for_purchase_order(sales_order):
	"""Baris SO yang masih bisa di-PO, buat isi tabel di modal `Purchase Order (per Supplier)`.

	Supplier-nya diisi dari SQTN yang nempel di baris item, tapi di modal masih bisa diganti -
	kasus barang habis di supplier pertama (R&C ke-6 di sheet Costing). Baris yang gak punya
	supplier tetap dibalikin dengan kolom supplier kosong, biar user yang milih di modal.
	"""
	doc = frappe.get_doc("Sales Order", sales_order)
	doc.check_permission("read")

	pending_qty = get_pending_qty(doc)
	rows = []

	for item in doc.items:
		remaining = pending_qty.get(item.name)
		if not remaining:
			continue

		rows.append(
			{
				"sales_order_item": item.name,
				"item_code": item.item_code,
				"item_name": item.item_name,
				"uom": item.uom,
				"pending_qty": flt(
					remaining / (flt(item.conversion_factor) or 1), item.precision("qty")
				),
				"transaction_type": item.custom_transaction_type or REGULER,
				"supplier": item.custom_supplier,
				"supplier_quotation": item.custom_supplier_quotation,
				# disimpan terpisah biar modal tau SQTN mana yang aslinya dipilih di Sales Order,
				# walaupun kolom SQTN-nya udah diubah user
				"sales_order_quotation": item.custom_supplier_quotation,
			}
		)

	return rows


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def supplier_quotation_query(doctype, txt, searchfield, start, page_len, filters):
	"""Isi dropdown Supplier Quotation di modal: cuma penawaran yang ada item barisnya.

	Milih SQTN yang gak nawarin item itu bikin harga belinya gak ketarik dan PO-nya ditolak
	waktu disimpan, jadi disaring dari awal.
	"""
	quotation = frappe.qb.DocType("Supplier Quotation")
	item = frappe.qb.DocType("Supplier Quotation Item")

	query = (
		frappe.qb.from_(quotation)
		.join(item)
		.on(item.parent == quotation.name)
		.select(quotation.name, quotation.supplier)
		.distinct()
		.where((quotation.docstatus == 1) & (item.item_code == filters.get("item_code")))
		.orderby(quotation.transaction_date, order=Order.desc)
		.limit(page_len)
		.offset(start)
	)

	if txt:
		query = query.where(quotation.name.like(f"%{txt}%") | quotation.supplier.like(f"%{txt}%"))

	return query.run()


@frappe.whitelist()
def make_purchase_orders(sales_order, selected_items=None):
	"""Bikin draft PO dari Sales Order: item digrup **per supplier**.

	Tipe transaksi gak ikut misahin PO. Satu pesanan ke supplier yang sama boleh campur -
	sebagian dikirim ke gudang sendiri (Reguler), sebagian langsung ke lapangan (Dropship),
	atau baris yang qty-nya dipecah dua-duanya (Mixed). Tipe tiap barisnya tetap kebawa ke
	baris PO-nya, header PO cuma nyimpen ringkasannya.

	`selected_items` itu isian dari modal: baris mana aja yang mau di-PO plus supplier, qty, dan
	tipe transaksinya.
	Kalau gak dikasih (dipanggil dari script), suppliernya diambil dari SQTN di baris item.

	Yang bikin dokumennya tetap `make_purchase_order` bawaan ERPNext (biar dapet handling
	currency dan exchange rate), kita yang nentuin suppliernya, ngisi harga beli, link SQTN,
	tipe transaksi, dan sisa qty yang beneran belum di-PO.
	"""
	from erpnext.selling.doctype.sales_order.sales_order import make_purchase_order

	doc = frappe.get_doc("Sales Order", sales_order)
	doc.check_permission("read")

	pending_qty = get_pending_qty(doc)
	validate_pending_qty(doc, pending_qty)

	selection = get_selection_by_row(doc, pending_qty, selected_items)
	groups = get_rows_by_group(doc, selection)

	if not groups:
		frappe.throw(
			_("No item in this Sales Order has a Supplier. Fill Supplier Quotation info first."),
			title=_("Supplier Not Found"),
		)

	purchase_orders = []
	for supplier, rows in groups.items():
		selected = [
			{"item_code": item_code, "supplier": supplier}
			for item_code in {row.item_code for row in rows}
		]
		# `make_purchase_order` milih baris SO cuma dari item code, padahal item code yang sama
		# bisa muncul di beberapa baris dengan supplier beda - jadi barisnya disaring lagi ke
		# baris punya supplier ini
		rows_of_group = {row.name for row in rows}

		# `make_purchase_order` nge-insert dokumennya di dalam sana, jadi penyesuaian tanggalnya
		# nebeng hook `before_validate` lewat flag ini
		frappe.flags.purchase_order_from_sales_order = True
		try:
			created = make_purchase_order(sales_order, selected) or []
		finally:
			frappe.flags.purchase_order_from_sales_order = False

		for purchase_order in created:
			set_supplier_quotation_details(purchase_order, doc, selection)

			if not set_pending_qty(purchase_order, pending_qty, rows_of_group, selection):
				# semua barisnya udah ketutup PO lain, dokumennya gak usah ada
				purchase_order.delete()
				continue

			# dipasang setelah baris nyasar dibuang, biar ringkasan tipe di header gak ngitung
			# baris yang barusan kepotong
			set_transaction_type_details(purchase_order, doc, selection)
			purchase_order.save()
			purchase_orders.append(purchase_order.name)

	return purchase_orders


def get_ordered_qty(sales_order):
	"""Qty tiap baris SO yang udah masuk PO aktif (draft + submitted).

	ERPNext cuma ngitung PO submitted lewat `Sales Order Item.ordered_qty`, jadi klik tombol
	dua kali bakal bikin PO draft dobel. Di sini draft ikut dihitung, sedangkan PO yang udah
	dibatalin (docstatus 2) sengaja gak dihitung - itu yang bikin item dari PO batal bisa
	dibikinin PO baru lagi.
	"""
	rows = frappe.get_all(
		"Purchase Order Item",
		filters={"sales_order": sales_order, "docstatus": ["<", 2]},
		fields=["sales_order_item", "stock_qty"],
	)

	ordered_qty = {}
	for row in rows:
		if row.sales_order_item:
			ordered_qty[row.sales_order_item] = (
				ordered_qty.get(row.sales_order_item, 0) + flt(row.stock_qty)
			)

	return ordered_qty


def get_pending_qty(doc):
	"""Sisa qty (stock uom) tiap baris SO yang belum ada PO aktifnya."""
	ordered_qty = get_ordered_qty(doc.name)
	pending_qty = {}

	for item in doc.items:
		remaining = flt(item.stock_qty) - ordered_qty.get(item.name, 0)
		if remaining > 0:
			pending_qty[item.name] = remaining

	return pending_qty


def validate_pending_qty(doc, pending_qty):
	"""Tolak kalau semua item udah ada PO-nya, dan kasih tau baris mana yang dilewatin."""
	purchase_orders = get_purchase_orders_by_row(doc.name)

	if not pending_qty:
		frappe.throw(
			_(
				"Every item in this Sales Order already has an active Purchase Order ({0}). Cancel the Purchase Order first if it needs to be recreated."
			).format(", ".join(get_purchase_order_links(get_active_purchase_orders(doc.name)))),
			title=_("Purchase Order Already Exists"),
		)

	ordered_items = [
		item for item in doc.items if item.name not in pending_qty and item.custom_supplier
	]
	if not ordered_items:
		return

	# PO-nya ikut disebut biar user gak perlu nyari sendiri baris ini kepakai di PO mana
	skipped = [
		"#{0} {1} - {2}".format(
			item.idx,
			item.item_code,
			", ".join(get_purchase_order_links(purchase_orders.get(item.name, []))) or _("no Purchase Order"),
		)
		for item in ordered_items
	]

	frappe.msgprint(
		_("These items already have an active Purchase Order and are skipped:")
		+ "<br>"
		+ "<br>".join(skipped),
		title=_("Item Skipped"),
		indicator="orange",
	)


def get_purchase_orders_by_row(sales_order):
	"""PO aktif (draft + submitted) yang nyantol di tiap baris Sales Order."""
	rows = frappe.get_all(
		"Purchase Order Item",
		filters={"sales_order": sales_order, "docstatus": ["<", 2]},
		fields=["sales_order_item", "parent"],
	)

	purchase_orders = {}
	for row in rows:
		if row.sales_order_item:
			purchase_orders.setdefault(row.sales_order_item, set()).add(row.parent)

	return purchase_orders


def get_purchase_order_links(purchase_orders):
	"""Nomor PO yang bisa diklik, sekalian ditandain yang masih draft."""
	links = []

	for name in sorted(purchase_orders):
		link = get_link_to_form("Purchase Order", name)
		if frappe.db.get_value("Purchase Order", name, "docstatus") == 0:
			link += " ({0})".format(_("Draft"))
		links.append(link)

	return links


def get_selection_by_row(doc, pending_qty, selected_items=None):
	"""Pilihan user dari modal per baris SO: supplier, Supplier Quotation, qty, dan tipe transaksi.

	Kalau dipanggil tanpa modal (dari script), suppliernya diambil dari baris item Sales
	Order-nya, qty-nya ngikut sisa yang belum di-PO, dan tipenya ngikut baris SO.
	"""
	if isinstance(selected_items, str):
		selected_items = frappe.parse_json(selected_items)

	if not selected_items:
		return {
			item.name: frappe._dict(
				supplier=item.custom_supplier,
				supplier_quotation=item.custom_supplier_quotation,
				qty=None,
				transaction_type=None,
			)
			for item in doc.items
			if item.custom_supplier and item.name in pending_qty
		}

	selection = {}
	for row in selected_items:
		row = frappe._dict(row)
		if not (row.supplier and row.sales_order_item in pending_qty):
			continue

		selection[row.sales_order_item] = frappe._dict(
			supplier=row.supplier,
			supplier_quotation=row.supplier_quotation,
			qty=flt(row.qty) or None,
			transaction_type=row.transaction_type if row.transaction_type in TRANSACTION_TYPES else None,
		)

	return selection


def get_active_purchase_orders(sales_order):
	return sorted(
		{
			row.parent
			for row in frappe.get_all(
				"Purchase Order Item",
				filters={"sales_order": sales_order, "docstatus": ["<", 2]},
				fields=["parent"],
			)
		}
	)


def set_pending_qty(purchase_order, pending_qty, rows_of_group, selection=None):
	"""Qty PO: pakai isian user di modal, kalau gak diisi ikut sisa yang belum di-PO.

	Qty dari modal dipakai apa adanya - user emang lagi mutusin mau mesen berapa, sama kayak
	dia ngedit draft PO-nya langsung. Baris yang sisa qty-nya udah nol tetap dibuang.

	Balikin jumlah baris yang tersisa, biar PO kosong bisa dibatalin sama pemanggilnya.
	"""
	selection = selection or {}
	items = []

	for item in purchase_order.items:
		if not item.sales_order_item:
			# baris yang gak nempel ke baris SO (product bundle), biarin apa adanya
			items.append(item)
			continue

		if item.sales_order_item not in rows_of_group:
			continue

		remaining = pending_qty.get(item.sales_order_item, 0)
		if remaining <= 0:
			continue

		chosen_qty = selection.get(item.sales_order_item, frappe._dict()).get("qty")

		if chosen_qty:
			item.qty = flt(chosen_qty, item.precision("qty"))
		elif flt(item.stock_qty) > remaining:
			item.qty = flt(remaining / (flt(item.conversion_factor) or 1), item.precision("qty"))

		items.append(item)

	purchase_order.items = items

	return len(items)


def set_schedule_date(doc, method=None):
	"""Hook `before_validate` Purchase Order: Required By minimal sama dengan tanggal PO.

	Tanggalnya ngikut delivery date Sales Order, dan buat SO yang tanggal kirimnya udah lewat
	ERPNext bakal nolak PO-nya (`Required By cannot be before Date`). Jadi yang udah lewat
	dimajuin ke tanggal PO - user tinggal ganti manual di draft-nya kalau perlu.

	Cuma jalan buat PO yang lahir dari tombol Create > Purchase Order (per Supplier), jadi PO
	yang diisi manual tetap divalidasi apa adanya sama ERPNext.
	"""
	if not (doc.is_new() and frappe.flags.get("purchase_order_from_sales_order")):
		return

	purchase_order = doc
	transaction_date = getdate(purchase_order.transaction_date)

	for item in purchase_order.items:
		if not item.schedule_date or getdate(item.schedule_date) < transaction_date:
			item.schedule_date = transaction_date

	purchase_order.schedule_date = min(getdate(item.schedule_date) for item in purchase_order.items)


def get_rows_by_group(doc, selection):
	"""Baris Sales Order dikelompokin **per supplier** - satu supplier satu PO.

	Item yang sama boleh nongol di beberapa baris. Selama suppliernya sama, barisnya digabung ke
	PO yang sama, gak peduli tipe transaksinya beda-beda: satu pesanan ke satu supplier itu satu
	dokumen, biar gak ngerepotin supplier maupun bagian purchasing.
	"""
	groups = {}

	for item in doc.items:
		chosen = selection.get(item.name)
		if not (chosen and chosen.supplier):
			continue

		groups.setdefault(chosen.supplier, []).append(item)

	return groups


def set_transaction_type_details(purchase_order, sales_order, selection=None):
	"""Tipe tiap baris PO: pilihan user di modal, kosong -> ngikut baris Sales Order-nya. Header-nya
	cuma ringkasan.

	Baris Sales Order-nya sendiri gak diubah - SO-nya udah submit, dan alur dropship berikutnya
	(Delivery Note / Purchase Receipt dari PO) bacanya tipe baris PO.

	Satu PO boleh campur, jadi alamat kirim customer dipasang begitu **ada** baris yang
	dikirim langsung ke lapangan (Dropship atau Mixed) - barang yang masuk gudang sendiri tetap
	dialamatkan ke situ lewat gudang di barisnya.
	"""
	selection = selection or {}
	types = {item.name: (item.custom_transaction_type or REGULER) for item in sales_order.items}

	for item in purchase_order.items:
		chosen = selection.get(item.sales_order_item, frappe._dict()).get("transaction_type")
		item.custom_transaction_type = chosen or types.get(item.sales_order_item, REGULER)

	set_transaction_type(purchase_order)

	if not any(item.custom_transaction_type in (DROPSHIP, MIXED) for item in purchase_order.items):
		return

	# barangnya dikirim supplier langsung ke lapangan, jadi alamat kirim PO ikut customer
	# (ERPNext-nya sendiri nolak alamat non-Company di sini, lihat `dropship.stash_customer_shipping_address`)
	shipping_address = sales_order.shipping_address_name or sales_order.customer_address
	if shipping_address:
		purchase_order.shipping_address = shipping_address
		purchase_order.shipping_address_display = (
			sales_order.shipping_address or sales_order.address_display
		)

	purchase_order.customer = sales_order.customer
	purchase_order.customer_name = sales_order.customer_name
	purchase_order.customer_contact_person = sales_order.contact_person
	purchase_order.customer_contact_display = sales_order.contact_display




def set_supplier_quotation_details(purchase_order, sales_order, selection=None):
	"""Isi harga beli + link SQTN di PO. SQTN yang dipilih user di modal yang menang.

	Link SQTN-nya ditaruh di custom field, bukan di field bawaan `supplier_quotation`.
	Field bawaan bikin ERPNext maksa PO item sama persis dengan SQTN (project, uom,
	conversion factor), padahal project di PO ngikut Sales Order, bukan SQTN.

	Kalau user gak milih SQTN di modal, dipakai SQTN dari baris Sales Order-nya - itu pun cuma
	kalau suppliernya masih sama, karena penawaran supplier lain gak nyambung lagi harganya.
	"""
	selection = selection or {}
	sales_order_items = {item.name: item for item in sales_order.items}

	for item in purchase_order.items:
		quotation = selection.get(item.sales_order_item, frappe._dict()).get("supplier_quotation")

		if not quotation:
			sales_order_item = sales_order_items.get(item.sales_order_item)
			if not (sales_order_item and sales_order_item.custom_supplier_quotation):
				continue

			if (
				sales_order_item.custom_supplier
				and sales_order_item.custom_supplier != purchase_order.supplier
			):
				continue

			quotation = sales_order_item.custom_supplier_quotation
		quotation_item = frappe.db.get_value(
			"Supplier Quotation Item",
			{"parent": quotation, "item_code": item.item_code},
			["name", "net_rate"],
			as_dict=True,
		)
		if not quotation_item:
			continue

		item.custom_supplier_quotation = quotation
		item.custom_supplier_quotation_item = quotation_item.name

		# harga cuma diambil kalau mata uangnya sama, biar gak ketuker kurs
		if frappe.db.get_value("Supplier Quotation", quotation, "currency") == purchase_order.currency:
			item.rate = quotation_item.net_rate


# ---------------------------------------------------------------------------------------------
# Tambah item ke Sales Order yang udah submit - cuma nambah, baris lama gak boleh diubah/dihapus
# ---------------------------------------------------------------------------------------------

# kolom baris lama yang dikirim balik apa adanya - ERPNext cuma ngelewatin baris yang semuanya sama
UNCHANGED_FIELDS = ("item_code", "qty", "rate", "uom", "conversion_factor", "delivery_date", "description")


@frappe.whitelist()
def add_sales_order_items(sales_order, items):
	"""Tombol *Add Items* di Sales Order submitted: tambah baris baru, baris lama gak disentuh.

	Pakai `update_child_qty_rate` bawaan ERPNext (mesin tombol Update Items), jadi status, % delivered
	& billed, pajak, dan validasinya tetap ERPNext yang ngurus. Baris lama dikirim balik persis apa
	adanya - baris yang gak ikut dikirim bakal dihapus ERPNext, dan baris yang beda dikit dianggap
	diubah. Tipe transaksi baris baru diisi setelahnya (mesin ERPNext gak nyentuh custom field).

	Beda sama Update Items bawaan: tetap bisa walau SO-nya udah 100% terkirim / ditagih, kecuali
	Closed atau On Hold.
	"""
	from erpnext.controllers.accounts_controller import update_child_qty_rate

	doc = frappe.get_doc("Sales Order", sales_order)
	doc.check_permission("write")

	if doc.docstatus != 1:
		frappe.throw(_("Items can only be added to a submitted Sales Order."))
	if doc.status in ("Closed", "On Hold"):
		frappe.throw(
			_("Sales Order {0} is {1}. Reopen or resume it first.").format(doc.name, _(doc.status)),
			title=_("Cannot Add Items"),
		)

	new_items = [frappe._dict(row) for row in frappe.parse_json(items) if row.get("item_code") and flt(row.get("qty"))]
	if not new_items:
		frappe.throw(_("Add at least one item with a quantity."), title=_("Nothing to Add"))

	existing = [
		{"docname": row.name, **{field: str(row.get(field)) if field == "delivery_date" else row.get(field) for field in UNCHANGED_FIELDS}}
		for row in doc.items
	]
	added = [
		{
			"item_code": row.item_code,
			"qty": flt(row.qty),
			"rate": flt(row.rate),
			"uom": row.uom,
			"delivery_date": row.delivery_date or doc.delivery_date,
			"description": frappe.db.get_value("Item", row.item_code, "description") or row.item_code,
		}
		for row in new_items
	]
	previous_rows = {row.name for row in doc.items}

	update_child_qty_rate("Sales Order", frappe.as_json(existing + added), doc.name, "items")

	# tipe transaksi baris baru (Reguler / Dropship / Mixed), header-nya ringkasan
	doc.reload()
	types = iter(row.get("transaction_type") or MIXED for row in new_items)
	for row in doc.items:
		if row.name not in previous_rows:
			row.db_set("custom_transaction_type", next(types, MIXED), update_modified=False)
	set_transaction_type(doc)
	doc.db_set("custom_transaction_type", doc.custom_transaction_type, update_modified=False)

	return [row.name for row in doc.items if row.name not in previous_rows]


@frappe.whitelist()
def update_child_qty_rate(parent_doctype, trans_items, parent_doctype_name, child_docname="items"):
	"""Pengganti `erpnext...update_child_qty_rate` (mesin Update Items): Sales Order cuma boleh nambah.

	Dipasang lewat `override_whitelisted_methods`, jadi berlaku dari jalur mana pun (dialog bawaan,
	API). Request yang ngehapus atau ngubah baris lama Sales Order ditolak; doctype lain diterusin
	apa adanya.
	"""
	from erpnext.controllers.accounts_controller import update_child_qty_rate as erpnext_update

	if parent_doctype == "Sales Order":
		validate_add_only(parent_doctype_name, frappe.parse_json(trans_items))

	return erpnext_update(parent_doctype, trans_items, parent_doctype_name, child_docname)


def validate_add_only(sales_order, rows):
	"""Semua baris lama harus ikut, dengan isi yang sama persis - yang boleh cuma baris baru."""
	sent = {row.get("docname"): row for row in rows if row.get("docname")}
	problems = []

	for item in frappe.get_doc("Sales Order", sales_order).items:
		row = sent.get(item.name)
		if not row:
			problems.append(_("Row #{0} ({1}) cannot be deleted").format(item.idx, item.item_code))
			continue

		changed = (
			row.get("item_code") != item.item_code
			or flt(row.get("qty")) != flt(item.qty)
			or flt(row.get("rate")) != flt(item.rate)
			or (row.get("uom") or item.uom) != item.uom
			or flt(row.get("conversion_factor") or item.conversion_factor) != flt(item.conversion_factor)
			or (row.get("delivery_date") and getdate(row.get("delivery_date")) != getdate(item.delivery_date))
		)
		if changed:
			problems.append(_("Row #{0} ({1}) cannot be changed").format(item.idx, item.item_code))

	if problems:
		frappe.throw(
			_("A submitted Sales Order can only get new items. Existing items cannot be changed or deleted:")
			+ "<br>"
			+ "<br>".join(problems),
			title=_("Only Adding Items Is Allowed"),
		)
