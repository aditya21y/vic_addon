"""Retensi di Sales Invoice: ditahan otomatis di invoice progress, ditagih balik di invoice retensi.

Retensi = sisa bayar yang ditahan customer padahal barang udah dikirim penuh (mis. termin SO
"dp 20%, 75% progress, 5% retensi"). Alurnya, bareng skema DP Item (`dp_item_invoice.py`):

	1. Invoice DP       centang Is DP Invoice                       -> DPP 20%
	2. Invoice progress centang Is Progress Invoice + pilih termin  -> barang penuh, baris RETENSI
	                    minus 5% x DPP barang ketambah sendiri, DP ditarik ke tabel DP Invoices
	3. Invoice retensi  centang Is Retention Invoice + pilih SO     -> satu baris RETENSI plus senilai
	                    retensi yang ditahan & belum ditagih, sisa DP dibalik semua

Baris RETENSI pakai akun neraca **Piutang Retensi** (bukan Penjualan): penjualan tetap diakui penuh
waktu barang dikirim, PPN & faktur ngikut tagihan, dan sisa retensi = saldo akun itu.

Persen retensi diambil dari baris Payment Schedule SO yang termin-nya retensi: Payment Term-nya
dicentang *Is Retention*, atau namanya/deskripsinya mengandung "retensi"/"retention".

ERPNext nolak rate minus kecuali *Selling Settings > Allow Negative rates for Items* nyala (setelan
global, gak bisa per baris). Karena itu di sini ada penjaga sendiri: yang boleh minus cuma baris
RETENSI di invoice progress.
"""

import frappe
from frappe import _
from frappe.utils import flt

from vic_addon.vic.dp_item_invoice import TOLERANCE, get_link, get_term_row

RETENTION_WORDS = ("retensi", "retention")


# ---------------------------------------------------------------------------------------------
# Hook
# ---------------------------------------------------------------------------------------------


def set_retention(doc, method=None):
	"""Hook `before_validate` Sales Invoice: susun baris RETENSI buat invoice progress / retensi."""
	if doc.docstatus != 0:
		return

	flags = [doc.get("custom_is_dp"), doc.get("custom_is_progress"), doc.get("custom_is_retention")]
	if sum(1 for flag in flags if flag) > 1:
		frappe.throw(_("Pick only one of Is DP Invoice, Is Progress Invoice, or Is Retention Invoice."))

	if doc.get("custom_is_progress"):
		set_progress_invoice(doc)
	elif doc.get("custom_is_retention"):
		set_retention_invoice(doc)


def validate_negative_rates(doc, method=None):
	"""Hook `validate` Sales Invoice: rate minus cuma boleh di baris RETENSI invoice progress."""
	if doc.get("is_return"):
		return

	item = get_settings(doc.company, throw=False).item
	for row in doc.get("items") or []:
		if flt(row.rate) >= 0:
			continue
		if not (item and row.item_code == item and doc.get("custom_is_progress")):
			frappe.throw(
				_("Row #{0}: rate of {1} cannot be negative. Only the retention line of a Progress Invoice can be.").format(
					row.idx, frappe.bold(row.item_code)
				),
				title=_("Negative Rate"),
			)


def block_cancel_of_billed_retention(doc, method=None):
	"""Hook `before_cancel`: invoice progress yang retensinya udah ditagih gak boleh dicancel duluan."""
	if not (doc.get("custom_is_progress") and doc.get("custom_dp_order")):
		return

	settings = get_settings(doc.company, throw=False)
	if not settings.item:
		return

	withheld_here = -sum(flt(row.amount) for row in doc.items if row.item_code == settings.item)
	remaining = get_withheld(doc.custom_dp_order, settings.item) - get_billed(doc.custom_dp_order, settings.item)
	if withheld_here > remaining + TOLERANCE:
		frappe.throw(
			_("The retention of {0} is already billed in {1}. Cancel the retention invoice first.").format(
				doc.custom_dp_order,
				", ".join(get_link("Sales Invoice", name) for name in get_retention_invoices(doc.custom_dp_order)),
			),
			title=_("Retention Already Billed"),
		)


# ---------------------------------------------------------------------------------------------
# Invoice progress
# ---------------------------------------------------------------------------------------------


