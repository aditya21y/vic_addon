### VIC

app for VIC

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:
```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-16
bench install-app vic_addon
```

### fix issue errpnext 16 
bench --site nic_vic.localhost execute erpnext.setup.install.create_address_and_contact_custom_fields
### staging setting to accessable
C:\Windows\System32\drivers\etc\hosts
[IP_ADDRESS] vic-app nic-app
http://nic-app:8000
http://vic-app:8000


### Multitenant Setting
# nyalain resolusi berdasarkan hostname
bench config dns_multitenant on

bench --site site1.local set-config host_name http://site1.local:8000
bench --site site2.local set-config host_name http://site2.local:8000

bench start


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

#### Costing (custom doctype)

Ngitung HPP dari harga Supplier Quotation + distribusi additional cost, terus nentuin harga
jual dari margin. Rumusnya ngikut sheet **5a. COSTING** di source of truth. Non-submittable
(sesuai bispro) biar item tetap bisa diedit & dihitung ulang kalau supplier/harga berubah.

Doctype: **Costing** (`CST-.YYMM.-`), dengan child table **Costing Item** dan
**Costing Additional Cost**.

Rumus:

```
Total Buying Amount        = sum(Rate x Qty)
Total Additional Costs     = sum(Additional Costs)
Additional Cost Percentage = Total Additional Costs / Total Buying Amount x 100

per item:
Distributed Cost Rate = Rate x Additional Cost Percentage x (1 + Additional Percentage)
HPP Rate              = Rate + Distributed Cost Rate
Selling Rate          = HPP Rate / (1 - Margin %)
Profit Amount         = Selling Amount - HPP Amount
Profit %              = Profit Amount / HPP Amount x 100
```

Additional cost dibagi proporsional lewat rate tiap item, jadi total distributed cost =
`Total Additional Costs x (1 + Additional Percentage)`. **Additional Percentage** itu buffer
manual di atas distribusi additional cost (alasannya ditulis di field Remarks).

Contoh (persis kayak sheet 5a — Additional Costs: Freight 3.000 + Selling 2.000 + Komisi 1.000,
Additional Percentage 5%):

| Item | Rate | Qty | Dist. Cost Rate | HPP Rate | Margin % | Selling Rate | Profit % |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Item A | 2.000 | 2 | 630 | 2.630 | 20 | 3.287,50 | 25,00 |
| Item B | 4.000 | 4 | 1.260 | 5.260 | 15 | 6.188,24 | 17,65 |

Total: buying 20.000, additional cost 6.000 (30%), distributed 6.300, HPP 26.300,
selling 31.327,96, profit 5.027,96 (19,12%).

**Quotation Rate** default ngikut Selling Rate (termasuk kalau margin/rate diubah), karena
angka inilah yang kebawa ke Quotation ke customer. Kalau user isi manual (harga nego), field
`Quotation Rate Manually Set` otomatis nyala dan nilainya berhenti ngikut Selling Rate.
Kosongin Quotation Rate-nya buat balik ke mode auto.

**Ambil item dari Supplier Quotation**, dua arah:

- Dari form Costing: tombol **Get Items from Supplier Quotation**, bisa pilih beberapa SQTN
  sekaligus (satu costing boleh campur beberapa supplier).
- Dari form Supplier Quotation yang udah submit: tombol **Create > Costing**.

Yang ditarik: item, qty, rate, Supplier Quotation ID, supplier, dan baris item SQTN-nya
(buat jejak audit).

Rate yang dipakai adalah **net rate** SQTN, yaitu harga setelah diskon bertingkat per item
**dan** diskon tambahan atas net total — jadi HPP-nya sesuai harga beli yang beneran dibayar.

Implementasi:

- `vic_addon/vic/doctype/costing/costing.py` — kalkulasi, validasi margin, fetch item SQTN,
  mapper `make_costing` buat tombol Create di SQTN
- `vic_addon/vic/doctype/costing/costing.js` — kalkulasi live + dialog pilih SQTN
- `vic_addon/public/js/supplier_quotation.js` — tombol Create > Costing

**Bikin Quotation ke customer**: tombol **Create > Quotation** di form Costing. Yang dibawa:

