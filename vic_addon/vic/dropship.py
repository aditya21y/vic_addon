"""Skema dropship: barang dikirim supplier langsung ke lapangan, dokumennya tetap lengkap.

ERPNext punya dropship bawaan (`delivered_by_supplier`), tapi itu justru ngecualiin item
dropship dari Purchase Receipt dan Delivery Note, dan nganggep SO udah terkirim begitu PO
disubmit. Di sini dua dokumen itu tetap harus ada, jadi dropship diperlakukan sebagai
atribut pengiriman doang - rantai dokumennya tetap standar:

	PO (alamat kirim ke customer/proyek)
	  -> Delivery Note
	       -> tepat sebelum DN disubmit, Purchase Receipt dibuat & disubmit otomatis

Barangnya lewat gudang transit dropship: masuk lewat Purchase Receipt, keluar lewat Delivery
Note di tanggal yang sama, jadi saldonya nol tapi stock ledger dan valuasinya tetap kecatat.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from vic_addon.vic.serial_no import (
	get_serial_nos_by_sales_order_item,
	set_serial_nos_on_delivery_note,
	set_serial_nos_on_receipt,
)

DROPSHIP = "Dropship"
REGULER = "Reguler"
MIXED = "Mixed"

# dokumen dropship pakai seri nomor sendiri biar gak ganggu penomoran transaksi reguler
DROPSHIP_NAMING_SERIES = {
	"Delivery Note": "MAT-DN-DS-.YYMM.-",
	"Purchase Receipt": "MAT-PRE-DS-.YYMM.-",
}


def set_transaction_type(doc, method=None):
	"""Ringkasan tipe di header, diambil dari tipe baris itemnya."""
	types = {(item.get("custom_transaction_type") or REGULER) for item in doc.get("items") or []}

	if not types:
		return

	doc.custom_transaction_type = types.pop() if len(types) == 1 else MIXED


def clear_delivered_by_supplier(doc, method=None):
	"""Hook `validate` Sales Order: matiin skema dropship bawaan ERPNext.

	Checkbox `Delivered By Supplier` itu dropship bawaan - itemnya dikecualiin dari Delivery
	Note (`make_delivery_note` ngelewatin baris yang flag-nya nyala) dan SO dianggap terkirim
	begitu PO diterima, makanya tombol Create > Delivery Note ikut ilang kalau semua barisnya
	kecentang. Di skema kita dokumennya justru harus lengkap, jadi flag-nya dimatiin dan tipe
	pengiriman diambil dari field Transaction Type.
	"""
	rows = [item for item in doc.get("items") or [] if item.get("delivered_by_supplier")]
	if not rows:
		return

	for item in rows:
		item.delivered_by_supplier = 0

	frappe.msgprint(
		_(
			"Delivered By Supplier turned off on row {0}. Use Transaction Type {1} instead - that way the Delivery Note and Purchase Receipt still get created."
		).format(", ".join(str(item.idx) for item in rows), frappe.bold(_(DROPSHIP))),
		title=_("Dropship Uses Transaction Type"),
		indicator="orange",
	)


def set_dropship_naming_series(doc, method=None):
	"""Hook `before_naming`: dokumen dropship pakai naming series sendiri."""
	series = DROPSHIP_NAMING_SERIES.get(doc.doctype)
	if not series or doc.name or not doc.meta.get_field("naming_series"):
		return

	# tipe header belum dihitung waktu penamaan, jadi dihitung duluan di sini
	set_transaction_type(doc)

	if doc.custom_transaction_type == DROPSHIP:
		doc.naming_series = series


def stash_customer_shipping_address(doc, method=None):
	"""Hook `before_validate` dokumen pembelian: alamat customer disingkirin dulu dari validasi.

	Dropship-nya ngirim ke lapangan, jadi Shipping Address di PO/PR/PI emang harus alamat
	customer - itu yang dibaca supplier waktu ngirim barang. Tapi ERPNext maksa field itu diisi
	alamat yang kedaftar di Company (`validate_company_linked_addresses`), dan satu-satunya
	pengecualian itu dropship bawaan (`delivered_by_supplier`) yang justru kita matiin biar
	Delivery Note & Purchase Receipt tetap kebentuk.

	Jadi alamatnya dititipin sebentar di sini, terus dipasang lagi sama
	`restore_customer_shipping_address` - hook `doc_events` jalannya setelah method controller-nya,
	jadi validasi intinya keburu lewat.

	Yang disingkirin cuma alamat yang beneran punya Customer. Alamat ngawur lain (punya supplier,
	atau gak nyambung ke siapa-siapa) tetap ditolak ERPNext kayak biasa.
	"""
	doc.flags.customer_shipping_address = None

	address = doc.get("shipping_address")
	if not address or not is_customer_address(address):
		return

	doc.flags.customer_shipping_address = address
	doc.shipping_address = None


def restore_customer_shipping_address(doc, method=None):
	"""Hook `validate` dokumen pembelian: alamat customer dipasang lagi habis validasi inti."""
	from frappe.contacts.doctype.address.address import get_address_display

	address = doc.flags.customer_shipping_address
	if not address:
		return

	doc.shipping_address = address
	doc.shipping_address_display = get_address_display(address)


def is_customer_address(address):
	return bool(
		frappe.db.exists(
			"Dynamic Link",
			{"parent": address, "parenttype": "Address", "link_doctype": "Customer"},
		)
	)


def set_purchase_order_on_items(doc, method=None):
	"""Hook `validate` Delivery Note: baris dropship nyimpen nomor PO-nya.

	Barang dropship dikirim supplier langsung ke lapangan, jadi pas ngecek DN orang butuh tau
	PO mana yang jadi sumbernya - dan sebaliknya, dari PO harus kelihatan DN mana yang udah
	jalan (lihat Connections di PO). Field `purchase_order` di Delivery Note Item itu field
	bawaan yang emang buat ini, cuma di skema kita gak keisi sendiri karena dropship bawaan
	ERPNext-nya dimatiin.
	"""
	for item in doc.get("items") or []:
		if item.get("custom_transaction_type") != DROPSHIP or not item.get("so_detail"):
			continue

		purchase_order_item = get_purchase_order_item(item.so_detail)
		if not purchase_order_item:
			continue

		item.purchase_order = purchase_order_item.parent
		item.purchase_order_item = purchase_order_item.name


def get_purchase_order_item(sales_order_item):
	"""Baris PO aktif buat baris Sales Order ini - yang udah disubmit diutamain."""
	rows = frappe.get_all(
		"Purchase Order Item",
		filters={"sales_order_item": sales_order_item, "docstatus": ["<", 2]},
		fields=["name", "parent"],
		order_by="docstatus desc, creation desc",
		limit=1,
	)

	return rows[0] if rows else None


def set_dropship_warehouse_on_items(doc, method=None):
	"""Item dropship keluar/masuk lewat gudang transit dropship."""
	warehouse = None

	for item in doc.get("items") or []:
		if item.get("custom_transaction_type") != DROPSHIP:
			continue

		warehouse = warehouse or get_dropship_warehouse(doc.company)
		item.warehouse = warehouse


def get_dropship_warehouse(company):
	"""Gudang transit dropship. Diambil dari Company, dibuatin kalau belum ada."""
	warehouse = frappe.db.get_value("Company", company, "custom_dropship_warehouse")
	if warehouse:
		return warehouse

	abbreviation = frappe.db.get_value("Company", company, "abbr")
	warehouse = f"Dropship - {abbreviation}"

	if not frappe.db.exists("Warehouse", warehouse):
		parent = f"All Warehouses - {abbreviation}"
		frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": "Dropship",
				"company": company,
				"parent_warehouse": parent if frappe.db.exists("Warehouse", parent) else None,
				"is_group": 0,
			}
		).insert(ignore_permissions=True)

	frappe.db.set_value("Company", company, "custom_dropship_warehouse", warehouse)

	return warehouse


def get_pending_delivery_qty(purchase_order_item, delivered=0):
	"""Sisa qty baris PO yang belum dikirim ke customer - dipakai jadi isian awal di modal."""
	return max(flt(purchase_order_item.qty) - flt(delivered), 0)


@frappe.whitelist()
def get_items_for_delivery_note(purchase_order):
	"""Baris PO yang barangnya dikirim langsung ke lapangan - isi tabel di modal Delivery Note.

	Yang masuk sini baris Dropship dan Mixed. Baris Mixed sengaja qty-nya gak ditebak sistem:
	berapa yang dikirim ke customer dan berapa yang masuk gudang itu keputusan user, diisi di
	modalnya.
	"""
	doc = frappe.get_doc("Purchase Order", purchase_order)
	doc.check_permission("read")

	delivered = get_delivered_qty_by_sales_order_item(doc)
	rows = []

	for item in doc.items:
		if item.custom_transaction_type not in (DROPSHIP, MIXED):
			continue

		rows.append(
			{
				"purchase_order_item": item.name,
				"sales_order": item.sales_order,
				"sales_order_item": item.sales_order_item,
				"item_code": item.item_code,
				"item_name": item.item_name,
				"uom": item.uom,
				"transaction_type": item.custom_transaction_type,
				"order_qty": flt(item.qty),
				"qty": get_pending_delivery_qty(item, delivered.get(item.sales_order_item)),
			}
		)

	return rows


@frappe.whitelist()
def get_items_for_purchase_receipt(purchase_order):
	"""Baris PO yang barangnya masuk gudang sendiri - isi tabel di modal Purchase Receipt.

	Baris Dropship gak ikut: barangnya gak pernah mampir ke gudang, penerimaannya dibikin
	otomatis waktu Delivery Note-nya disubmit.
	"""
	doc = frappe.get_doc("Purchase Order", purchase_order)
	doc.check_permission("read")

	rows = []

	for item in doc.items:
		if item.custom_transaction_type == DROPSHIP:
			continue

		pending = flt(item.qty) - flt(item.received_qty)
		if pending <= 0:
			continue

		rows.append(
			{
				"purchase_order_item": item.name,
				"item_code": item.item_code,
				"item_name": item.item_name,
				"uom": item.uom,
				"warehouse": item.warehouse,
				"transaction_type": item.custom_transaction_type,
				"order_qty": flt(item.qty),
				"qty": pending,
			}
		)

	return rows


def get_delivered_qty_by_sales_order_item(purchase_order):
	"""Qty yang udah dikirim ke customer per baris Sales Order, dari DN yang masih aktif."""
	sales_order_items = [item.sales_order_item for item in purchase_order.items if item.sales_order_item]
	if not sales_order_items:
		return {}

	rows = frappe.get_all(
		"Delivery Note Item",
		filters={"so_detail": ["in", sales_order_items], "docstatus": ["<", 2]},
		fields=["so_detail", "qty"],
	)

	delivered = {}
	for row in rows:
		delivered[row.so_detail] = delivered.get(row.so_detail, 0) + flt(row.qty)

	return delivered


@frappe.whitelist()
def make_delivery_note(source_name, selected_items=None, target_doc=None):
	"""Bikin Delivery Note dari Purchase Order buat barang yang dikirim langsung ke lapangan.

	DN-nya tetap dibikin dari Sales Order (itu dokumen ke customer), cuma isinya dibatasi ke
	baris yang dipilih user di modal, qty-nya ikut isian user, dan barangnya keluar dari gudang
	transit dropship.
	"""
	from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note as make_dn

	purchase_order = frappe.get_doc("Purchase Order", source_name)
	purchase_order.check_permission("read")

	qty_by_row = get_selected_qty(selected_items)

	items = [
		item
		for item in purchase_order.items
		if item.custom_transaction_type in (DROPSHIP, MIXED)
		and (not qty_by_row or item.name in qty_by_row)
	]
	if not items:
		frappe.throw(
			_("No Dropship or Mixed item in this Purchase Order."), title=_("Nothing to Deliver")
		)

	sales_orders = {item.sales_order for item in items if item.sales_order}
	if not sales_orders:
		frappe.throw(
			_("Dropship items in this Purchase Order are not linked to any Sales Order."),
			title=_("Sales Order Not Found"),
		)

	if len(sales_orders) > 1:
		frappe.throw(
			_("This Purchase Order covers more than one Sales Order ({0}). Create the Delivery Note from each Sales Order instead.").format(
				", ".join(sorted(sales_orders))
			)
		)

	qty_by_sales_order_item = {
		item.sales_order_item: qty_by_row.get(item.name, flt(item.qty)) for item in items
	}

	delivery_note = make_dn(sales_orders.pop(), target_doc)
	delivery_note.items = [
		item for item in delivery_note.items if item.so_detail in qty_by_sales_order_item
	]

	warehouse = get_dropship_warehouse(delivery_note.company)
	for item in delivery_note.items:
		item.custom_transaction_type = DROPSHIP
		item.warehouse = warehouse
		item.qty = flt(qty_by_sales_order_item[item.so_detail], item.precision("qty"))

	set_transaction_type(delivery_note)

	return delivery_note


@frappe.whitelist()
def make_purchase_receipt(source_name, selected_items=None, target_doc=None):
	"""Bikin Purchase Receipt dari Purchase Order buat barang yang masuk gudang sendiri.

	Dipakai buat baris Reguler dan porsi gudang dari baris Mixed. Baris Dropship gak pernah
	lewat sini - penerimaannya kebentuk otomatis waktu Delivery Note-nya disubmit.
	"""
	from erpnext.buying.doctype.purchase_order.purchase_order import (
		make_purchase_receipt as make_receipt,
	)

	purchase_order = frappe.get_doc("Purchase Order", source_name)
	purchase_order.check_permission("read")

	qty_by_row = get_selected_qty(selected_items)
	receipt = make_receipt(source_name, target_doc)

	items = []
	for item in receipt.items:
		source = item.purchase_order_item

		if qty_by_row and source not in qty_by_row:
			continue

		if not qty_by_row and item.custom_transaction_type == DROPSHIP:
			continue

		if qty_by_row:
			item.qty = flt(qty_by_row[source], item.precision("qty"))

		# porsi yang masuk gudang itu penerimaan biasa, bukan dropship
		item.custom_transaction_type = REGULER
		items.append(item)

	if not items:
		frappe.throw(
			_("Every item in this Purchase Order is either received already or delivered straight to the customer."),
			title=_("Nothing to Receive"),
		)

	receipt.items = items
	set_transaction_type(receipt)

	return receipt


def get_selected_qty(selected_items):
	"""Isian modal -> qty per baris PO. Baris yang qty-nya nol dianggap gak dipilih."""
	if isinstance(selected_items, str):
		selected_items = frappe.parse_json(selected_items)

	qty_by_row = {}
	for row in selected_items or []:
		row = frappe._dict(row)
		if row.purchase_order_item and flt(row.qty) > 0:
			qty_by_row[row.purchase_order_item] = flt(row.qty)

	return qty_by_row


def make_dropship_purchase_receipt(doc, method=None):
	"""Hook `before_submit` Delivery Note: terima barangnya dulu baru dikirim.

	Barang dropship gak pernah mampir ke gudang fisik, tapi stoknya harus ada sebelum DN
	disubmit. Jadi Purchase Receipt atas PO-nya dibuat & disubmit otomatis di tanggal yang
	sama dengan DN.

	Serial number-nya ikut lewat sini juga: nomor yang diketik user di Delivery Note dioper ke
	Purchase Receipt (barangnya masuk dengan nomor dari supplier), dan kalau user gak ngisi,
	nomor hasil generate Purchase Receipt ditarik balik ke Delivery Note. Lihat `serial_no.py`.
	"""
	if doc.custom_transaction_type != DROPSHIP or doc.custom_dropship_purchase_receipt:
		return

	quantity_by_sales_order_item = {
		item.so_detail: flt(item.qty)
		for item in doc.items
		if item.custom_transaction_type == DROPSHIP and item.so_detail
	}
	if not quantity_by_sales_order_item:
		return

	if getdate(doc.posting_date) > getdate():
		frappe.throw(
			_(
				"Posting Date {0} is in the future. Purchase Receipt for a dropship delivery cannot be dated in the future, so set the Delivery Note date to today or earlier."
			).format(frappe.format(doc.posting_date, {"fieldtype": "Date"})),
			title=_("Dropship Purchase Receipt"),
		)

	validate_purchase_order_exists(doc, quantity_by_sales_order_item)

	serial_nos = get_serial_nos_by_sales_order_item(doc)

	purchase_receipts = []
	for purchase_order in get_purchase_orders_to_receive(quantity_by_sales_order_item):
		receipt = create_purchase_receipt(doc, purchase_order, quantity_by_sales_order_item, serial_nos)
		if receipt:
			purchase_receipts.append(receipt.name)
			set_serial_nos_on_delivery_note(doc, receipt)

	if not purchase_receipts:
		return

	doc.custom_dropship_purchase_receipt = purchase_receipts[0]
	frappe.msgprint(
		_("Purchase Receipt {0} created automatically for this dropship delivery.").format(
			", ".join(purchase_receipts)
		),
		title=_("Dropship Purchase Receipt"),
		indicator="green",
		alert=True,
	)


def validate_purchase_order_exists(delivery_note, quantity_by_sales_order_item):
	"""Item dropship harus udah punya Purchase Order sebelum Delivery Note-nya disubmit.

	Purchase Receipt dropship dibikin di atas PO. Tanpa PO gak ada yang bisa diterima, dan
	kegagalannya baru kelihatan jauh di belakang - waktu ERPNext nyari Serial No yang harusnya
	kebentuk dari Purchase Receipt itu. Jadi dicegat di sini biar pesannya nunjuk ke penyebabnya.
	"""
	ordered = frappe.get_all(
		"Purchase Order Item",
		filters={"sales_order_item": ["in", list(quantity_by_sales_order_item)], "docstatus": ["<", 2]},
		fields=["sales_order_item"],
	)
	ordered_rows = {row.sales_order_item for row in ordered}

	missing = [
		item
		for item in delivery_note.items
		if item.custom_transaction_type == DROPSHIP
		and item.so_detail
		and item.so_detail not in ordered_rows
	]
	if not missing:
		return

	frappe.throw(
		_(
			"Row {0}: item {1} has no Purchase Order yet. Dropship items are received through a Purchase Receipt created from the Purchase Order, so create and submit the Purchase Order from Sales Order {2} first (Create > Purchase Order (per Supplier))."
		).format(
			", ".join(f"#{item.idx}" for item in missing),
			", ".join(sorted({item.item_code for item in missing})),
			missing[0].against_sales_order or "",
		),
		title=_("Purchase Order Not Found"),
	)


def get_purchase_orders_to_receive(quantity_by_sales_order_item):
	"""Purchase Order submitted yang barangnya belum diterima, buat baris DN ini."""
	rows = frappe.get_all(
		"Purchase Order Item",
		filters={
			"sales_order_item": ["in", list(quantity_by_sales_order_item)],
			"docstatus": 1,
		},
		fields=["parent", "qty", "received_qty"],
	)

	return sorted({row.parent for row in rows if flt(row.qty) > flt(row.received_qty)})


def create_purchase_receipt(
	delivery_note, purchase_order, quantity_by_sales_order_item, serial_nos_by_sales_order_item=None
):
	from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt

	receipt = make_purchase_receipt(purchase_order)
	receipt.posting_date = delivery_note.posting_date
	receipt.posting_time = delivery_note.posting_time
	receipt.set_posting_time = 1

	warehouse = get_dropship_warehouse(delivery_note.company)
	items = []

	for item in receipt.items:
		delivered_qty = quantity_by_sales_order_item.get(item.sales_order_item)
		if not delivered_qty:
			continue

		# terima sebanyak yang dikirim, gak lebih dari sisa PO
		item.qty = min(flt(item.qty), delivered_qty)
		item.received_qty = item.qty
		item.warehouse = warehouse
		item.custom_transaction_type = DROPSHIP
		items.append(item)

	if not items:
		return None

	receipt.items = items
	set_transaction_type(receipt)
	set_serial_nos_on_receipt(receipt, serial_nos_by_sales_order_item or {})
	receipt.insert(ignore_permissions=True)
	receipt.submit()

	return receipt
