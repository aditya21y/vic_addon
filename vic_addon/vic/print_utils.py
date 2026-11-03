"""Helper Jinja buat print format VIC."""

from frappe.utils import strip_html


def get_grand_total(doc, amount=None):
	"""Grand total yang dicetak di semua print format VIC.

	Rounded Total dipakai kalau isinya bukan 0 atau pembulatannya gak dimatiin (*Disable Rounded
	Total* gak dicentang); selain itu Grand Total. ERPNext ngenolin Rounded Total waktu
	pembulatannya dimatiin, jadi saat itu yang kecetak Grand Total.

	`amount` buat total yang dihitung sendiri sama print format-nya (VAT WAPU, ringkasan yang
	dipotong DP): dibulatin persis kayak ERPNext ngebulatin Rounded Total, kalau dokumennya pakai
	pembulatan. Doctype yang gak punya Rounded Total dibiarin apa adanya.
	"""
	from frappe.utils import flt, round_based_on_smallest_currency_fraction

	rounded = doc.get("rounded_total")
	uses_rounding = rounded is not None and (flt(rounded) or not doc.get("disable_rounded_total"))

	if amount is None:
		return flt(rounded) if uses_rounding else flt(doc.get("grand_total"))

	if not uses_rounding:
		return flt(amount)

	return round_based_on_smallest_currency_fraction(amount, doc.currency, doc.precision("rounded_total"))


# Centangan "Print Original Number" di PO, PR, PI, SO, DN, SI (muncul kalau dokumennya hasil amend)
ORIGINAL_NUMBER_FIELD = "custom_print_original_number"


def get_print_name(doc):
	"""Nomor dokumen yang dicetak: nomor aslinya kalau *Print Original Number* dicentang.

	Dokumen amend namanya `...-00001R1`, `...-00001R2`, dst., dan Amended From-nya nunjuk ke versi
	sebelumnya - jadi rantainya ditelusurin sampai dokumen pertama (yang gak punya Amended From).
	Gak dicentang, bukan hasil amend, atau doctype-nya gak punya centangan ini -> nomornya sendiri.
	"""
	if not (doc.get(ORIGINAL_NUMBER_FIELD) and doc.get("amended_from")):
		return doc.name

	return get_original_name(doc.doctype, doc.amended_from)


def get_print_names(doctype, names):
	"""Versi `get_print_name` buat nomor dokumen lain yang ikut dicetak (No. DO, No. PO, dst.) -
	tiap dokumen ngikut centangan *Print Original Number*-nya sendiri. Urutan & duplikat dijaga."""
	import frappe

	names = [name for name in names or [] if name]
	if not names or not frappe.get_meta(doctype).has_field(ORIGINAL_NUMBER_FIELD):
		return names

	flagged = {
		row.name: row.amended_from
		for row in frappe.get_all(
			doctype,
			filters={"name": ["in", list(set(names))], ORIGINAL_NUMBER_FIELD: 1, "amended_from": ["is", "set"]},
			fields=["name", "amended_from"],
		)
	}
	printed = [get_original_name(doctype, flagged[name]) if name in flagged else name for name in names]

	return list(dict.fromkeys(printed))


def get_original_name(doctype, name):
	"""Telusurin Amended From sampai dokumen pertama."""
	import frappe

	seen = set()
	while name and name not in seen:
		seen.add(name)
		previous = frappe.db.get_value(doctype, name, "amended_from")
		if not previous:
			break
		name = previous

	return name


def get_item_description(item):
	"""Isi kolom Description di tabel item: description dulu, kalau kosong baru item name.

	Description itu Text Editor (HTML), jadi dicetak apa adanya - format tebal/baris barunya ikut.
	Editor sering nyimpen tag kosong (`<p></p>`, `<br>`) waktu isinya dihapus; yang kayak gitu
	dianggap kosong. Doctype yang barisnya gak punya description (mis. Costing Item) langsung jatuh
	ke item name.
	"""
	description = item.get("description") or ""
	if strip_html(description).replace("&nbsp;", " ").strip():
		return description

	return item.get("item_name") or item.get("item_code") or ""