| Costing | Quotation |
| --- | --- |
| Customer | Quotation To = Customer + Party Name |
| Quotation Rate per item | Price List Rate **dan** Rate item Quotation |
| Qty, UOM | Qty, UOM |
| Supplier Quotation + Supplier per item | field SQTN + Supplier di Quotation Item |
| Nama costing | field Costing di Quotation (jejak balik) |

Quotation Rate masuk sebagai **Price List Rate sekaligus Rate**, jadi diskon per item di
Quotation ngurangin dari harga costing, terus masih bisa ditambah diskon atas total quotation
(Apply Additional Discount On = Net Total). Contoh: rate costing 3.287,50 → diskon item 10%
jadi 2.958,75 → diskon total 5% → net total turun lagi, dan DPP Nilai Lain ikut nyesuaiin.

Belum termasuk (nunggu prioritas):

- Buffer exchange rate buat pembelian impor (R&C 2 & 3 di sheet bispro)
- Tab/report rekap HPP & harga jual per periode (TAB 2 Summary masih kosong di sheet)
- Pembatasan permission biar tim Sales gak lihat rate beli / costing / profit %
  (perlu permlevel + role, sengaja belum dipasang biar gak ngunci field ke semua user)
- Workflow approval (doctype-nya udah non-submittable, tinggal bikin Workflow-nya)

#### DP Invoice (Payment Request) + sisa PPN/PPh di invoice final

Alur: **PO/SO → Payment Request (DP Invoice) → Payment Entry (DP) → Invoice final**

Field baru di **Payment Request**:

| Field | Isi |
| --- | --- |
| DP Type | `Purchase` / `Sales`, otomatis dari dokumen referensi (PO = Purchase, SO = Sales) |
| DP Amount (relabel dari Amount) | nilai DP |
| DP Percentage | isi persen → DP Amount kehitung dari grand total dokumen referensi |
| Purchase / Sales Taxes and Charges Template | template PPN/PPh atas DP |
| Advance Taxes and Charges | tabel PPN/PPh atas nilai DP |
| Total Taxes and Charges, Total Payable | total pajak dan total yang dibayar (DP + pajak) |

Persentase dan amount selalu nyambung: di form, ngisi persen bakal ngisi amount-nya; di
server, persen selalu dihitung balik dari amount, jadi angkanya gak pernah beda.