def set_progress_invoice(doc):
	settings = get_settings(doc.company)

	orders = {row.sales_order for row in doc.items if row.get("sales_order") and row.item_code != settings.item}
	if len(orders) != 1:
		frappe.throw(_("A Progress Invoice must bill items from exactly one Sales Order."))

	order = frappe.get_doc("Sales Order", orders.pop())
	doc.custom_dp_order = order.name

	# termin yang ditagih: wajib baris schedule SO yang bukan termin retensi
	term = get_term_row(order, doc.get("custom_progress_term"))
	if is_retention_term(term):
		frappe.throw(_("Pick the progress term, not the retention term, in Progress Term."))

	rows = [row for row in doc.items if row.item_code != settings.item]
	percent = get_retention_percent(order)
	# qty x rate, bukan `amount`: di before_validate kolom amount belum dihitung ulang kalau qty diubah
	base = sum(flt(row.qty) * flt(row.rate) for row in rows if row.get("sales_order") == order.name)
	amount = flt(base * percent / 100, doc.precision("net_total"))

	doc.set("items", rows)
	if amount:
		append_retention_row(doc, settings, -amount, percent, order.name)

	# disimpan pertama kali dengan tabel DP masih kosong -> DP order ini ditarik otomatis (porsi
	# default, masih bisa diedit sesudahnya)
	if doc.is_new() and not doc.get("custom_dp_allocations"):
		from vic_addon.vic.dp_item_invoice import get_default_allocations

		for row in get_default_allocations(doc):
			doc.append("custom_dp_allocations", row)


# ---------------------------------------------------------------------------------------------
# Invoice retensi
# ---------------------------------------------------------------------------------------------


def set_retention_invoice(doc):
	settings = get_settings(doc.company)

	if not doc.get("custom_dp_order"):
		frappe.throw(_("Select the Sales Order whose retention is billed."))

	order = frappe.get_doc("Sales Order", doc.custom_dp_order)
	if order.docstatus != 1 or order.customer != doc.customer or order.company != doc.company:
		frappe.throw(_("{0} must be a submitted Sales Order of {1}.").format(order.name, doc.customer))

	remaining = get_withheld(order.name, settings.item) - get_billed(order.name, settings.item, exclude=doc.name)
	remaining = flt(remaining, doc.precision("net_total"))
	if remaining <= TOLERANCE:
		frappe.throw(
			_("There is no unbilled retention left for {0}.").format(order.name), title=_("No Retention Left")
		)

	doc.set("items", [])
	append_retention_row(doc, settings, remaining, get_retention_percent(order), order.name)

	# pajaknya ngikut SO kalau invoice-nya belum punya
	if not doc.get("taxes") and order.get("taxes"):
		doc.taxes_and_charges = order.taxes_and_charges
		for tax in order.taxes:
			if tax.charge_type == "Actual":
				continue
			doc.append(
				"taxes",
				{
					field: tax.get(field)
					for field in ("charge_type", "account_head", "description", "rate", "cost_center", "included_in_print_rate")
				},
			)

	doc.payment_terms_template = None
	doc.set("payment_schedule", [])
	if doc.meta.has_field("update_stock"):
		doc.update_stock = 0

	# sisa DP order ini dibalik di invoice retensi (dokumen baru yang tabelnya masih kosong) - maksimal
	# senilai retensinya, biar tagihannya gak minus kalau DP-nya belum habis kebalik di invoice progress
	if doc.is_new() and not doc.get("custom_dp_allocations"):
		from vic_addon.vic.dp_item_invoice import compute_row_totals, get_default_allocations

		room = remaining
		for row in get_default_allocations(doc):
			allocated = min(flt(row["allocated_amount"]), room)
			if allocated <= TOLERANCE:
				break
			row["allocated_amount"] = flt(allocated, 2)
			row.update(compute_row_totals(row["dp_invoice"], doc.doctype, row["allocated_amount"]))
			doc.append("custom_dp_allocations", row)
			room -= allocated

	# Kalau ada DP yang dibalik di sini, pembulatan grand total dimatiin: DP yang dibalik ikut angka
	# persis (mis. 2.830,50), jadi tagihannya juga harus persis - kalau dibulatin jadi 2.830, DP-nya
	# kelebihan 0,50 dan invoice-nya ditolak.
	if doc.get("custom_dp_allocations"):
		doc.disable_rounded_total = 1

	warn_unreversed_dp(doc, order.name)


def warn_unreversed_dp(doc, order):
	"""Invoice retensi biasanya tagihan terakhir order-nya: kalau masih ada DP yang belum dibalik,
	kasih tau - DP itu masih nyangkut di akun uang muka dan customer bakal kelebihan bayar."""
	from vic_addon.vic.dp_item_invoice import get_allocated_elsewhere, get_dp_invoices

	available = sum(
		flt(dp.base_net_total) - get_allocated_elsewhere(doc.doctype, dp.name, doc.name)
		for dp in get_dp_invoices(doc.doctype, order, submitted_only=True)
	)
	left = flt(available - sum(flt(row.allocated_amount) for row in doc.get("custom_dp_allocations") or []), 2)
	if left > TOLERANCE:
		frappe.msgprint(
			_("DP of {0} still has {1} (DPP) not reversed after this invoice. Reverse it in a progress invoice, otherwise the customer pays it twice.").format(
				order, frappe.format(left, {"fieldtype": "Currency", "options": doc.currency})
			),
			title=_("DP Not Fully Reversed"),
			indicator="orange",
		)


# ---------------------------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------------------------


