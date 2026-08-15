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

**Status** (`Not Quoted` / `Quoted`) kebentuk otomatis: begitu ada Quotation yang nempel ke
costing ini (field `Costing` di Quotation), statusnya jadi `Quoted`; balik ke `Not Quoted`
kalau quotation-nya dibatalin atau dihapus. Field-nya read only, ada di list view sebagai
indikator warna, dan bisa dipakai filter buat lihat costing mana yang belum ditawarin ke
customer.

**Tab Connections** di form Costing nampilin dokumen yang nyambung, dua arahnya beda cara:

| Dokumen | Cara nyambungnya |
| --- | --- |
| Quotation | Quotation nyimpen nomor costing di field `custom_costing` — link biasa |
| Supplier Quotation | SQTN gak nyimpen apa-apa soal costing; justru Costing yang nyimpen nomor SQTN di tiap baris item, jadi dibaca lewat `internal_links` (`Costing Item.supplier_quotation`) |

Konfigurasinya di `vic_addon/vic/doctype/costing/costing_dashboard.py`.

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

Di desk doctype-nya muncul sebagai **Advance Invoice**, bukan "Payment Request" — frappe gak
punya field label buat doctype, jadi labelnya diganti lewat record `Translation` yang dipasang
pas install/migrate (`vic_addon/vic/labels.py`).

Field baru di **Payment Request**:

| Field | Isi |
| --- | --- |
| DP Type | `Purchase` / `Sales`, otomatis dari dokumen referensi (PO = Purchase, SO = Sales) |
| DP Amount (relabel dari Amount) | nilai DP |
| DP Percentage | isi persen → DP Amount kehitung dari **net total** dokumen referensi |
| Purchase / Sales Taxes and Charges Template | template PPN/PPh atas DP |
| Advance Taxes and Charges | tabel PPN/PPh atas nilai DP |
| Total Taxes and Charges, Total Payable | total pajak dan total yang dibayar (DP + pajak) |

Persentase dan amount selalu nyambung: di form, ngisi persen bakal ngisi amount-nya; di
server, persen selalu dihitung balik dari amount, jadi angkanya gak pernah beda.

**Bikin dari tombol `Create > Payment Request` di SO/PO**, tiga hal diisi otomatis dari
dokumen referensinya:

| Yang diisi | Dari mana |
| --- | --- |
| DP Percentage | `invoice_portion` baris Payment Schedule yang dipilih user |
| DP Amount | porsi termin x **Net Total** dokumen referensi |
| Advance Taxes and Charges + template-nya | tabel pajak dokumen referensi, charge type diubah ke `On Paid Amount` |

Ini penting karena nilai termin di Payment Schedule (`payment_amount`) itu porsi dari **grand
total** yang udah kena PPN. Kalau angka itu dipakai apa adanya jadi DP Amount, PPN-nya keitung
dua kali — dan buat termin 100% malah ketolak sama validasi (DP 22.200 > net total 20.000).
Contoh PO net 20.000 + PPN 11% dengan termin 100%:

```
DP Amount     = 100% x 20.000 = 20.000    (bukan 22.200)
PPN atas DP   =  11% x 20.000 =  2.200
Total Payable                 = 22.200    <- pas sama nilai termin di PO
```

Baris pajak yang basisnya persentase (`On Net Total`, `On Previous Row Total`, dst) jadi
`On Paid Amount` dengan rate yang sama, sedangkan baris `Actual` diambil sebagian sesuai porsi
DP. Baris pajak Sales gak punya Add/Deduct (itu cuma ada di Purchase buat PPh), jadi
default-nya diisi `Add`.

Penyesuaian ini **cuma jalan buat dokumen yang lahir dari tombol Create**, ditandain lewat
`frappe.flags` — Payment Request yang diketik manual gak diutak-atik, DP Amount-nya persis
seperti yang diisi user. Untuk yang manual, tabel pajaknya diisi dengan milih template di
field Purchase/Sales Taxes and Charges Template.

