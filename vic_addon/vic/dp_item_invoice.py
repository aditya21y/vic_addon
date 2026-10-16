"""Skema DP pakai Item DP: invoice DP biasa, terus dibalik lewat Reverse Journal di invoice progress.

Gantiin alur DP lama (Advance Invoice / Payment Request). Contoh order DPP 1.000 + PPN 100, DP 20%:

	1. Invoice DP     Dr Piutang 220 / Cr Uang Muka Penjualan 200 / Cr PPN 20
	                  Centang **Is DP Invoice**: semua item diganti Item DP (setting Company), rate =
	                  DP Percentage x Net Total order (DPP, bukan grand total). DP Percentage keisi
	                  dari porsi term DP yang dipilih, dan boleh diubah user.
	2. PE DP          Dr Bank 220 / Cr Piutang 220                        (bawaan ERPNext)
	3. Invoice progress (item asli, mis. 50% = 500)
	                  Dr Piutang 550 / Cr Penjualan 500 / Cr PPN 50       (bawaan ERPNext)
	4. Reverse Journal, otomatis waktu invoice progress disubmit:
	                  Dr Uang Muka Penjualan 100 / Dr PPN 10 / Cr Piutang 110 (nempel ke invoice
	                  progress, jadi tagihannya tinggal 440)
	5. PE             Dr Bank 440 / Cr Piutang 440                        (bawaan ERPNext)

Sisi pembelian sama persis, arahnya kebalik (Uang Muka Pembelian = aset, PPN Masukan).

DP yang dibalik ditarik ke tabel **DP Allocations** di invoice progress (tombol *Get DP
Invoices*, mirip *Get Advances*): DP Invoice dari order yang sama, party & company sama. Default
porsinya sebanding tagihan invoice ini terhadap order; invoice yang ngelunasin order ngambil semua
sisa DP. Angkanya boleh diubah user.

Reverse Journal-nya ngebalik **jurnal GL invoice DP-nya sendiri** (semua baris selain baris
piutang/hutang) secara proporsional: Allocated / DPP DP. Jadi akun Uang Muka, PPN, PPh, sampai
cost center-nya persis sama dengan yang dipakai invoice DP, gak ada akun yang ditebak.
"""

import json
import re

import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import flt

SIDES = {
	"Sales Invoice": frappe._dict(
		order_doctype="Sales Order",
		order_field="sales_order",
		party_type="Customer",
		party_field="customer",
		party_account="debit_to",
		item_account="income_account",
		company_account="custom_sales_dp_account",
	),
	"Purchase Invoice": frappe._dict(
		order_doctype="Purchase Order",
		order_field="purchase_order",
		party_type="Supplier",
		party_field="supplier",
		party_account="credit_to",
		item_account="expense_account",
		company_account="custom_purchase_dp_account",
	),
}

TOLERANCE = 0.005


# ---------------------------------------------------------------------------------------------
# Invoice DP
# ---------------------------------------------------------------------------------------------


