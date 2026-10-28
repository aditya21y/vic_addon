"""Purchase Invoice: Supplier Invoice No & Date bisa diubah setelah submit.

Nomor & tanggal tagihan supplier sering baru dateng setelah invoice-nya disubmit (dicetak di
Receipt Note buat tukar faktur), jadi dua field itu dibikin Allow on Submit lewat property setter.
"""

import frappe


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