def append_retention_row(doc, settings, amount, percent, order):
	item = frappe.get_cached_doc("Item", settings.item)
	doc.append(
		"items",
		{
			"item_code": item.name,
			"item_name": item.item_name,
			"description": _("Retensi {0}% - {1}").format(frappe.format(percent, {"fieldtype": "Float"}), order),
			"qty": 1,
			"uom": item.stock_uom,
			"stock_uom": item.stock_uom,
			"conversion_factor": 1,
			"price_list_rate": 0,
			"discount_percentage": 0,
			"discount_amount": 0,
			"rate": amount,
			"income_account": settings.account,
			"cost_center": doc.get("cost_center") or frappe.get_cached_value("Company", doc.company, "cost_center"),
		},
	)


def get_settings(company, throw=True):
	values = frappe.get_cached_value(
		"Company", company, ["custom_retention_item", "custom_retention_account"], as_dict=True
	) or frappe._dict()
	settings = frappe._dict(item=values.custom_retention_item, account=values.custom_retention_account)

	if throw and not (settings.item and settings.account):
		frappe.throw(
			_("Set the Retention Item and the Piutang Retensi account in Company {0} first.").format(
				frappe.bold(company)
			),
			title=_("Retention Not Set Up"),
		)
	return settings


def is_retention_term(row):
	if row.get("payment_term") and frappe.get_cached_value("Payment Term", row.payment_term, "custom_is_retention"):
		return True
	text = " ".join(filter(None, [row.get("payment_term"), row.get("description")])).lower()
	return any(word in text for word in RETENTION_WORDS)


def get_retention_percent(order):
	return sum(flt(row.invoice_portion) for row in order.get("payment_schedule") or [] if is_retention_term(row))


def get_withheld(order, item):
	"""Retensi yang ditahan di invoice progress submitted order ini (angka positif)."""
	return -flt(_sum_retention_rows(order, item, "custom_is_progress"))


def get_billed(order, item, exclude=None):
	"""Retensi yang udah ditagih di invoice retensi submitted order ini."""
	return flt(_sum_retention_rows(order, item, "custom_is_retention", exclude))


def _sum_retention_rows(order, item, flag, exclude=None):
	row = frappe.qb.DocType("Sales Invoice Item")
	invoice = frappe.qb.DocType("Sales Invoice")
	query = (
		frappe.qb.from_(row)
		.inner_join(invoice)
		.on(invoice.name == row.parent)
		.select(frappe.query_builder.functions.Sum(row.amount))
		.where(
			(row.item_code == item)
			& (invoice.docstatus == 1)
			& (invoice[flag] == 1)
			& (invoice.custom_dp_order == order)
		)
	)
	if exclude:
		query = query.where(invoice.name != exclude)
	result = query.run()
	return flt(result[0][0]) if result else 0


def get_retention_invoices(order):
	return frappe.get_all(
		"Sales Invoice",
		filters={"custom_is_retention": 1, "custom_dp_order": order, "docstatus": 1},
		pluck="name",
	)


@frappe.whitelist()
def get_progress_terms(order):
	"""Pilihan Progress Term buat form: baris schedule SO selain termin retensi."""
	order_doc = frappe.get_doc("Sales Order", order)
	order_doc.check_permission("read")

	from vic_addon.vic.dp_item_invoice import get_term_label

	return [
		{"label": get_term_label(row), "portion": flt(row.invoice_portion)}
		for row in order_doc.get("payment_schedule") or []
		if not is_retention_term(row)
	]


# ---------------------------------------------------------------------------------------------
# Tombol Create > Retention Invoice di Sales Order
# ---------------------------------------------------------------------------------------------
#
# SO yang barangnya udah ketagih semua (% Billed 100) gak bisa bikin Sales Invoice lewat mapper
# bawaan, dan SI baru yang Items-nya kosong ditolak form (Items wajib). Jadi invoice retensinya
# dibikin dari sini: dokumennya udah keisi baris RETENSI, pajak, dan sisa DP sebelum dibuka.


@frappe.whitelist()
def get_unbilled_retention(sales_order):
	"""Retensi order ini yang udah ditahan di invoice progress tapi belum ditagih."""
	order = frappe.get_doc("Sales Order", sales_order)
	order.check_permission("read")

	settings = get_settings(order.company, throw=False)
	if not settings.item:
		return 0
	return flt(get_withheld(order.name, settings.item) - get_billed(order.name, settings.item), 2)


@frappe.whitelist()
def make_retention_invoice(source_name):
	order = frappe.get_doc("Sales Order", source_name)
	order.check_permission("read")

	doc = frappe.new_doc("Sales Invoice")
	doc.update(
		{
			"customer": order.customer,
			"company": order.company,
			"currency": order.currency,
			"conversion_rate": order.conversion_rate,
			"selling_price_list": order.selling_price_list,
			"project": order.get("project"),
			"cost_center": order.get("cost_center"),
			"custom_is_retention": 1,
			"custom_dp_order": order.name,
		}
	)
	doc.run_method("set_missing_values")
	set_retention_invoice(doc)
	doc.run_method("calculate_taxes_and_totals")
	return doc
