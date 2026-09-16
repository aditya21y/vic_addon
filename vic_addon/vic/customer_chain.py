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
	if not opportunities:
		return

	for name in sorted(opportunities):
		opportunity = frappe.db.get_value(
			"Opportunity", name, ["opportunity_from", "party_name"], as_dict=True
		)
		# Opportunity bisa punya Lead, dan Lead belum jadi Customer - itu dilewat
		if opportunity and opportunity.opportunity_from == "Customer" and opportunity.party_name:
			doc.custom_customer = opportunity.party_name
			return


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
