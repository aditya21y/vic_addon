"""Customer ngalir dari Opportunity sampai ke Quotation.

Rantainya: Opportunity -> Request for Quotation -> Supplier Quotation -> Costing -> Quotation
-> Sales Order. Yang di tengah itu dokumen ke supplier, jadi bawaan ERPNext gak nyimpen
customer sama sekali - padahal yang dicariin harga itu kebutuhan customer tertentu.

Dua sambungan yang diurus di sini:

1. **Opportunity -> RFQ.** Mapper bawaan nyalin nama Opportunity ke tiap baris item RFQ
   (`opportunity`), jadi customer-nya dibaca balik dari situ. Field-nya beda nama (`party_name`
   di Opportunity, `custom_customer` di RFQ) dan Opportunity bisa juga milik Lead, makanya gak
   bisa ngandelin penyalinan field senama.

2. **RFQ -> Costing.** Costing gak nyimpen nomor RFQ; yang kesimpan link ke baris Supplier
   Quotation, dan dari situ nomor RFQ-nya kebaca.

Sambungan sisanya udah jalan sendiri: Costing -> Quotation lewat `make_quotation`, terus
Quotation -> Sales Order lewat mapper bawaan.

Dua-duanya cuma ngisi kalau field-nya masih kosong, jadi pilihan user gak pernah ketiban.
"""

import frappe


def set_customer_from_opportunity(doc, method=None):
	"""Hook `validate` Request for Quotation: isi Customer dari Opportunity asalnya."""
	if doc.get("custom_customer"):
		return

	opportunities = {item.opportunity for item in doc.get("items") or [] if item.get("opportunity")}

	customer = get_customer_of_opportunities(opportunities)
	if customer:
		doc.custom_customer = customer


@frappe.whitelist()
def get_customer_of_opportunities(opportunities):
	"""Customer dari sekumpulan Opportunity, `None` kalau gak ada yang punya.

	Dipanggil juga dari form (lihat `public/js/request_for_quotation.js`): waktu item ditarik
	lewat `Get Items From > Opportunity`, dokumennya belum disimpan - jadi kalau cuma ngandelin
	hook `validate`, kolom Customer-nya baru keisi setelah user nge-save. Di sini diisi duluan
	biar langsung kelihatan.
	"""
	if isinstance(opportunities, str):
		opportunities = frappe.parse_json(opportunities)

	for name in sorted(set(opportunities or [])):
		opportunity = frappe.db.get_value(
			"Opportunity", name, ["opportunity_from", "party_name"], as_dict=True
		)
		# Opportunity bisa punya Lead, dan Lead belum jadi Customer - itu dilewat
		if opportunity and opportunity.opportunity_from == "Customer" and opportunity.party_name:
			return opportunity.party_name

	return None


@frappe.whitelist()
def make_request_for_quotation(source_name, target_doc=None):
	"""Tombol `Create > Inquiry` di Opportunity.

	Sama kayak versi ERPNext, cuma Customer-nya langsung diisi di dokumen yang dibalikin - jadi
	udah kelihatan di form sebelum disimpan. Kalau cuma ngandelin hook `validate`, kolomnya baru
	keisi setelah user nge-save, dan itu yang bikin kelihatan kayak gak jalan.

	Customernya dibaca dari Opportunity-nya langsung, bukan dari baris item - jadi tetap keisi
	walaupun itemnya belum ada atau dihapus lagi di Inquiry-nya.
	"""
	from erpnext.crm.doctype.opportunity.opportunity import (
		make_request_for_quotation as make_erpnext_request_for_quotation,
	)

	doc = make_erpnext_request_for_quotation(source_name, target_doc)

	customer = get_customer_of_opportunities([source_name])
	if customer and not doc.get("custom_customer"):
		doc.custom_customer = customer

	return doc


def set_customer_from_request_for_quotation(doc, method=None):
	"""Hook `validate` Costing: isi Customer dari RFQ di balik penawaran suppliernya."""
	if doc.get("customer"):
		return

	from vic_addon.vic.doctype.costing.costing import get_request_for_quotations

	for name in get_request_for_quotations(doc):
		customer = frappe.db.get_value("Request for Quotation", name, "custom_customer")
		if customer:
			doc.customer = customer
			return