**Kalau dokumen referensinya punya payment terms**, ERPNext ngisi tabel Payment Reference dan
maksa totalnya sama persis dengan DP Amount (*"Grand Total must match sum of Payment
References"*). Tabel itu read only di form, jadi tiap DP Amount berubah, barisnya disamain
otomatis (diprorata kalau terminnya lebih dari satu).

Nilai DP-nya sengaja **gak dikunci ke payment term** — DP hasil nego sering beda dari termin,
dan ngunci berarti tiap ganti DP harus cancel + amend SO/PO. Gantinya ada dua penjaga:

- **Gak boleh over-request**: total DP (yang udah submitted + dokumen ini) gak boleh lebih
  dari sisa nilai dokumen referensi. ERPNext ngelewatin pengecekan ini begitu tabel Payment
  Reference keisi (`validate_payment_request_amount` langsung return), jadi dicek ulang di
  addon pakai hitungan yang sama.
- **Selisih dari termin dikasih tau**: kalau DP-nya beda dari nilai termin, muncul pesan info
  (bukan blokir) yang nyebutin sisa yang belum ditagih.

**Email pas submit dimatiin.** Payment Request tipe `Inward` bawaannya ngirim email ke
customer pas submit (butuh default outgoing Email Account + PDF dokumen referensi). DP Invoice
itu dokumen internal ke tim Finance, jadi field `Mute Email` default-nya dinyalain — sekalian
dimunculin di form (bawaannya hidden) biar tetap bisa dikirim manual per dokumen kalau perlu.
Tipe `Outward` emang gak pernah ngirim email.

Waktu Payment Entry dibikin dari DP Invoice itu, **tabel pajaknya kebawa otomatis** (cuma
kalau Payment Entry-nya belum punya baris pajak, jadi editan manual gak ketiban). Dokumen DP
Invoice sendiri gak posting jurnal — jurnalnya kebentuk di Payment Entry, sesuai R&C.

**Sisa PPN/PPh di invoice final.** Sales Invoice & Purchase Invoice punya checkbox
**Deduct Taxes Paid on DP** (default nyala). Kalau ada Payment Entry DP yang dialokasiin ke
invoice itu, baris pajaknya diubah jadi charge type `Actual` dengan nilai:

```
tax amount = pajak penuh - pajak yang sudah dibayar di DP
```

Contoh (SO 100.000 + PPN 11%, DP 30%):

| Dokumen | Nilai |
| --- | --- |
| Sales Order | net 100.000, PPN 11.000, grand total 111.000 |
| DP Invoice 30% | DP 33.300, PPN atas DP 3.663, total payable 36.963 |
| Payment Entry DP | terima 33.300 + pajak 3.663 = 36.963 |
| Sales Invoice | PPN ditagih **7.337** (11.000 − 3.663), grand total 107.337, outstanding 74.037 |

Kolom **Paid on DP** di baris pajak nunjukin berapa yang udah dibayar duluan. Kalau satu DP
dipakai buat beberapa invoice, potongannya diprorata sesuai porsi yang dialokasiin.

Setelan asli baris pajak (charge type + rate) disimpan di field tersembunyi, terus dibalikin
tiap dokumen disimpan sebelum ERPNext ngitung ulang — jadi potongannya gak numpuk walau
dokumennya disave berkali-kali, dan matiin checkbox-nya bikin pajak balik penuh.

Implementasi:

- `vic_addon/vic/dp_invoice.py` — Payment Request + auto-fetch pajak ke Payment Entry
- `vic_addon/vic/advance_tax.py` — sisa PPN/PPh di Sales/Purchase Invoice
- `vic_addon/public/js/payment_request.js` — persentase DP + load template pajak

Belum: rename doctype Payment Request jadi "DP Invoice" (frappe gak punya field label buat
doctype, jalurnya lewat record Translation), dan print format refund.

#### Sales Order: PO per supplier + dropship

Info supplier ikut turun sepanjang alur lewat field `Supplier Quotation` + `Supplier` di
tabel item:

```
SQTN -> Costing -> Quotation -> Sales Order -> Purchase Order
```

**Create > Purchase Order (per Supplier)** di Sales Order yang udah submit: item digrup per
supplier, satu draft PO per supplier, harga belinya diambil dari SQTN (net rate) dan PO item
langsung nyimpen link `Supplier Quotation` + balik ke Sales Order.

Contoh: SO isi 2 item dari 2 supplier beda → jadi 2 draft PO, masing-masing pakai harga beli
dari SQTN-nya sendiri (bukan harga jual di SO).

Dokumennya tetap dibikin `make_purchase_order` bawaan ERPNext, jadi handling currency,
exchange rate, alamat kirim buat dropship, dan sisa qty yang belum di-PO ikut kebawa. Kalau
satu item ada di dua supplier berbeda dalam satu SO, prosesnya ditolak dengan pesan jelas
(ERPNext ngegrup per item code, jadi harus dipisah SO).

Referensi SQTN di PO item pakai custom field (`custom_supplier_quotation`), **bukan** field
bawaan `supplier_quotation`. Field bawaan bikin ERPNext maksa PO item sama persis dengan
SQTN-nya di `project`, `uom`, dan `conversion_factor` — padahal project di PO ngikut Sales
Order, jadi PO gagal disimpan kalau SQTN-nya punya project yang beda.

**Transaction Type** (Reguler / Dropship) di header Sales Order. Kalau Dropship, semua item
otomatis ditandai `Delivered By Supplier` + suppliernya diisi dari SQTN, jadi flow drop ship
bawaan ERPNext jalan (alamat kirim PO ke customer, item dropship gak masuk Delivery Note).
Balik ke Reguler, tanda itu dilepas lagi.

Implementasi: `vic_addon/vic/sales_order.py` + `vic_addon/public/js/sales_order.js`.

Belum: print format Proforma Invoice (di sheet masih "Awaiting"). Auto reserve stock pas SO
submit / Purchase Receipt submit gak perlu custom, tinggal nyalain di Stock Settings.

#### DPP Nilai Lain (PPN 12%)

Field baru di **Quotation, Sales Order, Sales Invoice, Purchase Order, Purchase Invoice**:

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
- `vic_addon/fixtures/custom_field.json` — 10 custom field (2 per doctype)

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
