"""DP Invoice: Payment Request yang dipakai buat invoice uang muka (DP).

Alur: PO/SO -> Payment Request (DP Invoice) -> Payment Entry (DP) -> Invoice final.

Payment Request-nya nyimpen nilai DP (persentase atau amount) plus tabel PPN/PPh atas DP.
Dokumen ini gak posting jurnal; jurnalnya baru kebentuk di Payment Entry, makanya tabel
pajaknya dibawa otomatis ke Payment Entry.
"""

import frappe
from frappe import _
from frappe.utils import flt

# dokumen referensi -> jenis DP
DP_TYPE_BY_REFERENCE = {
	"Sales Order": "Sales",
	"Sales Invoice": "Sales",
	"POS Invoice": "Sales",
	"Purchase Order": "Purchase",
	"Purchase Invoice": "Purchase",
}

TAX_FIELDS_TO_COPY = (
	"charge_type",
	"account_head",
	"description",
	"rate",
	"row_id",
	"add_deduct_tax",
	"included_in_paid_amount",
	"cost_center",
)


def sync_payment_reference(doc, method=None):
	"""Hook `before_validate`: samain tabel Payment Reference sama DP Amount.

	Kalau dokumen referensinya punya payment terms, ERPNext ngisi tabel Payment Reference
	dan maksa totalnya sama persis dengan DP Amount ("Grand Total must match sum of Payment
	References"). Tabel itu read only di form, jadi begitu DP Amount diubah lewat DP
	Percentage, barisnya kita sesuaikan di sini - sebelum validasi ERPNext jalan.
	"""
	rows = doc.get("payment_reference") or []
	if not rows:
		return

	precision = doc.precision("grand_total")
	grand_total = flt(doc.grand_total, precision)
	total_reference = flt(sum(flt(row.amount) for row in rows), precision)

	if total_reference == grand_total or not total_reference:
		return

	if len(rows) == 1:
		rows[0].amount = grand_total
		return

	# lebih dari satu termin: diprorata sesuai bobot awal tiap baris
	allocated = 0.0
	for row in rows[:-1]:
		row.amount = flt(grand_total * flt(row.amount) / total_reference, precision)
		allocated += row.amount

	rows[-1].amount = flt(grand_total - allocated, precision)


def set_dp_details(doc, method=None):
	"""Hook `validate` Payment Request: jenis DP, persentase, dan total pajaknya."""
	set_dp_type(doc)
	set_dp_percentage(doc)
	calculate_taxes(doc)
	validate_dp_amount(doc)
	warn_if_different_from_payment_term(doc)


def validate_dp_amount(doc):
	"""Total DP gak boleh lebih dari Net Total dokumen referensi.

	DP dihitung dari Net Total (nilai sebelum PPN), jadi batasnya juga Net Total - bukan Grand
	Total kayak pengecekan bawaan ERPNext. Pengecekan bawaan juga dilewatin ERPNext kalau
	dokumen referensinya punya payment terms (`validate_payment_request_amount` langsung return
	begitu tabel Payment Reference keisi), jadi dicek ulang di sini.
	"""
	reference_amount = get_reference_total(doc)
	if not reference_amount:
		return

	already_requested = get_requested_amount(doc)
	precision = doc.precision("grand_total")
	total_requested = flt(already_requested + flt(doc.grand_total), precision)

	if total_requested > flt(reference_amount, precision):
		frappe.throw(
			_(
				"Total DP against {0} {1} would be {2}, more than its Net Total {3} (already requested: {4})."
			).format(
				_(doc.reference_doctype),
				doc.reference_name,
				frappe.format_value(total_requested, {"fieldtype": "Currency"}, doc),
				frappe.format_value(reference_amount, {"fieldtype": "Currency"}, doc),
				frappe.format_value(already_requested, {"fieldtype": "Currency"}, doc),
			),
			title=_("DP Amount Too Big"),
		)


def get_requested_amount(doc):
	"""Total DP yang udah diminta lewat DP Invoice lain atas dokumen referensi yang sama.

	Yang dijumlah nilai DP-nya (`grand_total`), bukan sisa tagihannya kayak hitungan ERPNext -
	DP yang udah dibayar tetap kepakai jatahnya.
	"""
	rows = frappe.get_all(
		"Payment Request",
		filters={
			"reference_doctype": doc.reference_doctype,
			"reference_name": doc.reference_name,
			"docstatus": 1,
			"name": ["!=", doc.name or ""],
		},
		fields=["grand_total"],
	)

	return sum(flt(row.grand_total) for row in rows)


