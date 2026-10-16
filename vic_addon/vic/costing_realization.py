"""Realisasi Costing: rencana di Costing vs realisasi di Sales Order (jual) & Purchase Order (beli).

Rantainya: Costing -> Quotation (`custom_costing`, submitted) -> Sales Order (baris SO nyimpen
Quotation asalnya di `prevdoc_docname`, barisnya di `quotation_item`) -> Purchase Order (baris PO
nyimpen baris SO di `sales_order_item`). Semua yang dihitung cuma dokumen **submitted**.

Baris SO dicocokin ke baris Costing lewat baris Quotation-nya: item code + Supplier Quotation
(`custom_supplier_quotation`), soalnya item yang sama bisa muncul dua kali dari penawaran supplier
beda. Kalau gak ketemu yang persis, jatuh ke baris Costing pertama dengan item code yang sama; kalau
tetap gak ada (item ditambah di SO), jadi baris sendiri dengan rencana nol.

Nilai pakai **net amount mata uang perusahaan** (`base_net_amount`): udah dipotong diskon, belum
termasuk pajak. Rencana:

	jual  = Quotation Amount Costing (harga nego ke customer)
	beli  = Amount Costing (harga beli dari Supplier Quotation)
	profit = jual - beli

Additional cost (ongkir dll) sengaja gak masuk profit rencana - realisasinya cuma SO - PO, jadi biar
dua angkanya sebanding.

Profit realisasi = nilai SO - biaya beli. Qty SO yang **belum di-PO** dinilai pakai harga beli
rencana (perkiraan) - kalau dibiarin nol, item yang belum dibeli kebaca untung 100%. Kolom PO Status
nunjukin baris mana yang masih ngandung perkiraan.
"""

import frappe
from frappe.utils import flt

AMOUNT_FIELDS = ("plan_qty", "so_qty", "po_qty", "plan_sell_amount", "so_amount", "plan_buy_amount", "po_amount")


@frappe.whitelist()
def get_costing_realization(costing):
	"""Buat section Realization di form Costing."""
	doc = frappe.get_doc("Costing", costing)
	doc.check_permission("read")
	return get_realization(doc)


def get_realization(costing):
	"""`{rows, total, quotations, sales_orders, purchase_orders}` buat satu Costing."""
	quotations = frappe.get_all(
		"Quotation", filters={"custom_costing": costing.name, "docstatus": 1}, pluck="name"
	)
	so_items = get_sales_order_items(quotations)
	po_items = get_purchase_order_items([row.name for row in so_items])

	rows = []
	index_by_key, index_by_item = {}, {}
	for item in costing.items:
		row = new_row(item.item_code, item.item_name)
		row.update(
			plan_qty=flt(item.qty),
			plan_sell_amount=flt(item.quotation_amount),
			plan_buy_amount=flt(item.amount),
		)
		index_by_key.setdefault((item.item_code, item.supplier_quotation or None), len(rows))
		index_by_item.setdefault(item.item_code, len(rows))
		rows.append(row)

	quotation_items = get_quotation_item_keys([row.quotation_item for row in so_items if row.quotation_item])

	po_by_so_item = {}
	for po in po_items:
		entry = po_by_so_item.setdefault(po.sales_order_item, frappe._dict(qty=0, amount=0))
		entry.qty += flt(po.qty)
		entry.amount += flt(po.base_net_amount)

	for so in so_items:
		key = quotation_items.get(so.quotation_item) or (so.item_code, None)
		index = index_by_key.get(key)
		if index is None:
			index = index_by_item.get(so.item_code)
		if index is None:
			# item yang gak ada di Costing (ditambah di Quotation/SO) - rencananya nol
			index = len(rows)
			rows.append(new_row(so.item_code, so.item_name))
			index_by_item[so.item_code] = index

		row = rows[index]
		row.so_qty += flt(so.qty)
		row.so_amount += flt(so.base_net_amount)

		po = po_by_so_item.get(so.name)
		if po:
			row.po_qty += po.qty
			row.po_amount += po.amount

	for row in rows:
		finish_row(row)

	total = new_row(None, None)
	for row in rows:
		for field in AMOUNT_FIELDS:
			total[field] += flt(row[field])
	finish_row(total)

	return frappe._dict(
		costing=costing.name,
		rows=rows,
		total=total,
		quotations=quotations,
		sales_orders=sorted({row.parent for row in so_items}),
		purchase_orders=sorted({row.parent for row in po_items}),
	)