**Kalau dokumen referensinya punya payment terms**, ERPNext ngisi tabel Payment Reference dan
maksa totalnya sama persis dengan DP Amount (*"Grand Total must match sum of Payment
References"*). Tabel itu read only di form, jadi tiap DP Amount berubah, barisnya disamain
otomatis (diprorata kalau terminnya lebih dari satu).

Nilai DP-nya sengaja **gak dikunci ke payment term** — DP hasil nego sering beda dari termin,
dan ngunci berarti tiap ganti DP harus cancel + amend SO/PO. Gantinya ada dua penjaga:

- **Gak boleh over-request**: total DP (yang udah submitted + dokumen ini) gak boleh lebih
  dari **Net Total** dokumen referensi. Batasnya net total, bukan grand total, karena DP-nya
  emang dihitung dari net total — PPN/PPh atas DP kecatat sendiri di tabel Advance Taxes and
  Charges, jadi kalau DP diambil dari grand total PPN-nya keitung dua kali. ERPNext juga
  ngelewatin pengecekan bawaannya begitu tabel Payment Reference keisi
  (`validate_payment_request_amount` langsung return), jadi tetap dicek ulang di addon.
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
- `vic_addon/vic/labels.py` — label doctype "Advance Invoice"
- `vic_addon/public/js/payment_request.js` — persentase DP + load template pajak

Belum: print format refund.

#### Sales Order: PO per supplier + dropship

Info supplier ikut turun sepanjang alur lewat field `Supplier Quotation` + `Supplier` di
tabel item:

```
SQTN -> Costing -> Quotation -> Sales Order -> Purchase Order
```

**Create > Purchase Order (per Supplier)** di Sales Order yang udah submit: muncul **modal**
berisi baris SO yang sisa qty-nya masih ada, lengkap dengan Pending Qty, tipe transaksi,
Supplier, dan SQTN-nya. Semua baris kecentang duluan; user tinggal ngurangin, ganti supplier per
baris (atau borongan lewat *Set Supplier for Selected Rows*), baru klik Create. Item yang belum
punya SQTN kolom suppliernya kosong dan wajib diisi sebelum lanjut.

Habis itu item digrup per supplier, satu draft PO per supplier, harga belinya diambil dari SQTN
(net rate) dan PO item langsung nyimpen link `Supplier Quotation` + balik ke Sales Order. Baris
yang suppliernya diganti di modal gak dikasih link SQTN dan harganya dikosongin — penawaran itu
punya supplier lain, jadi harga belinya diisi manual sesuai penawaran supplier baru.

Contoh: SO isi 2 item dari 2 supplier beda → jadi 2 draft PO, masing-masing pakai harga beli
dari SQTN-nya sendiri (bukan harga jual di SO).

Dokumennya tetap dibikin `make_purchase_order` bawaan ERPNext, jadi handling currency,
exchange rate, alamat kirim buat dropship, dan sisa qty yang belum di-PO ikut kebawa. Kalau
satu item ada di dua supplier berbeda dalam satu SO, prosesnya ditolak dengan pesan jelas
(ERPNext ngegrup per item code, jadi harus dipisah SO).

**PO dobel dicegah.** ERPNext cuma ngitung PO yang udah submit (lewat `Sales Order
Item.ordered_qty`), jadi tombolnya diklik dua kali bikin draft PO kembar. Di addon, PO draft
**dan** submitted dua-duanya dihitung: item yang udah ketutup PO aktif dilewatin (dikasih tau
item mana aja), dan kalau semua item udah ada PO-nya prosesnya ditolak sekalian nyebutin PO
mana yang udah ada.

**PO yang dibatalin boleh dibikin ulang.** PO dengan docstatus 2 sengaja gak dihitung, jadi
begitu PO di-cancel, tombolnya bikin PO baru cuma buat item dari PO yang batal itu — item lain
yang PO-nya masih aktif gak ikut kebikin lagi. Ini yang dipakai buat kasus supplier ganti
(R&C ke-6 di sheet Costing).

**Modal bawaan `Create > Purchase Order`** juga kepakai, kolom Supplier-nya keisi otomatis dari
`custom_supplier` tiap baris item (item tanpa SQTN dibiarin kosong biar user yang milih). Nilainya
dioper tepat sebelum modal kebuka dan cuma di memori, jadi dokumen Sales Order-nya gak ikut
berubah.

**Supplier di PO boleh diganti.** Barang habis di supplier pertama itu kasus normal (R&C ke-6 di
sheet Costing). Tiap PO disimpan, link SQTN-nya disamain dulu sama suppliernya:

| Kondisi | Yang terjadi |
| --- | --- |
| Supplier PO beda dari supplier SQTN | Link SQTN dilepas + dikasih tau, harga beli bebas diisi sesuai penawaran supplier baru |
| Baris dari SO belum punya link tapi suppliernya sama | Link SQTN-nya diambil dari baris Sales Order (biar PO dari modal bawaan tetap kekunci harganya) |

Ini jalan **sebelum** `rate_lock`, jadi harga belinya gak ketarik balik dari penawaran supplier
lama. Nomor supplier di Sales Order-nya sendiri gak ikut berubah — SO udah submitted, dan yang
diganti emang cuma keputusan beli di PO itu.

**Qty & link PO dicek balik ke SQTN** tiap PO disimpan (`vic_addon/vic/purchase_order.py`):

| Cek | Kalau gak lolos |
| --- | --- |
| SQTN-nya ada dan udah disubmit | ditolak |
| Supplier SQTN = supplier PO | ditolak |
| Item code-nya ada di SQTN itu | ditolak |
| SQTN sama dengan yang dipilih di baris Sales Order-nya | ditolak |
| Total qty di semua PO aktif ≤ qty di SQTN | ditolak |
| Baris SO punya SQTN tapi baris PO-nya kosong | cuma diingetin (gak diblokir) |

Referensi SQTN di PO item pakai custom field (`custom_supplier_quotation`), **bukan** field
bawaan `supplier_quotation`. Field bawaan bikin ERPNext maksa PO item sama persis dengan
SQTN-nya di `project`, `uom`, dan `conversion_factor` — padahal project di PO ngikut Sales
Order, jadi PO gagal disimpan kalau SQTN-nya punya project yang beda.

Implementasi: `vic_addon/vic/sales_order.py` + `vic_addon/vic/purchase_order.py` +
`vic_addon/public/js/sales_order.js`.

Belum: print format Proforma Invoice (di sheet masih "Awaiting"). Auto reserve stock pas SO
submit / Purchase Receipt submit gak perlu custom, tinggal nyalain di Stock Settings.

#### Customer WAPU

WAPU (Wajib Pungut): PPN-nya dipungut dan disetor sendiri sama customer — biasanya instansi
pemerintah atau BUMN — bukan sama kita.

| Doctype | Field |
| --- | --- |
| Customer | **WAPU Status** (Select: `Non WAPU` / `WAPU`), di tab Tax |
| Sales Invoice | **Customer WAPU** (checkbox, read only), diambil dari master Customer |

Checkbox-nya keisi otomatis waktu customer dipilih di form, dan di-set ulang tiap invoice
disimpan — jadi kalau status customernya berubah, invoice yang belum submit ikut nyesuaiin.
Dua-duanya bisa dipakai filter di list view.

Implementasi: `vic_addon/vic/sales_invoice.py` + `vic_addon/public/js/sales_invoice.js`.

#### Harga dikunci ke dokumen sumbernya

Tiap dokumen baru kebuka di form, ERPNext jalanin trigger `currency` → `apply_price_list()`
yang narik ulang harga dari Item Price, terus **maksa `rate = price_list_rate`**
(`transaction.js`, `_set_values_for_item_list`). Di alur VIC harganya bukan dari price list,
jadi harga hasil costing/SQTN bisa ketiban Item Price yang kebetulan ada.

Makanya tiap simpan, harganya dipasang lagi dari sumbernya:

| Dokumen | Sumber harga |
| --- | --- |
| Quotation, Sales Order | Quotation Rate di **Costing** (lewat field Costing yang ikut turun) |
| Purchase Order | **net rate** di Supplier Quotation baris itemnya |

Nego harga tetap bisa lewat kolom diskon per item (dan diskon atas total) — dihitung dari
harga sumber ini. Kalau harga belinya beneran beda dari penawaran supplier, yang bener revisi
SQTN lalu hitung ulang costing, bukan diubah diam-diam di PO.

Rate-nya sengaja gak dihitung sendiri, cuma `price_list_rate` yang dipasang lalu dikosongin
rate-nya biar ERPNext yang ngitung — beda pembulatan 1 sen aja bikin diskon persennya kereset.

Implementasi: `vic_addon/vic/rate_lock.py`.

Catatan: buat item yang harganya per-proyek, mending gak usah punya Item Price di price list
yang dipakai transaksi. Kalau tetap butuh harga acuan, taruh di Price List terpisah yang gak
pernah dipilih di dokumen — Item Price di price list yang gak kepilih gak akan ke-fetch.

#### Skema Dropship (dokumennya tetap lengkap)

Barang dikirim supplier langsung ke lapangan/proyek, **tapi Purchase Receipt dan Delivery Note
tetap ada**. Dropship bawaan ERPNext (`delivered_by_supplier`) sengaja **gak dipakai**, karena
justru ngebuang dua dokumen itu:

| Perilaku native | Lokasi | Akibat |
| --- | --- | --- |
| item dropship dikecualikan dari Delivery Note | `sales_order.py:1228` | DN gak bisa dibikin |
| item dropship dikecualikan dari Purchase Receipt | `purchase_order.py:413` | stok gak pernah masuk |
| `delivered_qty` SO diambil dari PO, bukan DN | `sales_order.py:686` | SO langsung "Delivered" pas PO submit |
| warehouse gak wajib di SO item | `sales_order.py:451` | stok gak kecatat |

Di sini dropship cuma atribut pengiriman, rantai dokumennya tetap standar:

```
Sales Order (tipe per item)
  └─ Create > Purchase Order (per Supplier)   → PO dipisah per supplier DAN per tipe
       └─ PO Dropship: Create > Delivery Note
            └─ pas DN disubmit: Purchase Receipt dibuat & disubmit otomatis
```

**Tipe transaksi ada di baris item** (`Transaction Type`: Reguler / Dropship), karena satu SO
bisa campur — sebagian dikirim dari gudang sendiri, sebagian dropship dari supplier lain.
Field di header cuma ringkasan read-only: `Reguler`, `Dropship`, atau `Mixed`.

Barang dropship lewat **gudang transit** (default dibikin otomatis `Dropship - {abbr}`, bisa
diganti lewat field *Dropship Warehouse* di Company): masuk lewat Purchase Receipt, keluar
lewat Delivery Note di tanggal yang sama — saldo nol, tapi stock ledger & valuasi tetap kecatat.

**Naming series kepisah** biar nomor dropship gak ganggu transaksi reguler, dan seriesnya
dipilih otomatis dari tipe dokumen:

| Dokumen | Reguler | Dropship |
| --- | --- | --- |
| Delivery Note | `MAT-DN-.YYMM.-` | `MAT-DN-DS-.YYMM.-` |
| Purchase Receipt | `MAT-PRE-.YYMM.-` | `MAT-PRE-DS-.YYMM.-` |

**Checkbox dropship bawaan ERPNext disembunyiin** (`Delivered by Supplier` di Item, Sales Order
Item, Sales Invoice Item, dan Packed Item), termasuk field `Supplier` bawaan di Sales Order Item
yang dobel sama `custom_supplier` punya kita. Kalau checkbox itu nyala, ERPNext ngecualiin
barisnya dari Delivery Note — tombol **Create > Delivery Note** di SO ikut ilang kalau semua
barisnya kecentang, dan kalaupun dipaksa, DN-nya keluar kosong. Selain disembunyiin, flag-nya
juga dimatiin tiap Sales Order disimpan (sekalian dikasih pesan), buat jaga-jaga dokumen lama
atau data hasil import. Yang dipakai cuma **Transaction Type** + **Supplier** di baris item.

Di PO dropship, tombol **Create > Purchase Receipt** disembunyiin (PR-nya otomatis), diganti
tombol **Create > Delivery Note**. PO dropship juga otomatis dapat alamat kirim + kontak
customer, jadi supplier tau kirimnya ke mana.

Implementasi: `vic_addon/vic/dropship.py` + `vic_addon/public/js/purchase_order.js`.

Catatan: Purchase Receipt gak boleh bertanggal masa depan (aturan ERPNext), jadi kalau posting
date DN di masa depan, submitnya ditolak dengan pesan yang jelas.

**Item dropship wajib udah punya PO sebelum DN-nya disubmit.** Purchase Receipt dropship dibikin
di atas PO — tanpa PO gak ada yang bisa diterima, dan gagalnya baru kelihatan jauh di belakang
(ERPNext ngamuk nyari Serial No yang harusnya lahir dari Purchase Receipt itu). Jadi dicegat di
`before_submit` dengan pesan yang nyebut baris, item, dan SO-nya.

**Required By di PO** ngikut delivery date Sales Order. Buat SO yang tanggal kirimnya udah lewat,
ERPNext bakal nolak PO-nya (`Required By cannot be before Date`), jadi tanggal yang udah lewat
dimajuin otomatis ke tanggal PO — cuma buat PO yang lahir dari tombol Create, PO manual tetap
divalidasi apa adanya.

#### Serial Number: penomoran sendiri + alirannya di dropship

**Penomorannya diatur di master `Serial Number Settings`** (Single doctype), bukan lewat field
`Serial No Series` di Item — penomoran bawaan ERPNext gak bisa nyelipin nomor & tanggal PO ke
dalam serial number. Field Serial No Series di Item dikosongin, biar yang kepakai seri ini.

Default seri nomornya:

```
{item_code}.{po_no}.{po_month}.{po_year}.############

-> VIC-SN-TEST.PUR-ORD-2608-00002.08.26.000000000001
```

| Variabel | Isi |
| --- | --- |
| `{item_code}` | Kode item |
| `{po_no}` | Nomor Purchase Order; kalau PR-nya gak punya PO, dipakai nomor Purchase Receipt |
| `{po_month}` / `{po_year}` | Bulan & tahun PO, 2 digit |
| `{po_date}` | Tanggal PO (YYYY-MM-DD) |
| `{supplier}` | Supplier di Purchase Receipt |
| `#` | Nomor urut, jumlah `#` = jumlah digit |

Nomor urutnya jalan **per prefix** (jadi per item per PO balik ke 1), pakai tabel `Series` yang
sama dengan naming series frappe. Variabel yang gak dikenal langsung ditolak waktu master
setting-nya disimpan.

**Barang masuk gudang (reguler):** begitu Purchase Receipt disimpan, tiap baris item yang
`Has Serial No`-nya nyala dan Serial No-nya masih kosong langsung diisi sebanyak qty-nya.
Nomornya ditaruh di field `serial_no` (bukan bikin Serial and Batch Bundle sendiri), jadi
ERPNext yang tetap ngurus pembuatan record Serial No + bundle-nya waktu submit.

**Dropship:** supplier ngirim barang langsung ke customer beserta serial number-nya, padahal
Purchase Receipt-nya gak pernah dibikin manual — dokumennya kebuat otomatis tepat sebelum
Delivery Note disubmit. Dua arah yang dilayanin:

| Kondisi | Yang terjadi |
| --- | --- |
| User ngetik Serial No di Delivery Note | Nomornya dioper ke Purchase Receipt dropship, jadi barang "masuk" dengan nomor dari supplier, terus keluar lagi lewat DN |
| Delivery Note dikosongin | Purchase Receipt yang generate nomornya, terus nomornya ditarik balik ke baris Delivery Note |

Urutannya aman karena Purchase Receipt & Delivery Note dua-duanya bikin Serial and Batch
Bundle di `on_submit`, sedangkan PR dropship dibuat di `before_submit` DN — jadi Serial No-nya
udah ada waktu DN butuh. Kalau jumlah Serial No yang diketik gak sama dengan qty barisnya,
submitnya ditolak dengan pesan yang nyebutin baris dan selisihnya.

**Tanggal garansi.** Sesuai bispro, garansi mulai jalan pas barang dikirim ke customer, jadi
tanggalnya diisi di Delivery Note terus diturunin ke tiap Serial No waktu DN disubmit:

| Doctype | Field |
| --- | --- |
| Delivery Note Item | Warranty Start Date, Warranty End Date |
| Serial No | Warranty Start Date (ERPNext cuma punya Warranty Expiry Date) |

- Dua field di Delivery Note Item cuma nongol buat item yang `Has Serial No`-nya nyala —
  penandanya field tersembunyi yang narik `has_serial_no` dari master Item.
- Start Date boleh dikosongin: otomatis ngikut posting date Delivery Note.
- End Date lebih awal dari Start Date langsung ditolak.
- Waktu submit, tiap Serial No di baris itu dapat Warranty Start Date, `Warranty Expiry Date`,
  dan `Warranty Period (Days)` — field bawaan ERPNext ikut diisi biar hitungannya tetap
  nyambung. Baris yang tanggal garansinya kosong gak nyentuh Serial No-nya sama sekali.

Prasyarat di site: **Stock Settings > Activate Serial and Batch No for Item** harus nyala,
kalau enggak ERPNext nolak bikin Serial and Batch Bundle sama sekali.

Implementasi: `vic_addon/vic/serial_no.py` +
`vic_addon/vic/doctype/serial_number_settings/`, nyambung ke `dropship.py`.

#### Print Format Date (Delivery Note)

Field **Print Format Date** di Delivery Note: tanggal yang nanti dipakai di print out, kepisah
dari Posting Date. Kasusnya dari bispro — barang dikirim 1 Januari tapi DN-nya baru disubmit di
sistem 2 Februari, sedangkan surat jalannya perlu dicetak dengan tanggal tertentu.

- Kosongin kalau tanggal cetaknya sama dengan Posting Date.
- **Bisa diubah setelah submit** (`allow_on_submit`), karena kebutuhan cetak ulang biasanya
  muncul setelah dokumennya jalan.
- `no_copy`, jadi gak kebawa waktu dokumennya di-amend atau diduplikat.

Print format-nya sendiri belum ada (masih nunggu format dari user), jadi sementara field ini
belum dipakai di mana-mana.

#### Print Format: Goods Received (Purchase Receipt)

Print format **Goods Received** buat Purchase Receipt, ngikutin format GR yang dipakai VIC:
logo di kiri, identitas perusahaan di kanan, kotak judul GOODS RECEIVED di tengah dengan GR No.
& tanggal di bawahnya, terus tabel item bergaris putus-putus.

| Bagian | Diambil dari |
| --- | --- |
| Logo | `/assets/vic_addon/img/vic logo.png` |
| Nama & alamat perusahaan | Company + Address utama yang kelink ke Company itu |
| Phone / Fax | `Company.phone_no` & `Company.fax`, fallback ke Address |
| GR No. / Date | `name` & `posting_date` (format `August 16, 2026`) |
| PO No. | daftar Purchase Order unik dari baris item |
| Heat Number | `custom_heat_number` kalau ada, kalau enggak `batch_no` |
| Description | nama item + daftar Serial No barisnya (kalau ada) |
| Qty | qty 2 desimal + UOM |

Ada blok tanda tangan (Received / Checked / Approved) di bawah. Waktu ngeprint, **matiin Letter
Head** — print format-nya udah punya kop sendiri, nanti dobel.

Isi print format-nya ditulis di `vic_addon/vic/print_format/goods_received/goods_received.html`.
Frappe cuma baca file `.json` waktu migrate (HTML-nya kesimpan sebagai satu string panjang di
situ), jadi file `.html` disalin ke dokumen Print Format tiap install & migrate lewat
`vic_addon/vic/print_formats.py` — **yang diedit file `.html`-nya**, `.json` cuma buat install
pertama.

#### Print Format: Serial No Label (stiker QR)

Print format kedua di Purchase Receipt, **Serial No Label** — buat stiker yang ditempel ke
barangnya. Satu Serial No = satu label, isinya nama item di atas, QR code di tengah, nomor seri
di bawah. QR-nya isi nomor seri itu sendiri, jadi bisa langsung discan buat nyari barangnya.

QR-nya digambar sendiri pakai `pyqrcode` (udah kebawa frappe buat 2FA), jadi labelnya tetap bisa
dicetak tanpa internet dan gak nitip ke layanan QR luar. Gambarnya nempel di HTML sebagai data
URI, bukan file.

**Ukuran labelnya diatur di master `Serial Number Settings`**, jadi gak perlu ngoding kalau
kertasnya ganti:

| Field | Default |
| --- | --- |
| Label Width | 50 mm |
| Label Height | 30 mm |
| Label Font Size | 7 pt |
| Show Item Name on Label | ya |

Ukuran itu dipakai buat `@page` sekaligus ukuran kotak labelnya, dan tiap label pindah halaman
sendiri. Buat cetak lewat browser (label printer), ukuran ini langsung kepakai. Buat download
PDF-nya wkhtmltopdf, samain juga **Print Settings > PDF Page Size = Custom** dengan angka yang
sama, karena ukuran halaman PDF diambil dari sana.

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