def warn_if_different_from_payment_term(doc):
	"""Kasih tau kalau DP-nya beda dari termin pembayaran di dokumen referensi.

	Gak diblokir - DP hasil nego emang boleh beda - cuma biar selisih yang belum ditagih
	kelihatan, bukan lewat diam-diam.
	"""
	for row in doc.get("payment_reference") or []:
		if not row.payment_schedule:
			continue

		term = frappe.db.get_value(
			"Payment Schedule",
			row.payment_schedule,
			["payment_term", "payment_amount", "due_date"],
			as_dict=True,
		)
		if not term:
			continue

		difference = flt(term.payment_amount) - flt(row.amount)
		if not flt(difference, doc.precision("grand_total")):
			continue

		frappe.msgprint(
			_("DP {0} differs from payment term {1} ({2}). Difference not yet requested: {3}.").format(
				frappe.format_value(flt(row.amount), {"fieldtype": "Currency"}, doc),
				term.payment_term or frappe.format(term.due_date, {"fieldtype": "Date"}),
				frappe.format_value(flt(term.payment_amount), {"fieldtype": "Currency"}, doc),
				frappe.format_value(difference, {"fieldtype": "Currency"}, doc),
			),
			title=_("DP Differs from Payment Term"),
			indicator="blue",
		)


def set_dp_type(doc):
	doc.custom_dp_type = DP_TYPE_BY_REFERENCE.get(doc.reference_doctype) or (
		"Sales" if doc.payment_request_type == "Inward" else "Purchase"
	)


def set_dp_percentage(doc):
	"""Persentase DP dihitung balik dari DP Amount, biar dua angkanya selalu nyambung.

	Di form, ngisi persentase bakal ngisi DP Amount-nya (lihat payment_request.js).
	"""
	reference_total = get_reference_total(doc)

	doc.custom_dp_percentage = (
		flt(flt(doc.grand_total) / reference_total * 100, doc.precision("custom_dp_percentage"))
		if reference_total
		else 0
	)


def get_reference_total(doc):
	"""Nilai dokumen referensi yang jadi dasar DP: Net Total, bukan Grand Total.

	Grand Total udah termasuk PPN, padahal PPN atas DP dicatat sendiri di tabel Advance Taxes
	and Charges. Kalau DP-nya diambil dari Grand Total, PPN-nya keitung dua kali.
	"""
	if not (doc.reference_doctype and doc.reference_name):
		return 0

	fieldname = (
		"net_total" if frappe.get_meta(doc.reference_doctype).has_field("net_total") else "grand_total"
	)

	return flt(frappe.db.get_value(doc.reference_doctype, doc.reference_name, fieldname))


def calculate_taxes(doc):
	"""Hitung PPN/PPh atas nilai DP.

	`On Paid Amount` dihitung dari DP Amount, `Actual` diisi manual. Rumusnya sama kayak
	Payment Entry biar angkanya konsisten waktu dibawa ke sana.
	"""
	total_taxes = 0.0

	for tax in doc.get("custom_taxes") or []:
		if tax.charge_type == "On Paid Amount":
			tax.tax_amount = flt(
				flt(doc.grand_total) * flt(tax.rate) / 100, tax.precision("tax_amount")
			)

		total_taxes += flt(tax.tax_amount) * (-1 if tax.add_deduct_tax == "Deduct" else 1)
		tax.total = flt(flt(doc.grand_total) + total_taxes, tax.precision("total"))

	doc.custom_total_taxes_and_charges = flt(
		total_taxes, doc.precision("custom_total_taxes_and_charges")
	)
	doc.custom_total_payable = flt(
		flt(doc.grand_total) + total_taxes, doc.precision("custom_total_payable")
	)


@frappe.whitelist()
def make_payment_entry(docname):
	"""Tombol `Create Payment Entry` di DP Invoice.

	Sama kayak versi ERPNext, cuma tabel pajaknya langsung diisi supaya kelihatan di form
	Payment Entry sebelum disimpan (dokumennya belum di-insert, jadi hook `before_validate`
	belum jalan di titik ini).
	"""
	doc = frappe.get_doc("Payment Request", docname)
	doc.check_permission("read")

	payment_entry = doc.create_payment_entry(submit=False)
	set_advance_taxes(payment_entry)

	if payment_entry.get("taxes"):
		payment_entry.set_amounts()
		payment_entry.apply_taxes()
		payment_entry.set_amounts_after_tax()

	return payment_entry.as_dict()


def set_advance_taxes(doc, method=None):
	"""Hook `before_validate` Payment Entry: ambil tabel pajak dari DP Invoice-nya.

	Cuma jalan kalau Payment Entry-nya belum punya baris pajak, jadi kalau user udah
	ngedit sendiri gak bakal ketiban.
	"""
	if doc.get("taxes"):
		return

	payment_request = get_payment_request(doc)
	if not payment_request:
		return

	source = frappe.get_doc("Payment Request", payment_request)
	for tax in source.get("custom_taxes") or []:
		doc.append("taxes", {fieldname: tax.get(fieldname) for fieldname in TAX_FIELDS_TO_COPY})

	if doc.get("taxes"):
		template_field = (
			"custom_sales_taxes_and_charges_template"
			if source.custom_dp_type == "Sales"
			else "custom_purchase_taxes_and_charges_template"
		)
		doc.set(template_field.replace("custom_", ""), source.get(template_field))


def get_payment_request(doc):
	for reference in doc.get("references") or []:
		if reference.payment_request:
			return reference.payment_request

	return None