def set_dp_invoice(doc, method=None):
	"""Hook `before_validate` SI/PI: invoice DP -> satu baris Item DP senilai term DP-nya.

	Dihitung ulang tiap draft disimpan, jadi kalau term atau order-nya diganti, nilainya ikut.
	"""
	if doc.docstatus != 0 or not doc.get("custom_is_dp"):
		return

	side = SIDES[doc.doctype]

	if doc.get("is_return"):
		frappe.throw(_("A return invoice cannot be a DP Invoice."))
	if doc.get("is_pos") or doc.get("is_paid"):
		frappe.throw(_("A DP Invoice cannot be paid inside the invoice. Pay it with a Payment Entry."))

	if not doc.get("custom_dp_order"):
		doc.custom_dp_order = next(
			(row.get(side.order_field) for row in doc.get("items") or [] if row.get(side.order_field)), None
		)
	if not doc.custom_dp_order:
		frappe.throw(_("Select the {0} this DP is for.").format(_(side.order_doctype)))

	order = frappe.get_doc(side.order_doctype, doc.custom_dp_order)
	validate_order(doc, order, side)

	term = get_term_row(order, doc.get("custom_dp_term"))
	# persen awalnya dari term, tapi boleh diubah user - yang dipakai isian di dokumen
	if not flt(doc.get("custom_dp_percentage")):
		doc.custom_dp_percentage = term.invoice_portion
	percent = flt(doc.custom_dp_percentage)
	if percent <= 0 or percent > 100:
		frappe.throw(_("DP Percentage must be more than 0 and at most 100."))

	amount = flt(flt(order.net_total) * percent / 100, doc.precision("net_total"))
	settings = get_dp_settings(doc.company, side)
	item = frappe.get_cached_doc("Item", settings.item)

	doc.set("items", [])
	doc.append(
		"items",
		{
			"item_code": item.name,
			"item_name": item.item_name,
			"description": _("Down Payment {0}% for {1}").format(
				frappe.format(percent, {"fieldtype": "Float"}), order.name
			),
			"qty": 1,
			"uom": item.stock_uom,
			"stock_uom": item.stock_uom,
			"conversion_factor": 1,
			"price_list_rate": 0,
			"discount_percentage": 0,
			"discount_amount": 0,
			"rate": amount,
			side.item_account: settings.account,
			"cost_center": get_order_cost_center(order) or doc.get("cost_center"),
			# kategori PPh baris ini diisi kayak ERPNext ngisi baris item biasa (master Item dulu,
			# lalu master party), biar PPh bawaan ikut jalan di invoice DP
			"tax_withholding_category": get_withholding_category(item, doc, side),
			# default field ini 1, tapi baris yang ditambah dari server gak dapet default-nya
			"apply_tds": 1,
		},
	)

	# satu tagihan, jatuh tempo sesuai tanggal invoice - termin order gak berlaku di sini
	doc.payment_terms_template = None
	doc.set("payment_schedule", [])
	doc.set("custom_dp_allocations", [])
	doc.custom_total_dp_allocated = 0
	if doc.meta.has_field("update_stock"):
		doc.update_stock = 0

	validate_dp_total(doc, order, term, amount)


def validate_order(doc, order, side):
	if order.docstatus != 1:
		frappe.throw(_("{0} {1} must be submitted.").format(_(side.order_doctype), order.name))
	if order.company != doc.company:
		frappe.throw(_("{0} {1} belongs to another company.").format(_(side.order_doctype), order.name))
	if order.get(side.party_field) != doc.get(side.party_field):
		frappe.throw(
			_("{0} {1} is for {2}, not {3}.").format(
				_(side.order_doctype), order.name, order.get(side.party_field), doc.get(side.party_field)
			)
		)
	if order.currency != doc.currency:
		frappe.throw(_("The DP Invoice must use the same currency as {0}.").format(order.name))


def get_term_row(order, term):
	"""Baris Payment Schedule order dari isian DP Term (`"<no>. ..."`)."""
	match = re.match(r"\s*(\d+)\.", term or "")
	if not match:
		frappe.throw(_("Select the DP Term from the Payment Schedule of {0}.").format(order.name))

	idx = int(match.group(1))
	row = next((row for row in order.get("payment_schedule") or [] if row.idx == idx), None)
	if not row:
		frappe.throw(_("{0} has no Payment Schedule row #{1}.").format(order.name, idx))

	return row


def get_term_label(row):
	name = row.payment_term or row.description or _("Term")
	return f"{row.idx}. {name} ({flt(row.invoice_portion):g}%)"


def validate_dp_total(doc, order, term, amount):
	"""Satu term cuma boleh di-DP sekali, dan total DP gak boleh lewat Net Total order."""
	others = get_dp_invoices(doc.doctype, order.name, exclude=doc.name)

	for other in others:
		if get_term_index(other.custom_dp_term) == term.idx:
			frappe.throw(
				_("DP Term {0} of {1} is already billed in {2}.").format(
					frappe.bold(get_term_label(term)), order.name, get_link(doc.doctype, other.name)
				),
				title=_("DP Term Already Billed"),
			)

	billed = sum(flt(other.net_total) for other in others)
	if billed + amount > flt(order.net_total) + TOLERANCE:
		frappe.throw(
			_("Total DP for {0} would be {1}, more than its Net Total {2}.").format(
				order.name,
				frappe.format(billed + amount, {"fieldtype": "Currency", "options": doc.currency}),
				frappe.format(order.net_total, {"fieldtype": "Currency", "options": doc.currency}),
			)
		)


