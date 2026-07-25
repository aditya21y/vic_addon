"""Naming series reset per bulan + amend pakai suffix `R`.

Frappe cuma punya variable `.YY.` / `.MM.` / `.YYYY.` yang selalu ambil tanggal HARI INI,
padahal nomor dokumen harusnya ikut tanggal dokumennya sendiri (posting date / transaction
date). Di sini ditambah dua variable baru lewat hook `naming_series_variables`:

	.YYMM.    -> 2502   (dari tanggal dokumen)
	.YYYYMM.  -> 202502 (dari tanggal dokumen)

Contoh `SAL-ORD-.YYMM.-` menghasilkan `SAL-ORD-2502-00001`, `SAL-ORD-2502-00002`, dst.

Karena bulan masuk ke prefix, counter di tabel `Series` otomatis kepisah per bulan, jadi:

- ganti bulan -> nomor balik ke 1
- dokumen backdate -> lanjut dari nomor terakhir di bulan itu, bukan bulan sekarang

Buat dokumen amend, nomornya `SAL-ORD-2502-00001R1` (bukan `...-00001-1` kayak default).
"""

import frappe
from frappe.model.naming import NamingSeries, parse_naming_series
from frappe.utils import cint, getdate, now_datetime

# Doctype yang pakai aturan naming di modul ini.
NAMING_DOCTYPES = (
	# Selling
	"Quotation",
	"Sales Order",
	"Delivery Note",
	"Sales Invoice",
	# Buying
	"Supplier Quotation",
	"Purchase Order",
	"Purchase Receipt",
	"Purchase Invoice",
	# Stock
	"Material Request",
	"Stock Entry",
	"Stock Reconciliation",
)

# Field tanggal yang jadi acuan bulan. Diambil yang pertama ketemu di dokumen,
# jadi Delivery Note / Stock Entry ikut `posting_date`, Sales Order ikut `transaction_date`.
DATE_FIELDS = ("posting_date", "transaction_date", "date")

# Override kalau ada doctype yang field tanggalnya beda dari urutan di atas.
DATE_FIELD_OVERRIDES: dict[str, str] = {}

AMEND_SUFFIX = "R"


def get_naming_date(doc):
	"""Tanggal yang dipakai buat variable bulan/tahun di naming series."""
	if doc:
		fieldnames = (DATE_FIELD_OVERRIDES.get(doc.doctype),) if DATE_FIELD_OVERRIDES.get(doc.doctype) else DATE_FIELDS
		for fieldname in fieldnames:
			value = doc.get(fieldname)
			if value:
				return getdate(value)

	return now_datetime().date()


def parse_yymm(doc, part=None):
	"""Variable `.YYMM.` -> contoh `2502` untuk Februari 2025."""
	return get_naming_date(doc).strftime("%y%m")


def parse_yyyymm(doc, part=None):
	"""Variable `.YYYYMM.` -> contoh `202502`."""
	return get_naming_date(doc).strftime("%Y%m")


def sync_series_counter(doc, method=None):
	"""Samain counter `Series` dengan nomor terakhir yang beneran ada di bulan tersebut.

	Hook `before_naming`. Normalnya counter di tabel `Series` udah bener, tapi kalau ada
	dokumen hasil import / migrasi (namanya diisi manual) counter-nya bisa ketinggalan dan
	bikin nomor duplikat. Ini mastiin nomor baru = nomor terakhir di bulan itu + 1.
	"""
	if doc.name or doc.get("amended_from"):
		return

	series = doc.get("naming_series")
	if not series:
		return

	prefix, digits = get_series_prefix(doc, series)
	if not prefix or not digits:
		return

	last_number = get_last_number_in_series(doc.doctype, prefix, digits)
	if last_number > get_series_current(prefix):
		set_series_current(prefix, last_number)


def set_amended_name(doc, method=None):
	"""Kasih nomor dokumen amend pakai suffix `R`: `SAL-ORD-2502-00001R1`, `...R2`, dst.

	Hook `autoname`. Cuma jalan buat dokumen amend, dokumen baru tetap pakai naming series
	standar frappe. Biar bisa sampai sini, `Document Naming Settings` di-set `Default Naming`
	buat doctype ini lewat `setup_amend_naming_rule`.
	"""
	if doc.name or not doc.get("amended_from"):
		return

	base = doc.amended_from
	revision = 0

	if frappe.db.get_value(doc.doctype, doc.amended_from, "amended_from"):
		# amend dari dokumen yang udah pernah di-amend, lanjutin nomor revisinya
		previous_base, suffix, previous_revision = doc.amended_from.rpartition(AMEND_SUFFIX)
		if suffix and previous_revision.isdigit():
			base, revision = previous_base, cint(previous_revision)

	revision += 1
	while frappe.db.exists(doc.doctype, f"{base}{AMEND_SUFFIX}{revision}"):
		revision += 1

	doc.name = f"{base}{AMEND_SUFFIX}{revision}"


def setup_amend_naming_rule():
	"""Set `Default Naming` buat doctype di `NAMING_DOCTYPES` biar suffix `R` yang dipakai.

	Kalau aturannya `Amend Counter` (default frappe), frappe udah nentuin nama `...-1`
	sebelum hook `autoname` jalan, jadi suffix `R` gak akan kepakai.

	Gak bisa dijadiin fixture karena `Document Naming Settings` itu Single doctype, makanya
	dijalanin lewat hook `after_install` & `after_migrate`.
	"""
	settings = frappe.get_single("Document Naming Settings")
	overrides = {row.document_type: row for row in settings.amend_naming_override}
	changed = False

	for doctype in NAMING_DOCTYPES:
		row = overrides.get(doctype)
		if row and row.action == "Default Naming":
			continue

		if row:
			row.action = "Default Naming"
		else:
			settings.append(
				"amend_naming_override", {"document_type": doctype, "action": "Default Naming"}
			)
		changed = True

	if changed:
		settings.flags.ignore_permissions = True
		settings.save()


def get_series_prefix(doc, series):
	"""Prefix yang jadi key counter di tabel `Series`, contoh `SAL-ORD-2502-` dan 5 digit."""
	captured = {}

	def capture_prefix(partial_series, digits):
		captured["prefix"] = partial_series
		captured["digits"] = digits
		return "#" * digits

	# NamingSeries() nambahin `.#####` kalau seriesnya belum ada bagian nomornya
	parse_naming_series(NamingSeries(series).series, doc=doc, number_generator=capture_prefix)

	return captured.get("prefix"), captured.get("digits")


def get_last_number_in_series(doctype, prefix, digits):
	"""Nomor terakhir yang kepakai buat prefix ini, contoh 12 dari `SAL-ORD-2502-00012`.

	Filter panjang nama biar dokumen amend (`...00012R1`) gak keitung.
	"""
	last_name = frappe.db.sql(
		f"""select max(`name`) from `tab{doctype}` where `name` like %s and length(`name`) = %s""",
		(f"{prefix}%", len(prefix) + digits),
	)

	if not (last_name and last_name[0][0]):
		return 0

	return cint(last_name[0][0][len(prefix) :])


def get_series_current(prefix):
	return cint(frappe.db.get_value("Series", prefix, "current", order_by="name"))


def set_series_current(prefix, value):
	series = frappe.qb.DocType("Series")

	if frappe.db.get_value("Series", prefix, "name", order_by="name") is None:
		frappe.qb.into(series).insert(prefix, cint(value)).columns("name", "current").run()
	else:
		frappe.qb.update(series).set(series.current, cint(value)).where(series.name == prefix).run()
