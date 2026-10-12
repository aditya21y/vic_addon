from vic_addon.vic.dpp_nilai_lain import DPP_NILAI_LAIN_DOCTYPES
from vic_addon.vic.item_header import ITEM_HEADER_DOCTYPES
from vic_addon.vic.naming import NAMING_DOCTYPES

app_name = "vic_addon"
app_title = "VIC"
app_publisher = "aditya"
app_description = "app for VIC"
app_email = "adityayudhaperdana21@gmail.com"
app_license = "mit"

# Fixtures
# --------
# Customization (custom field / property setter) milik module VIC di-sync otomatis
# saat install & migrate. Kalau ada perubahan lewat Customize Form, jalankan:
# 	bench --site <site> export-fixtures --app vic_addon
# Pastikan field Module di customization-nya keisi "VIC" biar keikut ke-export.

fixtures = [
	{"dt": "Custom Field", "filters": [["module", "=", "VIC"]]},
	{"dt": "Property Setter", "filters": [["module", "=", "VIC"]]},
]

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "vic_addon",
# 		"logo": "/assets/vic_addon/logo.png",
# 		"title": "VIC",
# 		"route": "/vic_addon",
# 		"has_permission": "vic_addon.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/vic_addon/css/vic_addon.css"
# app_include_js = "/assets/vic_addon/js/vic_addon.js"
# badge angka notifikasi belum dibaca + pop-up & suara notifikasi baru (sidebar desk)
app_include_js = ["/assets/vic_addon/js/notification_badge.js"]

# include js, css files in header of web template
# web_include_css = "/assets/vic_addon/css/vic_addon.css"
# web_include_js = "/assets/vic_addon/js/vic_addon.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "vic_addon/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# Naming Series
# -------------
# Variable tambahan buat naming series, bulannya ikut tanggal dokumen (bukan tanggal hari ini)

naming_series_variables = {
	"YYMM": "vic_addon.vic.naming.parse_yymm",
	"YYYYMM": "vic_addon.vic.naming.parse_yyyymm",
}

# Installation
# ------------
# aturan amend naming ada di Single doctype (Document Naming Settings), label doctype ada di
# Translation (gak punya field Module) - dua-duanya gak bisa jadi fixture

after_install = [
	"vic_addon.vic.naming.setup_amend_naming_rule",
	"vic_addon.vic.labels.setup_document_labels",
	# isi print format diambil dari file .html-nya (lihat vic/print_formats.py)
	"vic_addon.vic.print_formats.sync_print_formats",
	# Stock Entry Type buat alur peminjaman barang (Loan Memo)
	"vic_addon.vic.doctype.loan_memo.loan_memo.setup_stock_entry_types",
	# isian awal master Tax ID Type (TIN, NIK, Passport, Other ID), cuma kalau masih kosong
	"vic_addon.vic.doctype.tax_id_type.tax_id_type.setup_tax_id_types",
]
after_migrate = after_install

# include js in doctype views
doctype_js = {doctype: ["public/js/dpp_nilai_lain.js"] for doctype in DPP_NILAI_LAIN_DOCTYPES}
doctype_js["Supplier Quotation"] = ["public/js/supplier_quotation.js"]
# tombol download tabel perbandingan penawaran supplier
doctype_js["Request for Quotation"] = ["public/js/request_for_quotation.js"]
# DP Invoice: persentase DP + template pajak DP
doctype_js["Payment Request"] = ["public/js/payment_request.js"]
# tarik biaya yang nambah nilai barang dari Journal Entry
doctype_js["Landed Cost Voucher"] = ["public/js/landed_cost_voucher.js"]
# skema DP pakai Item DP: pilihan term DP + tombol Get DP Invoices
for doctype in ("Sales Invoice", "Purchase Invoice"):
	doctype_js.setdefault(doctype, []).append("public/js/dp_item_invoice.js")
# tombol bikin PO per supplier
doctype_js["Sales Order"].append("public/js/sales_order.js")
# PO dropship: tombol bikin Delivery Note, tombol Purchase Receipt disembunyiin
doctype_js["Purchase Order"].append("public/js/purchase_order.js")
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "vic_addon/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------
# dipakai di print format Goods Received (Serial No per baris) dan label Serial No (QR code)

