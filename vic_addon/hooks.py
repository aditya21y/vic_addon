from vic_addon.vic.dpp_nilai_lain import DPP_NILAI_LAIN_DOCTYPES
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
# aturan amend naming ada di Single doctype (Document Naming Settings), gak bisa jadi fixture

after_install = "vic_addon.vic.naming.setup_amend_naming_rule"
after_migrate = "vic_addon.vic.naming.setup_amend_naming_rule"

# include js in doctype views
doctype_js = {doctype: ["public/js/dpp_nilai_lain.js"] for doctype in DPP_NILAI_LAIN_DOCTYPES}
doctype_js["Supplier Quotation"] = ["public/js/supplier_quotation.js"]
# tombol bikin PO per supplier
doctype_js["Sales Order"].append("public/js/sales_order.js")
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

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "vic_addon.utils.jinja_methods",
# 	"filters": "vic_addon.utils.jinja_filters"
# }

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

doc_events["Supplier Quotation"]["before_validate"] = [
	"vic_addon.vic.multi_level_discount.validate_discount_levels",
	"vic_addon.vic.multi_level_discount.apply_multi_level_discount",
]

for doctype in DPP_NILAI_LAIN_DOCTYPES:
	# DPP Nilai Lain = 11/12 x net total, dihitung setelah total ERPNext beres
	doc_events.setdefault(doctype, {})["validate"] = [
		"vic_addon.vic.dpp_nilai_lain.set_dpp_nilai_lain"
	]

# tandai item delivered_by_supplier sesuai tipe transaksi (Reguler / Dropship)
doc_events["Sales Order"]["validate"].append("vic_addon.vic.sales_order.set_dropship_details")

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