def get_inquiry_signatory(doc):
	"""Nama di bawah "Best regards," pada Inquiry (print format, PDF, dan Excel).

	Field Best Regards dulu; kosong -> Person in Charge (Inquiry lama yang udah keisi tetap
	nyetak nama yang sama); kosong juga -> nama user pembuat dokumen.
	"""
	import frappe

	return (
		doc.get("custom_best_regards")
		or doc.get("custom_person_in_charge")
		or frappe.db.get_value("User", doc.owner, "full_name")
		or ""
	)


# ---------------------------------------------------------------------------------------------
# Kwitansi (Sales Invoice)
# ---------------------------------------------------------------------------------------------

BULAN = (
	"Januari", "Februari", "Maret", "April", "Mei", "Juni",
	"Juli", "Agustus", "September", "Oktober", "November", "Desember",
)


def terbilang(amount, upper=False):
	"""Angka -> kata bahasa Indonesia + "Rupiah": 17760000000 -> "Tujuh Belas Miliar ... Rupiah"."""
	from num2words import num2words
	from frappe.utils import flt

	words = num2words(int(round(flt(amount))), lang="id") + " rupiah"
	return words.upper() if upper else words.title()


def tanggal(date, upper=False):
	"""Tanggal bahasa Indonesia: 2026-07-06 -> "06 Juli 2026"."""
	from frappe.utils import getdate

	if not date:
		return ""
	date = getdate(date)
	text = f"{date.day:02d} {BULAN[date.month - 1]} {date.year}"
	return text.upper() if upper else text


def get_spp(doc):
	"""(SPP / SPK No., tanggal) buat kwitansi: isian tab Kwitansi di invoice, kosong -> Customer's
	Purchase Order (`po_no` / `po_date`) invoice-nya, kosong juga -> punya Sales Order-nya.

	Customer's PO udah kesalin sendiri dari Sales Order waktu invoice dibikin; Sales Order-nya
	dipakai buat PO No. yang baru diisi di SO setelah invoice-nya kebentuk (field itu bisa diubah
	setelah submit). Diambil sepasang: nomor & tanggal gak kecampur dari dua sumber.
	"""
	import frappe

	if doc.get("custom_kwitansi_spp_no"):
		return doc.custom_kwitansi_spp_no, doc.get("custom_kwitansi_spp_date")

	if doc.get("po_no"):
		return doc.po_no, doc.get("po_date")

	sales_order = next((row.sales_order for row in doc.get("items") or [] if row.get("sales_order")), None)
	if not sales_order:
		return None, None

	return frappe.db.get_value("Sales Order", sales_order, ["po_no", "po_date"]) or (None, None)


def set_spp_from_sales_order(doc, method=None):
	"""Hook `before_validate` Sales Invoice: SPP / SPK yang masih kosong diisi dari Customer's PO.

	Sumbernya sama kayak yang dicetak kwitansi (`get_spp`), cuma ditulis ke tab Kwitansi biar
	kelihatan di form. Isian user gak pernah ketiban.
	"""
	if doc.get("custom_kwitansi_spp_no"):
		return

	spp_no, spp_date = get_spp(doc)
	if spp_no:
		doc.custom_kwitansi_spp_no = spp_no
		doc.custom_kwitansi_spp_date = doc.get("custom_kwitansi_spp_date") or spp_date