def get_term_index(term):
	match = re.match(r"\s*(\d+)\.", term or "")
	return int(match.group(1)) if match else None


def get_dp_invoices(doctype, order, exclude=None, submitted_only=False):
	filters = {
		"custom_is_dp": 1,
		"custom_dp_order": order,
		"docstatus": 1 if submitted_only else ["<", 2],
	}
	if exclude:
		filters["name"] = ["!=", exclude]

	return frappe.get_all(
		doctype,
		filters=filters,
		fields=["name", "posting_date", "custom_dp_term", "net_total", "base_net_total"],
		order_by="posting_date asc, creation asc",
	)


def get_dp_settings(company, side):
	values = frappe.get_cached_value("Company", company, ["custom_dp_item", side.company_account], as_dict=True)
	item, account = values.custom_dp_item, values.get(side.company_account)

	if not (item and account):
		frappe.throw(
			_("Set the DP Item and the {0} account in Company {1} (section DP Invoice) first.").format(
				_("Uang Muka Penjualan") if side.company_account == "custom_sales_dp_account" else _("Uang Muka Pembelian"),
				frappe.bold(company),
			),
			title=_("DP Invoice Not Set Up"),
		)

	if frappe.get_cached_value("Item", item, "is_stock_item"):
		frappe.throw(_("DP Item {0} must not be a stock item.").format(frappe.bold(item)))

	return frappe._dict(item=item, account=account)


def get_withholding_category(item, doc, side):
	field = "sales_tax_withholding_category" if side.party_type == "Customer" else "purchase_tax_withholding_category"
	return item.get(field) or frappe.get_cached_value(
		side.party_type, doc.get(side.party_field), "tax_withholding_category"
	)


def get_order_cost_center(order):
	return next((row.cost_center for row in order.get("items") or [] if row.get("cost_center")), None)


@frappe.whitelist()
def get_dp_terms(order_doctype, order, invoice=None):
	"""Pilihan DP Term buat form: baris Payment Schedule order + tanda yang udah di-DP."""
	if order_doctype not in ("Sales Order", "Purchase Order"):
		frappe.throw(_("Invalid order type."))

	order_doc = frappe.get_doc(order_doctype, order)
	order_doc.check_permission("read")

	invoice_doctype = "Sales Invoice" if order_doctype == "Sales Order" else "Purchase Invoice"
	used = {
		get_term_index(row.custom_dp_term): row.name
		for row in get_dp_invoices(invoice_doctype, order, exclude=invoice)
	}

	return [
		{
			"label": get_term_label(row),
			"portion": flt(row.invoice_portion),
			"amount": flt(flt(order_doc.net_total) * flt(row.invoice_portion) / 100),
			"used_in": used.get(row.idx),
		}
		for row in order_doc.get("payment_schedule") or []
	]


def block_cancel_of_used_dp(doc, method=None):
	"""Hook `before_cancel`: invoice DP yang udah dibalik di invoice progress gak boleh dicancel."""
	if not doc.get("custom_is_dp"):
		return

	used_in = get_progress_invoices_using(doc.doctype, doc.name)
	if used_in:
		frappe.throw(
			_("DP Invoice {0} is already applied in {1}. Cancel those invoices first.").format(
				doc.name, ", ".join(get_link(doc.doctype, name) for name in used_in)
			),
			title=_("DP Invoice In Use"),
		)


# ---------------------------------------------------------------------------------------------
# Invoice progress: tarik DP, balik lewat Reverse Journal
# ---------------------------------------------------------------------------------------------


@frappe.whitelist()
def get_dp_allocations(doc):
	"""Tombol *Get DP Invoices*: DP Invoice dari order yang sama, dengan porsi default-nya."""
	if isinstance(doc, str):
		doc = json.loads(doc)
	if isinstance(doc, dict):
		doc = frappe.get_doc(doc)

	if doc.doctype not in SIDES:
		frappe.throw(_("Invalid invoice type."))
	doc.check_permission("write" if not doc.is_new() else "create")

	# invoice progress: rate di form belum dikali Progress Percentage (baru dikali waktu disimpan),
	# jadi dihitung dulu di memori biar porsi DP-nya ngikut nilai yang beneran ditagih
	if doc.doctype == "Sales Invoice" and doc.get("custom_is_progress") and doc.docstatus == 0:
		from vic_addon.vic.retention import preview_progress_rates

		preview_progress_rates(doc)

	return get_default_allocations(doc)


