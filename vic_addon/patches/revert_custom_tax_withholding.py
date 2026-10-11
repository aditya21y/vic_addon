"""Balikin PPh ke bawaan ERPNext: buang custom field & property setter PPh versi VIC.

PPh versi VIC (dihitung per item, selalu diakui di Payment Entry, mesin bawaan dimatiin) gak
jadi dipakai. Kodenya udah dicabut; patch ini ngebersihin sisanya di database, karena sinkronisasi
fixture gak pernah ngapus record yang dikeluarin dari file-nya.

Baris PPh versi VIC di Payment Entry **draft** ikut dibuang - kalau dibiarin, baris `Actual`
itu tetap motong waktu PE-nya disubmit, padahal udah gak ada yang ngitung ulang. PE yang udah
submit gak disentuh: jurnalnya udah kebukukan. Kolomnya sendiri dibiarin - Frappe gak ngedrop
kolom - jadi data lama masih kebaca kalau dibutuhin.
"""

import frappe

CUSTOM_FIELDS = (
	"Advance Taxes and Charges-custom_invoice_withholding",
	"Payment Entry Reference-custom_withholding_amount",
	"Payment Entry-custom_apply_invoice_tds",
	"Payment Request-custom_apply_tds",
	"Payment Request-custom_tax_withholding_amount",
)

PROPERTY_SETTERS = (
	"Payment Entry-apply_tds-read_only",
	"Payment Entry-apply_tds-depends_on",
	"Payment Entry-tax_withholding_group-read_only",
	"Payment Entry-ignore_tax_withholding_threshold-hidden",
	"Payment Entry-override_tax_withholding_entries-hidden",
	"Purchase Invoice-apply_tds-read_only",
	"Purchase Invoice-apply_tds-depends_on",
	"Purchase Invoice-tax_withholding_group-read_only",
	"Purchase Invoice-ignore_tax_withholding_threshold-hidden",
	"Purchase Invoice-override_tax_withholding_entries-hidden",
	"Sales Invoice-apply_tds-read_only",
	"Sales Invoice-apply_tds-depends_on",
	"Sales Invoice-tax_withholding_group-read_only",
	"Sales Invoice-ignore_tax_withholding_threshold-hidden",
	"Sales Invoice-override_tax_withholding_entries-hidden",
	"Payment Entry-tax_withholding_category-read_only",
	"Purchase Invoice Item-apply_tds-hidden",
	"Sales Invoice Item-apply_tds-hidden",
)


def execute():
	if frappe.db.has_column("Advance Taxes and Charges", "custom_invoice_withholding"):
		frappe.db.sql(
			"""
			delete tax from `tabAdvance Taxes and Charges` tax
			inner join `tabPayment Entry` payment on payment.name = tax.parent
			where tax.parenttype = 'Payment Entry'
				and tax.custom_invoice_withholding = 1
				and payment.docstatus = 0
			"""
		)

	for name in CUSTOM_FIELDS:
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, force=1, ignore_permissions=True)

	for name in PROPERTY_SETTERS:
		if frappe.db.exists("Property Setter", name):
			frappe.delete_doc("Property Setter", name, force=1, ignore_permissions=True)

	for doctype in (
		"Payment Entry",
		"Payment Entry Reference",
		"Advance Taxes and Charges",
		"Payment Request",
		"Purchase Invoice",
		"Purchase Invoice Item",
		"Sales Invoice",
		"Sales Invoice Item",
	):
		frappe.clear_cache(doctype=doctype)
