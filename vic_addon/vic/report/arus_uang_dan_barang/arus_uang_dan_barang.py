"""Kertas Kerja Pemeriksaan - Arus Uang dan Barang.

Penyerahan (penjualan) diadu sama pembelian, dikelompokin per proyek: kiri faktur pajak
keluaran, kanan faktur pajak masukan. Dipakai waktu pemeriksaan pajak buat nunjukin barang yang
dijual itu asalnya dari pembelian yang mana.

Dua sisinya gak punya hubungan baris-per-baris - yang nyambungin cuma **proyek**-nya. Jadi
barisnya disusun berdampingan: kiri jalan sendiri, kanan jalan sendiri, yang pendek diganjal
baris kosong sampai sejajar.

Satu invoice bisa makan beberapa baris: baris pertama bawa identitas lawan transaksi, nomor
faktur, DPP, dan PPN-nya; baris berikutnya cuma rincian barang. Sama persis kayak bentuk kertas
kerja yang dipakai pemeriksa.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

COLUMNS = [
	# --- PENYERAHAN ---
	("no", _("No"), "Data", 50),
	("sales_invoice", _("Sales Invoice"), "Link/Sales Invoice", 130),
	("buyer", _("Nama Pembeli"), "Data", 190),
	("buyer_npwp", _("NPWP Pembeli"), "Data", 150),
	("sales_item", _("Rincian Barang"), "Data", 260),
	("sales_faktur_no", _("Nomor Seri (Jual)"), "Data", 150),
	("sales_faktur_date", _("Tanggal (Jual)"), "Date", 100),
	("sales_dpp", _("DPP (Jual)"), "Currency", 130),
	("sales_ppn", _("PPN (Jual)"), "Currency", 120),
	# --- PEMBELIAN ---
	("purchase_invoice", _("Purchase Invoice"), "Link/Purchase Invoice", 130),
	("seller", _("Nama PKP Penjual BKP/JKP"), "Data", 190),
	("seller_npwp", _("NPWP Penjual"), "Data", 150),
	("purchase_faktur_no", _("Nomor Seri (Beli)"), "Data", 150),
	("purchase_faktur_date", _("Tanggal (Beli)"), "Date", 100),
	("purchase_item", _("Jenis Barang"), "Data", 260),
	("qty", _("Quantity"), "Float", 90),
	("uom", _("UOM"), "Data", 70),
	("rate", _("@ Hrg Satuan"), "Currency", 120),
	("purchase_dpp", _("DPP PPN (Beli)"), "Currency", 130),
	("purchase_ppn", _("PPN (Beli)"), "Currency", 120),
]


def execute(filters=None):
	filters = frappe._dict(filters or {})

	return get_columns(), get_rows(filters)


def get_columns():
	columns = []

	for fieldname, label, fieldtype, width in COLUMNS:
		column = {"fieldname": fieldname, "label": label, "width": width}

		if "/" in fieldtype:
			column["fieldtype"], column["options"] = fieldtype.split("/")
		else:
			column["fieldtype"] = fieldtype

		columns.append(column)

	return columns


def get_rows(filters):
	"""Baris siap tampil: tiap proyek dikasih judul, terus dua sisinya disejajarin."""
	rows = []

	for group in get_data(filters):
		rows.append({"buyer": group.project_label, "is_group": 1})

		sales = flatten_sales(group.sales)
		purchases = flatten_purchases(group.purchases)

		for index in range(max(len(sales), len(purchases))):
			row = {}
			row.update(sales[index] if index < len(sales) else {})
			row.update(purchases[index] if index < len(purchases) else {})
			rows.append(row)

	return rows


def get_data(filters):
	"""Data mentah per proyek: daftar invoice penjualan dan pembelian beserta rinciannya."""
	groups = []

	for project, label in get_projects(filters):
		sales = get_invoices("Sales Invoice", project, filters)
		purchases = get_invoices("Purchase Invoice", project, filters)

		if sales or purchases:
			groups.append(
				frappe._dict({"project": project, "project_label": label, "sales": sales, "purchases": purchases})
			)

	return groups


def get_projects(filters):
	"""Proyek yang kepakai di periode itu. `(nama, judul)` - proyek kosong ikut, judulnya khusus."""
	if filters.get("project"):
		name = filters.project
		return [(name, f"{name} - {frappe.db.get_value('Project', name, 'project_name') or ''}".strip(" -"))]

	names = set()
	for doctype in ("Sales Invoice", "Purchase Invoice"):
		names.update(
			frappe.get_all(doctype, filters=get_invoice_filters(doctype, filters), pluck="project", distinct=True)
		)

	projects = []
	for name in sorted(names, key=lambda value: (value is None, value or "")):
		if name:
			label = f"{name} - {frappe.db.get_value('Project', name, 'project_name') or ''}".strip(" -")
		else:
			label = _("Tanpa Proyek")
		projects.append((name, label))

	return projects


def get_invoice_filters(doctype, filters):
	conditions = {"docstatus": 1}

	if filters.get("company"):
		conditions["company"] = filters.company

	if filters.get("from_date") and filters.get("to_date"):
		conditions["posting_date"] = ["between", [filters.from_date, filters.to_date]]

	return conditions


def get_invoices(doctype, project, filters):
	"""Invoice satu proyek, lengkap sama barisnya. DPP & PPN diambil dari dokumennya."""
	conditions = get_invoice_filters(doctype, filters)
	conditions["project"] = project if project else ["in", ["", None]]

	invoices = []
	is_sales = doctype == "Sales Invoice"

	for name in frappe.get_all(doctype, filters=conditions, pluck="name", order_by="posting_date, name"):
		doc = frappe.get_doc(doctype, name)

		invoices.append(
			frappe._dict(
				{
					"name": doc.name,
					"party": doc.customer_name if is_sales else doc.supplier_name,
					"npwp": doc.tax_id,
					"faktur_no": doc.get("custom_faktur_pajak_no") if is_sales else doc.bill_no,
					"faktur_date": (doc.get("custom_faktur_pajak_date") if is_sales else doc.bill_date)
					or doc.posting_date,
					"dpp": flt(doc.net_total),
					"ppn": get_ppn(doc),
					"items": [
						frappe._dict(
							{
								"description": item.item_name or item.item_code,
								"qty": flt(item.qty),
								"uom": item.uom,
								"rate": flt(item.rate),
							}
						)
						for item in doc.items
					],
				}
			)
		)

	return invoices


def get_ppn(doc):
	"""Total PPN dokumen. Baris PPh dilewat - dia potongan, bukan pajak yang ditagih."""
	total = 0.0

	for tax in doc.get("taxes") or []:
		if tax.get("is_tax_withholding_account") or tax.get("add_deduct_tax") == "Deduct":
			continue

		total += flt(tax.base_tax_amount)

	return total


def flatten_sales(invoices):
	"""Sisi penyerahan jadi baris datar: baris pertama bawa identitas, sisanya rincian barang."""
	rows = []

	for number, invoice in enumerate(invoices, start=1):
		for index, item in enumerate(invoice["items"] or [frappe._dict({"description": ""})]):
			head = index == 0
			rows.append(
				{
					"no": str(number) if head else "",
					"sales_invoice": invoice.name if head else "",
					"buyer": invoice.party if head else "",
					"buyer_npwp": invoice.npwp if head else "",
					"sales_item": item.description,
					"sales_faktur_no": invoice.faktur_no if head else "",
					"sales_faktur_date": invoice.faktur_date if head else None,
					"sales_dpp": invoice.dpp if head else None,
					"sales_ppn": invoice.ppn if head else None,
				}
			)

	return rows


def flatten_purchases(invoices):
	"""Sisi pembelian jadi baris datar, dengan qty dan harga satuan per barang."""
	rows = []

	for invoice in invoices:
		for index, item in enumerate(invoice["items"] or [frappe._dict({"description": ""})]):
			head = index == 0
			rows.append(
				{
					"purchase_invoice": invoice.name if head else "",
					"seller": invoice.party if head else "",
					"seller_npwp": invoice.npwp if head else "",
					"purchase_faktur_no": invoice.faktur_no if head else "",
					"purchase_faktur_date": invoice.faktur_date if head else None,
					"purchase_item": item.description,
					"qty": item.get("qty"),
					"uom": item.get("uom"),
					"rate": item.get("rate"),
					"purchase_dpp": invoice.dpp if head else None,
					"purchase_ppn": invoice.ppn if head else None,
				}
			)

	return rows