def get_default_allocations(doc):
	side = SIDES[doc.doctype]
	if doc.get("custom_is_dp"):
		return []

	orders = []
	for item in doc.get("items") or []:
		order = item.get(side.order_field)
		if order and order not in orders:
			orders.append(order)
	# invoice retensi gak punya baris yang nempel ke SO - order-nya di header
	if doc.get("custom_is_retention") and doc.get("custom_dp_order") and doc.custom_dp_order not in orders:
		orders.append(doc.custom_dp_order)

	rows = []
	for order in orders:
		dp_invoices = [
			dp
			for dp in get_dp_invoices(doc.doctype, order, submitted_only=True)
			if is_same_party(doc, dp.name, side)
		]
		if not dp_invoices:
			continue

		order_net = flt(frappe.db.get_value(side.order_doctype, order, "base_net_total"))
		this_net = sum(get_row_base_net(doc, item) for item in doc.items if item.get(side.order_field) == order)
		billed_before = get_billed_before(doc, order, side)
		total_dp = sum(flt(dp.base_net_total) for dp in dp_invoices)

		# invoice yang ngelunasin order ngambil semua sisa DP, biar gak ada sisa receh nyangkut
		closes_order = billed_before + this_net >= order_net - TOLERANCE
		target = None if closes_order or not order_net else total_dp * this_net / order_net

		for dp in dp_invoices:
			available = flt(dp.base_net_total) - get_allocated_elsewhere(doc.doctype, dp.name, doc.name)
			if available <= TOLERANCE:
				continue

			allocated = available if target is None else min(available, target)
			if target is not None:
				target -= allocated
			if allocated <= TOLERANCE:
				continue

			rows.append(
				{
					"dp_invoice_type": doc.doctype,
					"dp_invoice": dp.name,
					"order": order,
					"posting_date": dp.posting_date,
					"dp_amount": flt(dp.base_net_total),
					"available_amount": flt(available, 2),
					"allocated_amount": flt(allocated, 2),
				}
			)

	for row in rows:
		row.update(compute_row_totals(row["dp_invoice"], doc.doctype, row["allocated_amount"]))

	return rows


def get_row_base_net(doc, item):
	"""DPP baris (mata uang perusahaan). Dokumen baru di form bisa belum ngitung `base_net_amount`
	(masih 0) - kalau gitu dihitung dari qty x rate, biar porsi DP-nya gak kebaca nol."""
	if flt(item.get("base_net_amount")):
		return flt(item.base_net_amount)
	rate = flt(item.get("net_rate")) or flt(item.get("rate"))
	return flt(item.get("qty")) * rate * (flt(doc.get("conversion_rate")) or 1)


def is_same_party(doc, dp_invoice, side):
	values = frappe.db.get_value(doc.doctype, dp_invoice, [side.party_field, "company"], as_dict=True)
	return values.get(side.party_field) == doc.get(side.party_field) and values.company == doc.company


def get_billed_before(doc, order, side):
	"""DPP order ini yang udah ditagih invoice progress lain yang submitted."""
	item = frappe.qb.DocType(f"{doc.doctype} Item")
	parent = frappe.qb.DocType(doc.doctype)

	total = (
		frappe.qb.from_(item)
		.inner_join(parent)
		.on(parent.name == item.parent)
		.select(Sum(item.base_net_amount))
		.where(
			(item[side.order_field] == order)
			& (parent.docstatus == 1)
			& (parent.custom_is_dp == 0)
			& (parent.is_return == 0)
			& (parent.name != (doc.name or ""))
		)
	).run()

	return flt(total[0][0]) if total else 0


def get_allocated_elsewhere(doctype, dp_invoice, exclude=None):
	"""DPP DP ini yang udah dibalik di invoice progress lain yang submitted."""
	allocation = frappe.qb.DocType("DP Allocation")
	parent = frappe.qb.DocType(doctype)

	query = (
		frappe.qb.from_(allocation)
		.inner_join(parent)
		.on(parent.name == allocation.parent)
		.select(Sum(allocation.allocated_amount))
		.where(
			(allocation.parenttype == doctype)
			& (allocation.dp_invoice == dp_invoice)
			& (parent.docstatus == 1)
		)
	)
	if exclude:
		query = query.where(parent.name != exclude)

	total = query.run()
	return flt(total[0][0]) if total else 0


