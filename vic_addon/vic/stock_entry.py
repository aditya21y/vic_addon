"""Repack Percentage: nilai bahan Repack dibagi ke item hasil pakai persentase.

Repack bawaan ERPNext dengan lebih dari satu item hasil maksa semua baris hasil dicentang
"Set Basic Rate Manually" - user ngitung rate tiap hasil sendiri. Kalau gak dicentang, nilai
bahannya dibagi rata per qty, padahal hasil potongan/bongkaran nilainya jarang sebanding sama
qty-nya.

Di sini tiap baris hasil diisi **Repack Percentage** (`custom_repack_percentage`), terus:

	basic amount hasil = total nilai bahan keluar x persentase / 100
	basic rate hasil   = basic amount / qty (stock UOM)

Baris hasil terakhir dapet sisanya (bukan dikali persen lagi), jadi total nilai hasil persis sama
dengan nilai bahan - gak ada selisih pembulatan yang nyasar ke akun Stock Adjustment.

Aturannya: kalau ada satu baris hasil yang diisi persentase, semua baris hasil wajib diisi, dan
totalnya harus 100%. Centangan Set Basic Rate Manually di baris yang pakai persentase dicopot.
Kalau gak ada yang diisi, Repack jalan persis kayak bawaan.

Hitungannya nempel di `set_basic_rate`, jadi ikut kepakai waktu ERPNext ngitung ulang nilai
Stock Entry pas repost valuasi (`stock_ledger.recalculate_amounts_in_stock_entry`) - kalau harga
bahannya berubah karena transaksi mundur, nilai hasilnya ikut nyesuain dengan persentase yang
sama. (Beda sama Set Basic Rate Manually yang rate-nya beku.)
"""

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry


class VICStockEntry(StockEntry):
	def validate_repack_entry(self):
		if not uses_repack_percentage(self):
			return super().validate_repack_entry()

		finished = [row for row in self.items if row.is_finished_item]
		missing = [str(row.idx) for row in finished if flt(row.custom_repack_percentage) <= 0]
		if missing:
			frappe.throw(
				_("Row {0}: fill the Repack Percentage of every finished item, or clear it in all rows.").format(
					", ".join(missing)
				),
				title=_("Repack Percentage"),
			)

		total = sum(flt(row.custom_repack_percentage) for row in finished)
		if abs(total - 100) > 0.001:
			frappe.throw(
				_("Total Repack Percentage of the finished items must be 100%, currently {0}%.").format(
					flt(total, 3)
				),
				title=_("Repack Percentage"),
			)

		# rate-nya dari persentase, bukan diketik
		for row in finished:
			row.set_basic_rate_manually = 0

	def set_basic_rate(self, reset_outgoing_rate=True, raise_error_if_no_rate=True):
		super().set_basic_rate(reset_outgoing_rate, raise_error_if_no_rate)

		if uses_repack_percentage(self):
			apply_repack_percentage(self)


def uses_repack_percentage(doc):
	return doc.purpose == "Repack" and any(
		flt(row.custom_repack_percentage) for row in doc.items if row.is_finished_item
	)


def apply_repack_percentage(doc):
	rows = [row for row in doc.items if row.is_finished_item]
	outgoing_cost = sum(flt(row.basic_amount) for row in doc.items if row.s_warehouse and not row.t_warehouse)

	remaining = outgoing_cost
	for i, row in enumerate(rows):
		if i == len(rows) - 1:
			amount = remaining
		else:
			amount = flt(outgoing_cost * flt(row.custom_repack_percentage) / 100, row.precision("basic_amount"))
			remaining -= amount

		row.basic_amount = flt(amount, row.precision("basic_amount"))
		# rate gak dibulatin, sama kayak bawaan - biar qty x rate balik ke amount-nya
		row.basic_rate = flt(amount) / flt(row.transfer_qty) if flt(row.transfer_qty) else 0