jinja = {
	"methods": [
		"vic_addon.vic.item_header.group_items_by_header",
		"vic_addon.vic.doctype.costing.costing.get_request_for_quotations",
		"vic_addon.vic.serial_no.get_row_serial_nos",
		"vic_addon.vic.serial_no.get_label_rows",
		"vic_addon.vic.serial_no.get_qr_code",
	]
}

# Installation
# ------------

# before_install = "vic_addon.install.before_install"
# after_install = "vic_addon.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "vic_addon.uninstall.before_uninstall"
# after_uninstall = "vic_addon.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "vic_addon.utils.before_app_install"
# after_app_install = "vic_addon.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "vic_addon.utils.before_app_uninstall"
# after_app_uninstall = "vic_addon.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "vic_addon.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "vic_addon.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	doctype: {
		# nomor diambil dari nomor terakhir di bulan dokumen (aman buat backdate & data import)
		"before_naming": "vic_addon.vic.naming.sync_series_counter",
		# dokumen amend pakai suffix R: SAL-ORD-2502-00001R1
		"autoname": "vic_addon.vic.naming.set_amended_name",
	}
	for doctype in NAMING_DOCTYPES
}

# status Costing ngikut ada/enggaknya Quotation yang nempel ke costing itu
for event in ("on_update", "on_cancel", "after_delete"):
	doc_events["Quotation"][event] = "vic_addon.vic.doctype.costing.costing.update_status_from_quotation"

doc_events["Quotation"]["before_submit"] = [
	# satu Costing cuma boleh punya satu Quotation yang jadi (submitted)
	"vic_addon.vic.doctype.costing.costing.validate_single_submitted_quotation",
	# habis lolos: harga final penawaran ditulis balik ke Quotation Rate di Costing
	"vic_addon.vic.doctype.costing.costing.update_costing_rates",
]

doc_events["Supplier Quotation"]["before_validate"] = [
	"vic_addon.vic.multi_level_discount.validate_discount_levels",
	"vic_addon.vic.multi_level_discount.apply_multi_level_discount",
]

for doctype in DPP_NILAI_LAIN_DOCTYPES:
	# DPP Nilai Lain = 11/12 x net total, dihitung setelah total ERPNext beres
	doc_events.setdefault(doctype, {})["validate"] = [
		"vic_addon.vic.dpp_nilai_lain.set_dpp_nilai_lain"
	]

# Dropship: tipe transaksi ada di baris item, header cuma ringkasannya
for doctype in ("Sales Order", "Purchase Order", "Delivery Note", "Purchase Receipt"):
	events = doc_events.setdefault(doctype, {})
	if isinstance(events.get("validate"), str):
		events["validate"] = [events["validate"]]

	events.setdefault("validate", []).append("vic_addon.vic.dropship.set_transaction_type")

# dropship bawaan ERPNext dimatiin, tipe pengiriman diambil dari field Transaction Type
doc_events["Sales Order"]["validate"].append("vic_addon.vic.dropship.clear_delivered_by_supplier")

for doctype in ("Delivery Note", "Purchase Receipt"):
	# seri nomor dropship dipilih duluan, baru counternya disinkronin
	doc_events[doctype]["before_naming"] = [
		"vic_addon.vic.dropship.set_dropship_naming_series",
		"vic_addon.vic.naming.sync_series_counter",
	]

# barang dropship keluar dari gudang transit, dan stoknya dimasukin dulu lewat
# Purchase Receipt yang dibuat otomatis tepat sebelum Delivery Note disubmit
doc_events["Delivery Note"]["validate"].append(
	"vic_addon.vic.dropship.set_dropship_warehouse_on_items"
)

# baris DN dropship nyimpen nomor PO-nya, sekalian jadi jembatan Connections PO <-> DN
doc_events["Delivery Note"]["validate"].append(
	"vic_addon.vic.dropship.set_purchase_order_on_items"
)
doc_events["Delivery Note"]["before_submit"] = "vic_addon.vic.dropship.make_dropship_purchase_receipt"