def get_progress_invoices_using(doctype, dp_invoice):
	allocation = frappe.qb.DocType("DP Allocation")
	parent = frappe.qb.DocType(doctype)

	return [
		row[0]
		for row in (
			frappe.qb.from_(allocation)
			.inner_join(parent)
			.on(parent.name == allocation.parent)
			.select(parent.name)
			.distinct()
			.where(
				(allocation.parenttype == doctype)
				& (allocation.dp_invoice == dp_invoice)
				& (parent.docstatus == 1)
			)
		).run()
	]


def get_dp_gl_lines(doctype, dp_invoice):
	"""Baris GL invoice DP selain piutang/hutang-nya: `[(akun, cost center, debit - credit)]`
	plus total DPP-nya (base)."""
	rows = frappe.get_all(
		"GL Entry",
		filters={
			"voucher_type": doctype,
			"voucher_no": dp_invoice,
			"is_cancelled": 0,
			"party": ["is", "not set"],
		},
		fields=["account", "cost_center", "debit", "credit"],
	)
	return [(row.account, row.cost_center, flt(row.debit) - flt(row.credit)) for row in rows]


def compute_row_totals(dp_invoice, doctype, allocated):
	"""Pajak & total yang dibalik buat satu baris: bagian GL invoice DP sebanding Allocated."""
	dp_net = flt(frappe.db.get_value(doctype, dp_invoice, "base_net_total"))
	if not dp_net:
		return {"tax_amount": 0, "total_amount": 0}

	ratio = flt(allocated) / dp_net
	# baris GL non-party itu sisi lawan piutang/hutang; jumlahnya = total tagihan DP (bertanda)
	total = abs(sum(value for _account, _cc, value in get_dp_gl_lines(doctype, dp_invoice))) * ratio
	total = flt(total, 2)

	return {"tax_amount": flt(total - flt(allocated), 2), "total_amount": total}


def validate_dp_allocations(doc, method=None):
	"""Hook `validate` SI/PI progress: cek & hitung ulang tabel DP Allocations."""
	side = SIDES[doc.doctype]

	if doc.get("custom_is_dp") or doc.get("is_return"):
		doc.set("custom_dp_allocations", [])
		doc.custom_total_dp_allocated = 0
		return

	rows = [row for row in doc.get("custom_dp_allocations") or [] if flt(row.allocated_amount) > TOLERANCE]
	if len(rows) != len(doc.get("custom_dp_allocations") or []):
		doc.set("custom_dp_allocations", rows)

	if rows:
		validate_currency(doc, side)

	seen = set()
	for row in rows:
		if row.dp_invoice in seen:
			frappe.throw(_("Row #{0}: DP Invoice {1} is listed twice.").format(row.idx, row.dp_invoice))
		seen.add(row.dp_invoice)

		dp = frappe.db.get_value(
			doc.doctype,
			row.dp_invoice,
			["docstatus", "custom_is_dp", "custom_dp_order", "company", side.party_field, "posting_date", "base_net_total"],
			as_dict=True,
		)
		if not dp or dp.docstatus != 1 or not dp.custom_is_dp:
			frappe.throw(_("Row #{0}: {1} is not a submitted DP Invoice.").format(row.idx, row.dp_invoice))
		if dp.company != doc.company or dp.get(side.party_field) != doc.get(side.party_field):
			frappe.throw(
				_("Row #{0}: DP Invoice {1} belongs to another {2} or company.").format(
					row.idx, row.dp_invoice, _(side.party_type)
				)
			)

		available = flt(dp.base_net_total) - get_allocated_elsewhere(doc.doctype, row.dp_invoice, doc.name)
		row.dp_invoice_type = doc.doctype
		row.order = dp.custom_dp_order
		row.posting_date = dp.posting_date
		row.dp_amount = flt(dp.base_net_total)
		row.available_amount = flt(available, 2)

		if flt(row.allocated_amount) > available + TOLERANCE:
			frappe.throw(
				_("Row #{0}: Allocated {1} is more than the available DP {2} of {3}.").format(
					row.idx, flt(row.allocated_amount), flt(available, 2), row.dp_invoice
				),
				title=_("DP Over Allocated"),
			)

		row.update(compute_row_totals(row.dp_invoice, doc.doctype, row.allocated_amount))

	doc.custom_total_dp_allocated = flt(sum(flt(row.total_amount) for row in rows), 2)

	invoice_total = flt(doc.get("base_rounded_total") or doc.base_grand_total)
	if doc.custom_total_dp_allocated > invoice_total + TOLERANCE:
		frappe.throw(
			_("Total DP reversed ({0}) is more than this invoice's total ({1}).").format(
				doc.custom_total_dp_allocated, invoice_total
			),
			title=_("DP Over Allocated"),
		)


