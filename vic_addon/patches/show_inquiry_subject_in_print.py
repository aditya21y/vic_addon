"""Nyalain "Show Subject in Print" di Inquiry lama yang Subject-nya udah keisi.

Sebelum ada centangan ini, Subject di print format Inquiry selalu dicetak kalau diisi. Sekarang
cuma dicetak kalau dicentang, dan default-nya mati - tanpa patch ini Subject di Inquiry lama
mendadak ilang dari kertasnya. Project gak perlu: dulu emang gak pernah dicetak di Inquiry.

Patch `post_model_sync` jalan **sebelum** fixture disinkron waktu migrate (`frappe/migrate.py`),
jadi kolomnya belum ada - fixture VIC disinkron duluan di sini.
"""

import frappe
from frappe.utils.fixtures import sync_fixtures


def execute():
	sync_fixtures("vic_addon")

	frappe.db.sql(
		"""
		update `tabRequest for Quotation`
		set custom_show_subject = 1
		where ifnull(custom_subject, '') != ''
		"""
	)
