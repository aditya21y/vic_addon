"""Purchase Invoice: Supplier Invoice No & Date bisa diubah setelah submit, dan Target Grand Total.

Nomor & tanggal tagihan supplier sering baru dateng setelah invoice-nya disubmit (dicetak di
Receipt Note buat tukar faktur), jadi dua field itu dibikin Allow on Submit lewat property setter.

**Target Grand Total**: tagihan supplier sering beda dikit sama hitungan PI (pembulatan di pihak
supplier). Isi Grand Total di tagihannya, waktu disimpan rate tiap item disesuaikan biar Net Total +
pajak = angka itu. Karena yang berubah rate item (`base_net_amount`), selisihnya kebawa ke Purchase
Receipt & COGS Delivery Note-nya kalau *Set Landed Cost Based on Purchase Invoice Rate* di Buying
Settings nyala - alurnya DN & PR udah ada duluan, PI belakangan.
"""

import frappe
from frappe import _
from frappe.utils import flt

TARGET_FIELD = "custom_target_grand_total"

# batas langkah penyesuaian sen per simpan - jaga-jaga, normalnya beres jauh sebelum ini
MAX_NUDGES = 200


def validate_supplier_invoice_after_submit(doc, method=None):
	"""Hook `before_update_after_submit`: Supplier Invoice No yang diganti tetap dicek gak dobel.

	Cek bawaan ERPNext (`validate_supplier_invoice`, kalau *Check Supplier Invoice Number
	Uniqueness* nyala di Accounts Settings) cuma jalan waktu validate, yang gak kepanggil di update
	setelah submit.
	"""
	before = doc.get_doc_before_save()
	if before and before.bill_no == doc.bill_no:
		return

	doc.validate_supplier_invoice()


def apply_target_grand_total(doc, method=None):
	"""Hook `before_validate` Purchase Invoice: rate item disesuaikan ke Target Grand Total.

	1. Semua rate diskalain proporsional. Pajak persentase ikut naik-turun sebanding, pajak
	   nominal tetap (`Actual`) dianggap tetap - jadi faktornya (target - tetap) / (sekarang - tetap).
	2. Sisa sen (rate dibulatin ke presisi mata uang) dikejar dengan geser rate 0,01 per langkah,
	   mulai dari baris yang qty-nya paling kecil (langkahnya paling halus).
	3. Kalau tetap gak bisa pas (pembulatan pajak kadang ngelompat 0,02), dikasih tahu selisihnya.

	Cuma draft & bukan retur. Selama field-nya keisi, tiap simpan rate-nya disesuaiin lagi (mis.
	qty diubah); kosongin field-nya buat berhenti.
	"""
	target = flt(doc.get(TARGET_FIELD))
	if doc.docstatus != 0 or doc.get("is_return") or not target:
		return

	items = [item for item in doc.get("items") or [] if flt(item.qty)]
	if not items:
		return

	precision = doc.precision("grand_total")
	doc.calculate_taxes_and_totals()

	fixed = sum(
		flt(tax.tax_amount) * (-1 if tax.add_deduct_tax == "Deduct" else 1)
		for tax in doc.get("taxes") or []
		if tax.charge_type == "Actual"
	)
	for _round in range(3):
		current = flt(doc.grand_total)
		if abs(current - target) < 0.5 / 10**precision or not flt(current - fixed):
			break
		factor = (target - fixed) / (current - fixed)
		for item in items:
			item.rate = flt(flt(item.rate) * factor, item.precision("rate"))
		doc.calculate_taxes_and_totals()

	nudge_to_target(doc, items, target, precision)

	difference = flt(target - flt(doc.grand_total), precision)
	if difference:
		frappe.msgprint(
			_("Item rates were adjusted, but Grand Total is still {0} away from Target Grand Total {1} because of tax rounding. Adjust one item rate manually if it must match exactly.").format(
				frappe.bold(frappe.format(difference, {"fieldtype": "Currency", "options": doc.currency})),
				frappe.format(target, {"fieldtype": "Currency", "options": doc.currency}),
			),
			title=_("Target Grand Total"),
			indicator="orange",
		)


def nudge_to_target(doc, items, target, precision):
	"""Geser rate satu baris 0,01 per langkah selama Grand Total-nya makin deket ke target."""
	by_qty = sorted(items, key=lambda item: flt(item.qty))
	gap = abs(target - flt(doc.grand_total))

	for _step in range(MAX_NUDGES):
		if gap < 0.5 / 10**precision:
			return

		direction = 1 if target > flt(doc.grand_total) else -1
		improved = False
		for item in by_qty:
			step = direction / 10 ** item.precision("rate")
			if flt(item.rate) + step <= 0:
				continue

			item.rate = flt(flt(item.rate) + step, item.precision("rate"))
			doc.calculate_taxes_and_totals()
			new_gap = abs(target - flt(doc.grand_total))
			if new_gap < gap:
				gap = new_gap
				improved = True
				break

			item.rate = flt(flt(item.rate) - step, item.precision("rate"))
			doc.calculate_taxes_and_totals()

		if not improved:
			return


class TargetGrandTotalMixin:
	"""Mixin controller Purchase Invoice (hook `extend_doctype_class`).

	*Maintain Same Rate Throughout the Purchase Cycle* (Buying Settings) nolak rate PI yang beda dari
	PO/PR. Invoice yang Target Grand Total-nya diisi justru sengaja beda rate-nya, jadi cek itu
	dilewatin cuma buat invoice tersebut - invoice lain tetap dicek kayak biasa.
	"""

	def validate_rate_with_reference_doc(self, ref_details):
		if flt(self.get(TARGET_FIELD)) and not self.get("is_return"):
			return

		return super().validate_rate_with_reference_doc(ref_details)
