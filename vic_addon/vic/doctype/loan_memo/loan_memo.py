"""Loan Memo: nota peminjaman barang ke customer.

Customer minjem barang buat dicoba/dipakai dulu di lapangan. Barangnya keluar dari gudang
asal ke gudang peminjaman customer, terus ujungnya cuma dua: dibeli (lanjut ke Sales Order)
atau dibalikin (masuk lagi ke gudang asal).

Statusnya jalan sendiri ngikutin dokumen turunannya, user cuma milih di satu percabangan:

	Draft
	  -> submit                                  Approved to Deliver
	  -> Stock Entry (Customer Loan) disubmit     Delivered
	       -> tombol Approve to Sell              Approved to Sell
	            -> Sales Order disubmit           Sold
	       -> tombol Approve to Return            Approved to Return
	            -> Stock Entry (Customer Loan Return) disubmit   Returned

Tiap dokumen turunannya dibatalin, statusnya balik ke langkah sebelumnya - jadi salah submit
tinggal di-cancel, gak usah bikin memo baru.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, nowdate

from vic_addon.vic.warehouse import get_default_warehouse

# gudang penampung barang yang lagi dipinjem customer, satu per company
CUSTOMER_LOAN_WAREHOUSE = "Customer Loan"

# Stock Entry Type buat kirim & terima balik barang pinjaman (dua-duanya Material Transfer)
CUSTOMER_LOAN = "Customer Loan"
CUSTOMER_LOAN_RETURN = "Customer Loan Return"

DRAFT = "Draft"
APPROVED_TO_DELIVER = "Approved to Deliver"
DELIVERED = "Delivered"
APPROVED_TO_SELL = "Approved to Sell"
APPROVED_TO_RETURN = "Approved to Return"
SOLD = "Sold"
RETURNED = "Returned"
CANCELLED = "Cancelled"


class LoanMemo(Document):
	def validate(self):
		self.set_warehouses()
		self.validate_qty()
		self.validate_warehouses()

	def on_submit(self):
		self.db_set("loan_memo_status", APPROVED_TO_DELIVER)

	def before_cancel(self):
		# dicegat sebelum docstatus-nya kesentuh, biar gak nyandar sama rollback
		self.validate_no_active_documents()

	def on_cancel(self):
		self.db_set("loan_memo_status", CANCELLED)

	def validate_no_active_documents(self):
		"""Memo gak boleh dibatalin selama dokumen turunannya masih aktif."""
		documents = get_linked_documents(self.name)
		if not documents:
			return

		frappe.throw(
			_("Cancel {0} first - it was created from this Loan Memo.").format(", ".join(documents)),
			title=_("Linked Document Exists"),
		)

	def set_status(self, status):
		"""Ganti status + catat di timeline, biar kelihatan siapa yang mutusin dan kapan."""
		if self.loan_memo_status == status:
			return

		self.db_set("loan_memo_status", status)
		self.add_comment("Info", _("Loan Memo Status set to {0}").format(_(status)))

	def set_warehouses(self):
		"""Gudang asal ikut default item, gudang tujuan ikut gudang peminjaman company."""
		loan_warehouse = None

		for item in self.items:
			if not item.from_warehouse:
				item.from_warehouse = get_default_warehouse(item.item_code, self.company)

			if not item.to_warehouse:
				loan_warehouse = loan_warehouse or get_customer_loan_warehouse(self.company)
				item.to_warehouse = loan_warehouse

	def validate_qty(self):
		for item in self.items:
			if flt(item.qty) <= 0:
				frappe.throw(
					_("Row #{0}: Qty for item {1} has to be more than zero.").format(
						item.idx, item.item_code
					),
					title=_("Qty Required"),
				)

	def validate_warehouses(self):
		for item in self.items:
			if item.from_warehouse == item.to_warehouse:
				frappe.throw(
					_("Row #{0}: From Warehouse and To Warehouse cannot be the same ({1}).").format(
						item.idx, item.from_warehouse
					),
					title=_("Same Warehouse"),
				)


def get_customer_loan_warehouse(company):
	"""Gudang peminjaman customer. Diambil dari Company, dibuatin kalau belum ada."""
	warehouse = frappe.db.get_value("Company", company, "custom_customer_loan_warehouse")
	if warehouse:
		return warehouse

	abbreviation = frappe.db.get_value("Company", company, "abbr")
	warehouse = f"{CUSTOMER_LOAN_WAREHOUSE} - {abbreviation}"

	if not frappe.db.exists("Warehouse", warehouse):
		parent = f"All Warehouses - {abbreviation}"
		frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": CUSTOMER_LOAN_WAREHOUSE,
				"company": company,
				"parent_warehouse": parent if frappe.db.exists("Warehouse", parent) else None,
				"is_group": 0,
			}
		).insert(ignore_permissions=True)

	frappe.db.set_value("Company", company, "custom_customer_loan_warehouse", warehouse)

	# peta akun gudang di-cache per proses; gudang yang baru lahir belum ada di sana, dan kalau
	# kepakai di proses yang sama ERPNext ngamuk "not linked to any account"
	frappe.flags.pop("warehouse_account_map", None)

	return warehouse


@frappe.whitelist()
def approve_to_sell(loan_memo):
	"""Tombol Approve to Sell: customer jadi beli barang pinjamannya."""
	return set_decision(loan_memo, APPROVED_TO_SELL)


@frappe.whitelist()
def approve_to_return(loan_memo):
	"""Tombol Approve to Return: customer batal beli, barangnya dibalikin."""
	return set_decision(loan_memo, APPROVED_TO_RETURN)


def set_decision(loan_memo, status):
	"""Keputusan customer cuma bisa diambil setelah barangnya beneran kekirim."""
	doc = frappe.get_doc("Loan Memo", loan_memo)
	doc.check_permission("submit")

	if doc.loan_memo_status != DELIVERED:
		frappe.throw(
			_("Loan Memo {0} is {1}. This decision can only be made after the goods are {2}.").format(
				doc.name, _(doc.loan_memo_status), _(DELIVERED)
			),
			title=_("Not Delivered Yet"),
		)

	doc.set_status(status)

	return status


@frappe.whitelist()
def make_loan_stock_entry(source_name, target_doc=None):
	"""Tombol Create > Stock Entry (Customer Loan): barang keluar ke gudang peminjaman."""
	return make_stock_entry(source_name)


@frappe.whitelist()
def make_return_stock_entry(source_name, target_doc=None):
	"""Tombol Create > Stock Entry (Customer Loan Return): barang balik ke gudang asal."""
	return make_stock_entry(source_name, is_return=1)


def make_stock_entry(source_name, is_return=0):
	"""Stock Entry transfer barang pinjaman: keluar ke gudang customer, atau balik ke gudang asal.

	Dipisah jadi dua tombol di atas, bukan satu method ber-argumen: `open_mapped_doc` ngirim
	`args` lewat `frappe.flags`, dan yang dioper ke method cuma `source_name` doang - argumen
	kedua bakal diem-diem kepakai nilai default (lihat `frappe.model.mapper.make_mapped_doc`).
	"""
	is_return = cint(is_return)

	doc = frappe.get_doc("Loan Memo", source_name)
	doc.check_permission("read")

	required = APPROVED_TO_RETURN if is_return else APPROVED_TO_DELIVER
	if doc.loan_memo_status != required:
		frappe.throw(
			_("Loan Memo {0} is {1}, so this Stock Entry cannot be created yet (needs {2}).").format(
				doc.name, _(doc.loan_memo_status), _(required)
			),
			title=_("Status Not Ready"),
		)

	stock_entry = frappe.new_doc("Stock Entry")
	stock_entry.company = doc.company
	stock_entry.stock_entry_type = CUSTOMER_LOAN_RETURN if is_return else CUSTOMER_LOAN
	stock_entry.purpose = "Material Transfer"
	stock_entry.custom_loan_memo = doc.name

	for item in doc.items:
		stock_entry.append(
			"items",
			{
				"item_code": item.item_code,
				"qty": item.qty,
				"uom": item.uom,
				"stock_uom": item.uom,
				"conversion_factor": 1,
				# balikin barang = gudangnya kebalik
				"s_warehouse": item.to_warehouse if is_return else item.from_warehouse,
				"t_warehouse": item.from_warehouse if is_return else item.to_warehouse,
			},
		)

	stock_entry.set_missing_values()

	return stock_entry


@frappe.whitelist()
def make_sales_order(source_name, target_doc=None):
	"""Sales Order atas barang pinjaman yang jadi dibeli.

	Barangnya udah nangkring di gudang peminjaman customer, jadi gudang di SO ikut ke situ -
	Delivery Note-nya nanti ngeluarin dari gudang yang bener.
	"""
	doc = frappe.get_doc("Loan Memo", source_name)
	doc.check_permission("read")

	if doc.loan_memo_status != APPROVED_TO_SELL:
		frappe.throw(
			_("Loan Memo {0} is {1}, so the Sales Order cannot be created yet (needs {2}).").format(
				doc.name, _(doc.loan_memo_status), _(APPROVED_TO_SELL)
			),
			title=_("Status Not Ready"),
		)

	sales_order = frappe.new_doc("Sales Order")
	sales_order.company = doc.company
	sales_order.customer = doc.customer
	sales_order.custom_loan_memo = doc.name
	# barangnya udah di tangan customer, jadi tanggal kirimnya paling telat ya hari ini
	delivery_date = doc.expected_end_loan_date or nowdate()
	sales_order.delivery_date = delivery_date

	for item in doc.items:
		sales_order.append(
			"items",
			{
				"item_code": item.item_code,
				"qty": item.qty,
				"uom": item.uom,
				"warehouse": item.to_warehouse,
				"delivery_date": delivery_date,
			},
		)

	if doc.sales_person:
		sales_order.append("sales_team", {"sales_person": doc.sales_person, "allocated_percentage": 100})

	sales_order.set_missing_values()

	return sales_order


def update_status_from_stock_entry(doc, method=None):
	"""Hook `on_submit` / `on_cancel` Stock Entry: status memo ngikutin transfer barangnya."""
	if not doc.get("custom_loan_memo") or doc.stock_entry_type not in (CUSTOMER_LOAN, CUSTOMER_LOAN_RETURN):
		return

	is_return = doc.stock_entry_type == CUSTOMER_LOAN_RETURN

	if doc.docstatus == 1:
		status = RETURNED if is_return else DELIVERED
	else:
		# dibatalin: balik ke langkah sebelumnya
		status = APPROVED_TO_RETURN if is_return else APPROVED_TO_DELIVER

	frappe.get_doc("Loan Memo", doc.custom_loan_memo).set_status(status)


def update_status_from_sales_order(doc, method=None):
	"""Hook `on_submit` / `on_cancel` Sales Order: barang pinjaman resmi kejual."""
	if not doc.get("custom_loan_memo"):
		return

	frappe.get_doc("Loan Memo", doc.custom_loan_memo).set_status(
		SOLD if doc.docstatus == 1 else APPROVED_TO_SELL
	)


def get_linked_documents(loan_memo):
	"""Stock Entry & Sales Order aktif yang lahir dari memo ini."""
	documents = []

	for doctype in ("Stock Entry", "Sales Order"):
		documents += frappe.get_all(
			doctype, filters={"custom_loan_memo": loan_memo, "docstatus": ["<", 2]}, pluck="name"
		)

	return sorted(documents)


def setup_stock_entry_types():
	"""Hook `after_install` / `after_migrate`: dua Stock Entry Type buat alur peminjaman."""
	for name in (CUSTOMER_LOAN, CUSTOMER_LOAN_RETURN):
		if frappe.db.exists("Stock Entry Type", name):
			continue

		frappe.get_doc(
			{
				"doctype": "Stock Entry Type",
				"__newname": name,
				"purpose": "Material Transfer",
				"is_standard": 0,
			}
		).insert(ignore_permissions=True)
