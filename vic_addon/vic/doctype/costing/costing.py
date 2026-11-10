# Copyright (c) 2026, aditya and contributors
# For license information, please see license.txt

"""Costing: hitung HPP dari harga Supplier Quotation + distribusi additional cost, terus
tentuin harga jual dari margin. Rumusnya ngikut sheet "5a. COSTING" di source of truth:

	Total Buying Amount        = sum(Rate x Qty)
	Total Additional Costs     = sum(Additional Costs)
	Additional Cost Percentage = Total Additional Costs / Total Buying Amount x 100

	per item:
	Distributed Cost Rate = Rate x Additional Cost Percentage x (1 + Additional Percentage)
	HPP Rate              = Rate + Distributed Cost Rate
	Selling Rate          = HPP Rate / (1 - Margin %)
	Profit Amount         = Selling Amount - HPP Amount

Additional cost dibagi proporsional lewat rate tiap item, jadi total distributed cost
= Total Additional Costs x (1 + Additional Percentage).

Discount (% atau nominal) itu simulasi diskon ke customer atas Total Quotation Amount:

	Total Quotation After Discount = Total Quotation Amount - Discount Amount
	Total Profit After Discount    = Total Quotation After Discount - Total HPP Amount

Mata uang Costing **selalu mata uang perusahaan** (IDR). Harga dari Supplier Quotation diambil
versi mata uang perusahaannya (`base_net_rate` / `base_price_list_rate` - harga valas x kurs di
SQTN itu), jadi penawaran USD, SGD, dst bisa langsung masuk Costing yang sama tanpa nyaring
mata uang, dan perbandingan harga termurah antar supplier ikut sebanding.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder import Order
from frappe.utils import cint, flt, get_link_to_form

from vic_addon.vic.warehouse import get_default_warehouse, get_valuation_rate

NOT_QUOTED = "Not Quoted"
QUOTED = "Quoted"


class Costing(Document):
	def validate(self):
		self.set_company_currency()
		self.validate_margin_percentage()
		self.set_warehouses()
		self.set_rates_from_valuation()
		self.set_price_list_rates()
		self.calculate()
		self.validate_discount()
		self.set_status()

	def set_company_currency(self):
		"""Costing selalu dalam mata uang perusahaan - harga SQTN valas dikonversi waktu ditarik."""
		if self.company:
			self.currency = frappe.get_cached_value("Company", self.company, "default_currency")

	def set_warehouses(self):
		"""Gudang stok tiap baris, dipakai buat narik harga barang yang gak lewat SQTN.

		Cuma diisi kalau kosong, jadi pilihan user gak ketiban. Kalau item sama Stock Settings
		dua-duanya gak punya gudang default, baris itu dibiarin kosong.
		"""
		for item in self.items:
			if not item.warehouse:
				item.warehouse = get_default_warehouse(item.item_code, self.company)

	def set_rates_from_valuation(self):
		"""Baris tanpa Supplier Quotation ambil harga pokok dari valuation rate gudangnya.

		Barang stok yang udah nangkring di gudang gak punya penawaran supplier, jadi harga
		pokoknya diambil dari nilai persediaan di gudang itu. Cuma diisi kalau Rate-nya beneran
		kosong (belum pernah diisi): harga dari SQTN maupun angka yang diketik user - termasuk 0,
		mis. barang tambahan - gak ketiban. Kalau di gudang itu item-nya belum punya nilai
		persediaan, Rate-nya jadi 0 buat diisi manual.
		"""
		for item in self.items:
			if item.supplier_quotation or item.rate not in (None, ""):
				continue

			item.rate = flt(get_valuation_rate(item.item_code, item.warehouse))

	def set_price_list_rates(self):
		"""Price List Rate (harga sebelum diskon, dicetak sebagai Act Price di Costing (Import))
		diisi dari baris SQTN-nya kalau masih kosong.

		Dulu dialog Get Items gak nyalin field ini, jadi Costing lama banyak yang 0 dan print-nya
		jatuh ke Rate setelah diskon. Disimpan ulang = beres sendiri.
		"""
		missing = [row for row in self.items if row.supplier_quotation_item and not flt(row.price_list_rate)]
		if not missing:
			return

		sources = {
			row.name: row
			for row in frappe.get_all(
				"Supplier Quotation Item",
				filters={"name": ["in", [row.supplier_quotation_item for row in missing]]},
				fields=["name", "base_price_list_rate", "base_rate", "base_net_rate"],
			)
		}
		for row in missing:
			source = sources.get(row.supplier_quotation_item)
			if source:
				row.price_list_rate = get_company_currency_rates(source)["price_list_rate"]

	def set_status(self):
		self.status = NOT_QUOTED if self.is_new() else get_status(self.name)

	def validate_margin_percentage(self):
		for item in self.items:
			if flt(item.margin_percentage) >= 100:
				frappe.throw(
					_("Row #{0}: Margin % must be less than 100").format(item.idx),
					title=_("Invalid Margin"),
				)

	def validate_discount(self):
		if flt(self.discount_percentage) < 0 or flt(self.discount_amount) < 0:
			frappe.throw(_("Discount cannot be negative"), title=_("Invalid Discount"))

		if flt(self.discount_amount) > flt(self.total_quotation_amount):
			frappe.throw(
				_("Discount Amount cannot be more than Total Quotation Amount"),
				title=_("Invalid Discount"),
			)

	def calculate(self):
		self.calculate_buying_amount()
		self.calculate_additional_cost_percentage()
		self.calculate_items()
		self.calculate_totals()
		self.calculate_discount()

	def calculate_buying_amount(self):
		for item in self.items:
			item.amount = flt(flt(item.rate) * flt(item.qty), item.precision("amount"))

		self.total_buying_amount = flt(
			sum(flt(item.amount) for item in self.items), self.precision("total_buying_amount")
		)

	def calculate_additional_cost_percentage(self):
		self.total_additional_costs = flt(
			sum(flt(cost.amount) for cost in self.additional_costs),
			self.precision("total_additional_costs"),
		)

		self.additional_cost_percentage = (
			flt(
				self.total_additional_costs / self.total_buying_amount * 100,
				self.precision("additional_cost_percentage"),
			)
			if self.total_buying_amount
			else 0
		)

	def calculate_items(self):
		# additional cost yang dibebankan ke tiap rupiah harga beli
		cost_factor = (
			flt(self.additional_cost_percentage) / 100 * (1 + flt(self.additional_percentage) / 100)
		)

		for item in self.items:
			item.distributed_cost_rate = flt(
				flt(item.rate) * cost_factor, item.precision("distributed_cost_rate")
			)
			item.distributed_cost_amount = flt(
				flt(item.distributed_cost_rate) * flt(item.qty),
				item.precision("distributed_cost_amount"),
			)

			item.hpp_rate = flt(
				flt(item.rate) + flt(item.distributed_cost_rate), item.precision("hpp_rate")
			)
			item.hpp_amount = flt(flt(item.hpp_rate) * flt(item.qty), item.precision("hpp_amount"))

			item.selling_rate = flt(
				flt(item.hpp_rate) / (1 - flt(item.margin_percentage) / 100),
				item.precision("selling_rate"),
			)
			item.margin_rate = flt(
				flt(item.selling_rate) - flt(item.hpp_rate), item.precision("margin_rate")
			)
			item.margin_amount = flt(
				flt(item.margin_rate) * flt(item.qty), item.precision("margin_amount")
			)
			item.selling_amount = flt(
				flt(item.selling_rate) * flt(item.qty), item.precision("selling_amount")
			)

			# quotation rate default ngikut selling rate, kecuali user isi manual
			if not item.quotation_rate_manually_set:
				item.quotation_rate = item.selling_rate

			item.quotation_amount = flt(
				flt(item.quotation_rate) * flt(item.qty), item.precision("quotation_amount")
			)

			item.profit_amount = flt(
				flt(item.selling_amount) - flt(item.hpp_amount), item.precision("profit_amount")
			)
			item.profit_percentage = (
				flt(item.profit_amount / item.hpp_amount * 100, item.precision("profit_percentage"))
				if item.hpp_amount
				else 0
			)

	def calculate_totals(self):
		totals = {
			"total_distributed_cost_amount": "distributed_cost_amount",
			"total_hpp_amount": "hpp_amount",
			"total_selling_amount": "selling_amount",
			"total_quotation_amount": "quotation_amount",
			"total_profit_amount": "profit_amount",
		}

		for total_field, item_field in totals.items():
			self.set(
				total_field,
				flt(
					sum(flt(item.get(item_field)) for item in self.items),
					self.precision(total_field),
				),
			)

		self.total_profit_percentage = (
			flt(
				self.total_profit_amount / self.total_hpp_amount * 100,
				self.precision("total_profit_percentage"),
			)
			if self.total_hpp_amount
			else 0
		)

		# Profit di atas dihitung dari Selling Rate (harga hasil margin). Yang dinego ke customer
		# itu Quotation Rate, jadi profit versi harga nego dihitung sendiri di sini - basis
		# persentasenya sama (Total HPP) biar dua angkanya bisa langsung dibandingin.
		self.total_quotation_profit_amount = flt(
			flt(self.total_quotation_amount) - flt(self.total_hpp_amount),
			self.precision("total_quotation_profit_amount"),
		)
		self.total_quotation_profit_percentage = (
			flt(
				self.total_quotation_profit_amount / self.total_hpp_amount * 100,
				self.precision("total_quotation_profit_percentage"),
			)
			if self.total_hpp_amount
			else 0
		)

	def calculate_discount(self):
		"""Diskon bisa diisi persen atau nominal - yang terakhir diketik user yang dipegang.

		Polanya sama kayak Quotation Rate: nominal yang diketik user ditandain
		`discount_amount_manually_set`, jadi waktu Total Quotation Amount berubah nominalnya tetap
		dan persennya yang dihitung ulang. Kalau yang diketik persen, nominalnya yang ngikut.
		"""
		base = flt(self.total_quotation_amount)

		if self.discount_amount_manually_set:
			self.discount_amount = flt(self.discount_amount, self.precision("discount_amount"))
			self.discount_percentage = (
				flt(self.discount_amount / base * 100, self.precision("discount_percentage"))
				if base
				else 0
			)
		else:
			self.discount_amount = flt(
				base * flt(self.discount_percentage) / 100, self.precision("discount_amount")
			)

		self.total_after_discount_amount = flt(
			base - flt(self.discount_amount), self.precision("total_after_discount_amount")
		)
		self.total_profit_after_discount_amount = flt(
			self.total_after_discount_amount - flt(self.total_hpp_amount),
			self.precision("total_profit_after_discount_amount"),
		)
		self.total_profit_after_discount_percentage = (
			flt(
				self.total_profit_after_discount_amount / self.total_hpp_amount * 100,
				self.precision("total_profit_after_discount_percentage"),
			)
			if self.total_hpp_amount
			else 0
		)


def get_request_for_quotations(costing):
	"""Nomor RFQ asal penawaran yang dipakai di Costing ini, buat dicetak di print format.

	Costing gak nyimpen link ke RFQ - yang kesimpan link ke baris Supplier Quotation, dan dari
	situ nomor RFQ-nya kebaca.
	"""
	rows = [row.supplier_quotation_item for row in costing.items if row.supplier_quotation_item]
	if not rows:
		return []

	names = frappe.get_all(
		"Supplier Quotation Item",
		filters={"name": ["in", rows]},
		pluck="request_for_quotation",
	)

	return sorted({name for name in names if name})


@frappe.whitelist()
def get_header_from_supplier_quotation_items(supplier_quotation_items):
	"""Tombol Get Items: Customer/RFQ/Project/Subject dari Inquiry asal baris yang baru ditarik,
	biar udah keisi sebelum disimpan (hook validate ngisi lagi kalau masih ada yang kosong)."""
	from vic_addon.vic.customer_chain import get_inquiry_header

	rows = frappe.parse_json(supplier_quotation_items) or []
	names = frappe.get_all(
		"Supplier Quotation Item",
		filters={"name": ["in", rows]},
		pluck="request_for_quotation",
	)
	return get_inquiry_header(sorted({name for name in names if name}))


def get_status(costing):
	"""`Quoted` kalau costing ini udah punya Quotation yang belum dibatalin."""
	quoted = frappe.db.exists("Quotation", {"custom_costing": costing, "docstatus": ["<", 2]})

	return QUOTED if quoted else NOT_QUOTED


def update_status(costing):
	if not (costing and frappe.db.exists("Costing", costing)):
		return

	frappe.db.set_value("Costing", costing, "status", get_status(costing), update_modified=False)


def update_status_from_quotation(doc, method=None):
	"""Hook Quotation (`on_update`, `on_cancel`, `after_delete`): segarin status costing.

	Costing sebelumnya ikut diupdate juga, buat kasus link Costing-nya dipindah ke costing lain.
	"""
	previous = doc.get_doc_before_save()
	costings = {doc.custom_costing, previous.custom_costing if previous else None}

	for costing in costings:
		update_status(costing)


def validate_single_submitted_quotation(doc, method=None):
	"""Hook `before_submit` Quotation: satu Costing cuma boleh punya satu Quotation submitted.

	Costing itu perhitungan buat satu penawaran. Kalau ada dua Quotation submitted nempel ke
	costing yang sama, angka di Costing (termasuk profit lawan harga nego) jadi gak ketahuan
	ngikut yang mana - dan tombol `Update Costing Rate` bakal saling timpa.

	Draft boleh banyak: bikin beberapa versi penawaran itu normal, yang dibatesin cuma yang jadi.
	"""
	if not doc.get("custom_costing"):
		return

	existing = frappe.db.get_value(
		"Quotation",
		{"custom_costing": doc.custom_costing, "docstatus": 1, "name": ["!=", doc.name]},
		"name",
	)
	if not existing:
		return

	frappe.throw(
		_(
			"Costing {0} already has a submitted Quotation: {1}. Cancel that Quotation first, or point this one to another Costing."
		).format(get_link_to_form("Costing", doc.custom_costing), get_link_to_form("Quotation", existing)),
		title=_("Costing Already Quoted"),
	)


def set_quotation_discount(costing, quotation):
	"""Diskon Costing -> Additional Discount Quotation, dasarnya sama: total sebelum pajak.

	Tanpa ini mapper cuma nyalin `discount_amount` (namanya kebetulan sama) dan Quotation
	nerapinnya ke Grand Total - net total-nya jadi beda dari Total Quotation After Discount.
	Yang terakhir diketik di Costing yang dipegang: nominal kalau nominal, persen kalau persen.
	"""
	quotation.apply_discount_on = "Net Total"
	if not flt(costing.discount_amount):
		quotation.additional_discount_percentage = 0
		quotation.discount_amount = 0
		return

	quotation.additional_discount_percentage = (
		0 if costing.discount_amount_manually_set else flt(costing.discount_percentage)
	)
	quotation.discount_amount = flt(costing.discount_amount)


@frappe.whitelist()
def make_quotation(source_name, target_doc=None):
	"""Bikin Quotation ke customer dari Costing.

	Harga jualnya diambil dari Quotation Rate (yang default-nya ngikut Selling Rate), plus
	SQTN ID dan supplier per item biar ketahuan harga belinya dari mana. Diskon di section
	Discount ikut jadi Additional Discount Quotation (lihat `set_quotation_discount`).
	"""
	from frappe.model.mapper import get_mapped_doc

	def set_missing_values(source, target):
		if source.customer:
			target.quotation_to = "Customer"
			target.party_name = source.customer

		target.custom_costing = source.name
		target.project = source.project
		# syarat penawaran ikut dari Costing (field Quotation juga fetch dari Costing kalau kosong)
		target.custom_delivery_time = source.delivery_time
		target.custom_validity = source.validity
		target.custom_subject = source.subject
		set_quotation_discount(source, target)
		target.run_method("set_missing_values")
		target.run_method("calculate_taxes_and_totals")

	def update_item(source_item, target_item, source_parent):
		target_item.rate = source_item.quotation_rate
		target_item.price_list_rate = source_item.quotation_rate
		target_item.custom_supplier_quotation = source_item.supplier_quotation
		target_item.custom_supplier = source_item.supplier

	return get_mapped_doc(
		"Costing",
		source_name,
		{
			"Costing": {
				"doctype": "Quotation",
			},
			"Costing Item": {
				"doctype": "Quotation Item",
				"field_map": {"qty": "qty", "uom": "uom"},
				"postprocess": update_item,
			},
		},
		target_doc,
		set_missing_values,
	)


@frappe.whitelist()
def make_costing(source_name, target_doc=None):
	"""Bikin Costing dari satu Supplier Quotation (tombol Create di form SQTN)."""
	from frappe.model.mapper import get_mapped_doc

	def update_item(source_item, target_item, source_parent):
		target_item.update(get_company_currency_rates(source_item))
		target_item.supplier_quotation = source_parent.name
		target_item.supplier = source_parent.supplier
		target_item.supplier_quotation_item = source_item.name

		# Header 1 & Header 2 dari baris Inquiry asalnya (SQTN gak punya field-nya)
		inquiry_row = get_inquiry_rows([source_item.name]).get(source_item.name)
		if inquiry_row:
			target_item.custom_header = inquiry_row.custom_header
			target_item.custom_pengerjaan = inquiry_row.custom_pengerjaan

	def set_missing_values(source, target):
		# Customer/Project/Subject dari Inquiry-nya langsung keisi, biar udah kelihatan sebelum
		# disimpan - hook validate-nya ngisi lagi kalau masih ada yang kosong
		from vic_addon.vic.customer_chain import set_customer_from_request_for_quotation

		set_customer_from_request_for_quotation(target)
		# mapper nyalin currency SQTN (bisa USD) - Costing selalu mata uang perusahaan
		target.set_company_currency()

	return get_mapped_doc(
		"Supplier Quotation",
		source_name,
		{
			"Supplier Quotation": {
				"doctype": "Costing",
				"validation": {"docstatus": ["=", 1]},
			},
			"Supplier Quotation Item": {
				"doctype": "Costing Item",
				"postprocess": update_item,
			},
		},
		target_doc,
		set_missing_values,
	)


@frappe.whitelist()
def get_supplier_quotation_items(supplier_quotations):
	"""Ambil item dari satu atau beberapa Supplier Quotation buat tabel Costing."""
	return get_costing_items(supplier_quotations=supplier_quotations)


@frappe.whitelist()
def get_supplier_quotations(request_for_quotation=None, company=None, txt=None, project=None):
	"""Daftar Supplier Quotation buat dipilih di dialog `Get Items from Supplier Quotation`.

	Kalau nomor Request for Quotation diisi, yang muncul cuma penawaran yang lahir dari RFQ itu -
	biar gak kecampur penawaran proyek lain. Kalau Project diisi, cuma penawaran project itu: yang
	lahir dari Inquiry project itu, atau yang field Project-nya sendiri sama. Mata uangnya gak
	disaring: harganya diambil dalam mata uang perusahaan (lihat `get_company_currency_rates`).
	"""
	quotation = frappe.qb.DocType("Supplier Quotation")
	query = (
		frappe.qb.from_(quotation)
		.select(quotation.name, quotation.supplier, quotation.transaction_date)
		.where(quotation.docstatus == 1)
		.orderby(quotation.transaction_date, order=Order.desc)
		.limit(50)
	)

	if company:
		query = query.where(quotation.company == company)

	if txt:
		query = query.where(quotation.name.like(f"%{txt}%") | quotation.supplier.like(f"%{txt}%"))

	if request_for_quotation:
		query = query.where(quotation.name.isin(get_quotations_of_rfq(request_for_quotation)))

	if project:
		inquiries = frappe.get_all("Request for Quotation", filters={"project": project}, pluck="name")
		from_inquiries = (
			frappe.get_all(
				"Supplier Quotation Item",
				filters={"request_for_quotation": ["in", inquiries]},
				pluck="parent",
				distinct=True,
			)
			if inquiries
			else []
		)
		condition = quotation.project == project
		if from_inquiries:
			condition = condition | quotation.name.isin(from_inquiries)
		query = query.where(condition)

	return [
		{
			"value": row[0],
			"description": f"{row[1]} — {frappe.utils.formatdate(row[2])}",
			"supplier": row[1],
		}
		for row in query.run()
	]


def get_quotations_of_rfq(request_for_quotation):
	"""Supplier Quotation yang lahir dari RFQ ini, dibaca dari baris itemnya."""
	names = frappe.get_all(
		"Supplier Quotation Item",
		filters={"request_for_quotation": request_for_quotation},
		pluck="parent",
		distinct=True,
	)

	return names or [""]


@frappe.whitelist()
def get_costing_items(supplier_quotations=None, request_for_quotation=None, only_cheapest=0):
	"""Baris item buat tabel di dialog, sebelum dimasukin ke Costing.

	Tiga cara ngambilnya:

	- pilih Supplier Quotation sendiri -> semua itemnya kebawa
	- centang **harga termurah** + isi RFQ -> tiap item diambil dari penawaran termurah, ngikut
	  aturan yang sama kayak tabel Supplier Comparison (cuma penawaran terakhir tiap supplier)
	- centang **harga termurah** tanpa RFQ -> termurah di antara penawaran yang dipilih

	Qty-nya diisi dari RFQ kalau ada (itu jumlah yang beneran dibutuhin), kalau enggak ikut qty
	di penawarannya. Di dialog qty ini masih bisa diubah user sebelum masuk Costing.
	"""
	if isinstance(supplier_quotations, str):
		supplier_quotations = frappe.parse_json(supplier_quotations)

	if isinstance(supplier_quotations, str):
		supplier_quotations = [supplier_quotations]

	only_cheapest = cint(only_cheapest)
	names = get_source_quotations(supplier_quotations, request_for_quotation, only_cheapest)
	if not names:
		return []

	quantities = get_rfq_quantities(request_for_quotation)
	items = []

	for name in names:
		quotation = frappe.get_doc("Supplier Quotation", name)
		quotation.check_permission("read")

		for item in quotation.items:
			items.append(
				{
					"item_code": item.item_code,
					"item_name": item.item_name,
					"uom": item.uom,
					"qty": quantities.get(item.item_code) or flt(item.qty),
					**get_company_currency_rates(item),
					"supplier_quotation": quotation.name,
					"supplier": quotation.supplier,
					"supplier_quotation_item": item.name,
				}
			)

	if only_cheapest:
		items = keep_cheapest(items)

	return sort_by_inquiry(set_inquiry_groups(items))


def get_inquiry_rows(supplier_quotation_items):
	"""Baris SQTN -> baris Inquiry asalnya (Header 1, Header 2, urutan baris).

	SQTN yang dibikin dari Inquiry nyimpen `request_for_quotation_item` di tiap barisnya, dan baris
	Inquiry nyimpen Header 1/2 secara eksplisit (diturunin waktu disimpan, lihat item_header.py).
	SQTN sendiri gak punya field Header, jadi kelompoknya diambil langsung dari Inquiry.
	"""
	names = [name for name in supplier_quotation_items if name]
	if not names:
		return {}

	links = frappe.get_all(
		"Supplier Quotation Item",
		filters={"name": ["in", names]},
		fields=["name", "request_for_quotation_item"],
	)
	rfq_rows = {
		row.name: row
		for row in frappe.get_all(
			"Request for Quotation Item",
			filters={"name": ["in", [link.request_for_quotation_item for link in links if link.request_for_quotation_item]]},
			fields=["name", "parent", "idx", "custom_header", "custom_pengerjaan"],
		)
	}

	return {
		link.name: rfq_rows[link.request_for_quotation_item]
		for link in links
		if link.request_for_quotation_item in rfq_rows
	}


def set_inquiry_groups(items):
	"""Header 1 & Header 2 tiap baris Costing ngikut baris Inquiry asalnya."""
	rfq_rows = get_inquiry_rows([item["supplier_quotation_item"] for item in items])

	for item in items:
		row = rfq_rows.get(item["supplier_quotation_item"])
		item["custom_header"] = (row.custom_header or "") if row else ""
		item["custom_pengerjaan"] = (row.custom_pengerjaan or "") if row else ""
		item["_inquiry_order"] = (row.parent, row.idx) if row else None

	return items


def sort_by_inquiry(items):
	"""Urutan baris ngikut Inquiry, biar kelompok Header 1/2 tetap nyambung walau barisnya dari
	beberapa SQTN. Baris tanpa Inquiry ditaruh paling bawah, urutannya gak diubah."""
	linked = sorted((item for item in items if item["_inquiry_order"]), key=lambda item: item["_inquiry_order"])
	unlinked = [item for item in items if not item["_inquiry_order"]]

	for item in items:
		item.pop("_inquiry_order")

	return linked + unlinked


def get_source_quotations(supplier_quotations, request_for_quotation, only_cheapest):
	"""Penawaran mana yang dibaca: pilihan user, atau penawaran terakhir tiap supplier di RFQ."""
	if only_cheapest and request_for_quotation:
		from vic_addon.vic.supplier_comparison import get_offers

		# aturan yang sama kayak Supplier Comparison: cuma penawaran terakhir tiap supplier
		return [offer["name"] for offer in get_offers(request_for_quotation) if offer["is_latest"]]

	return supplier_quotations or []


def get_rfq_quantities(request_for_quotation):
	"""Qty yang diminta di RFQ, per item code."""
	if not request_for_quotation:
		return {}

	rows = frappe.get_all(
		"Request for Quotation Item",
		filters={"parent": request_for_quotation},
		fields=["item_code", "qty"],
	)

	return {row.item_code: flt(row.qty) for row in rows}


def keep_cheapest(items):
	"""Satu baris per item: yang harganya paling murah. Harga nol dianggap belum ada penawaran."""
	cheapest = {}

	for item in items:
		if not flt(item["rate"]):
			continue

		current = cheapest.get(item["item_code"])
		if not current or flt(item["rate"]) < flt(current["rate"]):
			cheapest[item["item_code"]] = item

	return list(cheapest.values())


@frappe.whitelist()
def get_quotation_item_details(supplier_quotation, item_code):
	"""Harga + supplier dari sebuah SQTN buat satu baris Costing.

	Dipanggil form waktu kolom Supplier Quotation di baris item diganti, biar harganya langsung
	ngikut penawaran yang baru dipilih. Yang diambil **net rate** - harga per unit setelah diskon
	bertingkat per item maupun diskon atas total - dalam mata uang perusahaan.
	"""
	quotation = frappe.db.get_value(
		"Supplier Quotation", supplier_quotation, ["supplier", "docstatus"], as_dict=True
	)
	if not quotation:
		return {}

	item = frappe.db.get_value(
		"Supplier Quotation Item",
		{"parent": supplier_quotation, "item_code": item_code},
		["name", "base_net_rate", "base_rate", "base_price_list_rate", "uom"],
		as_dict=True,
	)
	if not item:
		frappe.msgprint(
			_("Item {0} is not in Supplier Quotation {1}, so the rate is left as it is.").format(
				item_code, supplier_quotation
			),
			title=_("Item Not Quoted"),
			indicator="orange",
		)
		return {"supplier": quotation.supplier}

	return {
		"supplier": quotation.supplier,
		"supplier_quotation_item": item.name,
		"uom": item.uom,
		**get_company_currency_rates(item),
	}


def get_company_currency_rates(item):
	"""Harga baris Supplier Quotation dalam mata uang perusahaan, buat Costing.

	`base_*` = harga valas x kurs SQTN-nya, jadi penawaran USD langsung jadi IDR. Rate pakai
	**net rate** (setelah diskon bertingkat per item + diskon tambahan atas net total); harga
	sebelum diskon disimpan terpisah di Price List Rate, dicetak di print format Costing.
	"""
	return {
		"rate": flt(item.base_net_rate) or flt(item.base_rate),
		"price_list_rate": flt(item.base_price_list_rate) or flt(item.base_rate),
	}


@frappe.whitelist()
def get_stock_item_details(item_code, company, warehouse=None):
	"""Gudang + harga pokok buat baris Costing yang gak lewat Supplier Quotation.

	Dipanggil form waktu item atau gudangnya diganti, biar angkanya langsung kelihatan tanpa
	nunggu dokumennya disimpan.
	"""
	warehouse = warehouse or get_default_warehouse(item_code, company)

	return {
		"warehouse": warehouse,
		"rate": flt(get_valuation_rate(item_code, warehouse)),
	}


def update_costing_rates(doc, method=None):
	"""Hook `before_submit` Quotation: harga final dibalikin ke Costing-nya.

	Harga jual di Costing itu rencana; yang beneran ditawarin ke customer bisa lebih rendah
	gara-gara diskon per item atau diskon atas total. Begitu penawarannya jadi (submit), harga
	itu ditulis balik ke Quotation Rate di Costing supaya profit di Costing ngikut kenyataan.

	Jalan otomatis karena satu Costing cuma boleh punya satu Quotation submitted (lihat
	`validate_single_submitted_quotation`) - jadi gak ada lagi pertanyaan "harga dari Quotation
	mana yang dipakai". Baris yang ketimpa ditandain `quotation_rate_manually_set`, biar gak
	ketarik balik ke Selling Rate waktu Costing dihitung ulang.
	"""
	changes = get_costing_rate_changes(doc)
	if not changes:
		return

	costing = frappe.get_doc("Costing", doc.custom_costing)
	rates = {change["costing_item"]: change["quotation_rate"] for change in changes}

	for item in costing.items:
		if item.name in rates:
			item.quotation_rate = rates[item.name]
			item.quotation_rate_manually_set = 1

	costing.save(ignore_permissions=True)
	costing.add_comment(
		"Info",
		_("Quotation Rate updated from {0}").format(get_link_to_form("Quotation", doc.name)),
	)

	# nulis ke dokumen lain jangan diem-diem, user mesti tau angka costingnya berubah
	frappe.msgprint(
		_("Quotation Rate in {0} updated for {1} item(s): {2}").format(
			get_link_to_form("Costing", costing.name),
			len(changes),
			", ".join(change["item_code"] for change in changes),
		),
		title=_("Costing Updated"),
		indicator="green",
		alert=True,
	)


def get_costing_rate_changes(quotation):
	"""Baris Costing yang harganya beda sama harga final di Quotation ini.

	Yang dibandingin `base_net_rate` Quotation - harga per unit setelah semua diskon, dalam mata
	uang perusahaan - lawan
	Quotation Rate di baris Costing-nya.
	"""
	doc = quotation if hasattr(quotation, "items") else frappe.get_doc("Quotation", quotation)

	if not doc.get("custom_costing"):
		return []

	costing = frappe.get_doc("Costing", doc.custom_costing)
	costing_items = get_costing_items_by_key(costing)
	changes = []

	for item in doc.items:
		costing_item = costing_items.get((item.item_code, item.get("custom_supplier_quotation")))
		costing_item = costing_item or costing_items.get((item.item_code, None))

		if not costing_item:
			continue

		# Costing selalu mata uang perusahaan, jadi yang dibandingin versi base-nya
		rate = flt(item.base_net_rate) or flt(item.base_rate)
		if flt(rate, costing_item.precision("quotation_rate")) == flt(
			costing_item.quotation_rate, costing_item.precision("quotation_rate")
		):
			continue

		changes.append(
			{
				"costing_item": costing_item.name,
				"idx": costing_item.idx,
				"item_code": item.item_code,
				"item_name": item.item_name,
				"costing_rate": flt(costing_item.quotation_rate),
				"quotation_rate": flt(rate),
			}
		)

	return changes


def get_costing_items_by_key(costing):
	"""Baris Costing, dikunci sama item code + SQTN-nya (item kembar bisa beda supplier)."""
	items = {}

	for item in costing.items:
		items[(item.item_code, item.supplier_quotation)] = item
		items.setdefault((item.item_code, None), item)

	return items