# Serial No dibikin sendiri (seri nomornya di master Serial Number Settings), bukan lewat
# field Serial No Series di Item
doc_events["Purchase Receipt"]["validate"].append("vic_addon.vic.serial_no.set_serial_nos")

# garansi mulai jalan pas barang dikirim, tanggalnya diturunin ke tiap Serial No
doc_events["Delivery Note"]["validate"].append("vic_addon.vic.serial_no.set_warranty_dates")
doc_events["Delivery Note"]["on_submit"] = "vic_addon.vic.serial_no.update_serial_no_warranty"

# harga dikunci ke dokumen sumbernya, jangan ketiban Item Price
# for doctype in ("Quotation", "Sales Order"):
# 	doc_events[doctype]["before_validate"] = "vic_addon.vic.rate_lock.set_selling_rate_from_costing"

doc_events["Purchase Order"]["before_validate"] = [
	# jalan duluan: link SQTN disamain dulu sama supplier PO-nya, baru harganya dipasang
	"vic_addon.vic.purchase_order.sync_supplier_quotation",
	"vic_addon.vic.rate_lock.set_buying_rate_from_supplier_quotation",
	# PO dari tombol di Sales Order: Required By yang udah lewat dimajuin ke tanggal PO
	"vic_addon.vic.sales_order.set_schedule_date",
]

# qty & link PO dicek balik ke Supplier Quotation-nya
doc_events["Purchase Order"]["validate"].append(
	"vic_addon.vic.purchase_order.validate_supplier_quotation"
)

# DP Invoice: nilai DP + PPN/PPh atas DP, dibawa ke Payment Entry
doc_events["Payment Request"] = {
	"before_validate": [
		# dokumen baru dari tombol Create > Payment Request: DP diambil dari dokumen referensi
		"vic_addon.vic.dp_invoice.set_dp_from_reference_on_create",
		# baru tabel Payment Reference disamain sama DP Amount
		"vic_addon.vic.dp_invoice.sync_payment_reference",
	],
	"validate": "vic_addon.vic.dp_invoice.set_dp_details",
}
# satu Journal Entry cuma boleh ditarik ke satu Landed Cost Voucher
doc_events["Landed Cost Voucher"] = {"validate": "vic_addon.vic.landed_cost.validate_journal_entries"}
doc_events["Payment Entry"] = {
	"before_validate": [
		"vic_addon.vic.dp_invoice.set_advance_taxes",
	],
	# PPN uang muka pindah dari akun penampung ke akun aslinya begitu DP-nya kebayar
	"on_submit": "vic_addon.vic.dp_ppn.make_vat_reclass_entry",
	"on_cancel": "vic_addon.vic.dp_ppn.cancel_vat_reclass_entry",
}

# Purchase Request dari Sales Order: nomor PO customer ikut kebawa
doc_events["Material Request"] = {
	"before_validate": "vic_addon.vic.material_request.set_customer_po_no",
}

# Customer ngalir dari Opportunity -> Request for Quotation -> Costing (Costing juga narik
# Project & Subject dari Inquiry-nya)
doc_events.setdefault("Request for Quotation", {}).setdefault("validate", []).append(
	"vic_addon.vic.customer_chain.set_customer_from_opportunity"
)
# baris item Inquiry yang warehouse-nya kosong diisi gudang default Stock Settings
doc_events["Request for Quotation"]["before_validate"] = [
	"vic_addon.vic.request_for_quotation.set_default_warehouse"
]
doc_events.setdefault("Costing", {}).setdefault("validate", []).append(
	"vic_addon.vic.customer_chain.set_customer_from_request_for_quotation"
)

# Header di baris item: yang dikosongin ngikut baris di atasnya
for doctype in ITEM_HEADER_DOCTYPES:
	events = doc_events.setdefault(doctype, {})
	if isinstance(events.get("validate"), str):
		events["validate"] = [events["validate"]]

	events.setdefault("validate", []).append("vic_addon.vic.item_header.set_item_headers")

