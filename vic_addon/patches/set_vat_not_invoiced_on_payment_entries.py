"""Nyalain centangan PPN Masukan Belum Ditagih di Payment Entry lama yang PPN-nya udah dialihin.

Sebelum centangan ini ada, PPN DP ke supplier dialihin ke akun penampung lewat DP Invoice, terus
langsung dipindahin balik oleh Journal Entry otomatis waktu Payment Entry disubmit. Sekarang
pemindahannya manual (tombol Create > PPN Reclass Journal) dan yang nentuin akunnya centangan di
Payment Entry - jadi Payment Entry lama yang barisnya udah dialihin dicentang di sini:

- draft: biar waktu disimpan ulang PPN-nya gak dibalikin ke PPN Masukan
- submitted tanpa jurnal pemindahan: biar tombolnya muncul dan PPN-nya bisa dipindah begitu
  faktur pajaknya datang
- submitted yang jurnal otomatisnya udah ada: tombolnya cuma buka jurnal itu
"""

import frappe
from frappe.utils.fixtures import sync_fixtures


def execute():
	# patch post_model_sync jalan sebelum fixture di-sync, field-nya mesti ada dulu
	sync_fixtures("vic_addon")

	names = frappe.db.sql_list(
		"""
		select distinct pe.name
		from `tabPayment Entry` pe
		join `tabAdvance Taxes and Charges` tax on tax.parent = pe.name and tax.parenttype = 'Payment Entry'
		where pe.payment_type = 'Pay' and pe.docstatus < 2
			and ifnull(tax.custom_original_account_head, '') != ''
			and tax.custom_original_account_head != tax.account_head
		"""
	)
	for name in names:
		frappe.db.set_value("Payment Entry", name, "custom_vat_not_invoiced", 1, update_modified=False)