def get_kwitansi(doc):
	"""Semua isian kwitansi Sales Invoice, dipakai print format Kwitansi & Kwitansi (Progress).

	Yang diketik user ada di tab Kwitansi (bisa diisi setelah submit); sisanya diambil dari invoice,
	Company, dan Bank Account-nya.
	"""
	import frappe
	from frappe.utils import flt

	company = frappe.get_cached_doc("Company", doc.company)

	# nilai yang beneran ditagih: total dikurangi DP yang dibalik & uang muka yang udah dialokasiin
	amount = flt(doc.get("custom_kwitansi_amount")) or (
		get_grand_total(doc)
		- flt(doc.get("custom_total_dp_allocated"))
		- flt(doc.get("total_advance"))
	)

	bank = frappe._dict()
	if doc.get("custom_kwitansi_bank_account"):
		bank = frappe.db.get_value(
			"Bank Account",
			doc.custom_kwitansi_bank_account,
			["bank", "bank_account_no", "branch_code"],
			as_dict=True,
		) or frappe._dict()

	delivery_notes = sorted({row.delivery_note for row in doc.get("items") or [] if row.get("delivery_note")})
	project = (frappe.db.get_value("Project", doc.project, "project_name") or doc.project) if doc.get("project") else ""
	# invoice yang udah submit sebelum SPP-nya diisi di SO tetap kecetak nomornya
	spp_no, spp_date = get_spp(doc)

	return frappe._dict(
		no=doc.get("custom_kwitansi_no") or "",
		date=doc.get("custom_kwitansi_date") or doc.posting_date,
		city=company.get("custom_kwitansi_city") or "Jakarta",
		amount=amount,
		received_from=(doc.get("custom_kwitansi_received_from") or "").strip() or doc.customer_name or doc.customer,
		project=project,
		payment_for=(doc.get("custom_kwitansi_payment_for") or "").strip(),
		invoice_no=get_print_name(doc),
		delivery_notes=get_print_names("Delivery Note", delivery_notes),
		faktur_no=doc.get("custom_faktur_pajak_no") or "",
		spp_no=spp_no or "",
		spp_date=spp_date,
		period_from=doc.get("custom_kwitansi_period_from"),
		period_to=doc.get("custom_kwitansi_period_to"),
		bank=bank.get("bank") or "",
		bank_branch=bank.get("branch_code") or "",
		account_no=bank.get("bank_account_no") or "",
		account_name=company.company_name,
		signer=company.get("custom_kwitansi_signer") or "",
		signer_title=company.get("custom_kwitansi_signer_title") or "",
		currency=doc.currency,
	)


# ---------------------------------------------------------------------------------------------
# Receipt Note (Purchase Invoice) - tanda terima tukar faktur
# ---------------------------------------------------------------------------------------------

def get_receipt_note(doc):
	"""Isian print format Receipt Note (tanda terima tukar faktur) dari Purchase Invoice.

	Satu invoice = satu baris tabel. Invoice No. & Date = Supplier Invoice No & Date (dua-duanya
	bisa diisi setelah submit; kosong -> dibiarin kosong buat ditulis tangan, bukan nomor PI). DO No.
	= field Supplier DO No., kosong -> Supplier Delivery Note di Purchase Receipt yang nyambung ke
	baris item invoice-nya. PO No. = nomor Purchase Order di baris item.
	"""
	import frappe
	from frappe.utils import flt

	items = doc.get("items") or []
	purchase_orders = sorted({row.purchase_order for row in items if row.get("purchase_order")})
	purchase_receipts = sorted({row.purchase_receipt for row in items if row.get("purchase_receipt")})
	supplier_do_no = (doc.get("custom_supplier_do_no") or "").strip()
	delivery_notes = [supplier_do_no] if supplier_do_no else (
		frappe.get_all(
			"Purchase Receipt",
			filters={"name": ["in", purchase_receipts], "supplier_delivery_note": ["is", "set"]},
			pluck="supplier_delivery_note",
			order_by="posting_date, name",
		)
		if purchase_receipts
		else []
	)

	amount = get_grand_total(doc)
	row = frappe._dict(
		invoice_no=doc.get("bill_no") or "",
		date=doc.get("bill_date"),
		nominal=amount,
		tax_invoice_no=doc.get("custom_faktur_pajak_no") or "",
		do_no=", ".join(dict.fromkeys(delivery_notes)),
		po_no=", ".join(get_print_names("Purchase Order", purchase_orders)),
	)

	return frappe._dict(
		rows=[row],
		amount=amount,
		in_words=doc.get("in_words") or frappe.utils.money_in_words(amount, doc.currency),
		received_from=get_received_from(doc),
		supplier=doc.supplier_name or doc.supplier,
	)


def get_received_from(doc):
	"""Kotak RECEIVED FROM yang dicentang: invoice subkon -> Subcontractor, terus dari nama Supplier
	Group-nya (ekspedisi/forwarder -> Expedite, subkon -> Subcontractor), sisanya Supplier."""
	import frappe

	if doc.get("is_subcontracted"):
		return "Subcontractor"

	group = (frappe.db.get_value("Supplier", doc.supplier, "supplier_group") or "").lower()
	if any(word in group for word in ("subcon", "subkon")):
		return "Subcontractor"
	if any(word in group for word in ("expedi", "ekspedisi", "forward", "logisti", "cargo", "kargo")):
		return "Expedite"

	return "Supplier"


# ---------------------------------------------------------------------------------------------
# Proforma Invoice (Sales Order)
# ---------------------------------------------------------------------------------------------


