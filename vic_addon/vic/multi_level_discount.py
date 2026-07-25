"""Diskon bertingkat (multi level) per item untuk Supplier Quotation.

Supplier biasanya kasih diskon bertingkat, misal 10% + 5% + 2%. Diskonnya berantai,
bukan dijumlah:

	net factor = (1 - 10%) x (1 - 5%) x (1 - 2%) = 0.8379
	total diskon = 16.21%, bukan 17%

Hasilnya ditulis ke field standar `discount_percentage` (Discount on Price List Rate)
biar rate, amount, taxes, dan diskon tambahan atas net total tetap dihitung ERPNext.
"""

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.controllers.taxes_and_totals import get_rate_with_margin

MAX_DISCOUNT_LEVELS = 3
DISCOUNT_LEVEL_FIELDS = [f"custom_discount_level_{level}" for level in range(1, MAX_DISCOUNT_LEVELS + 1)]


def get_effective_discount_percentage(levels):
	"""Gabungkan diskon bertingkat jadi satu persentase."""
	net_factor = 1.0
	for level in levels:
		net_factor *= 1 - flt(level) / 100.0

	return (1 - net_factor) * 100.0


def validate_discount_levels(doc, method=None):
	for item in doc.get("items") or []:
		for level, fieldname in enumerate(DISCOUNT_LEVEL_FIELDS, start=1):
			value = flt(item.get(fieldname))
			if value < 0 or value > 100:
				frappe.throw(
					_("Row #{0}: Discount Level {1} must be between 0 and 100").format(item.idx, level)
				)


def apply_multi_level_discount(doc, method=None):
	"""Hitung total diskon bertingkat ke `discount_percentage`.

	Jalan di `before_validate` supaya ERPNext yang menghitung rate dari diskon hasilnya.
	Baris tanpa diskon bertingkat dibiarkan apa adanya, jadi rate masih bisa diisi manual
	seperti standar.
	"""
	for item in doc.get("items") or []:
		levels = [flt(item.get(fieldname)) for fieldname in DISCOUNT_LEVEL_FIELDS]
		if not any(levels) or not flt(item.price_list_rate):
			continue

		item.discount_percentage = flt(
			get_effective_discount_percentage(levels), item.precision("discount_percentage")
		)
		rate_with_margin = flt(get_rate_with_margin(item))
		item.discount_amount = flt(
			rate_with_margin * item.discount_percentage / 100.0, item.precision("discount_amount")
		)
		item.rate = flt(rate_with_margin - item.discount_amount, item.precision("rate"))