def validate_currency(doc, side):
	company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
	account_currency = frappe.get_cached_value("Account", doc.get(side.party_account), "account_currency")

	if doc.currency != company_currency or (account_currency and account_currency != company_currency):
		frappe.throw(
			_("DP reversal only supports invoices in the company currency ({0}) for now.").format(
				company_currency
			)
		)


def make_reverse_journal(doc, method=None):
	"""Hook `on_submit` SI/PI progress: bikin & submit Reverse Journal DP-nya."""
	rows = [row for row in doc.get("custom_dp_allocations") or [] if flt(row.allocated_amount) > TOLERANCE]
	if doc.get("custom_is_dp") or not rows:
		return

	side = SIDES[doc.doctype]
	lines = {}

	for row in rows:
		dp_net = flt(frappe.db.get_value(doc.doctype, row.dp_invoice, "base_net_total"))
		if not dp_net:
			continue

		ratio = flt(row.allocated_amount) / dp_net
		for account, cost_center, value in get_dp_gl_lines(doc.doctype, row.dp_invoice):
			key = (account, cost_center)
			# dibalik: yang dulu dikredit sekarang didebit, dan sebaliknya
			lines[key] = lines.get(key, 0) - value * ratio

	accounts = []
	for (account, cost_center), value in lines.items():
		value = flt(value, 2)
		if not value:
			continue

		accounts.append(
			{
				"account": account,
				"cost_center": cost_center,
				"debit_in_account_currency": value if value > 0 else 0,
				"credit_in_account_currency": -value if value < 0 else 0,
			}
		)

	if not accounts:
		return

	# baris piutang/hutang nyeimbangin, nempel ke invoice progress biar tagihannya berkurang
	party_value = -flt(sum(row["debit_in_account_currency"] - row["credit_in_account_currency"] for row in accounts), 2)
	accounts.append(
		{
			"account": doc.get(side.party_account),
			"party_type": side.party_type,
			"party": doc.get(side.party_field),
			"reference_type": doc.doctype,
			"reference_name": doc.name,
			"cost_center": doc.get("cost_center") or frappe.get_cached_value("Company", doc.company, "cost_center"),
			"debit_in_account_currency": party_value if party_value > 0 else 0,
			"credit_in_account_currency": -party_value if party_value < 0 else 0,
		}
	)

	journal = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"company": doc.company,
			"posting_date": doc.posting_date,
			"user_remark": _("Reverse DP {0} against {1}").format(
				", ".join(row.dp_invoice for row in rows), doc.name
			),
			"custom_dp_invoice_type": doc.doctype,
			"custom_dp_invoice": doc.name,
			"accounts": accounts,
		}
	)
	journal.flags.ignore_permissions = True
	journal.insert()
	journal.submit()

	frappe.msgprint(
		_("DP reversed through {0}.").format(get_link("Journal Entry", journal.name)),
		indicator="green",
		alert=True,
	)


def cancel_reverse_journal(doc, method=None):
	"""Hook `before_cancel` SI/PI progress: Reverse Journal-nya dicancel duluan.

	Harus sebelum cancel invoice-nya sendiri - jurnal itu nempel ke invoice ini, dan Frappe nolak
	cancel dokumen yang masih dirujuk dokumen submitted lain.
	"""
	for name in frappe.get_all(
		"Journal Entry",
		filters={"custom_dp_invoice_type": doc.doctype, "custom_dp_invoice": doc.name, "docstatus": 1},
		pluck="name",
	):
		journal = frappe.get_doc("Journal Entry", name)
		journal.flags.ignore_permissions = True
		journal.cancel()


def get_link(doctype, name):
	return frappe.utils.get_link_to_form(doctype, name)