def get_proforma(doc):
	"""Isian Proforma Invoice dari Sales Order: ringkasan total, terbilang, rekening, dll.

	DOWN PAYMENT = DPP Invoice DP order ini yang udah submit (skema Item DP). Rumus ringkasannya
	lihat `get_invoice_summary`.
	"""
	import frappe
	from frappe.utils import flt

	down_payment = sum(
		flt(row.net_total)
		for row in frappe.get_all(
			"Sales Invoice",
			filters={"custom_is_dp": 1, "custom_dp_order": doc.name, "docstatus": 1},
			fields=["net_total"],
		)
	) if frappe.get_meta("Sales Invoice").has_field("custom_dp_order") else 0

	delivery_notes = frappe.get_all(
		"Delivery Note Item",
		filters={"against_sales_order": doc.name, "docstatus": 1},
		pluck="parent",
		distinct=True,
		order_by="parent",
	)

	return get_invoice_summary(doc, down_payment, delivery_notes)


def get_sales_invoice_print(doc):
	"""Isian print format Invoice (VIC) dari Sales Invoice - formulirnya sama kayak Proforma.

	DOWN PAYMENT = DPP DP yang dibalik di invoice ini (tabel DP Allocations, kolom Allocated).
	DO No. dari baris item, Payment Terms = Due Date + jumlah harinya dari Posting Date.
	"""
	from frappe.utils import date_diff, flt

	down_payment = sum(flt(row.allocated_amount) for row in doc.get("custom_dp_allocations") or [])
	delivery_notes = sorted({row.delivery_note for row in doc.get("items") or [] if row.get("delivery_note")})

	summary = get_invoice_summary(doc, down_payment, delivery_notes)
	summary.due_days = date_diff(doc.due_date, doc.posting_date) if doc.get("due_date") else None

	return summary


def get_invoice_summary(doc, down_payment, delivery_notes):
	"""Ringkasan total + rekening & penandatangan buat Proforma Invoice dan Invoice (VIC).

	Ringkasannya ngikut formulir VIC:

		TOTAL         = Total (sebelum diskon tambahan)
		DISCOUNT      = Total - Net Total
		DOWN PAYMENT  = DPP uang muka yang dipotong (lihat pemanggilnya)
		SUB TOTAL     = Net Total - Down Payment
		PPN           = PPN dokumen, dihitung ulang sebanding Sub Total kalau ada DP;
		                Show VAT for WAPU tanpa baris PPN -> 11% x Sub Total
		GRAND TOTAL   = Sub Total + PPN, dibulatin kayak Rounded Total dokumennya (`get_grand_total`)

	Rekening & penandatangan ikut setting Kwitansi di Company.
	"""
	import frappe
	from frappe.utils import flt

	company = frappe.get_cached_doc("Company", doc.company)

	total = flt(doc.total)
	net_total = flt(doc.net_total)
	sub_total = net_total - flt(down_payment)

	vat_rows = [
		tax for tax in doc.get("taxes") or []
		if not tax.get("is_tax_withholding_account") and tax.get("add_deduct_tax") != "Deduct"
	]
	vat = sum(flt(tax.tax_amount_after_discount_amount or tax.tax_amount) for tax in vat_rows)
	vat_rate = next((flt(tax.rate) for tax in vat_rows if flt(tax.rate)), 11)
	if vat_rows and down_payment and net_total:
		vat = vat * sub_total / net_total
	elif not vat_rows and doc.get("custom_show_vat_for_wapu"):
		vat = sub_total * 0.11

	vat = flt(vat, doc.precision("total_taxes_and_charges"))
	grand_total = get_grand_total(doc, flt(sub_total + vat, doc.precision("grand_total")))

	bank = frappe._dict()
	if company.get("custom_kwitansi_bank_account"):
		bank = frappe.db.get_value(
			"Bank Account",
			company.custom_kwitansi_bank_account,
			["bank", "bank_account_no", "branch_code"],
			as_dict=True,
		) or frappe._dict()

	return frappe._dict(
		total=total,
		discount=total - net_total,
		down_payment=flt(down_payment),
		sub_total=sub_total,
		vat=vat,
		vat_rate=vat_rate,
		grand_total=grand_total,
		in_words=amount_in_english(grand_total, doc.currency),
		delivery_notes=get_print_names("Delivery Note", delivery_notes),
		bank=bank.get("bank") or "",
		bank_branch=bank.get("branch_code") or "",
		account_no=bank.get("bank_account_no") or "",
		account_name=company.company_name,
		signer=company.get("custom_kwitansi_signer") or "",
	)


