"""Batalin perampingan form Purchase Receipt: munculin lagi semua field harga yang disembunyiin.

Dulu Purchase Receipt dirampingin biar cuma nunjukin barang + qty - section Currency, Totals, Taxes,
Pricing Rules, Accounting Dimensions, plus Rate/Amount di baris item, disembunyiin lewat property
setter `hidden`. Fitur itu dibatalin, jadi property setter-nya dihapus (fixtures cuma nambah/ngubah,
gak pernah ngehapus - makanya lewat patch) dan form-nya balik ke standar ERPNext. Re-hide di JS juga
udah dicopot (`public/js/purchase_receipt.js`).
"""

import frappe

NAMES = (
	"Purchase Receipt-accounting_dimensions_section-hidden",
	"Purchase Receipt-currency_and_price_list-hidden",
	"Purchase Receipt-base_total-hidden",
	"Purchase Receipt-total-hidden",
	"Purchase Receipt-net_total-hidden",
	"Purchase Receipt-taxes_charges_section-hidden",
	"Purchase Receipt-taxes_section-hidden",
	"Purchase Receipt-totals-hidden",
	"Purchase Receipt-totals_section-hidden",
	"Purchase Receipt-base_totals_section-hidden",
	"Purchase Receipt-section_break_42-hidden",
	"Purchase Receipt-sec_tax_breakup-hidden",
	"Purchase Receipt-pricing_rule_details-hidden",
	"Purchase Receipt Item-rate_and_amount-hidden",
	"Purchase Receipt Item-discount_and_margin_section-hidden",
	"Purchase Receipt Item-sec_break1-hidden",
	"Purchase Receipt Item-section_break_29-hidden",
	"Purchase Receipt Item-accounting_dimensions_section-hidden",
	"Purchase Receipt Item-rate-hidden",
	"Purchase Receipt Item-amount-hidden",
)


def execute():
	deleted = False
	for name in NAMES:
		if frappe.db.exists("Property Setter", name):
			frappe.db.delete("Property Setter", name)
			deleted = True

	if deleted:
		frappe.clear_cache(doctype="Purchase Receipt")
		frappe.clear_cache(doctype="Purchase Receipt Item")