def get_sales_order_items(quotations):
	if not quotations:
		return []

	item = frappe.qb.DocType("Sales Order Item")
	order = frappe.qb.DocType("Sales Order")
	return (
		frappe.qb.from_(item)
		.inner_join(order)
		.on(order.name == item.parent)
		.select(item.name, item.parent, item.item_code, item.item_name, item.qty, item.base_net_amount, item.quotation_item)
		.where((item.prevdoc_docname.isin(quotations)) & (order.docstatus == 1))
		.orderby(item.parent)
		.orderby(item.idx)
	).run(as_dict=True)


def get_purchase_order_items(so_item_names):
	if not so_item_names:
		return []

	item = frappe.qb.DocType("Purchase Order Item")
	order = frappe.qb.DocType("Purchase Order")
	return (
		frappe.qb.from_(item)
		.inner_join(order)
		.on(order.name == item.parent)
		.select(item.parent, item.sales_order_item, item.qty, item.base_net_amount)
		.where((item.sales_order_item.isin(so_item_names)) & (order.docstatus == 1))
	).run(as_dict=True)


def get_quotation_item_keys(names):
	"""Baris Quotation -> (item code, Supplier Quotation), kunci buat nyari baris Costing-nya."""
	if not names:
		return {}
	return {
		row.name: (row.item_code, row.custom_supplier_quotation or None)
		for row in frappe.get_all(
			"Quotation Item",
			filters={"name": ["in", names]},
			fields=["name", "item_code", "custom_supplier_quotation"],
		)
	}


def new_row(item_code, item_name):
	row = frappe._dict(item_code=item_code, item_name=item_name)
	for field in AMOUNT_FIELDS:
		row[field] = 0.0
	return row


def finish_row(row):
	"""Harga rata-rata, selisih, profit & margin dari angka qty/nilai yang udah dijumlah."""
	def rate(amount, qty):
		return flt(amount) / flt(qty) if flt(qty) else 0

	row.plan_sell_rate = rate(row.plan_sell_amount, row.plan_qty)
	row.so_rate = rate(row.so_amount, row.so_qty)
	row.plan_buy_rate = rate(row.plan_buy_amount, row.plan_qty)
	row.po_rate = rate(row.po_amount, row.po_qty)

	row.sell_variance = row.so_amount - row.plan_sell_amount

	# qty SO yang belum di-PO dinilai pakai harga beli rencana (perkiraan), biar gak kebaca untung 100%
	unordered = max(flt(row.so_qty) - flt(row.po_qty), 0)
	row.real_buy_amount = row.po_amount + unordered * row.plan_buy_rate
	row.po_status = get_po_status(row.so_qty, row.po_qty)
	row.buy_variance = row.real_buy_amount - row.plan_buy_amount

	row.plan_profit = row.plan_sell_amount - row.plan_buy_amount
	row.real_profit = row.so_amount - row.real_buy_amount
	row.profit_variance = row.real_profit - row.plan_profit

	row.plan_margin = row.plan_profit / row.plan_sell_amount * 100 if row.plan_sell_amount else 0
	row.real_margin = row.real_profit / row.so_amount * 100 if row.so_amount else 0
	return row


def get_po_status(so_qty, po_qty):
	if not flt(so_qty):
		return "Belum SO"
	if not flt(po_qty):
		return "Belum PO"
	if flt(po_qty) < flt(so_qty):
		return "PO Sebagian"
	if flt(po_qty) > flt(so_qty):
		return "PO Lebih"
	return "Lengkap"