def amount_in_english(amount, currency="IDR"):
	"""16.676.640 -> "Sixteen million six hundred seventy-six thousand six hundred forty rupiah"."""
	from frappe.utils import flt
	from num2words import num2words

	whole = int(flt(amount))
	words = num2words(whole, lang="en").replace(",", "").replace(" and ", " ")
	unit = "rupiah" if currency == "IDR" else (currency or "")
	cents = round((flt(amount) - whole) * 100)
	if cents and currency != "IDR":
		words += f" and {cents:02d}/100"
	return f"{words[:1].upper()}{words[1:]} {unit}".strip()


# ---------------------------------------------------------------------------------------------
# Payment terms panjang -> Note
# ---------------------------------------------------------------------------------------------

PAYMENT_TERMS_LIMIT = 20


def split_payment_terms(text):
	"""Term pembayaran buat print format: yang pendek dicetak di tempatnya, yang panjang pindah ke Note.

	Tempat term di kop print format sempit (kotak Payment Terms, kolom kanan). Term lebih dari
	`PAYMENT_TERMS_LIMIT` karakter (mis. "20% DP, 30% Copy BL, ... 5% Retensi") ditulis "Lihat di Note"
	di tempatnya, dan teks lengkapnya dicetak jadi poin pertama baris Note - baris terakhir tabel
	item, di kolom Description. Dipakai Proforma Invoice, Quotation (VIC), Purchase Order (VIC),
	Costing (Sales).
	"""
	import frappe

	text = (text or "").strip()
	if len(text) > PAYMENT_TERMS_LIMIT:
		return frappe._dict(header="Lihat di Note", note=text)
	return frappe._dict(header=text, note="")


# ---------------------------------------------------------------------------------------------
# Barang tambahan & Delivery Order dari Sales Invoice
# ---------------------------------------------------------------------------------------------


def get_printed_items(doc):
	"""Baris item yang dicetak di print format Sales Invoice: baris **Barang Tambahan** dibuang.

	Cuma barisnya yang gak dicetak - dokumennya sendiri (qty, stok, nilai, total) gak berubah.
	"""
	return [item for item in doc.get("items") or [] if not item.get("custom_is_additional_item")]


def get_invoice_delivery_order(doc):
	"""Isian print format Delivery Order (Invoice): surat jalan yang dicetak dari Sales Invoice.

	DO No. = Delivery Note di baris item invoice (kosong -> nomor invoice, mis. invoice yang
	langsung update stock). Tanggal, Vehicle No., & Delivered To dari Delivery Note pertama. Serial No diambil
	dari baris invoice-nya, kalau kosong dari baris Delivery Note-nya.
	"""
	import frappe

	from vic_addon.vic.serial_no import get_serial_nos

	items = get_printed_items(doc)
	delivery_notes = sorted({item.delivery_note for item in doc.get("items") or [] if item.get("delivery_note")})

	delivery_note = frappe._dict()
	if delivery_notes:
		meta = frappe.get_meta("Delivery Note")
		fields = ["posting_date", "vehicle_no"]
		fields += [field for field in ("custom_print_format_date", "custom_delivered_to") if meta.has_field(field)]
		delivery_note = frappe.db.get_value("Delivery Note", delivery_notes[0], fields, as_dict=True) or frappe._dict()

	serials = {}
	for item in items:
		numbers = get_serial_nos(item)
		if not numbers and item.get("dn_detail"):
			numbers = get_serial_nos(frappe.get_doc("Delivery Note Item", item.dn_detail))
		serials[item.name] = numbers

	# key-nya `rows`, bukan `items`: di Jinja `dlv.items` kebaca method dict.items, bukan isinya
	return frappe._dict(
		rows=items,
		do_no=", ".join(get_print_names("Delivery Note", delivery_notes)) or get_print_name(doc),
		date=delivery_note.get("custom_print_format_date") or delivery_note.get("posting_date") or doc.posting_date,
		vehicle_no=delivery_note.get("vehicle_no") or "",
		delivered_to=delivery_note.get("custom_delivered_to") or "",
		serials=serials,
	)
