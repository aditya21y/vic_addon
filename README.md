### VIC

app for VIC

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:
### fix issue errpnext 16 
bench --site nic_vic.localhost execute erpnext.setup.install.create_address_and_contact_custom_fields

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-16
bench install-app vic_addon
```

### Fitur

#### Diskon bertingkat per item (Supplier Quotation)

Supplier bisa kasih diskon bertingkat max 3 level per item. Diskonnya dihitung berantai
(compounded), bukan dijumlah:

| Field | Contoh |
| --- | --- |
| Price List Rate | 1.000.000 |
| Discount Level 1 (%) | 10 |
| Discount Level 2 (%) | 5 |
| Discount Level 3 (%) | 2 |
| **Total Discount on Price List Rate (%)** (otomatis, read only) | **16,21** |
| Rate | 837.900 |

Rumus: `total diskon = (1 - (1-d1)(1-d2)(1-d3)) x 100`.

Total diskon ditulis ke field standar `discount_percentage`, jadi rate, amount, taxes,
dan diskon tambahan tetap dihitung logika bawaan ERPNext.

- Kalau supplier cuma kasih diskon flat 1 tingkat, isi Level 1 saja.
- Baris tanpa diskon bertingkat tetap bisa diisi `rate` manual seperti standar.
- Diskon tambahan atas net total pakai field bawaan **Apply Additional Discount On**
  (default sudah diarahkan ke `Net Total`) + **Additional Discount Percentage / Amount**,
  jadi diskonnya dihitung sebelum Taxes and Charges.

Implementasi:

- `vic_addon/vic/multi_level_discount.py` — kalkulasi + validasi (hook `before_validate`)
- `vic_addon/public/js/supplier_quotation.js` — kalkulasi realtime di form
- `vic_addon/fixtures/` — custom field & property setter

Kalau ada perubahan customization lewat Customize Form, export ulang fixtures-nya:

```bash
bench --site $SITE export-fixtures --app vic_addon
```

#### DPP Nilai Lain (PPN 12%)

Field baru di **Sales Order, Sales Invoice, Purchase Order, Purchase Invoice**:

| Field | Isi |
| --- | --- |
| DPP Nilai Lain | `11/12 x Net Total`, read only, dihitung otomatis |
| DPP Nilai Lain (Company Currency) | versi mata uang perusahaan |

Sesuai PMK 131/2024, tarif PPN 12% dikenakan atas DPP Nilai Lain (11/12 dari nilai
transaksi), jadi pajaknya setara 11%:

```
Net Total                        10.000
DPP Nilai Lain = 11/12 x 10.000   9.166,67
PPN 12% x 9.166,67                1.100      (= 11% x 10.000)
```

Baris pajaknya sendiri tetap pakai setup ERPNext standar: **Purchase/Sales Taxes and Charges
Template** dengan `Charge Type = On Net Total` dan `Rate = 11`, description misal
`PPN 12% (DPP Nilai Lain)`. Hasil rupiahnya identik dengan 12% x DPP Nilai Lain, tapi
perhitungan per item, item-wise tax breakup, dan GL entry tetap logika bawaan ERPNext.
Field DPP Nilai Lain dipakai buat print / e-Faktur / laporan pajak.

Rasionya konstanta di `vic_addon/vic/dpp_nilai_lain.py`:

```python
DPP_NILAI_LAIN_RATIO = 11 / 12
```

Kalau aturannya berubah (misal PPN 12% penuh tanpa DPP Nilai Lain), ganti jadi `1` dan
sesuaikan rate di tax template jadi 12.

Implementasi:

- `vic_addon/vic/dpp_nilai_lain.py` — kalkulasi (hook `validate`)
- `vic_addon/public/js/dpp_nilai_lain.js` — update angkanya live di form
- `vic_addon/fixtures/custom_field.json` — 8 custom field (2 per doctype)

#### Naming series reset per bulan + amend suffix R

Variable naming series baru yang ambil bulan dari **field tanggal dokumennya sendiri**
(bukan tanggal hari ini):

| Variable | Hasil | Contoh series |
| --- | --- | --- |
| `.YYMM.` | `2602` | `SAL-ORD-.YYMM.-` → `SAL-ORD-2602-00001` |
| `.YYYYMM.` | `202602` | `SAL-ORD-.YYYYMM.-` → `SAL-ORD-202602-00001` |

Acuan tanggalnya: `posting_date` → `transaction_date` → `date` (dipakai yang pertama ada di
doctype tersebut). Jadi Delivery Note / Stock Entry ikut posting date, Sales Order /
Purchase Order ikut transaction date.

Karena bulan masuk ke prefix, counter di tabel `Series` kepisah per bulan:

| Dokumen | Nomor |
| --- | --- |
| Sales Order, transaction date 2026-02-10 | SAL-ORD-2602-00001 |
| Sales Order, transaction date 2026-02-20 | SAL-ORD-2602-00002 |
| Sales Order, transaction date 2026-07-25 | SAL-ORD-**2607**-**00001** (reset) |
| Sales Order backdate ke 2026-02-28 | SAL-ORD-2602-**00003** (lanjut nomor terakhir Feb) |
| Delivery Note, posting date 2026-02-15 | MAT-DN-2602-00001 |

Dokumen amend pakai suffix `R`, bukan `-1` bawaan ERPNext:

```
SAL-ORD-2602-00001  ->  SAL-ORD-2602-00001R1  ->  SAL-ORD-2602-00001R2
```

Doctype yang dicover (Selling, Buying, Stock): Quotation, Sales Order, Delivery Note,
Sales Invoice, Supplier Quotation, Purchase Order, Purchase Receipt, Purchase Invoice,
Material Request, Stock Entry, Stock Reconciliation. Series lama (`.YYYY.-`) tetap
disimpan sebagai opsi biar dokumen existing gak gagal validasi.

Implementasi:

- `vic_addon/vic/naming.py` — variable `.YYMM.`, sinkronisasi counter, amend suffix R
- `naming_series_variables` + `doc_events` (`before_naming`, `autoname`) di `hooks.py`
- Property setter `naming_series` (options + default) per doctype di `vic_addon/fixtures/`

Nambah doctype lain: tambahin ke `NAMING_DOCTYPES` di `vic_addon/vic/naming.py`, set
seriesnya lewat **Document Naming Settings**, terus export ulang fixtures.

Catatan:

- Aturan amend (`Document Naming Settings` → `Default Naming` per doctype) di-set lewat hook
  `after_install` / `after_migrate`, karena Single doctype gak bisa jadi fixture.
- `.YYMM.` selalu ikut tanggal dokumen. Beda sama variable bawaan `.YY.` / `.MM.` yang cuma
  ikut posting date kalau **Global Defaults → Use Posting Datetime for Naming Documents**
  dinyalain (default mati, jadi ambil tanggal hari ini). Kalau tetap mau pakai `.YY.`/`.MM.`
  di series lain, nyalain dulu opsi itu biar konsisten.

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/vic_addon
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