# Loan Memo: statusnya jalan sendiri ngikutin Stock Entry & Sales Order turunannya
for doctype, handler in (
	("Stock Entry", "update_status_from_stock_entry"),
	("Sales Order", "update_status_from_sales_order"),
):
	events = doc_events.setdefault(doctype, {})

	for event in ("on_submit", "on_cancel"):
		if isinstance(events.get(event), str):
			events[event] = [events[event]]
		events.setdefault(event, []).append(
			f"vic_addon.vic.doctype.loan_memo.loan_memo.{handler}"
		)

# invoice final cuma nagih sisa PPN/PPh yang belum dibayar lewat DP
for doctype in ("Sales Invoice", "Purchase Invoice"):
	doc_events[doctype]["before_validate"] = [
		# invoice DP (Is DP Invoice): semua item diganti satu baris Item DP senilai term DP-nya
		"vic_addon.vic.dp_item_invoice.set_dp_invoice",
		"vic_addon.vic.advance_tax.restore_tax_rows",
	]
	doc_events[doctype]["validate"].append("vic_addon.vic.advance_tax.deduct_advance_taxes")
	# invoice progress: DP dari order yang sama dibalik lewat Reverse Journal waktu submit
	doc_events[doctype]["validate"].append("vic_addon.vic.dp_item_invoice.validate_dp_allocations")
	doc_events[doctype].setdefault("on_submit", [])
	if isinstance(doc_events[doctype]["on_submit"], str):
		doc_events[doctype]["on_submit"] = [doc_events[doctype]["on_submit"]]
	doc_events[doctype]["on_submit"].append("vic_addon.vic.dp_item_invoice.make_reverse_journal")
	doc_events[doctype]["before_cancel"] = [
		"vic_addon.vic.dp_item_invoice.block_cancel_of_used_dp",
		"vic_addon.vic.dp_item_invoice.cancel_reverse_journal",
	]

# alamat kirim dropship itu alamat customer, yang ditolak validasi alamat bawaan ERPNext -
# disingkirin sebelum validasi inti, dipasang lagi sesudahnya
for doctype in ("Purchase Order", "Purchase Receipt", "Purchase Invoice"):
	events = doc_events.setdefault(doctype, {})

	for event in ("before_validate", "validate"):
		if isinstance(events.get(event), str):
			events[event] = [events[event]]
		events.setdefault(event, [])

	events["before_validate"].append("vic_addon.vic.dropship.stash_customer_shipping_address")
	events["validate"].append("vic_addon.vic.dropship.restore_customer_shipping_address")

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"vic_addon.tasks.all"
# 	],
# 	"daily": [
# 		"vic_addon.tasks.daily"
# 	],
# 	"hourly": [
# 		"vic_addon.tasks.hourly"
# 	],
# 	"weekly": [
# 		"vic_addon.tasks.weekly"
# 	],
# 	"monthly": [
# 		"vic_addon.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "vic_addon.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "vic_addon.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# Bank Clearance: tanggal jurnal ikut digeser ke tanggal cair di bank
override_doctype_class = {"Bank Clearance": "vic_addon.vic.bank_clearance.VICBankClearance"}

# PO dropship: Delivery Note-nya ikut nongol di tab Connections
override_doctype_dashboards = {
	"Purchase Order": "vic_addon.vic.purchase_order.get_dashboard_data",
}

override_whitelisted_methods = {
	# tombol Create Payment Entry di DP Invoice, biar tabel pajak DP langsung keisi di form
	"erpnext.accounts.doctype.payment_request.payment_request.make_payment_entry": "vic_addon.vic.dp_invoice.make_payment_entry",
	# tombol Create Payment Request di SO/PO: DP dihitung dari net total + tabel pajak keisi
	"erpnext.accounts.doctype.payment_request.payment_request.make_payment_request": "vic_addon.vic.dp_invoice.make_payment_request",
	# tombol Create Inquiry di Opportunity: Customer-nya udah keisi waktu formnya kebuka
	"erpnext.crm.doctype.opportunity.opportunity.make_request_for_quotation": "vic_addon.vic.customer_chain.make_request_for_quotation",
}

# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "vic_addon.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "vic_addon.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["vic_addon.utils.before_request"]
# after_request = ["vic_addon.utils.after_request"]

# Job Events
# ----------
# before_job = ["vic_addon.utils.before_job"]
# after_job = ["vic_addon.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"vic_addon.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

