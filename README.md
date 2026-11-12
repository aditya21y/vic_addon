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
### Akses staging

Buka lewat domain, **tanpa port**:

- http://vic.thenextflow.cloud
- http://nic.thenextflow.cloud

Jangan lewat `http://vic-app:8000` (setelan file hosts lama) atau `IP:8000`: halamannya kebuka, tapi
realtime (socket.io — notifikasi, update tanpa refresh) ditolak **"Invalid origin"**, karena nama host
halaman beda sama yang diterima server socket lewat nginx. Entri `vic-app` / `nic-app` di
`C:\Windows\System32\drivers\etc\hosts` boleh dihapus.


### Multitenant Setting
# nyalain resolusi berdasarkan hostname
bench config dns_multitenant on

bench --site site1.local set-config host_name http://site1.local:8000
bench --site site2.local set-config host_name http://site2.local:8000

bench start


### Realtime (socket.io) di staging

Staging jalan pakai dev server (`bench serve` di belakang nginx). Di mode itu client socket.io
Frappe nyambung **langsung ke port `socketio_port`** (`frappe/public/js/frappe/socketio_client.js`,
`get_host`), bukan lewat `/socket.io` di nginx. Akibatnya header `X-Frappe-Site-Name` gak ikut,
server socket nebak nama site dari domain (`vic.thenextflow.cloud` ≠ `vic-app`), dan koneksinya
ditolak **"Invalid namespace"** — notifikasi, assign, dan update realtime lain gak nyampe sampai
halaman di-refresh.

Perbaikannya: `socketio_port` di **site_config** tiap site diset `80`, jadi browser nyambung lewat
nginx yang nambahin header-nya. Server socket tetap dengerin port 9000 (dibaca dari
`common_site_config.json`, bukan site config):

```
bench --site vic-app set-config socketio_port 80
bench --site nic-app set-config socketio_port 80
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

#### Costing (custom doctype)

Ngitung HPP dari harga Supplier Quotation + distribusi additional cost, terus nentuin harga
jual dari margin. Rumusnya ngikut sheet **5a. COSTING** di source of truth. Non-submittable
(sesuai bispro) biar item tetap bisa diedit & dihitung ulang kalau supplier/harga berubah.

Doctype: **Costing** (`CST-.YYMM.-`), dengan child table **Costing Item** dan
**Costing Additional Cost**. Ada field **Project** juga, yang ikut kebawa ke Quotation waktu
costing-nya dijadiin penawaran.

**Customer, RFQ, Project, dan Subject diambil dari Inquiry** asal penawarannya (nomor Inquiry
kebaca lewat baris Supplier Quotation di tabel item; field RFQ = nomor Inquiry-nya sendiri,
`PUR-RFQ-...`, yang pertama kalau lebih dari satu),
masing-masing cuma kalau masih kosong — isian user gak pernah ketiban. Centangan **Show Project in
Print** / **Show Subject in Print** ikut disalin bareng nilainya. Lewat tombol *Create > Costing* di
Supplier Quotation maupun dialog *Get Items* semuanya udah keisi sebelum disimpan, dan diisi lagi
waktu disimpan kalau masih ada yang kosong.

**Send Email** (tombol di form Costing): composer email bawaan Frappe dengan PDF **Costing
(Import)** langsung kelampir — buat dikirim ke internal (review harga). Emailnya kecatat di
timeline Costing.

**Discount** (section di bawah Totals): diskon ke customer, buat ngira profit kalau
harga jual diturunin. User isi **Discount %** atau **Discount Amount** — yang satunya dihitung
otomatis. Yang terakhir diketik yang dipegang: kalau nominal yang diketik, nominalnya tetap waktu
Total Quotation Amount berubah dan persennya yang ngikut (dan sebaliknya).

| Field | Rumus |
| --- | --- |
| Total Quotation After Discount | Total Quotation Amount − Discount Amount |
| Total Profit After Discount | Total Quotation After Discount − Total HPP Amount |
| Total Profit % After Discount | Total Profit After Discount / Total HPP Amount × 100 |

Diskon ini **ikut kebawa ke Quotation** (Create > Quotation) sebagai **Additional Discount** dengan
**Apply Additional Discount On = Net Total**, jadi dasarnya sama kayak di Costing (total sebelum
pajak) dan Net Total Quotation = Total Quotation After Discount. Kalau di Costing yang diketik
persen, Quotation dapat persennya (nominal dihitung ulang kalau qty/harga di Quotation diubah);
kalau nominal, Quotation dapat nominalnya. Masih bisa diubah di Quotation-nya. Diskon gak boleh
minus dan gak boleh lebih dari Total Quotation Amount.

Di **Costing (Import)**, kolom **Act Price After Disc** dicetak **merah**; kolom lain tetap hitam.

Ringkasan di bawah tabel **Costing (Import)**:

| Baris | Rumus |
| --- | --- |
| Total Buying Price / Total Selling Price | Σ harga beli / Σ harga nego (Quotation Rate) |
| Disc | Discount Amount (section **Discount** di Costing) |
| Ongkir | Total Distributed Cost Amount (Total Additional Costs × (1 + Additional Percentage)) |
| TSP (Total Selling Price after discount) | Total Selling Price − (Disc + Ongkir) |
| (tanpa label) | TSP − Total Buying Price |

Di print format **Costing (Import)** dan **Costing (Sales)**, Project dan Subject cuma dicetak
kalau centangannya nyala — bisa salah satu atau dua-duanya. Baris Attn, Phone, dan Fax di Costing
(Import) dibuang. Costing lama yang Project-nya udah keisi dicentangin otomatis lewat patch
`show_costing_project_in_print` (dulu Project selalu dicetak, dengan label Subject).

**Tombol `Get Items from Supplier Quotation`** ngebuka satu dialog berisi:

| Isian | Gunanya |
| --- | --- |
| **Project** | Default Project Costing. Kalau diisi, pilihan Request for Quotation cuma Inquiry project itu, dan daftar Supplier Quotation cuma penawaran dari Inquiry project itu (atau yang Project-nya sendiri sama). Ganti Project → Inquiry yang udah kepilih dikosongin kalau project-nya beda |
| **Request for Quotation** | Nyaring daftar penawaran ke RFQ itu doang, biar gak kecampur proyek lain |
| **Take the cheapest price only** | Satu baris per item, diambil dari penawaran termurah |
| **Supplier Quotation** | Pilih penawarannya sendiri (disembunyiin kalau ambil termurah dari RFQ) |
| **Items** | Item, qty, rate, supplier, dan SQTN-nya kelihatan dulu sebelum masuk — **qty bisa diedit**, dan angka itu yang dipakai di Costing |

Qty awalnya diambil dari **RFQ** kalau RFQ-nya diisi (itu jumlah yang beneran dibutuhin), kalau
enggak ikut qty di penawarannya.

Centang **termurah** ngikut aturan yang sama persis kayak tabel Supplier Comparison: yang
dibandingin cuma **penawaran terakhir tiap supplier**, penawaran lama diabaikan — jadi harga yang
masuk Costing sama dengan yang ditandain kuning di file perbandingan. Kalau centangnya dipakai
tanpa RFQ, yang dibandingin cuma penawaran yang dipilih di dialog.

**Ganti SQTN di baris Costing = harganya ikut ganti.** Kolom Supplier Quotation di tabel item
pilihannya dibatesin ke penawaran submitted yang beneran ada item baris itu, dan begitu diganti,
**net rate** penawaran baru langsung ketarik ke kolom Rate bareng nama suppliernya. Kalau
kolomnya dikosongin, barisnya balik diperlakuin sebagai barang stok — harganya ngambil valuation
rate gudang.

**Costing selalu mata uang perusahaan (IDR).** Field Currency read only dan dipaksa ke default
currency company tiap disimpan. Harga dari SQTN diambil **versi IDR-nya**: `base_net_rate` (Rate)
dan `base_price_list_rate` (Price List Rate) — harga valas × kurs yang dipakai di SQTN itu. Contoh
(udah dites): SQTN USD kurs 16.000, harga $10 diskon 10% → Rate **144.000**, Price List Rate
**160.000**. Jadi:

- dialog Get Items **gak nyaring mata uang** lagi — penawaran USD, SGD, IDR bisa dicampur di satu
  Costing, dan centang *termurah* ngebandingin harga yang udah sama-sama IDR;
- ganti SQTN di baris / Create > Costing dari SQTN valas juga langsung keisi IDR;
- harga final Quotation yang ditulis balik ke Costing (`update_costing_rates`) ikut pakai
  `base_net_rate`.

Kursnya beku di kurs SQTN — kalau kurs berubah, SQTN-nya yang mesti diperbarui.

**Price List Rate** di baris Costing = harga beli **sebelum diskon** dari SQTN (read only), dicetak sebagai
**Act Price** di Costing (Import); Rate (setelah diskon) jadi **Act Price After Disc**. Diisi lewat Get Items,
Create > Costing, dan ganti SQTN di baris; baris yang punya SQTN tapi Price List Rate-nya masih 0 diisi ulang
tiap Costing disimpan (`set_price_list_rates` — Costing lama yang dibikin lewat Get Items sebelum ini 0
semua, beres begitu disimpan ulang). Baris barang stok (tanpa SQTN) dibiarin 0 — print-nya jatuh ke Rate.

Tiap baris Costing Item punya field **Warehouse** yang keisi otomatis: gudang default item di
company itu (`Item Default`) dulu, kalau item gak punya baru ikut default warehouse di Stock
Settings. Kalau dua-duanya gak diset, field-nya dibiarin kosong. Gudang Stock Settings yang
punya company lain sengaja gak dipakai. Diisi waktu item dipilih (biar langsung kelihatan) dan
dipasang lagi tiap dokumen disimpan, tapi cuma buat baris yang masih kosong — pilihan manual
user gak ketiban.

**Barang stok yang gak lewat SQTN harganya dari gudang.** Baris Costing yang kolom Supplier
Quotation-nya kosong ngambil Rate dari **valuation rate item di gudang baris itu** (`Bin`) —
barang yang udah nangkring di gudang emang gak punya penawaran supplier, jadi harga pokoknya
ya nilai persediaannya. Aturannya:

| Baris | Rate-nya |
| --- | --- |
| Ada Supplier Quotation | Dari net rate SQTN, gak disentuh |
| Tanpa SQTN, Rate masih kosong (belum pernah diisi) | Valuation rate item di gudang baris itu |
| Tanpa SQTN, Rate diisi manual — **termasuk 0** | Angka user dipertahanin |
| Tanpa SQTN, gudangnya belum punya nilai persediaan | Jadi 0 buat diisi manual |

**Rate gak wajib dan boleh 0** — buat item tambahan yang gak ada harganya (mis. barang tambahan).
Baris bisa ditambah langsung di tabel Items, gak harus lewat Get Items. Rate 0 bikin HPP, Selling,
dan Quotation Rate baris itu ikut 0. Karena 0 sekarang dianggap isian user, Rate yang udah kesimpan
0 gak ditarik ulang dari gudang tiap simpan — ganti item/gudang di form buat narik valuation-nya lagi.

Angkanya per gudang, jadi item yang sama di gudang beda bisa beda harga pokok. Di form, gudang
dan rate-nya keisi begitu item dipilih dan ditarik ulang kalau gudangnya diganti; server ngisi
lagi tiap dokumen disimpan.

Helper-nya di `vic_addon/vic/warehouse.py` (`get_default_warehouse`, `get_valuation_rate`) —
yang gudang dipakai bareng sama Loan Memo buat gudang asal barang pinjaman.

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

di header, dua-duanya dibanding Total HPP Amount:
Total Profit Amount / %              -> dari Total Selling Amount (harga hasil margin)
Total Profit Amount / % vs Quotation -> dari Total Quotation Amount (harga nego ke customer)
```

**Harga final dari Quotation ditulis balik ke Costing otomatis waktu Quotation disubmit**
(hook `before_submit`, gak ada tombol lagi). Yang dibandingin `net_rate` tiap baris Quotation —
harga per unit setelah diskon item maupun diskon atas total — lawan Quotation Rate di baris
Costing-nya; yang beda ditimpa. Baris yang ketimpa ditandain `quotation_rate_manually_set` biar
gak ketarik balik ke Selling Rate, Costing-nya dapat komentar nyebut Quotation mana sumbernya,
dan user dikasih notifikasi item mana aja yang angkanya berubah (nulis ke dokumen lain jangan
diem-diem).

Bisa otomatis karena satu Costing cuma boleh punya **satu** Quotation submitted (aturan di bawah)
— jadi gak ada lagi pertanyaan "harga dari Quotation mana yang dipakai". Draft-nya gak nyentuh
Costing sama sekali: selama masih nego, angka di Costing tetap versi rencana.

**Satu Costing cuma boleh punya satu Quotation yang jadi.** Waktu Quotation disubmit, kalau
costing yang sama udah punya Quotation submitted lain, submitnya ditolak sekalian nunjuk nomor
Quotation-nya. **Draft-nya boleh banyak** — bikin beberapa versi penawaran itu normal, yang
dibatesin cuma yang jadi. Aturan ini yang bikin angka di Costing (termasuk profit lawan harga
nego) jelas ngikut penawaran yang mana, dan bikin tombol `Update Costing Rate` gak saling timpa.
Kalau mau ganti ke penawaran lain, Quotation yang lama dibatalin dulu.

**Kenapa profitnya dua versi.** `Selling Rate` itu harga hasil rumus margin, sedangkan
`Quotation Rate` itu harga yang beneran ditawarin ke customer (boleh dinego turun). Profit yang
lama ngukur rencana, yang **vs Quotation** ngukur kenyataan. Basis persentasenya sama-sama Total
HPP Amount, jadi dua angkanya bisa langsung dibandingin — misalnya harga nego dipotong 10%:
profit rencana 25% jadi kenyataan 12,5%.

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
`Quotation Rate Manually Set` otomatis nyala dan nilainya berhenti ngikut Selling Rate — **termasuk
kalau diisi 0** (harga ke customer 0, mis. barang tambahan yang gak ditagih; profit baris itu jadi
minus sebesar HPP-nya). Kosongin Quotation Rate-nya (bukan diisi 0) buat balik ke mode auto.

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


**Realisasi (Costing Realization).** Rencana di Costing dibandingin otomatis sama realisasinya, per
item — lewat **Script Report "Costing Realization"** (pohon: baris Costing berisi total, item di
bawahnya; filter company, tanggal, customer, project, costing) dan **section Realization** di form
Costing (tabel ringkas + link SO/PO + tombol ke report).

Rantainya: Costing → Quotation submitted (`custom_costing`) → Sales Order submitted (baris SO nyimpen
Quotation asal) → Purchase Order submitted (baris PO nyimpen baris SO). Baris SO dicocokin ke baris
Costing lewat item code + Supplier Quotation di baris Quotation-nya; item yang ditambah di SO jadi baris
sendiri dengan rencana nol.

| Kolom | Rencana (Costing) | Realisasi |
| --- | --- | --- |
| Qty | Qty Costing | Qty SO / Qty PO |
| Jual | Quotation Amount | net amount SO (setelah diskon, sebelum pajak) |
| Beli | Amount (harga beli SQ) | net amount PO + qty SO yang **belum di-PO** dinilai harga beli rencana (perkiraan) |
| Profit & margin | jual − beli | jual SO − biaya beli realisasi |

**PO Status** (Belum PO / PO Sebagian / Lengkap / PO Lebih) nunjukin baris yang profitnya masih ngandung
perkiraan. Additional cost (ongkir dll) gak ikut profit rencana — realisasinya cuma SO − PO, biar
sebanding. Selisih jual/profit minus dan selisih beli plus ditandain merah.

Implementasi: `vic_addon/vic/costing_realization.py`, report di `vic_addon/vic/report/costing_realization/`.
#### DP Invoice pakai Item DP (skema sekarang, cuma penjualan)

Sumber: `new dp schemaa.xlsx`, **Opsi 2**. **Cuma Sales Invoice.** Sisi pembelian dulu ikut skema ini,
sekarang dicabut: DP ke supplier cukup **advance payment** — Payment Entry (Pay) ke Purchase Order,
terus dialokasiin di Purchase Invoice lewat tabel **Advances** (*Get Advances Paid*) bawaan ERPNext.
Field Is DP Invoice / DP Term / tabel DP Invoices di Purchase Invoice dan akun Uang Muka Pembelian di
Company dibuang (patch `drop_purchase_dp_invoice`; kolom & jurnal lama tetap utuh). Jalan **berdampingan** dengan alur DP lewat Advance
Invoice (bagian berikutnya) — dua-duanya masih dipakai, tombol *Create > Payment Request* di Sales
Order & Purchase Order tetap ada.

Contoh order DPP 1.000 + PPN 10%, payment schedule DP 20% + 80%, ditagih progress 50% dua kali:

| # | Dokumen | Jurnal | Yang bikin |
| --- | --- | --- | --- |
| 1 | **Invoice DP** (centang *Is DP Invoice*) | Dr Piutang 220 / Cr Uang Muka Penjualan 200 / Cr PPN 20 | user |
| 2 | Payment Entry DP | Dr Bank 220 / Cr Piutang 220 | bawaan ERPNext |
| 3 | Invoice progress 50% (item asli) | Dr Piutang 550 / Cr Penjualan 500 / Cr PPN 50 | bawaan ERPNext |
| 4 | **Reverse Journal** (otomatis waktu #3 disubmit) | Dr Uang Muka Penjualan 100 / Dr PPN 10 / Cr Piutang 110 → tagihan #3 tinggal 440 | sistem |
| 5 | Payment Entry | Dr Bank 440 / Cr Piutang 440 | bawaan ERPNext |
| 6 | Progress 50% kedua | sama kayak #3–#5: reverse 100 + 10, bayar 440 | |

**Setting (Company → section *DP Invoice (Item DP)*):** **DP Item** (item jasa, *Maintain Stock*
mati, boleh dijual) dan akun **Uang Muka Penjualan** (income baris DP di Sales Invoice).

**Invoice DP** — bikin Sales Invoice dari Sales Order seperti biasa, lalu centang **Is DP
Invoice** dan pilih **DP Term** (baris Payment Schedule order). Waktu disimpan semua item diganti
satu baris Item DP:

- rate = porsi term × **Net Total** order (DPP, bukan grand total — pajaknya ikut tabel pajak
  invoice). Dihitung ulang tiap draft disimpan.
- akun baris = akun Uang Muka dari Company; kategori PPh baris ngikut cara ERPNext (master Item,
  lalu master party), jadi PPh bawaan tetap jalan di invoice DP.
- payment terms invoice dikosongin (satu tagihan), Update Stock dimatiin.
- satu term cuma boleh di-DP sekali (dan gak boleh term yang udah dipakai invoice progress), dan
  total DP gak boleh lewat Net Total order.

**Invoice progress** — tabel **DP Invoices** (di bawah Advances) narik DP dari order yang sama
(party & company sama), otomatis waktu dokumen baru kebuka atau lewat tombol **Get DP Invoices**:

| Kolom | Isinya |
| --- | --- |
| Allocated (DPP) | default DP order × DPP invoice ini / DPP order; invoice yang ngelunasin order ngambil semua sisa. **Boleh diedit**, maksimal sisa DP |
| Tax | pajak DP (PPN/PPh) yang ikut dibalik, sebanding Allocated |
| Total Reversed | Allocated + Tax — ngurangin tagihan invoice ini |

Waktu invoice progress disubmit, **Reverse Journal** dibikin & disubmit otomatis (field *DP
Reversal For* di JE nunjuk ke invoice-nya). Isinya ngebalik **jurnal GL invoice DP-nya sendiri**
(semua baris selain piutang/hutang) × Allocated / DPP DP — akun Uang Muka, PPN, PPh, sampai cost
center-nya persis yang dipakai invoice DP. Baris piutang/hutangnya nempel ke invoice progress.

**Connections di Sales Order:** baris Item DP nyimpen nomor SO-nya (field `sales_order`, `so_detail`
sengaja kosong), jadi invoice DP muncul di tab **Connections → Sales Invoice** SO itu bareng invoice
progress & retensi. Cuma link — % Billed SO tetap dihitung dari baris barang. Invoice DP & retensi
lama diisi lewat patch `link_dp_retention_invoices_to_sales_order`.

**Cancel:** cancel invoice progress → Reverse Journal-nya ikut dicancel duluan, DP-nya bisa dipakai
lagi. Invoice DP yang udah dipakai invoice progress submitted **gak bisa dicancel**.

**Belum ditangani:** invoice/akun party mata uang asing (reverse ditolak dengan pesan jelas), dan
tabel deskripsi penagihan khusus buat print (Opsi A di Excel).

Implementasi: `vic_addon/vic/dp_item_invoice.py`, `vic_addon/public/js/dp_item_invoice.js`,
child table **DP Allocation**.

#### Retensi (invoice progress & invoice retensi)

Retensi = sisa bayar yang ditahan customer padahal barang udah dikirim penuh (mis. termin SO
"dp 20%, 75% progress, 5% retensi"). Ditagih terpisah di akhir, pakai invoice + faktur sendiri.
Jalan bareng skema DP Item.

| # | Invoice | Yang dilakuin user | Yang otomatis |
| --- | --- | --- | --- |
| 1 | DP | centang **Is DP Invoice** + DP Term | item diganti Item DP (lihat DP Invoice pakai Item DP) |
| 2 | Progress | centang **Is Progress Invoice** + **Progress Term** (mis. "2. 75 (75%)") | baris **RETENSI minus** = % termin retensi × DPP barang; DP ditarik ke tabel DP Invoices (bisa diedit) — waktu dicentang, dan lagi waktu disimpan pertama kalau tabelnya masih kosong |
| 3 | Retensi | di Sales Order: **Create → Retention Invoice** (muncul kalau masih ada retensi yang belum ditagih) | form kebuka udah berisi satu baris **RETENSI plus** senilai retensi yang ditahan & belum ditagih; pajak ikut SO; sisa DP dibalik (maks. senilai retensi) |

Contoh SO DPP 51.000 + PPN 11% (udah dites): DP 11.322 → progress DPP 48.450 (retensi −2.550), DP
dibalik 11.322, sisa tagih 42.458 → retensi DPP 2.550 + PPN = 2.830 → total dari customer **56.610 =
grand total SO**, saldo Piutang Retensi balik 0.

Baris RETENSI plus di invoice retensi nyimpen nomor SO, jadi invoice retensinya muncul di tab
**Connections** SO (kecuali SO-nya udah **Closed / On Hold** — ERPNext nolak invoice yang barisnya nunjuk
SO begitu, jadi baris itu dibiarin tanpa link). Baris RETENSI minus di invoice progress gak di-link;
invoice progress udah nempel lewat baris barangnya.

Invoice retensi dibikin dari tombol di SO, bukan *Create → Sales Invoice* bawaan: SO yang barangnya
udah ketagih semua (% Billed 100) gak bisa bikin invoice lewat mapper bawaan, dan SI baru yang Items-nya
kosong ditolak form.

**Jurnalnya:** baris RETENSI pakai akun neraca **Piutang Retensi** (bukan Penjualan) — penjualan diakui
penuh waktu barang dikirim, PPN & faktur ngikut tagihan, sisa retensi = saldo akun itu.

**Termin retensi** di Payment Schedule SO dikenali dari centangan **Is Retention** di master Payment
Term; kalau gak dicentang, dari nama/deskripsinya yang mengandung "retensi"/"retention".

**Penjaga:**

- Satu invoice cuma boleh satu dari Is DP / Is Progress / Is Retention; invoice progress cuma boleh
  narik item dari satu Sales Order.
- **Termin yang udah ditagih gak bisa dipilih lagi** (dicek per Sales Order, invoice draft & submitted;
  yang cancelled gak dihitung). SO "DP 20%, 75% progress, 5% retensi" yang DP 20%-nya udah ditagih:
  Progress Term cuma nawarin "75%", dan kalau "20%" tetap dikirim, simpannya ditolak (*Term ... is
  already billed in ... (DP Invoice)*). Sebaliknya, termin yang udah dipakai invoice progress gak bisa
  jadi DP Term. Termin progress yang sama **boleh** dipakai lebih dari satu invoice progress — barang
  yang dikirim bertahap ditagih per pengiriman pakai termin progress yang sama.
- *Allow Negative rates for Items* (setelan global ERPNext) harus nyala, tapi yang boleh rate minus
  **cuma baris RETENSI di invoice progress** — item lain ditolak.
- Invoice retensi ditolak kalau retensi order itu udah habis ditagih.
- Invoice progress yang retensinya udah ditagih gak bisa dicancel sebelum invoice retensinya dicancel.
- Invoice retensi yang narik DP: pembulatan grand total dimatiin, biar DP yang dibalik pas dengan
  tagihannya (sisa tagih 0, gak lebih 0,50).
- Kalau setelah invoice retensi masih ada DP yang belum dibalik, muncul peringatan oranye — DP itu
  masih nyangkut di akun uang muka dan customer bakal kelebihan bayar.

**Setup sekali per site/company:**

1. Akun **Piutang Retensi** (Asset; tipe akun **jangan** *Receivable* — akun tipe itu wajib party di
   tiap jurnal). Local: `1132.002 - Piutang Retensi - N`.
2. Item **RETENSI** (non-stock, sales item).
3. Company → section *DP Invoice (Item DP)*: **Retention Item** = RETENSI, **Piutang Retensi** = akun di
   atas.
4. Master **Payment Term** termin retensi: centang **Is Retention** (opsional kalau namanya udah
   mengandung "retensi").
5. **Selling Settings → Allow Negative rates for Items** dinyalain.

Implementasi: `vic_addon/vic/retention.py`, form di `vic_addon/public/js/dp_item_invoice.js`.

#### DP Invoice (Payment Request) + sisa PPN/PPh di invoice final

> Masih dipakai, berdampingan dengan skema Item DP di atas. Sempat disembunyiin waktu skema Item DP
> masuk, lalu dibalikin karena alur ini ternyata masih kepakai.

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

Property setter `default = 1` doang gak cukup buat dokumen yang lahir dari tombol **Create >
Payment Request**: `make_payment_request` bawaan ERPNext nimpa field-nya pakai `args.mute_email`
yang kosong, jadi centangnya balik mati. Makanya override kita ngisi `mute_email` di args
sebelum manggil versi bawaannya — kalau pemanggilnya udah ngisi sendiri (webshop), nilainya
dihormati.

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

Pencocokannya lewat **akun pajak**. Kalau PPN uang muka ditampung di akun lain (lihat *PPN uang
muka ditampung dulu*), yang dipakai buat nyocokin tetap **akun aslinya**, bukan akun penampung —
invoice finalnya pakai akun asli itu. Yang dipotong cuma DP yang **kedaftar di tabel Advances**
invoice-nya; kalau tabelnya kosong (Payment Entry-nya belum dialokasiin ke invoice ini), gak ada
yang dipotong walau checkbox-nya nyala.

Setelan asli baris pajak (charge type + rate) disimpan di field tersembunyi, terus dibalikin
tiap dokumen disimpan sebelum ERPNext ngitung ulang — jadi potongannya gak numpuk walau
dokumennya disave berkali-kali, dan matiin checkbox-nya bikin pajak balik penuh.

Implementasi:

- `vic_addon/vic/dp_invoice.py` — Payment Request + auto-fetch pajak ke Payment Entry
- `vic_addon/vic/advance_tax.py` — sisa PPN/PPh di Sales/Purchase Invoice
- `vic_addon/vic/labels.py` — label doctype "Advance Invoice" (lihat *Nama dokumen di desk beda dari bawaan ERPNext*)
- `vic_addon/public/js/payment_request.js` — persentase DP + load template pajak

Belum: print format refund.

#### PPh pakai bawaan ERPNext

PPh (misalnya PPh 23 jasa) ngikut cara **bawaan ERPNext**, gak ada kustomisasi: dipotong di
Purchase / Sales Invoice lewat **Consider for Tax Withholding**, dan buat uang muka bisa dicentang
manual di Payment Entry (kategori + grupnya diisi sendiri).

Sempat ada versi VIC (PPh selalu diakui di Payment Entry, dihitung per item, centangan dikunci),
tapi gak jadi dipakai dan udah dicabut lewat patch `revert_custom_tax_withholding`: custom field &
property setter-nya dihapus, dan baris PPh versi VIC di Payment Entry **draft** dibuang. PE yang
udah submit gak disentuh. Kodenya masih ada di riwayat git kalau suatu saat dibutuhin lagi.

Yang tetap dipertahanin: penanda `is_tax_withholding_account` dipakai di `advance_tax.py`,
`dp_ppn.py`, dan report Arus Uang dan Barang supaya baris PPh bawaan ERPNext gak salah keitung
sebagai PPN atau ikut dikurangin dari pajak invoice.

#### PPN uang muka ditampung dulu, baru dipindah waktu DP kebayar

Waktu bayar DP ke supplier, faktur pajaknya belum ada. Jadi PPN-nya belum boleh masuk PPN
Masukan — ditampung dulu di akun sendiri, baru dipindah setelah pembayarannya jadi.

Dinyalain per company, di tab **Accounts** bagian **PPN Uang Muka (DP)**:

| Field | Isi |
| --- | --- |
| Enable PPN DP Pembelian | centang buat nyalain sisi beli |
| COA PPN DP Pembelian | akun penampung, mis. `1152.003 - PPN MASUKKAN BELUM DITAGIH` |
| Enable PPN DP Penjualan | centang buat nyalain sisi jual |
| COA PPN DP Penjualan | akun penampung sisi jual |

Field akunnya cuma muncul (dan jadi wajib) kalau centangannya nyala, dan daftar akunnya
kefilter ke akun milik company itu yang bukan akun induk.

Jalannya:

1. **DP Invoice dibikin dari PO/SO** — baris PPN yang ditarik dari dokumen referensi akunnya
   diganti ke akun penampung. Akun aslinya disimpan di baris yang sama (`Original Account
   Head`), jadi lawan jurnalnya nanti gak perlu ditebak.
2. **Payment Entry** — baris pajaknya kebawa apa adanya, jadi jurnal DP-nya kena akun penampung.
3. **Payment Entry disubmit** — Journal Entry otomatis mindahin saldonya ke akun asli:

   ```
   DR  PPN Masukan                          12.000
   CR  PPN Masukan Belum Ditagih                    12.000
   ```

   Jurnalnya nyimpen nomor Payment Entry-nya (field `DP PPN Payment Entry`), dan ikut
   **dibatalin otomatis** kalau Payment Entry-nya dibatalin.

Arah jurnalnya ngikut jenis pembayaran: DP pembelian (`Pay`) nampung di sisi debit, jadi
pemindahannya ngredit penampung; DP penjualan kebalikannya.

**Yang dianggap baris PPN**: pajak yang *nambah* nilai bayar dan hitungannya persentase
(`On Paid Amount`). PPh 23 kelewat karena dia motong (`Deduct`), begitu juga baris `Actual`
kayak ongkos kirim.

Pemindahannya bersandar ke jejak `Original Account Head` di barisnya, **bukan** ke centangan di
Company. Jadi kalau centangannya dimatiin setelah DP kebayar, saldo yang terlanjur nyangkut di
akun penampung tetap kepindah.

Implementasi: `vic_addon/vic/dp_ppn.py`.

#### Target Grand Total (Purchase Invoice)

Tagihan supplier sering beda dikit sama hitungan PI (pembulatan di pihak supplier). Field **Target Grand
Total** (`custom_target_grand_total`, di bawah Grand Total): isi Grand Total di tagihan supplier, waktu
**disimpan** rate tiap item disesuaikan biar **Net Total + pajak = angka itu**.

1. Semua rate diskalain proporsional (pajak persentase ikut, pajak nominal/`Actual` dianggap tetap).
2. Sisa sen dikejar dengan geser rate 0,01 per langkah, mulai dari baris qty terkecil.
3. Kalau tetap gak bisa pas — rate 2 desimal + pembulatan PPN kadang ngelompat 0,02 — muncul peringatan
   oranye berisi selisihnya (biasanya 0,01), gak ada diskon/akun tersembunyi yang nutupin.

Selama field-nya keisi, tiap simpan rate-nya disesuaiin lagi (mis. qty diubah); kosongin buat berhenti.
Cuma draft, bukan retur.

**Nyambung ke PR & COGS.** Alurnya DO & PR udah ada duluan, PI belakangan. Yang berubah rate item
(`base_net_amount` PI), jadi kalau **Buying Settings → Set Landed Cost Based on Purchase Invoice Rate**
nyala, selisihnya masuk ke *Amount Difference with Purchase Invoice* di PR, valuasi di-repost, dan COGS
Delivery Note ikut berubah (dites: PI dari 362,22 jadi 360,36 → COGS DN −362,22 → −360,36). Repost-nya
jalan lewat antrean background ERPNext — worker/scheduler harus nyala.

**Maintain Same Rate.** Buying Settings di site ini *Maintain Same Rate Throughout the Purchase Cycle* =
**Stop**, yang nolak rate PI beda dari PO/PR. Buat invoice yang Target Grand Total-nya diisi, cek itu
dilewatin (mixin `TargetGrandTotalMixin`, hook `extend_doctype_class`); invoice lain tetap dicek.
**Over billing tetap berlaku:** kalau target lebih **besar** dari nilai PO, submit ditolak ERPNext kecuali
*Over Billing Allowance* (Accounts Settings / Item) cukup.

Implementasi: `vic_addon/vic/purchase_invoice.py` (hook `before_validate`).

#### PPN Masukan Tertunda (Purchase Invoice)

Purchase Invoice yang **faktur pajaknya belum diterima**: PPN-nya dicatat dulu di akun PPN
Masukan Tertunda, baru direklas ke PPN Masukan begitu fakturnya dateng.

Akunnya diset per company, di tab **Accounts** bagian **PPN Masukan Tertunda**:

| Field | Isi |
| --- | --- |
| COA PPN Masukan Tertunda | akun yang dipilih di tabel pajak invoice; dikredit waktu reklas |
| COA PPN Masukan | akun tujuan reklas; didebit waktu reklas |

Jalannya:

1. **Purchase Invoice** — centang **PPN Tertunda** (di bawah *Deduct Taxes Paid on DP*), terus
   **pilih manual** akun PPN Masukan Tertunda sebagai *Account Head* baris PPN di tabel pajak.
   Waktu submit dicek: kalau dicentang tapi gak ada baris yang pakai akun itu (atau akunnya belum
   diset di Company), submit-nya ditolak. Draft bebas disimpan.
2. **Faktur pajak dateng** — tombol **Create > Reklas PPN Tertunda** di invoice yang udah submit
   bikin **draft** Journal Entry, terus langsung dibuka:

   ```
   DR  PPN Masukan                 11.000
   CR  PPN Masukan Tertunda                11.000
   ```

   Nilainya persis yang dijurnal invoice ke akun tertunda (`base_tax_amount_after_discount_amount`,
   baris `Deduct` ngurangin), dipecah per cost center baris pajaknya. Tanggalnya hari ini — masih
   draft, jadi tanggal (mis. tanggal faktur diterima) dan akunnya bisa dicek dulu sebelum submit.
   Debit note (nilai minus) arahnya kebalik.

Jurnalnya nyimpen nomor invoice-nya (field **PPN Tertunda Invoice**, `custom_ppn_tertunda_invoice`).
Satu invoice cuma dapat satu jurnal reklas: tombolnya diklik lagi = jurnal yang udah ada (draft
atau submitted) yang dibuka. Kalau jurnalnya dibatalin, tombolnya bisa bikin yang baru. Selama
jurnal reklasnya submitted, invoice-nya gak bisa dibatalin (link-nya ngunci).

Implementasi: `vic_addon/vic/ppn_tertunda.py` + `vic_addon/public/js/purchase_invoice.js`.

#### Vendor Deposit (uang jaminan ke supplier lewat PO)

Deposit / uang jaminan ke supplier (mis. deposit kontainer) — dicatat sebagai **aset**, bukan
biaya dan bukan uang muka barang. Tanpa PPN/PPh.

| Tempat | Field / tombol |
| --- | --- |
| Company → section **Vendor Deposit** | **Vendor Deposit Account** — akun aset (bukan grup) |
| Purchase Order (bagian total, di bawah Advance Paid) | **Deposit Amount** (mata uang perusahaan, bisa diubah setelah submit) + **Deposit Paid** (otomatis) |
| Purchase Order submitted | tombol **Pay Deposit** — muncul selama Deposit Paid < Deposit Amount |
| Payment Entry | **Deposit for Purchase Order** (penanda, read only) |

**Pay Deposit** buka Payment Entry yang udah keisi: Pay ke supplier PO, **Paid Amount = sisa
deposit** (boleh dikurangin, bayar sebagian), **Account Paid To = Vendor Deposit Account**,
**Account Paid From** = akun bank dari **Mode of Payment** yang dipilih (bawaan ERPNext; default awal
akun bank default company). Jurnalnya:

```
DR  Vendor Deposit Account (party: supplier)     600.000
CR  Bank / Kas                                           600.000
```

Akun deposit bukan akun hutang, jadi ERPNext **gak** bikin Payment Ledger Entry: deposit gak
nambah **Advance Paid** PO dan gak ketarik *Get Advances* di Purchase Invoice. Saldo deposit per
supplier dibaca dari **General Ledger** (filter akun deposit + party). Payment Entry deposit
sengaja gak boleh punya References, pajak, maupun potongan.

**Penjaga:** supplier & company harus sama dengan PO; Account Paid To harus akun deposit; total
deposit dibayar gak boleh lewat Deposit Amount; Deposit Amount gak boleh diturunin di bawah yang
udah dibayar. Deposit Paid dihitung ulang tiap Payment Entry deposit disubmit / dibatalin.

**Pengembalian deposit** (penuh atau sebagian) dicatat **manual**, mis. Payment Entry Receive dari
supplier dengan Account Paid From = akun deposit — gak ngubah Deposit Paid di PO.

**Book Advance Payments in Separate Party Account** (setting Company): kalau nyala, ERPNext nimpa akun
party Payment Entry ke akun uang muka waktu validate (`set_liability_account`). Payment Entry yang
akun party-nya Vendor Deposit Account dilewatin (`VICPaymentEntry`, lewat `override_doctype_class`),
baik bayar deposit maupun pengembaliannya. Payment Entry lain tetap ke akun uang muka kayak bawaan.

Dites (rollback): PO deposit 1jt → bayar 600rb → PE kedua keisi 400rb (bayar 500rb ditolak) → lunas,
tombol ditolak → cancel PE kedua, Deposit Paid balik 600rb; Advance Paid PO tetap 0.

Implementasi: `vic_addon/vic/vendor_deposit.py`, `vic_addon/public/js/vendor_deposit.js`.

#### Sales Order submitted: cuma bisa tambah item

Tombol bawaan **Update Items** di Sales Order diganti **Add Items**: SO yang udah submit cuma boleh dapat
**baris baru** — baris yang udah ada gak bisa diubah (qty, rate, UOM, tanggal) atau dihapus.

- **Muncul** di SO submitted selama statusnya bukan Closed / On Hold — **termasuk yang udah 100% terkirim
  atau ditagih** (Update Items bawaan ERPNext ngilang di kondisi itu; yang *partially* sebenarnya masih
  ada).
- Dialognya cuma berisi baris baru: Item, Qty, UOM, Rate, Delivery Date (default dari SO), Transaction
  Type (default Mixed).
- Barisnya ditambahin lewat mesin Update Items bawaan ERPNext (`update_child_qty_rate`), jadi status,
  % delivered/billed, pajak, dan validasinya tetap ERPNext yang ngurus. Contoh (dites): SO 100%
  terkirim + 1 item baru → % Delivered 40, status balik *To Deliver and Bill*.
- **Dijaga di server juga:** `update_child_qty_rate` di-override (`override_whitelisted_methods`) — request
  buat Sales Order yang ngubah atau ngehapus baris lama ditolak, dari jalur mana pun. Doctype lain
  (Purchase Order dll) gak kena.

Implementasi: `add_sales_order_items`, `update_child_qty_rate`, `validate_add_only` di
`vic_addon/vic/sales_order.py` + `vic_addon/public/js/sales_order.js`.

#### Sales Order: PO per supplier + dropship

Info supplier ikut turun sepanjang alur lewat field `Supplier Quotation` + `Supplier` di
tabel item:

```
SQTN -> Costing -> Quotation -> Sales Order -> Purchase Order
```

**Create > Purchase Order (per Supplier)** di Sales Order yang udah submit: muncul **modal**
berisi baris SO yang sisa qty-nya masih ada, lengkap dengan Pending Qty, tipe transaksi,
Supplier, dan SQTN-nya. Semua baris kecentang duluan; user tinggal ngurangin, baru klik Create.
Item yang belum punya SQTN kolom suppliernya kosong dan wajib diisi sebelum lanjut.

Tombol bawaan ERPNext **Create > Purchase Order** di Sales Order disembunyiin — udah gak dipakai,
diganti tombol ini.

Empat kolom bisa diedit langsung di modal:

| Kolom | Kelakuannya |
| --- | --- |
| **Qty** | Boleh dikurangin buat mesen sebagian dulu — sisanya tetap kecatat belum di-PO, jadi bisa dibikinin PO lagi nanti |
| **Supplier Quotation** | Pilihannya cuma penawaran submitted yang **ada item baris itu**; milih penawaran yang gak nawarin itemnya bikin harga gak ketarik, jadi disaring dari sumbernya |
| **Supplier** | Ngikut otomatis begitu SQTN dipilih, dan kekunci selama SQTN keisi — mau isi supplier sendiri, kosongin dulu SQTN-nya |
| **Transaction Type** | Reguler / Dropship / Mixed, default dari baris SO. Yang dipilih masuk ke baris PO (header PO ringkasannya) — alur Delivery Note / Purchase Receipt dari PO ngikut tipe ini. Baris SO-nya sendiri gak diubah |

Harga beli PO ngikut SQTN yang dipilih di modal (bukan yang nempel di baris SO), jadi kalau ada
penawaran lain yang lebih murah tinggal ditukar di situ.

**Nuker SQTN mesti disetujui dulu.** Begitu SQTN di sebuah baris beda dari yang dipakai waktu
penawaran ke customer disusun, tombol Create munculin konfirmasi yang nyebut item mana, SQTN di
Sales Order-nya apa, dan SQTN yang bakal dipakai apa — PO baru dibuat setelah user setuju. Ini
gantiin peringatan lama yang munculnya belakangan (setelah PO terlanjur dibuat).

Habis itu barisnya digrup per **supplier** — satu supplier satu draft PO. Harga
belinya diambil dari SQTN (net rate) dan PO item langsung nyimpen link `Supplier Quotation` +
balik ke Sales Order. Baris yang suppliernya diganti di modal gak dikasih link SQTN dan harganya
dikosongin — penawaran itu punya supplier lain, jadi harga belinya diisi manual sesuai penawaran
supplier baru.

Grupnya per baris, bukan per item code, jadi **item yang sama boleh muncul di beberapa baris**:

| Baris SO | Hasil |
| --- | --- |
| Item sama, supplier sama | Digabung jadi satu PO (beberapa baris di dalam PO yang sama) |
| Item sama, supplier beda | PO-nya kepisah, satu per supplier |
| Tipe transaksi beda (Reguler / Dropship / Mixed) | **Gak** misahin PO — satu pesanan ke satu supplier tetap satu dokumen |

Tipe transaksi tiap baris SO kebawa ke baris PO-nya masing-masing; header PO cuma nyimpen
ringkasan (`Mixed` kalau barisnya campur). Alamat kirim customer dipasang begitu ada **satu aja**
baris yang dikirim langsung ke lapangan — barang yang masuk gudang sendiri tetap kearah gudang
lewat field warehouse di barisnya.

Contoh nyata: SO isi `ITM-EL-00001` di baris #1 (Common Supplier) dan baris #2 (Electrical
Supplier) → jadi 2 draft PO, masing-masing pakai harga beli dari SQTN-nya sendiri (bukan harga
jual di SO). Kalau supplier di dua baris itu sama tapi tipenya beda, hasilnya cuma **1** PO.

> **Tipe `Mixed` baru sebatas penanda.** Dipakai buat baris yang qty-nya dipecah — misalnya
> qty 2: 1 dikirim langsung ke customer, 1 masuk gudang. Berapa yang ke mana **belum** ada
> field-nya, jadi otomatisasi dropship (gudang transit, Purchase Receipt otomatis waktu DN
> disubmit, tombol Create Delivery Note di PO, seri nomor `-DS-`) masih ngebaca tipe `Dropship`
> doang dan ngelewatin baris `Mixed`. Itu bagian yang nyusul.

Dokumennya tetap dibikin `make_purchase_order` bawaan ERPNext, jadi handling currency, exchange
rate, alamat kirim buat dropship, dan sisa qty yang belum di-PO ikut kebawa. Mapper bawaannya
milih baris SO dari item code doang, jadi tiap PO yang kebentuk disaring lagi ke baris punya
grupnya — baris nyasar dibuang sebelum PO disimpan, tanpa notif palsu ke user.

**PO dobel dicegah.** ERPNext cuma ngitung PO yang udah submit (lewat `Sales Order
Item.ordered_qty`), jadi tombolnya diklik dua kali bikin draft PO kembar. Di addon, PO draft
**dan** submitted dua-duanya dihitung: item yang udah ketutup PO aktif dilewatin, dan pesannya
nyebut baris, item, plus **nomor PO-nya** (link ke dokumennya, ditandain kalau masih draft) biar
user gak perlu nyari sendiri. Kalau semua item udah ada PO-nya, prosesnya ditolak sekalian nyebut
PO mana aja yang udah ada.

**PO yang dibatalin boleh dibikin ulang.** PO dengan docstatus 2 sengaja gak dihitung, jadi
begitu PO di-cancel, tombolnya bikin PO baru cuma buat item dari PO yang batal itu — item lain
yang PO-nya masih aktif gak ikut kebikin lagi. Ini yang dipakai buat kasus supplier ganti
(R&C ke-6 di sheet Costing).

**Tombol bawaan `Create > Purchase Order` dibiarin apa adanya** - gak di-override, gak
disembunyiin. Cuma perlu diinget mapper bawaan ERPNext milih baris Sales Order dari **item code**,
bukan dari barisnya: kalau satu item muncul di dua baris SO dengan supplier beda, PO buat supplier
A ikut kebawa baris punya supplier B. Buat kasus multi-supplier kayak gitu, pakai tombol **Purchase
Order (per Supplier)** di atas yang nyaringnya per baris.

Pengamannya ada di sisi server: PO baru dari tombol bawaan yang kebawa baris jatah supplier lain,
barisnya dibuang waktu disimpan sekalian dikasih tau item mana yang dibuang. Kecuali kalau semua
barisnya begitu: dibiarin, biar dokumennya gak jadi kosong dan user bisa lihat sendiri apa yang
kejadian. Pengaman ini gak jalan buat PO dari tombol custom — di sana barisnya udah disaring per
baris, dan suppliernya emang boleh sengaja diganti di modal.

**Supplier di PO boleh diganti.** Barang habis di supplier pertama itu kasus normal (R&C ke-6 di
sheet Costing). Tiap PO disimpan, link SQTN-nya disamain dulu sama suppliernya:

| Kondisi | Yang terjadi |
| --- | --- |
| Supplier PO beda dari supplier SQTN | Link SQTN dilepas + dikasih tau, harga beli bebas diisi sesuai penawaran supplier baru |
| Baris dari SO belum punya link tapi suppliernya sama | Link SQTN-nya diambil dari baris Sales Order (biar PO dari modal bawaan tetap kekunci harganya) |

Ini jalan **sebelum** `rate_lock`, jadi harga belinya gak ketarik balik dari penawaran supplier
lama. Nomor supplier di Sales Order-nya sendiri gak ikut berubah — SO udah submitted, dan yang
diganti emang cuma keputusan beli di PO itu.

**Link PO dicek balik ke SQTN** tiap PO disimpan (`vic_addon/vic/purchase_order.py`):

| Cek | Kalau gak lolos |
| --- | --- |
| SQTN-nya ada dan udah disubmit | ditolak |
| Supplier SQTN = supplier PO | ditolak |
| Item code-nya ada di SQTN itu | ditolak |
| Baris SO punya SQTN tapi baris PO-nya kosong | cuma diingetin (gak diblokir) |

**Qty PO gak dibatesin qty yang ditawarin SQTN.** Dulu ada aturan "total qty di semua PO aktif
gak boleh lewat dari qty di SQTN" dan itu dicabut: penawaran supplier sering ditulis buat 1 unit
doang sebagai patokan harga, sedangkan pesanannya bisa lebih banyak — sanggup atau enggaknya
supplier itu urusan yang dibereskan di lapangan, bukan diblokir sistem. Qty di Costing maupun
Quotation juga sengaja gak dicek balik ke SQTN.

Referensi SQTN di PO item pakai custom field (`custom_supplier_quotation`), **bukan** field
bawaan `supplier_quotation`. Field bawaan bikin ERPNext maksa PO item sama persis dengan
SQTN-nya di `project`, `uom`, dan `conversion_factor` — padahal project di PO ngikut Sales
Order, jadi PO gagal disimpan kalau SQTN-nya punya project yang beda.

Implementasi: `vic_addon/vic/sales_order.py` + `vic_addon/vic/purchase_order.py` +
`vic_addon/public/js/sales_order.js`.

Belum: print format Proforma Invoice (di sheet masih "Awaiting"). Auto reserve stock pas SO
submit / Purchase Receipt submit gak perlu custom, tinggal nyalain di Stock Settings.

#### Loan Memo (custom doctype)

Nota peminjaman barang ke customer: barang dipinjemin dulu buat dicoba di lapangan, ujungnya
cuma dua — **dibeli** (lanjut ke Sales Order) atau **dibalikin** (masuk lagi ke gudang asal).
Dokumen ini yang jadi pegangan dua-duanya.

| Field | Isi |
| --- | --- |
| Series | `LM-.YYMM.-` (reset per bulan, amend pakai suffix `R`) |
| Posting Date | Tanggal memo |
| Expected End Loan Date | Perkiraan barang balik / diputusin dibeli |
| Company, Customer | Wajib |
| Project | Proyek yang minjem barangnya; ikut kebawa ke Stock Entry & Sales Order turunannya |
| Sales Person Name | Link ke Sales Person |
| Loan Memo Status | *Approved to Buy* / *Approved to Return* — keputusan customer, bisa diisi setelah submit |
| Remarks | Catatan bebas |

Child table **Loan Memo Item**: Item, Item Name, Qty, UOM, From Warehouse, To Warehouse.
Qty & UOM ditambahin sendiri (gak ada di sheet) karena tanpa itu Stock Entry peminjamannya gak
bisa dibikin.

Dua gudangnya keisi otomatis tiap memo disimpan, dan tetap bisa diganti manual:

- **From Warehouse** — gudang default item di company itu (`Item Default`), kalau kosong jatuh ke
  default warehouse di Stock Settings
- **To Warehouse** — gudang peminjaman customer, diambil dari field **Customer Loan Warehouse**
  di Company. Belum ada? dibikinin `Customer Loan - {abbr}` terus disimpen balik ke Company —
  pola yang sama kayak gudang transit dropship

Yang divalidasi: qty harus lebih dari nol, dan From/To Warehouse gak boleh sama.

Implementasi: `vic_addon/vic/doctype/loan_memo/`.

**Statusnya jalan sendiri**, user cuma milih di satu percabangan. Field Loan Memo Status
read-only, yang ngubah dokumen turunannya:

```
Draft
  └─ submit ─────────────────────────────────────► Approved to Deliver
       └─ Stock Entry (Customer Loan) disubmit ───► Delivered
            ├─ tombol Approve to Sell ────────────► Approved to Sell
            │    └─ Sales Order disubmit ─────────► Sold
            └─ tombol Approve to Return ──────────► Approved to Return
                 └─ Stock Entry (Customer Loan Return) disubmit ─► Returned
```

Tombolnya nongol ngikutin status, jadi gak ada jalan pintas:

| Status | Tombol |
| --- | --- |
| Approved to Deliver | Create > Stock Entry (Customer Loan) |
| Delivered | **Approve to Sell** / **Approve to Return** |
| Approved to Sell | Create > Sales Order |
| Approved to Return | Create > Stock Entry (Customer Loan Return) |

Dua Stock Entry Type (`Customer Loan`, `Customer Loan Return`) dibikin otomatis waktu
install/migrate, dua-duanya purpose **Material Transfer** — barangnya cuma pindah gudang, belum
kejual. Yang balikin gudangnya kebalik sendiri (Customer Loan → gudang asal).

Sales Order-nya ngambil gudang **peminjaman customer** (barangnya emang udah di sana), tanggal
kirim ikut Expected End Loan Date, dan Sales Person Name masuk ke Sales Team 100%.

Tiap dokumen turunan dibatalin, status memo balik ke langkah sebelumnya — jadi salah submit
tinggal di-cancel, gak usah bikin memo baru. Memonya sendiri gak bisa dibatalin selama masih ada
Stock Entry/Sales Order aktif yang lahir dari dia, dan pesannya nyebut dokumen mana yang harus
dibatalin duluan. Tiap perpindahan status dicatat di timeline.

Tab **Connections** di Loan Memo nampilin Stock Entry & Sales Order-nya (lewat field
`custom_loan_memo` di dua doctype itu).

> Catatan: di sheet, baris *Characters* nulis statusnya "Approved to **Buy**", baris *Workflow*
> nulis "Approved to **Sell**". Yang kepakai di sini yang versi Workflow, soalnya di situ semua
> state-nya lengkap.

#### Selling Price Estimate (custom doctype)

Alat hitung buat Purchasing/Sales: ancer-ancer harga jual sebuah barang sebelum ada costing
resmi. Dokumennya gak posting jurnal dan gak dipakai transaksi.

```
Estimasi Harga Jual = (Last Purchase Rate + Biaya Tambahan per Unit) / (1 - Margin %)

contoh: (15.000 + 2.000) / (1 - 20%) = 21.250
```

User milih **Item** + **Warehouse**, sisanya keisi sendiri:

| Field | Isinya |
| --- | --- |
| Last Purchase Rate | Rate dari baris **Purchase Receipt** submitted paling akhir buat item itu. Warehouse dikosongin = dari gudang mana aja |
| Purchase Receipt, Purchase Date, Qty | Dokumen sumbernya, biar angkanya bisa dilacak |
| Margin % | Margin atas harga jual, harus di bawah 100 |

**Biaya tambahannya dua rasa**, dipilih lewat checkbox **With Last LCV**:

| With Last LCV | Tabel yang muncul | Biayanya dari |
| --- | --- | --- |
| Mati | **Additional Costs** (isi manual, pola sama kayak Costing) | Jumlah kolom Amount — diisi **per unit** |
| Nyala | **Landed Cost dari Pembelian Terakhir** (read-only) | Landed Cost Voucher yang nempel di Purchase Receipt tadi |

Baris Landed Cost-nya diambil dari `applicable_charges` — porsi biaya yang udah dialokasiin
ERPNext ke baris penerimaan itu — terus dibagi qty biar ketemu **biaya per unit**. Nama biayanya
(Freight, Handling, dst) ikut ditampilin di kolom Description. Kalau Purchase Receipt-nya gak
punya Landed Cost Voucher, biayanya nol dan user dikasih tau.

Hitungannya jalan dua kali: di form (biar angkanya langsung kelihatan waktu isian diubah) dan di
server tiap disimpan — yang di server itu yang jadi pegangan.

Implementasi: `vic_addon/vic/doctype/selling_price_estimate/`.

#### Kertas Kerja Arus Uang dan Barang (PPN masukan vs keluaran)

Kertas kerja buat pemeriksaan pajak: **penyerahan** diadu sama **pembelian**, dikelompokin per
**proyek**. Kiri faktur pajak keluaran, kanan faktur pajak masukan — buat nunjukin barang yang
dijual itu asalnya dari pembelian yang mana.

Dua bentuk, datanya sama:

| Bentuk | Buat apa |
| --- | --- |
| Report **Arus Uang dan Barang** di desk | dilihat & difilter langsung, bisa di-drill ke dokumennya |
| Tombol **Download Excel** di report itu | bentuknya persis kertas kerja pemeriksa, buat diserahin |

Filternya: Company, From Date, To Date, Project (opsional — kosong berarti semua proyek, plus
satu kelompok "Tanpa Proyek").

Sumber datanya:

| Kolom | Dari |
| --- | --- |
| NPWP | `tax_id` di Sales/Purchase Invoice (ketarik dari master Customer/Supplier) |
| Faktur Pajak jual | field baru **Nomor Faktur Pajak** + **Tanggal Faktur Pajak** di Sales Invoice |
| Faktur Pajak beli | `bill_no` + `bill_date` di Purchase Invoice |
| DPP | `net_total` |
| PPN | total baris pajak, **kecuali** baris PPh (`is_tax_withholding_account` atau `Deduct`) |
| Quantity, UOM, harga satuan | baris item Purchase Invoice |

Dua sisinya gak punya hubungan baris-per-baris — yang nyambungin cuma proyeknya. Jadi barisnya
disusun berdampingan: kiri jalan sendiri, kanan jalan sendiri, yang pendek diganjal baris kosong
sampai sejajar. Satu invoice bisa makan beberapa baris: baris pertama bawa identitas lawan
transaksi + nomor faktur + DPP + PPN, baris berikutnya cuma rincian barang.

Versi Excel-nya disusun sendiri pakai openpyxl (bukan export bawaan Frappe) karena judul
kolomnya bertingkat tiga dan perlu di-merge — report bawaan gak bisa gitu.

Implementasi: `vic_addon/vic/report/arus_uang_dan_barang/` (data + tampilan desk) dan
`vic_addon/vic/arus_uang_dan_barang.py` (versi Excel).

#### Warehouse default di Inquiry

Baris item Inquiry yang warehouse-nya **kosong** diisi gudang dari **Stock Settings → Default
Warehouse**. Yang udah ada isinya — dipilih user atau kebawa dari Material Request — dibiarin.

| Jalur | Kapan keisi |
| --- | --- |
| Tombol *Create → Inquiry* di RFQ | langsung, sebelum disimpan |
| Nambah baris manual / jalur lain | waktu disimpan |

Dipasang di `before_validate`, bukan `validate`: cek field wajib jalan di antara dua itu, jadi
kalau warehouse-nya diwajibin, baris kosong udah keburu ditolak sebelum sempat diisi.

Catatan: Stock Settings itu satu nilai buat **semua company**. Kalau nanti butuh gudang default
yang beda per company, perlu field tambahan di Company.

Implementasi: `set_default_warehouse` di `vic_addon/vic/request_for_quotation.py`.

#### Kirim Inquiry ke supplier (pilih item dulu)

Tombol **Actions → Send Inquiry** di Request for Quotation (di desk namanya *Inquiry*) buka satu
pop up: pilih supplier, centang item mana aja yang mau dimintain harganya, tulis subject sama
isi emailnya. Barang sering dipecah per jenis supplier, jadi jarang satu supplier dimintain
semua item di dokumen.

Empat tombol di pop up-nya, semuanya pakai item yang dicentang doang:

| Tombol | Yang terjadi |
| --- | --- |
| **Send Email** | Kirim ke email supplier di baris tabel Suppliers, lampirannya Excel atau PDF. Emailnya masuk timeline dokumen |
| **Send WhatsApp** | Bikin file publik + link, terus buka WhatsApp Web/Desktop dengan teksnya udah keisi |
| **Download Excel** | Unduh sendiri |
| **Download PDF** | Print format Inquiry jadi PDF |

**Jejaknya:** tiap kirim, file yang dikirim nempel di dokumennya — jadi kelihatan kapan dikirim
ke siapa dan isinya apa. File buat email disimpan **privat**; file buat WhatsApp **publik**,
soalnya penerimanya buka dari HP tanpa akun. Nama filenya dikasih kode acak 8 karakter di
ujungnya, itu yang jadi kunci link — gak bisa ditebak dari nomor dokumen, dan link-nya mati
begitu lampirannya dihapus dari dokumen.

Penyaringan itemnya cuma di **salinan memori** — dokumen aslinya gak disentuh, jadi kirim ke
supplier A dengan 3 item dan ke supplier B dengan 2 item lain gak saling ganggu.

**Tombol bawaan yang dicopot.** Grup **Tools** di dokumen yang udah submit isinya dua tombol
yang sekarang digantiin Send Inquiry, dan dua-duanya disembunyiin biar gak bikin bingung:

| Tombol | Kelakuan bawaannya |
| --- | --- |
| Send Emails to Suppliers | Ngirim *link portal* supaya supplier ngisi harga sendiri di web, subject/body dari Email Template, lampirannya semua file yang nempel di dokumen |
| Download PDF | Nanya print format + supplier lewat prompt, terus diunduh — tanpa pilih item |

Dicopotnya waktu `refresh`, bukan `setup` — tombolnya baru dipasang ERPNext pas refresh jalan.
Tombol **Tools** waktu dokumennya masih draft (*Link to Material Requests*, *Get Suppliers*)
sengaja **dibiarin** — itu buat nyusun dokumennya, bukan buat ngirim, dan gak ada gantinya.

**Kolom Send Email di tabel Suppliers disembunyiin, default 0** (property setter
`Request for Quotation Supplier-send_email-*`). Centangan ini yang bikin ERPNext otomatis ngirim
email link portal ke supplier **waktu Inquiry di-submit** (`on_submit` → `send_to_supplier`) — jadi
sekarang submit gak ngirim apa-apa, ngirimnya lewat Send Inquiry. Draft lama yang masih kecentang
dinolin patch `disable_inquiry_supplier_email`; yang udah submitted dibiarin.

Implementasi: `vic_addon/vic/request_for_quotation.py` +
`vic_addon/public/js/request_for_quotation.js`.

#### Inquiry versi Excel

Print format **Inquiry** itu buat dicetak dan diisi tangan. Tombol **Actions > Download Inquiry**
di Request for Quotation ngeluarin isi yang sama dalam bentuk Excel, **tata letaknya niru
`RFQ Excel Template.xlsx`** yang selama ini dipakai purchasing:

| Bagian | Letaknya |
| --- | --- |
| Logo VIC (gambar) | Kiri atas, mulai kolom B |
| Nama + alamat perusahaan | Rata kanan, baris 1-6 |
| Judul `INQUIRY` | `B7:N8`, ukuran 20, di tengah |
| Inquiry No. / Date | `G9` / `G10`, titik dua di kolom sendiri |
| Subject, kalimat pengantar | `B15`, `B16` |
| Judul kolom | Baris 17-18, diapit garis melintang, tanpa garis tegak |
| Item | Mulai baris 19, ditutup garis di bawah baris terakhir |
| Penutup | `Wait for your reply immediately`, lalu `Best regards,` + nama penanda tangan (sama kayak print format, lihat field **Best Regards**) |

Kolom A dipakai jadi margin kiri (lebar 1,1) kayak template, fontnya **Aptos Narrow**, dan tiga
kolom **Unit Price, Weight, Remarks** dibiarin kosong buat diisi supplier. Supplier ngisi di
spreadsheet lalu kirim balik — purchasing gak perlu ngetik ulang.

Bagian yang dipakai bareng (logo, blok alamat, judul, margin) ada di `vic_addon/vic/excel.py`.

Kolom lebar di print format-nya juga dibenerin: tabelnya sekarang pakai `table-layout: fixed`, jadi
lebar kolom ngikut angka yang ditulis di header. Sebelumnya lebar dihitung dari isi sel, dan karena
tiga kolom terakhir emang sengaja kosong, kolomnya kekempis dan judulnya gak sejajar sama nilainya.
Perbaikan ini kena ke semua print format karena ada di kop surat bareng.

Implementasi: `vic_addon/vic/request_for_quotation.py`.

#### Supplier Comparison (download dari Request for Quotation)

Satu RFQ dikirim ke beberapa supplier, dan tiap supplier bisa nawar berkali-kali di waktu yang
beda. Tombol **Actions > Download Comparison** di RFQ yang udah submit nyusun semua penawaran itu
jadi satu file Excel — format kolomnya ngikutin tabel perbandingan yang selama ini dipakai
purchasing.

**Penawaran mana yang dipakai:** cuma **dua terakhir** tiap supplier, diurut dari tanggal
dokumennya — yang lebih tua diabaikan. Supplier yang baru nawar sekali cuma dapat satu kolom
(nama suppliernya turun nutupin baris Lama/Baru).

**Penawaran yang gak lengkap.** Barang sering dipecah per jenis supplier, jadi wajar kalau ada
supplier yang cuma nawar sebagian item RFQ (baris sisanya dihapus manual di Supplier Quotation).
Yang dijaga di sini: penawaran sebagian **gak boleh diadu totalnya** lawan penawaran lengkap —
totalnya kecil bukan karena murah, tapi karena itemnya kurang.

| Keadaan | Yang dilakuin |
| --- | --- |
| Item gak ditawar | Selnya diisi tanda `—` berlatar abu-abu, bukan dibiarin kosong (kosong gampang kebaca sebagai harga nol) |
| Baris **Item Ditawar** | Nunjukin `3 / 5` — berapa item yang ditawar dari total item RFQ |
| Penentuan termurah | Cuma penawaran **lengkap** yang diadu. Yang sebagian gak dapat sorotan termurah dan gak dapat angka **vs Termurah** |
| Catatan kaki | Muncul otomatis kalau ada penawaran yang gak lengkap, ngejelasin arti tanda `—` |

Penandaan harga termurah **per baris item** tetap jalan seperti biasa — itu perbandingan yang
sah, soalnya barangnya sama. Yang dibatesin cuma perbandingan total antar supplier.

Yang dibaca sebagai "ditawar" itu **ada atau enggaknya baris** di Supplier Quotation, bukan
nilainya — jadi barang yang emang ditawar dengan harga nol tetap kehitung ditawar.

| Kolom | Isinya |
| --- | --- |
| Item, Description, Qty, UOM | Dari baris RFQ — jadi qty-nya satu acuan buat semua supplier |
| Unit Price | `net_rate` penawaran (harga setelah diskon bertingkat) |
| Total Price | Unit Price x Qty di RFQ, bukan qty yang ditulis supplier |

Bawahnya Total → PPn 11% → Grand Total, terus **dua lapis selisih**:

1. **Lama vs Baru** per supplier: `(Lama - Baru) / Baru` — hasil nego turun berapa persen
2. **vs Termurah**: penawaran **terakhir** tiap supplier dibanding yang paling murah; yang termurah
   ditandain hijau, gitu juga harga satuan termurah per baris item

Urutan suppliernya ngikut daftar di RFQ biar kolomnya gak tuker-tukeran tiap kali di-download.

**Actions > Share to WhatsApp** buat ngirim hasilnya ke orang yang gak punya akun ERPNext
(misalnya direksi):

1. Tabel yang sama dirender jadi **PDF** (landscape, kop VIC, penanda kuning ikut kebawa)
2. PDF-nya di-attach ke RFQ, namanya diakhiri kode acak 8 karakter — kode itu yang jadi kunci
   link: `/api/method/vic_addon.vic.supplier_comparison.view_comparison?key=0883a153`
3. Muncul dialog berisi link + tombol **Open WhatsApp** — WhatsApp Web/aplikasi kebuka dengan
   pesan udah keisi (nama proyek, supplier termurah, link), tinggal pilih kontak dan kirim

Link-nya kebuka tanpa login — itu emang tujuannya, tapi artinya **siapa pun yang pegang link bisa
lihat harga semua supplier**. Buat nyabut, hapus lampirannya dari RFQ.

**Sekali share, satu file.** Tiap tombolnya dipencet, PDF lama di RFQ itu dihapus (record File
sekaligus filenya di disk), jadi lampirannya gak numpuk dan cuma ada satu link yang hidup.
Hapusnya dilakuin **setelah** PDF baru jadi — kalau proses bikin PDF-nya gagal, link lama masih
kepakai. Efek sampingnya: link yang udah terlanjur dibagi mati begitu ada share baru, jadi kirim
ulang link terbarunya.

Logo di PDF ditanam sebagai data URI, bukan link ke `/assets` — kalau lewat link, `wkhtmltopdf`
gagal narik gambarnya dan PDF-nya batal kebentuk.

**Nomor halaman di semua print format.** File `vic_footer.html` (di-include paling bawah tiap
print format) nyimpen blok `<div id="footer-html">` berisi
`Page <span class="page">01</span> of <span class="topage">01</span>`. Frappe nyabut blok itu dari
badan dokumen (`prepare_header_footer`) dan ngirimnya ke wkhtmltopdf sebagai `--footer-html`, jadi
dia nempel di **setiap halaman** dan angkanya ngikut jumlah halaman beneran. Script kecil di situ
nambahin nol di depan biar formatnya `Page 01 of 02` kayak form kertas VIC. Label stiker Serial No
gak kena karena dia emang gak pakai kop surat.

Dua hal yang bikin blok ini ditulis begitu:

- **Ditaruh paling bawah, bukan di atas.** Frappe **gak punya** aturan CSS buat kelas
  `visible-pdf`, jadi di tampilan layar (print view / cetak dari browser) blok ini tetap kerender.
  Di bawah dia kebaca wajar sebagai baris penutup; waktu ditaruh di atas, dia nongol nyasar di
  kepala dokumen.
- **Isi bawaannya ditulis `01`,** bukan span kosong. Di layar gak ada yang ngisi angka itu — kalau
  dikosongin, yang kebaca user cuma tulisan "Page of". Waktu jadi PDF, wkhtmltopdf nimpa isinya
  dengan nomor beneran.

> **Butuh wkhtmltopdf build "patched qt".** Versi bawaan Ubuntu (`0.12.6-2build2`) nolak semua
> switch header/footer — pesannya *"The switch --footer-html, is not support using unpatched qt,
> and will be ignored"* — dan diam-diam juga ngabaikan `--print-media-type` sama
> `--disable-smart-shrinking`, jadi PDF-nya dirender pakai CSS layar. Staging udah diganti ke
> `wkhtmltopdf 0.12.6.1 (with patched qt)` dari rilis resmi wkhtmltopdf (paket `wkhtmltox`).
> Mesin lain yang mau bikin PDF mesti pakai build yang sama.
####
cd /tmp
curl -sLO https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-3/wkhtmltox_0.12.6.1-3.jammy_amd64.deb
sudo apt-get install -y xfonts-75dpi          # cuma ini yang belum ada di laptop lo
sudo dpkg -i wkhtmltox_0.12.6.1-3.jammy_amd64.deb
wkhtmltopdf --version        # harus keluar: 0.12.6.1 (with patched qt)
###

**Kenapa gak pakai URL `/files/...` langsung.** Frappe nyari folder site buat file statis dari
**nama host** (`StaticDataMiddleware`), bukan dari header `X-Frappe-Site-Name` yang dipasang
nginx. Di server kita nama folder site (`vic-app`) beda dari domainnya
(`vic.thenextflow.cloud`), jadi link `/files/...` nyariin folder `sites/vic.thenextflow.cloud/`
dan berujung 404. Lewat endpoint `view_comparison` permintaannya masuk ke alur biasa, di mana
nama site dibaca dari header nginx — jadi jalan tanpa nyentuh setelan server.

Endpoint-nya `allow_guest`, tapi yang bisa dibuka cuma lampiran PDF perbandingan di Request for
Quotation, kuncinya wajib alfanumerik, dan PDF-nya dikirim `inline` biar kebuka langsung di HP.

Implementasi: `vic_addon/vic/supplier_comparison.py`, `vic_addon/templates/supplier_comparison.html`,
`vic_addon/public/js/request_for_quotation.js`.

#### Biaya dari Journal Entry ditarik ke Landed Cost Voucher

Biaya impor (ongkos kapal, bea masuk, jasa forwarder) biasanya udah kecatat duluan lewat Journal
Entry. Yang belum kejadian: biayanya masih nangkring di akun biaya, belum nempel ke nilai
barangnya. Landed Cost Voucher yang mindahin — cuma bawaannya biayanya mesti diketik ulang
satu-satu.

Alurnya sekarang:

1. Di **Journal Entry Template**, baris biaya yang nambah nilai persediaan dicentang
   **Biaya yang masuk nilai barang**. Dicentang sekali di templatenya.
2. Waktu template dipilih di **Journal Entry**, centangannya kebawa sendiri. Nama field-nya
   sengaja sama persis di dua doctype, dan ERPNext nyalin semua field baris template apa adanya
   — jadi gak perlu kode tambahan.
3. Di **Landed Cost Voucher**, tombol **Get Expenses From → Journal Entry**. Pilihan jurnalnya
   udah kesaring: cuma yang punya minimal satu baris bercentang, submitted, dan se-company.
4. Yang ketarik ke tabel Landed Cost **cuma baris bercentang**. Jurnal yang isinya campur (biaya
   barang + biaya lain) tetap aman — yang gak dicentang gak ikut.

Yang diambil cuma sisi **debit**: itu yang nunjukin biaya keluar. Baris kredit di jurnal yang
sama (kas/hutang) bukan biaya, jadi dilewat. Tiap baris nyimpen nomor jurnal asalnya di field
**Journal Entry**.

**Satu jurnal cuma boleh dipakai di satu voucher aktif** (draft atau submit) — kalau kepakai dua
kali, biayanya nempel dua kali ke nilai barang. Dicek di tiga lapis:

| Lapis | Perilaku |
| --- | --- |
| Pilihan jurnal di dialog | Jurnal yang udah kepakai voucher lain gak ditawarin |
| Tombol **Get Expenses** | Ditolak kalau jurnalnya udah kepakai (juga kalau dipilih dua kali di voucher yang sama) |
| Simpan / submit voucher (hook `validate`) | Ditolak — nangkep jalur di luar form (import, API) dan dua draft yang narik jurnal sama |

Pesannya nyebut voucher mana yang udah make. Voucher yang **dicancel** ngelepas jurnalnya, jadi
bisa ditarik lagi ke voucher baru (atau amend-annya).

Tabel **Vendor Invoices** di Landed Cost Voucher disembunyiin (property setter `hidden`) — biaya
diambil dari Journal Entry, bukan dari invoice supplier. Tabel itu emang opsional di ERPNext,
cuma dipakai nyatet klaim landed cost ke Purchase Invoice.

Implementasi: `vic_addon/vic/landed_cost.py` + `vic_addon/public/js/landed_cost_voucher.js`.

#### Repack Percentage (Stock Entry Repack)

Repack bawaan ERPNext yang hasilnya lebih dari satu item **maksa** semua baris hasil dicentang *Set
Basic Rate Manually* — user ngitung rate tiap hasil sendiri. Kalau gak dicentang, nilai bahannya
dibagi rata per qty, padahal hasil bongkaran/potongan nilainya jarang sebanding sama qty-nya.

Field **Repack Percentage** (`custom_repack_percentage`) di baris item Stock Entry — muncul cuma di
Repack, di baris yang punya Target Warehouse (item hasil). Isi porsi nilai bahan buat tiap hasil:

```
basic amount hasil = total nilai bahan keluar × persentase / 100
basic rate hasil   = basic amount / qty (stock UOM)
```

Contoh (udah dites): bahan 3 × 1.000 = 3.000 → hasil A 2 pcs 70% = **2.100** (1.050/pcs), hasil B
7 pcs 30% = **900** (128,57/pcs). Total masuk = total keluar, selisih 0.

| Aturan | |
| --- | --- |
| Satu baris hasil diisi | semua baris hasil wajib diisi, totalnya **harus 100%** |
| Baris hasil terakhir | dapet sisa nilai (bukan dikali persen lagi) — gak ada selisih pembulatan ke akun Stock Adjustment |
| Set Basic Rate Manually | dicopot otomatis di baris yang pakai persentase |
| Gak ada yang diisi | Repack jalan persis kayak bawaan (termasuk error wajib Set Basic Rate Manually) |
| Additional Costs | tetap dibagi bawaan ERPNext, proporsional ke nilai hasil |

Hitungannya nempel di `set_basic_rate`, jadi ikut kepakai waktu **repost valuasi**: kalau harga
bahannya berubah karena ada transaksi mundur, nilai hasilnya ikut nyesuain dengan persentase yang
sama (dites: bahan jadi 3.600 → 2.520 / 1.080). Beda sama Set Basic Rate Manually yang rate-nya beku.
Rate hasil baru kelihatan setelah Save (dihitung server).

Implementasi: `vic_addon/vic/stock_entry.py` (`VICStockEntry`, lewat `override_doctype_class`) +
`vic_addon/public/js/stock_entry.js`.

#### Tanggal jurnal ikut pindah ke tanggal cair di bank

Bank Clearance bawaan cuma nulis **Clearance Date** ke dokumennya — tanggal posting sama
jurnalnya gak kesentuh, jadi kas tetap kecatat di tanggal dokumen dibikin, bukan tanggal duitnya
beneran cair. Di sini tanggal postingnya digeser ikut Clearance Date, terus jurnalnya ditulis
ulang lewat **Repost Accounting Ledger** bawaan ERPNext.

| Langkah | Yang terjadi |
| --- | --- |
| Clearance Date diisi | Tanggal semula disimpan di **Original Posting Date**, `posting_date` diganti jadi tanggal clearance, jurnalnya ditulis ulang |
| Clearance Date dikosongin | `posting_date` balik ke Original Posting Date, field-nya dikosongin, jurnalnya ditulis ulang |
| Clearance Date **sama** dengan posting date | Gak ngapa-ngapain |

**Urutannya gak boleh kebalik**: tanggal dokumennya diganti dulu, baru di-repost. Repost bikin
jurnal baru dari nilai dokumen yang sekarang — kalau repost duluan, jurnalnya cuma ketulis ulang
di tanggal yang lama.

**Yang ikut kegeser**: GL Entry **dan** Payment Ledger Entry (yang dipakai buat umur piutang/
hutang). Jurnal lama gak dihapus — barisnya tetap ada dengan tanda cancelled, gak keitung di
laporan tapi masih bisa ditelusuri.

**Yang digeser cuma Payment Entry sama Journal Entry**, dan cuma kalau doctype-nya kedaftar di
*Accounts Settings → Repost → Allowed DocTypes* (tabel itu kosong dari sananya, jadi harus diisi
dulu). Invoice sengaja gak ikut walau kedaftar di situ: geser tanggal invoice itu mindahin
pengakuan pendapatan/biaya, bukan cuma tanggal kas.

Pengaman periode gak dibikin sendiri — ERPNext ngecek dua-duanya: periode **asal** dicek waktu
jurnal lama dibalikin, periode **tujuan** dicek waktu jurnal baru ditulis. Kalau salah satu
ketutup (Accounting Period, Period Closing Voucher, atau tanggal beku), semuanya dibatalin, gak
ada yang setengah jalan.

> **Jangan nyalain *Enable Immutable Ledger*** di Accounts Settings tanpa ngobrol dulu. Kalau
> nyala, jurnal lama gak boleh ditandain cancelled — dia dibalikin pakai jurnal pembalik
> bertanggal **hari ini**, jadi bulan asalnya tetap kecatat dan fitur ini berubah arti sama
> sekali.

Implementasi: `vic_addon/vic/bank_clearance.py` (lewat `override_doctype_class`).

#### Nambah supplier ke Inquiry yang udah disubmit

Tabel **Suppliers** di Request for Quotation (di desk namanya *Inquiry*) dikasih Allow on Submit,
jadi supplier masih bisa ditambah setelah dokumennya disubmit — kejadian biasa: inquiry-nya udah
jalan, terus ada supplier lain yang mau dimintain harga juga.

Yang bisa dan yang enggak:

| Aksi di dokumen yang udah submit | Hasil |
| --- | --- |
| Nambah baris supplier baru | bisa |
| Hapus baris supplier | bisa |
| Ubah isi baris supplier yang udah ada (mis. Email ID) | ditolak |

Yang terakhir itu bawaan Frappe: Allow on Submit di tabelnya cuma ngebolehin baris **baru**;
baris lama tiap field-nya masih dicek satu-satu. Kalau emang perlu, field anaknya mesti
dikasih Allow on Submit sendiri.

Dinyalain lewat property setter `Request for Quotation-suppliers-allow_on_submit`.

#### Isi tabel item Opportunity lewat file

Tabel **Items** di Opportunity (di desk namanya *Request For Quotation*) dinyalain Bulk Edit-nya,
jadi di pojok grid muncul tombol **Download** sama **Upload**. Kepakai buat permintaan yang
itemnya banyak: download dulu buat dapet template kolomnya, isi di Excel, terus upload.

Format filenya **CSV**, bukan `.xlsx` — itu bawaan Frappe, tombol upload-nya emang cuma nerima
`.csv`. Excel bisa buka dan nyimpen CSV, jadi alurnya tetap lewat Excel: buka file hasil
download, edit, terus *Save As* → CSV sebelum diupload.

Catatan cara kerjanya: upload **ngeganti seluruh isi tabel**, bukan nambahin ke baris yang udah
ada. Baris 1–7 file itu header template (judul, label kolom, nama field, keterangan) — jangan
diutak-atik, data mulai baris 8. Maksimal 5000 baris sekali upload.

Dinyalain lewat property setter `Opportunity-items-allow_bulk_edit`.

#### Payment Entry: Paid Amount ngikut tabel Deductions or Loss

Isi/ubah/hapus baris di tabel **Deductions or Loss** → **Paid/Received Amount** dihitung ulang
otomatis biar Difference Amount nol, dan **Allocated Amount tetap sebesar Outstanding**.

Bawaannya user ngitung sendiri, dan begitu Paid Amount diubah ERPNext ngalokasiin ulang
(`allocate_amount_to_references`) — dengan setelan default semua Allocated Amount malah di-nol-in.
Di sini angkanya dipasang langsung ke dokumen tanpa nyalain trigger Paid/Received Amount.

Rumusnya ngikut validasi server (`set_difference_amount`). Baris potongan selalu **didebit**:

| Tipe | Paid/Received Amount | Contoh (outstanding 1.000, potongan 10) |
| --- | --- | --- |
| Receive | Allocated + pajak termasuk − Total Deduction | terima 990 (biaya bank / PPh dipotong customer) |
| Pay | Allocated + pajak termasuk + Total Deduction | bayar 1.010 (biaya bank ditanggung kita); potongan dari supplier diisi **minus** |

Cuma jalan di PE draft yang punya baris referensi dan akun asal-tujuannya satu mata uang;
multi-currency dibiarin kayak bawaan. Implementasi: `vic_addon/public/js/payment_entry_deduction.js`.

#### Badge & pop-up notifikasi

Lonceng **Notification** di sidebar nunjukin angka notifikasi belum dibaca, dan tiap notifikasi baru
(di-tag, di-assign, dll) muncul pop-up di pojok kanan bawah + suara `alert` bawaan Frappe (ikut
setting *Mute Sounds* user). Klik pop-up → buka dokumennya.

Angkanya ditaruh di **pill sebaris sama label lonceng** (di sebelah kanan tulisan *Notification*),
bukan badge yang nempel di pojok ikon. Badge lama nongol keluar kotak ikon, jadi kepotong sama area
scroll sidebar (`overflow` hidden/auto). Kalau versi Frappe-nya punya pill angka sendiri
(`.notification-count`), pill itu yang dipakai; di v16.25–16.27 belum ada (lonceng cuma punya titik
`.notifications-unseen`), jadi pill-nya dibikin sendiri (`.vic-notification-count`). Angkanya diambil
dari database (Notification Log yang belum dibaca).

- Update tanpa refresh lewat event realtime `notification` yang dikirim Notification Log waktu
  dibikin; cadangannya polling tiap 60 detik kalau socket-nya putus.
- Client socket.io bawaan cuma nyoba nyambung ulang 3x lalu nyerah sampai halaman di-refresh —
  batas itu dicabut (`reconnectionAttempts(Infinity)`).
- Angkanya diitung ulang waktu notifikasi dibaca / *Mark all as read* di dropdown bawaan.
- Subject notifikasi itu HTML; di pop-up cuma teksnya yang dipakai (`DOMParser`, gak ngejalanin
  apa pun).

Butuh realtime yang nyambung — lihat *Realtime (socket.io) di staging* di atas.

Implementasi: `vic_addon/public/js/notification_badge.js` (`app_include_js`),
`vic_addon/vic/notifications.py`.

#### Nama dokumen di desk beda dari bawaan ERPNext

Istilah yang dipakai sehari-hari di VIC beda dari nama doctype ERPNext, jadi labelnya diganti.
Doctype-nya sendiri **gak** di-rename — nama aslinya tetap kepakai di kode, hooks, link field,
dan laporan. Yang berubah cuma tulisan yang kelihatan user.

| Doctype ERPNext | Kelihatan di desk |
| --- | --- |
| Opportunity | **Request For Quotation** (permintaan harga dari customer) |
| Request for Quotation | **Inquiry** (permintaan harga ke supplier) |
| Payment Request | **Advance Invoice** |

Caranya lewat record `Translation`, dipasang tiap install & migrate
(`vic_addon/vic/labels.py`). Frappe gak nyediain field label buat doctype — yang bisa dicustom
lewat Customize Form cuma label field-nya.

Yang dicocokin **teks persis**, dan berlaku di seluruh desk. Jadi field yang labelnya persis
`Opportunity` di doctype lain (Quotation, Supplier Quotation, Customer) ikut kebaca jadi label
baru — itu emang dimau, soalnya nunjuk ke dokumen yang sama. Label gabungan di form Opportunity
(`Opportunity Type`, `Opportunity From`, dst) ikut diganti juga biar gak setengah-setengah.

Tulisan `Request For Quotation` muncul dua kali di daftar terjemahan: sebagai **hasil**
terjemahan Opportunity, dan sebagai **teks asli** yang diterjemahin jadi Inquiry (itu tulisan
tombol `Create` di Opportunity — satu-satunya tempat di ERPNext yang nulisnya pakai F besar).
Gak muter-muter: Frappe nerjemahin sekali, hasilnya gak dilempar balik buat diterjemahin lagi.

Gara-gara itu, nyari record Translation-nya **gak boleh** ngandelin pencarian database —
collation bawaan MySQL gak bedain huruf besar-kecil, jadi `Request For Quotation` bakal nimpa
`Request for Quotation` dan salah satunya gak pernah kepasang. Kandidatnya diambil dulu, baru
dicocokin persis di Python (`find_translation`).

Print format-nya udah ngikut dari dulu: **Request For Quotation (Customer)** buat Opportunity,
**Inquiry** buat Request for Quotation.

#### Customer ngalir dari Opportunity sampai ke Quotation

Rantainya: **Opportunity → Request for Quotation → Supplier Quotation → Costing → Quotation →
Sales Order**. Yang di tengah itu dokumen ke supplier, jadi bawaan ERPNext gak nyimpen customer
sama sekali — padahal yang dicariin harga itu kebutuhan customer tertentu.

Request for Quotation dikasih field **Customer**, dan dua sambungan yang bolong diisi:

| Sambungan | Caranya |
| --- | --- |
| Opportunity → RFQ | Mapper bawaan nyalin nama Opportunity ke tiap baris item RFQ (`opportunity`), jadi customer-nya dibaca balik dari situ |
| RFQ → Costing | Costing gak nyimpen nomor RFQ; yang kesimpan link ke baris Supplier Quotation, dan dari situ nomor RFQ-nya kebaca. Project & Subject (plus centangan cetaknya) ikut diambil lewat jalur yang sama |

Sisanya udah jalan sendiri: Costing → Quotation lewat `make_quotation`, Quotation → Sales Order
lewat mapper bawaan.

Dua-duanya cuma ngisi kalau field-nya **masih kosong**, jadi pilihan user gak pernah ketiban.
Opportunity yang punya **Lead** (belum jadi Customer) dilewat, dan RFQ yang dibikin manual
tanpa Opportunity ya customer-nya kosong — bukan error.

Di form RFQ, Customer-nya diisi **dua kali**: sekali dari form begitu item ditarik lewat
*Get Items From → Opportunity* (biar langsung kelihatan tanpa nge-save dulu), sekali lagi di
server tiap dokumennya disimpan. Yang di server tetap perlu — dokumen yang dibikin lewat API
atau import gak lewat form sama sekali.

Implementasi: `vic_addon/vic/customer_chain.py`.

#### Project ngalir dari Opportunity sampai ke bawah

Field **Project** ditambahin di tiga dokumen yang belum punya: **Opportunity**, **Request for
Quotation**, dan **Quotation**. Sisanya (Supplier Quotation, Sales Order, Delivery Note, Sales
Invoice, Purchase Order) emang udah punya bawaan, plus Costing & Loan Memo punya kita.

Field-nya sengaja dinamain persis `project`, **bukan** `custom_project`: `map_fields` di
`frappe/model/mapper.py` nyalin field yang namanya sama antara dokumen sumber dan tujuan, jadi
project ngalir sendiri tanpa nambah kode di tiap tombol Create. Rantai lengkapnya (udah dites):

```
Opportunity  ─┬─► Request for Quotation ─► Supplier Quotation ─► Costing ─► Quotation ─► Sales Order ─► Delivery Note
              └─► Quotation (langsung)
```

Konsekuensi yang perlu diinget: karena namanya nabrak nama field bawaan, kalau suatu hari ERPNext
nambahin field `project` sendiri di salah satu doctype itu, custom field kita bakal bentrok dan
mesti dicabut. Itu risiko yang diambil sadar — imbalannya nol kode tambahan di semua mapper.

Di **Opportunity (RFQ)**, kalau Opportunity From = Customer dan Customer-nya udah keisi, dropdown
Project cuma nampilin project milik customer itu (`Project.customer`). Ganti Customer → Project
yang kepilih dikosongin kalau punya customer lain. Opportunity dari Lead/Prospect gak disaring.
Cuma filter di form (`public/js/opportunity.js`), gak divalidasi di server.

**Rate item RFQ otomatis 0.** Rate di Opportunity Item wajib diisi, tapi ERPNext gak pernah
ngambilin harga (di tahap RFQ harganya emang belum ada). Property setter
`Opportunity Item-rate-default` = 0 bikin baris baru langsung 0 — termasuk yang dibikin lewat
server/import. Di form, ngisi Item Code di baris yang Rate-nya kosong ikut ngisi 0; Rate yang udah
diketik user gak ditimpa.

Amount, Rate (Company Currency), dan Amount (Company Currency) juga wajib, tapi ERPNext baru ngitung
ketiganya waktu Qty/Rate **diubah**. Baris yang baru ditambah terus langsung disimpan jadi ditolak
("... is required in every row"), jadi ketiganya ikut default 0 (`Opportunity Item-amount-default`,
`-base_rate-default`, `-base_amount-default`). Rate-nya 0, jadi 0 itu emang nilai yang bener; begitu
Rate diisi, ERPNext ngitung ulang kayak biasa.

#### Delivery Note: Vehicle No di tab Details

**Vehicle No** (`vehicle_no`) dipindah dari tab More Info (section Transporter Info) ke header tab
**Details**, kolom kanan di bawah Company — lewat property setter `field_order`. Isinya dicetak di
print format Delivery Order.

#### Billing Currency wajib di Customer & Supplier

**Billing Currency** (`default_currency`) di Customer dan Supplier dibikin **wajib** (property setter
`reqd`), biar mata uang transaksinya gak ketebak dari default company. Customer/Supplier lama yang
masih kosong gak diubah otomatis — begitu dibuka & disimpan lagi, field-nya harus diisi dulu. Di
Quick Entry (tombol + New) field-nya ikut muncul karena wajib.

#### Form Supplier dirampingin

- **Disembunyiin** (property setter `hidden`): Company Bank Account (`default_bank_account`),
  Price List (`default_price_list`), dan Alias.
- **Tax ID Type** (`custom_tax_id_type`, Link) di tab Tax, paling atas section Tax Identification
  (di atas Tax ID). Pilihannya dari master baru **Tax ID Type** (modul VIC), diisi awal
  **TIN** (NPWP), **NIK**, **Passport**, **Other ID** — jenis ID pembeli/penjual di Coretax. Isian
  awal itu cuma dibikin kalau master-nya masih kosong (tiap install/migrate), jadi data yang udah
  diubah/dihapus user gak muncul lagi. Field yang sama (posisi & master-nya sama) ada juga di
  **Customer**.

Implementasi: fixture + `vic_addon/vic/doctype/tax_id_type/`.

#### Form Purchase Receipt dirampingin

Purchase Receipt cuma buat nyatet **barang apa dan berapa qty** yang diterima, jadi semua yang
nyangkut harga disembunyiin (property setter `hidden` di `fixtures/property_setter.json`):

| Bagian | Yang disembunyiin |
| --- | --- |
| Header | Section **Accounting Dimensions** (Cost Center, Project), **Currency and Price List**, **Taxes and Charges** (termasuk Incoterm, Shipping Rule, Show VAT for WAPU), tabel pajak, semua **Totals**, **Additional Discount**, **Tax Breakup**, **Pricing Rules** |
| Di bawah tabel item | Total, Net Total, dan versi Company Currency-nya — **Total Quantity** tetap kelihatan |
| Baris item | Section **Rate and Amount**, **Discount and Margin**, Rate/Amount/Net Rate/Valuation dkk, **Accounting Dimensions**; kolom Rate & Amount di grid |

Nilainya tetap keisi dan kehitung kayak biasa (ditarik dari PO), cuma gak ditampilin — stock
ledger & valuasinya gak berubah. Baris item sisanya: item, deskripsi, qty (received / accepted /
rejected), UOM, gudang, referensi, serial/batch.

Total, Net Total, dan Total (Company Currency) dimunculin lagi sama ERPNext lewat JS tiap refresh
atau ganti currency, jadi disembunyiin ulang di `vic_addon/public/js/purchase_receipt.js`.

Print format **Goods Received** gak kena — itu emang udah tanpa harga.

#### Form Project dirampingin

Semua lewat property setter di `fixtures/property_setter.json`, gak ada kode:

- **Disembunyiin**: From Template, % Complete Method, Estimated Cost, Department, dan seluruh
  tab **Progress** (cukup tab break-nya yang di-hide, field di dalamnya ikut ketutup).
- **Customer Details** (Customer, Sales Order) dan **Notes** dipindah ke tab **Details**, di bawah
  section Timeline — lewat property setter `field_order` di level DocType.
- **Company** dipindah dari tab Costing ke tab **Details**, paling atas di kolom kanan (sebelah
  Project Name) — lewat `field_order` yang sama.

Field yang disembunyiin tetap jalan pakai default-nya: % Complete Method tetap `Task Completion`,
jadi % Completed masih keitung dari Task.

Kalau ERPNext nambah field baru di Project, field itu gak ada di daftar `field_order` kita —
Frappe naruh field yang gak kedaftar sesuai urutan bawaan, jadi aman, cuma posisinya mungkin perlu
dicek.

#### Customer WAPU (udah dibuang)

Penanda WAPU (Wajib Pungut) gak dipakai lagi. Dua field-nya udah dihapus:

- **WAPU Status** di master Customer — patch `drop_customer_wapu_status`
- **Customer WAPU** (checkbox) di Sales Invoice — patch `drop_wapu_fields`

Gak ada kode yang make penanda ini. Kolomnya di database dibiarin (Frappe gak pernah ngedrop
kolom), jadi data lama masih kebaca kalau suatu saat dibutuhin.

#### Harga dikunci ke dokumen sumbernya

> **Status: penguncian sisi jual dimatiin.** Hook `before_validate` buat Quotation dan Sales
> Order dikomentarin di `vic_addon/hooks.py` karena user perlu bisa ngedit rate sendiri di dua
> dokumen itu. Jadi yang masih jalan cuma penguncian sisi beli (Purchase Order ← net rate
> Supplier Quotation). Buat nyalain lagi, buka komentar barisnya:
>
> ```python
> for doctype in ("Quotation", "Sales Order"):
> 	doc_events[doctype]["before_validate"] = "vic_addon.vic.rate_lock.set_selling_rate_from_costing"
> ```
>
> Konsekuensinya: harga di Quotation/Sales Order **gak** ketiban Quotation Rate dari Costing lagi
> tiap simpan — termasuk kalau dokumennya nempel ke Costing. Penjelasan di bawah ini nyeritain
> cara kerja aslinya, dan tetap berlaku penuh buat Purchase Order.

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

**Price List Rate di Quotation & Sales Order bisa diketik manual** (read-only-nya dilepas lewat
property setter). Selama hook sisi jual dimatiin (lihat catatan di atas), angka ketikan itu
bertahan buat semua dokumen — termasuk yang nempel ke Costing.

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
Baris item baru di Sales Order default-nya **Mixed** (sebelumnya Reguler) — tinggal diganti kalau
barisnya murni Reguler atau Dropship. Baris lama gak berubah.

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

**Di PO yang punya baris Dropship atau Mixed**, tombol bawaan **Create > Purchase Receipt**
disembunyiin (dia narik semua baris, termasuk yang gak pernah mampir ke gudang), diganti dua
tombol yang dua-duanya lewat modal berisi baris + **qty yang bisa diedit**:

| Tombol | Isinya | Qty awalnya |
| --- | --- | --- |
| **Create > Delivery Note** | Baris Dropship & Mixed | Sisa baris itu |
| **Create > Purchase Receipt** | Baris Reguler & Mixed (Dropship gak ikut) | Sisa baris itu |

**Tarik banyak PO sekaligus dari Delivery Note.** Di DN draft ada tombol **Get Items From > Purchase
Order (Dropship)**, dua langkah:

1. pilih PO-nya (bisa banyak) — pilihannya PO submitted yang masih punya baris Dropship/Mixed belum
   terkirim penuh, disaring ke customer DN kalau udah keisi;
2. tabel baris Dropship & Mixed dari semua PO itu (PO, SO, item, tipe, Order Qty, **Qty** yang bisa
   diedit — baris Mixed dipecah di sini), centang yang dikirim → **Get Items**.

Barisnya **ditambahin** ke DN yang lagi dibuka: dirakit lewat Sales Order masing-masing (baris PO
dikelompokin per SO, tiap SO dipetain ke DN yang sama), qty ngikut isian, gudang transit dropship. Baris
yang udah ada di DN dibiarin, baris SO yang udah ada gak ditambahin dobel. Semua PO-nya harus buat
**customer & company yang sama** — kalau beda ditolak. Waktu DN disubmit, Purchase Receipt dropship
kebentuk otomatis per PO kayak biasa.

Tombol **Create > Delivery Note** di PO pakai perakit yang sama (`build_delivery_note` di
`vic_addon/vic/dropship.py`), jadi PO yang nyakup beberapa SO (customer sama) sekarang juga bisa — dulu
ditolak.

**Sisanya dihitung sekali, dipakai dua modal**: `qty - received_qty - qty yang nyangkut di DN
draft`. `received_qty` di baris PO udah nyakup dua jalur — porsi yang masuk gudang lewat Purchase
Receipt biasa, **dan** porsi dropship yang penerimaannya kebentuk otomatis waktu DN disubmit — jadi
dua modal itu gak pernah nawarin qty yang sama dua kali. DN yang masih draft belum bikin
penerimaan, makanya dikurangin terpisah.

Qty-nya bisa diedit karena baris **Mixed** emang dipecah di situ: misal qty 2, user kirim 1 ke
customer lewat Delivery Note, sisanya 1 diterima ke gudang lewat Purchase Receipt. Baris yang
masuk DN ditandain `Dropship` (keluarnya dari gudang transit), yang masuk PR ditandain `Reguler`.

Alur lengkapnya buat PO campur (Mixed 2 + Reguler 1 + Dropship 1):

```
Create > Delivery Note   -> Mixed 1 + Dropship 1   -> DN submit
                            -> Purchase Receipt dropship kebentuk otomatis (gudang transit)
Create > Purchase Receipt -> Mixed 1 + Reguler 1   -> PR submit (gudang sendiri)
                            -> PO jadi 100% received
```

PO yang ada baris dropship-nya juga otomatis dapat alamat kirim + kontak customer, jadi supplier
tau kirimnya ke mana.

**Alamat customer di Shipping Address dokumen pembelian.** ERPNext v16 maksa `Shipping Address`
di PO/PR/PI diisi alamat yang kedaftar di Company (`validate_company_linked_addresses`), dan
satu-satunya pengecualian itu dropship bawaan (`delivered_by_supplier`) — yang justru kita matiin
biar DN & PR tetap kebentuk. Tanpa penanganan, PO dropship ditolak dengan *"Shipping Address does
not belong to the Company"*, atau kalau dikosongin malah keisi alamat kantor sendiri — padahal
supplier butuh alamat lapangannya.

Jadi alamatnya dititipin sebentar: hook `before_validate` nyingkirin alamat customer dari field
itu, hook `validate` masang lagi habis validasi inti lewat. Bisa gitu karena hook `doc_events`
jalannya **setelah** method controller-nya (`Document.hook` di frappe), jadi core-nya gak perlu
disentuh. Yang disingkirin cuma alamat yang beneran punya Customer — alamat ngawur lain tetap
ditolak ERPNext kayak biasa.

**PO <-> DN nyambung dua arah.** Tiap Delivery Note disimpan, baris dropship-nya nyimpen nomor
PO di field bawaan `purchase_order` + `purchase_order_item` (Delivery Note Item) - field itu
emang buat dropship, cuma gak keisi sendiri karena dropship bawaan ERPNext-nya dimatiin. Hasilnya:

| Dari | Ke | Caranya |
| --- | --- | --- |
| Delivery Note | Purchase Order | Connections > Internal Transfer (bawaan ERPNext, tinggal keisi) |
| Purchase Order | Delivery Note | Connections > **Dropship** (dari `override_doctype_dashboards`) |

Implementasi: `vic_addon/vic/dropship.py` + `vic_addon/public/js/purchase_order.js`.

Catatan: Purchase Receipt gak boleh bertanggal masa depan (aturan ERPNext), jadi kalau posting
date DN di masa depan, submitnya ditolak dengan pesan yang jelas.

**Item dropship wajib udah punya PO sebelum DN-nya disubmit.** Purchase Receipt dropship dibikin
di atas PO — tanpa PO gak ada yang bisa diterima, dan gagalnya baru kelihatan jauh di belakang
(ERPNext ngamuk nyari Serial No yang harusnya lahir dari Purchase Receipt itu). Jadi dicegat di
`before_submit` dengan pesan yang nyebut baris, item, dan SO-nya.

**Retur dropship.** Customer ngeretur barang dropship → barangnya balik ke supplier juga. Waktu **retur
Delivery Note** (Create > Return dari DN dropship) disubmit:

| # | Dokumen | Yang terjadi |
| --- | --- | --- |
| 1 | Retur DN | barang masuk lagi ke gudang transit dropship (bawaan ERPNext) |
| 2 | **Retur Purchase Receipt** (otomatis, submitted) | atas PR dropship-nya — barang keluar dari gudang transit balik ke supplier. Serial No yang diretur customer ikut dibalikin |
| 3 | **Retur Purchase Invoice / debit note** (otomatis, submitted) | cuma kalau baris PR itu **udah ditagih** — sebanyak qty yang diretur |
| — | Payment Entry | **gak dibikin**, walaupun PI-nya udah dibayar. Debit note-nya nyimpen outstanding sendiri (piutang ke supplier), dibereskan manual |

Retur PR dibikin di `on_submit` (bukan `before_submit` kayak alur maju): stoknya baru masuk gudang transit
setelah retur DN-nya kecatat. Qty retur dibagi ke baris PR dropship atas baris SO yang sama, sebatas yang
belum diretur — PR yang dibikin buat DN asalnya didahuluin. Retur PI-nya ngambil baris invoice yang nagih
baris PR itu (`pr_detail`), sebatas qty yang belum diretur di invoice itu. Tanggal posting semua ngikut
retur DN.

PR dropship (alur maju) dan retur PR/PI nyimpen nomor DN-nya di field **Dropship Delivery Note**
(`custom_dropship_delivery_note`). Retur DN dibatalin → retur PI lalu retur PR-nya ikut dibatalin duluan.

**Cancel DN dropship (maju maupun retur).** DN & PR dropship saling nge-link (DN →
`custom_dropship_purchase_receipt`, PR → `custom_dropship_delivery_note`), jadi kalau dibatalin satu-satu
dua-duanya saling ngunci — dan dialog *Cancel All* bawaan Frappe nyoba ngebatalin PR-nya duluan, yang
gagal karena stok gudang transit jadi minus. Sekarang:

| Yang dibatalin | Yang terjadi |
| --- | --- |
| DN dropship | PR dropship-nya ikut dibatalin otomatis **sesudah** DN-nya (hook `on_cancel`, `cancel_dropship_purchase_receipts`). Kalau PR-nya udah ditagih, PI-nya dibatalin dulu |
| Retur DN dropship | retur PI & retur PR-nya dibatalin duluan (`cancel_dropship_returns`, kayak sebelumnya) |
| PR / retur PR dropship langsung | ditolak, pesannya nyuruh batalin DN-nya (`block_direct_cancel`) |

Di form, PR/PI gak ditawarin di dialog *Cancel All* DN dropship, dan DN gak ditawarin di dialog PR dropship
(`frm.ignore_doctypes_on_cancel_all` bawaan Frappe, di `delivery_note.js` / `purchase_receipt.js`).
Dites (rollback): cancel DN maju, cancel PR langsung (ditolak), retur DN lalu cancel retur, lalu cancel DN
asalnya.
Implementasi: `vic_addon/vic/dropship_return.py`.

**Required By di PO** ngikut delivery date Sales Order. Buat SO yang tanggal kirimnya udah lewat,
ERPNext bakal nolak PO-nya (`Required By cannot be before Date`), jadi tanggal yang udah lewat
dimajuin otomatis ke tanggal PO — cuma buat PO yang lahir dari tombol Create, PO manual tetap
divalidasi apa adanya.


**Qty lebih/kurang dari SO atau PO.** Modal PO per Supplier (di SO) dan Create DN (di PO) nerima qty
berapa pun; yang ngebatesin validasi bawaan ERPNext waktu **submit**. Yang ngontrol PO > SO, DN > SO,
**dan** PR > PO itu satu setelan yang sama: **Stock Settings → Over Delivery/Receipt Allowance (%)**
(bisa juga per item di master Item). *Buying Settings → Over Order Allowance* **gak** ngaruh di sini.
Invoice dari DN yang ngelebihin DN/SO dikontrol **Accounts Settings → Over Billing Allowance**.

Skenario yang udah dites (dropship, harga jual 5.000, harga beli 3.000):

| Skenario | Caranya | Setelan |
| --- | --- | --- |
| **Rugi**, kelebihan dipakai customer: SO 2 → PO 3 → DN 3 → SI 2 | PO & DN qty 3 di modal; SI dari DN, qty diubah jadi 2 (DN jadi *Partially Billed*, SO *Completed*) | Over Delivery/Receipt Allowance ≥ 50% |
| **Rugi**, kelebihan masuk gudang VIC: SO 2 → PO 3 → DN 2 + PR 1 | baris SO tipe **Mixed**: DN 2 dari modal DN, sisa 1 lewat *Create Purchase Receipt* di PO ke gudang | Over Delivery/Receipt Allowance ≥ 50% |
| **Untung**: SO 2 → PO 1 → DN 1 → SI 2 | SI dibikin **dari SO** (bukan dari DN — DN cuma 1, ditolak *overbill*), lalu SO di-**Close** | — |
| Terima kurang: PO 2 → PR 1 | PR qty 1, sisanya PO di-Close kalau gak bakal dikirim | — |
| Terima lebih: PO 2 → PR 3 | baris PO tetap 2 + **baris tambahan qty 1, rate 0** (Price List Rate juga 0 — kalau enggak, rate-nya diisi ulang ERPNext dari price list), centang *Allow Zero Valuation Rate* | — (naikin qty baris PO ditolak di toleransi 0%) |

Purchase Receipt otomatis dropship nerima **persis qty DN**: dibagi berurutan ke PO-PO baris SO itu
sebatas sisa masing-masing (PO yang dipecah gak kelebihan nerima), dan kalau DN lebih dari total sisa
PO, kelebihannya masuk ke PO terakhir (ikut Over Delivery/Receipt Allowance). Dulu dibatasi sisa PO,
jadi DN yang lebih gagal karena stok gudang dropship kurang (`allocate_receipt_qty` di
`vic/dropship.py`).
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
  penandanya checkbox **With Serial Number** (`custom_has_serial_no`) yang narik `has_serial_no` dari
  master Item. Checkbox-nya kelihatan di form baris & sebagai kolom di tabel item (read only, ngikut
  master Item).
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

#### Print Format: form VIC lainnya

Lima form kertas VIC yang lain ikut dibikin, semuanya pakai kop surat + gaya yang sama dari
`vic_addon/templates/print_formats/vic_letterhead.html` (satu file, dipakai bareng lewat
`{% include %}`). Blok nama + alamat company di kop **gak pernah bergaris** — dikunci `!important`
di letterhead, karena class `box`-nya juga dipakai print lain buat kotak bergaris (sempat kena di
Delivery Order).

**Kolom Description di tabel item** semua print VIC ngambil **description** baris itu dulu; kalau
kosong (termasuk editor yang isinya cuma tag kosong kayak `<p></p>`) baru **item name**. Satu
helper Jinja dipakai bareng: `get_item_description` di `vic_addon/vic/print_utils.py`. Costing Item
gak punya field description, jadi Costing tetap nyetak item name.

Judul & isi kolom **Description** rata kiri di semua print (judul kolom lain tetap tengah): `<th>`-nya
dikasih class `left`, `<td>`-nya class `text`, aturannya di letterhead.

| Print Format | Doctype | Judul di kertas |
| --- | --- | --- |
| Quotation (VIC) | **Quotation** (bisa juga dipasang di Sales Order) | QUOTATION |
| Purchase Order (VIC) | Purchase Order | PURCHASE ORDER |
| Invoice (VIC) | Sales Invoice | INVOICE (formulirnya sama kayak Proforma Invoice) |
| Delivery Order (Invoice) | Sales Invoice | DELIVERY ORDER ("DO asli" dari invoice, tanpa Barang Tambahan) |
| Receipt Note | Purchase Invoice | "RECEIPT NOTE" (tanda terima tukar faktur, lihat di bawah) |
| Purchase Request | Material Request | PURCHASE REQUEST |
| Inquiry | Request for Quotation | INQUIRY (+ versi Excel, lihat di bawah) |
| Request For Quotation (Customer) | Opportunity | REQUEST FOR QUOTATION |
| Costing (Sales) | Costing | COSTING (harga jual + Terms & Conditions) |
| Costing (Import) | Costing | COSTING (harga beli, harga jual, profit) |

Field yang ditambah buat nutupin isian di kertas:

| Doctype | Field | Isinya |
| --- | --- | --- |
| Material Request | Subject, Customer's Purchase Order | Nomor PO customer keisi otomatis dari Sales Order (lihat di bawah) |
| Request for Quotation | Subject | Judul inquiry |
| Opportunity | Subject, Your Ref | Dicetak di RFQ (Subject di bawah From, Your Ref di bawah Date). Subject-nya ikut kebawa ke Inquiry — nama field-nya sama (`custom_subject`) |
| Opportunity, Request for Quotation | Show Project in Print, Show Subject in Print | Centangan di samping Project / Subject — yang dicetak cuma yang dicentang |
| Request for Quotation | Person in Charge | Nama penanggung jawab inquiry |
| Request for Quotation | Best Regards | Nama di bawah **Best regards** di Inquiry — print format, PDF, dan Excel dari Send Inquiry. Kosong → Person in Charge → nama user pembuat. Bisa diubah setelah submit |
| Request for Quotation Item | Weight, Remarks | Kolom tambahan di tabel inquiry |
| Costing | Subject, Show Project in Print, Show Subject in Print | Project/Subject di kepala Costing (Import) & (Sales), cuma yang dicentang |
| Costing | Delivery Time, Delivery Point, Payment, Validity | Blok Terms & Conditions di Costing (Sales). Field Mark Up udah dibuang |
| Costing | RFQ (link ke Inquiry, nomor `PUR-RFQ-...`) | Dicetak sebagai **Our RFQ** di Costing (Import) & (Sales) |

**Nomor PO customer ikut turun ke Purchase Request.** Material Request yang lahir dari Sales
Order (Create > Material Request) narik `po_no` dari Sales Order-nya lewat field `sales_order` di
baris item — kalau permintaannya diketik manual, field-nya dibiarin buat diisi sendiri, dan angka
yang udah diketik user gak pernah ketiban. Implementasi: `vic_addon/vic/material_request.py`.

**Customer's Purchase Order di Sales Order dipindah ke tab Details** (bawaannya nyempil di tab
More Info), lewat property setter `field_order` — cara yang sama dipakai Customize Form.

**Purchase Order (VIC)** ngikut template `Purchase Order.pdf`: kotak bergaris **Order To** (nama
supplier tebal, nomor telepon kontak, nama kontak + sapaan dari Contact), di kanannya Payment Terms &
Delivery Time (*Required By*) plus kotak bergaris **Delivered To**. Isinya dari field **Delivered To**
(`custom_delivered_to`, tab Address & Contact → Shipping Address, **bisa diubah setelah submit** —
buat dropship yang dikirim ke lokasi customer); kosong → alamat pengiriman PO (Shipping Address),
lalu nama alamatnya, lalu nama project. Di kotak **Order To**, di bawah nama supplier, dicetak field
**Order To** (`custom_order_to`, di bawah Supplier Address Details, bisa diubah setelah submit);
kosong → alamat supplier (Supplier Address).

Order To dan Delivered To **keisi otomatis** tiap Supplier Address / Shipping Address dipilih (termasuk
waktu ganti supplier), dalam bentuk teks biasa per baris — habis itu bebas diedit. Ganti alamat lagi =
isiannya ketimpa alamat yang baru. Terbilang di kiri, sejajar blok total di kanan. Tanda tangan: kiri
*Best regards,* → field **Best Regards** (`custom_best_regards`, tab Details di bawah Company, bisa
diubah setelah submit; kosong → nama user pembuat) → *Director*; kanan *Supplier Approved* → nama
kontak supplier.

**Note** dicetak sebagai baris terakhir tabel item, di kolom Description: isi **Terms and
Conditions** PO (`terms`, dari template Terms), lalu di bawahnya **Penalty Clause**
(`custom_penalty_clause`, Long Text di section Terms & Conditions) kalau diisi. Kalau dua-duanya
kosong, baris Note gak dicetak.

Di bawah Total Price selalu ada baris **PPN 11%** (persennya dari rate baris
PPN; PO tanpa PPN tetap kecetak senilai 0, ngikut formulir — kecuali **Show VAT for WAPU** dicentang, lihat di bawah) — bukan deskripsi akun kayak "PPN
Masukan @ 11.0". Baris pajak lain (PPh, potongan) tetap dicetak pakai deskripsinya. Terbilang dari
field `in_words` bawaan ERPNext, blok tanda
tangan Supplier Approved + Director, dan baris warna salinan (Putih = Supplier, Merah =
Purchasing, Kuning = Accounting, Hijau = Finance). Delivery Time-nya ngambil field **Delivery Time**
(`custom_delivery_time`, teks bebas di sebelah Required By, mis. "2-3 minggu setelah PO", bisa diubah
setelah submit); kosong → tanggal **Required By** (`schedule_date`).

**Quotation (VIC)** ngikut template `Quotation.pdf`: kotak bergaris **Customer** (nama tebal + kontak
dengan sapaan dari Contact), di kanannya Delivery Point, Delivery Time, Validity, Payment Terms; Your Ref
& Subject di bawah kotak. Ringkasan di bawah tabel:

| Baris | Isi |
| --- | --- |
| TOTAL PRICE | Total |
| DISCOUNT x % | Total − Net Total (cuma muncul kalau ada diskon tambahan; persennya dari *Additional Discount Percentage*) |
| TOTAL PRICE AFTER DISC | Net Total |
| VAT 11 % | pajak setelah diskon; selalu muncul (0 kalau gak ada PPN, atau Net Total × 11% kalau **Show VAT for WAPU** dicentang), persennya dari rate baris PPN |
| GRAND TOTAL PRICE | Grand Total |

Diskon dihitung Total − Net Total biar angkanya nyambung baik diskon tambahannya *Apply On* Net Total
maupun Grand Total. Tanda tangan *Best regards,* + **Sales Name** (kosong → nama user pembuat), huruf besar, di kiri.

#### Show VAT for WAPU

Checkbox **Show VAT for WAPU** (`custom_show_vat_for_wapu`, tab Taxes di sebelah Sales/Purchase
Taxes and Charges Template, **bisa diubah setelah submit**) di **Quotation, Sales Order, Delivery
Note, Sales Invoice, Purchase Order, Purchase Receipt**. Buat transaksi WAPU: PPN-nya dipungut
pembeli, jadi tabel Taxes and Charges dikosongin — tapi di kertas PPN tetap harus kelihatan.

**Otomatis dari Tax Category.** Tax Category punya centangan **WAPU** (`custom_is_wapu`). Di **Sales
Order, Delivery Note, dan Sales Invoice**, begitu Tax Category yang ditandai WAPU dipilih, Show VAT for
WAPU langsung kecentang (dan dicentang lagi waktu disimpan) — lewat `fetch_from` +
`fetch_if_empty` bawaan Frappe, gak ada kode. Cuma nyentang: centangan manual tanpa Tax Category WAPU
tetap boleh dan gak ketimpa, dan ganti ke Tax Category non-WAPU **gak** ngelepas centangannya —
lepas manual kalau perlu.

Kalau dicentang **dan** dokumennya gak punya baris PPN, print format nyetak:

| Baris | Isi |
| --- | --- |
| VAT 11 % / PPN 11% | Net Total × 11% |
| GRAND TOTAL | Grand Total dokumen + VAT di atas |
| in Words (PO) | terbilang dari Grand Total yang baru |

Cuma di kertas — nilai dokumen, GL, dan outstanding gak berubah. Kalau tabel pajaknya **ada** baris
PPN, centangan ini diabaikan dan baris PPN itu yang dicetak (biar gak dobel). Nama field-nya sama di
semua doctype itu, jadi ikut kebawa lewat mapper bawaan (Quotation → SO → DN → SI, PO → PR).

Yang beneran nyetak baru **Quotation (VIC)** (juga kalau dipasang di Sales Order) dan **Purchase
Order (VIC)**. Sales Invoice dan Purchase Receipt belum punya print format VIC yang nyetak total
harga (Kwitansi nyetak nilai tagihan, Goods Received gak ada harga) — checkbox-nya udah ada, tinggal
dipakai begitu print format-nya dibikin.

#### Print Original Number (dokumen amend)

Dokumen yang di-amend namanya dapet akhiran `R` (`SAL-ORD-2610-00001R1`, `...R2`, lihat naming di atas).
Checkbox **Print Original Number** (`custom_print_original_number`) di **Purchase Order, Purchase Receipt,
Purchase Invoice, Sales Order, Delivery Note, Sales Invoice** — paling atas, di bawah Series, cuma muncul
kalau *Amended From* keisi, bisa diubah setelah submit. Kalau dicentang, print format nyetak **nomor
dokumen aslinya** (yang pertama kali dibikin): rantai Amended From ditelusurin sampai ujung, jadi `...R2`
tetap kecetak `SAL-ORD-2610-00001`, bukan `...R1`.

Kena ke nomor dokumen itu sendiri di print format-nya (Purchase Order (VIC), Goods Received, Receipt Note,
Proforma Invoice, Purchase Request (Sales Order), Quotation (VIC) kalau dicetak dari SO, Delivery Order,
Delivery Order (Stock Only), Invoice (VIC), Delivery Order (Invoice), Kwitansi), **dan** ke nomor dokumen
lain yang ikut dicetak — No. DO di Invoice/Proforma/Kwitansi/Delivery Order (Invoice), No. PO di Goods
Received & Receipt Note — tiap dokumen ngikut centangannya sendiri. Nama dokumennya di sistem gak berubah.

Helper: `get_print_name` / `get_print_names` di `vic_addon/vic/print_utils.py`.

#### Disable Rounded Total default nyala

**Disable Rounded Total** default-nya **1** di semua dokumen transaksi: Quotation, Sales Order, Sales
Invoice, Delivery Note, Supplier Quotation, Purchase Order, Purchase Invoice, Purchase Receipt.
Dokumen baru langsung gak dibulatin; user masih bisa nguncheck per dokumen. Dokumen lama gak
disentuh.

**Grand Total di print format ngikut pembulatan dokumennya.** Semua print format VIC yang nyetak
Grand Total (Quotation, Purchase Order, Invoice, Proforma Invoice, Kwitansi, Kwitansi (Progress),
Receipt Note) pakai **Rounded Total** kalau isinya bukan 0 atau Disable Rounded Total-nya gak dicentang;
selain itu **Grand Total**. Total yang dihitung sendiri sama print format-nya (VAT WAPU, ringkasan Invoice /
Proforma yang dipotong DP) dibulatin persis kayak ERPNext ngebulatin Rounded Total, kalau dokumennya
pakai pembulatan. Terbilangnya ikut angka yang dicetak. Helper: `get_grand_total` di
`vic_addon/vic/print_utils.py`.

Lewat property setter `<Doctype>-disable_rounded_total-default` — namanya sengaja sama persis
dengan yang dibikin **Global Defaults → Disable Rounded Total**, jadi fixture kita nimpa record itu,
bukan nambah yang kedua. Bedanya: centangan di Global Defaults juga nyembunyiin field Rounded Total
di form & print, fixture kita cuma ngubah default-nya.

Catatan: kalau **Global Defaults** di-save (mis. ganti default company), ERPNext nulis ulang
property setter ini sesuai centangan di sana (bawaannya 0). `bench migrate` berikutnya ngembaliin
ke 1 — fixture selalu di-import ulang tiap migrate (udah dites).

Isian syarat di **Quotation (VIC)** diketik di lima field doctype Quotation: **Payment Terms**,
**Delivery Point**, **Delivery Time**, **Validity**, dan **Subject**. Template-nya sadar dokumen,
jadi satu file bisa dipasang di dua doctype:

- dicetak dari **Quotation** -> field-nya dibaca dari dokumen itu sendiri
- dicetak dari **Sales Order** -> dibaca dari Quotation asalnya (nomornya nempel di baris item)

Kalau field-nya kosong (atau SO-nya gak lahir dari Quotation), tiga baris jatuh ke cadangan:
`payment_terms_template`, alamat pengiriman, dan tanggal `valid_till`; Delivery Time jatuh ke teks
"Reconfrom stock before PO".

**Delivery Time, Validity, dan Subject diambil dari Costing**: diisi langsung waktu *Create >
Quotation* dari Costing, dan field-nya juga `fetch_from` ke Costing (`fetch_if_empty`) — jadi kalau
Costing-nya dipilih belakangan, nilainya ikut keisi waktu disimpan; isian user gak ketiban. Subject
di Quotation tipenya **Small Text** (dulu Data, maks 140 karakter — Subject Costing bisa lebih
panjang).

**Sales Name** (`custom_sales_name`) dicetak di bawah **Best regards,** (huruf besar). Kalau
dicetak dari Sales Order, yang dipakai Sales Name di Quotation asalnya. Kosong → nama user pembuat
Quotation. Bisa diubah setelah submit.

**Your Ref** punya field sendiri (`custom_your_ref`); kalau kosong, yang dicetak contact person /
PO customer kayak sebelumnya. Nama field-nya sama dengan Your Ref di Request For Quotation
(Opportunity), jadi Quotation yang dibikin dari RFQ ikut kebawa.

Field **Frappe CRM Deal** (`crm_deal`, custom field dari integrasi Frappe CRM bawaan ERPNext)
disembunyiin di Quotation.

**Purchase Request (Sales Order)**: tiga blok tanda tangan (SALES, ACKNOWLEDGMENT, APPROVED BY) dikotakin, nyambung jadi satu baris
kotak tiga kolom.

**Request For Quotation (Customer)** (Opportunity):

- Baris **Customer** (nama customer; dulu labelnya *From*), di bawahnya **Project** (nama project-nya) dan **Subject**. Dua-duanya bisa diisi,
  jadi yang dicetak ditentuin centangan di sampingnya: **Show Project in Print** dan **Show
  Subject in Print** (default mati). Centangannya ikut kebawa ke Inquiry (nama field-nya sama),
  dan print format **Inquiry** pakai aturan yang sama. **Your Ref** di bawah Date.
- Inquiry lama yang udah punya Subject dicentangin otomatis lewat patch
  `show_inquiry_subject_in_print`, biar Subject-nya gak mendadak ilang dari kertas — dulu Subject
  di Inquiry selalu dicetak kalau diisi.
- Tanda tangan **SALES** di pojok kiri bawah dalam **kotak** bergaris (label SALES di atas, ruang
  tanda tangan, nama di bawah), lebarnya sepertiga halaman. Namanya ngambil field **Sales Name**; kalau kosong, nama user yang bikin.

Form Opportunity-nya juga dirapiin lewat property setter: section **Organization** dibikin
collapsible, dan **Opportunity Date** (`transaction_date`) dipindah dari More Information ke
header, persis di atas section Organization (`field_order`).

#### Header 1 & Header 2: ngelompokin baris item

Dua field di baris item buat ngelompokin item dua tingkat:

| Field | Fieldname | Doctype |
| --- | --- | --- |
| **Header 1** (kelompok atas, dulu labelnya *Pengiriman*) | `custom_header` | Opportunity (RFQ), Request for Quotation (Inquiry), Costing, Quotation, Sales Order, Delivery Note, Sales Invoice, Purchase Order, Purchase Receipt, Purchase Invoice |
| **Header 2** (di dalam Header 1, dulu labelnya *Pengerjaan*) | `custom_pengerjaan` | doctype di atas kecuali Purchase Order, Purchase Receipt, Purchase Invoice |

Di form, kolom Header 1 ada di depan Header 2.

Dua-duanya opsional dan cukup diisi di baris pertama tiap kelompok — baris yang dikosongin ikut
baris di atasnya, dan waktu disimpan nilainya ditulis balik ke tiap baris. Header 2 mulai dari nol
lagi tiap ganti Header 1 (gak ngewarisin Header 2 dari Header 1 sebelumnya).

Gak ada kombinasi yang ditolak: baris pertama boleh kosong salah satu, kosong dua-duanya, atau keisi
semua. Baris yang di atasnya belum ada nilai tetap kosong dan dicetak tanpa judul. Yang perlu
diingat: begitu ada baris yang keisi, baris di bawahnya yang kosong ikut nilainya — jadi item tanpa
kelompok taruh di atas, sebelum baris yang pertama diisi.

Di grid, dua kolomnya lebar 1 — grid item udah penuh, kalau lebih lebar kolom Rate/Amount
kedorong keluar.

Karena nama field-nya sama di semua doctype, nilainya ikut kebawa sendiri lewat mapper bawaan
(RFQ → Inquiry, Quotation → Sales Order → Delivery Note / Sales Invoice; dites sampai DN).

Di print format (Quotation (VIC), Delivery Order, Delivery Order (Invoice), Invoice (VIC), Proforma
Invoice, Inquiry, Request For Quotation (Customer), Costing (Sales), Costing (Import), Purchase Request
(Sales Order)) **Header 1 dicetak paling atas** (tebal + garis bawah), **Header 2 di bawahnya**
(tebal), terus itemnya. **Gak ada yang menjorok** — judul & item sama-sama mulai di kolom
Description. Urutan kelompok ngikut kemunculan pertamanya. Print format PO & Goods Received tetap satu
tingkat (Header 1 aja, tebal + garis bawah, item juga gak menjorok).
Implementasi: `vic_addon/vic/item_header.py` (`group_items` / `group_items_by_header`).

**Inquiry → Costing.** Supplier Quotation gak punya dua field ini, tapi tiap barisnya nyimpen link ke
baris Inquiry asalnya (`request_for_quotation_item`, bawaan ERPNext). Jadi waktu Costing diisi lewat
**Get Items from Supplier Quotation** (pilih SQTN maupun ambil termurah per Inquiry) atau **Create >
Costing** dari SQTN, Header 1 & Header 2 tiap baris diambil langsung dari baris Inquiry-nya
(`get_inquiry_rows` di `costing.py`). Baris dari Get Items diurutin ngikut urutan Inquiry, biar kelompoknya
tetap nyambung walau dari beberapa SQTN; baris SQTN yang gak dari Inquiry ditaruh paling bawah. Header
yang udah ada di Costing gak diubah, dan ganti SQTN di satu baris gak ngubah Header-nya.

Versi Excel Inquiry belum nampilin Header 1/Header 2.

Di tabel item, **yang tebal cuma baris Header 1 & Header 2**. Baris item dicetak
normal, termasuk tebal bawaan editor (`<b>`/`<strong>`) di Description — dinormalin lewat
`.vic-pf .items .desc` di `templates/print_formats/vic_letterhead.html`, jadi berlaku ke semua
print format VIC sekaligus. Judul kolom dan baris total tetap tebal.

Jarak Header 1 → Header 2 dan Header 2 → item pertama **rapat kayak teks biasa** (padding di bawah judul
dan di atas baris sesudahnya nol, di `vic_letterhead.html`, jadi berlaku ke semua print format VIC yang
pakai kelompok). Jarak sebelum kelompok baru dan antar item tetap.

Di **Inquiry** (satu-satunya print yang punya garis tegak di dalam tabel item — kotak isian Qty, Unit
Price, Weight, Remarks buat supplier), baris judul Header 1/2 gak pakai `colspan`: judulnya di kolom
Description, kolom sisanya tetap sel sendiri, jadi garis tegaknya nyambung terus. Tinggi 30px (ruang
nulis) cuma buat baris item, baris judul ngikut teks.

#### Print Format: Kwitansi (Sales Invoice)

Dua print format kwitansi buat tagihan progress/pelunasan, sama-sama dari Sales Invoice:

| Print Format | Bentuk |
| --- | --- |
| **Kwitansi** | polos tanpa kop: Kwitansi No., Telah Terima Dari, Uang Sejumlah (terbilang huruf besar), Untuk Pembayaran, kotak nilai `IDR 36.594.480,-`, rekening, kota + tanggal, nama penandatangan |
| **Kwitansi (Progress)** | berbingkai + logo: No. & Faktur No., Sudah Terima dari (+ nama project), Sejumlah Uang (terbilang), Untuk Pembayaran + SPP No./Tanggal + Periode Tanggal, rekening, `Rp. 17,760,000,000`, penandatangan + jabatan |

Isian yang diketik user ada di tab baru **Kwitansi** di Sales Invoice — **semuanya bisa diisi setelah
submit**: No. Kwitansi, Tanggal Kwitansi (kosong → tanggal invoice), **Telah Terima Dari** (kosong → nama
customer; dicetak di "Telah Terima Dari" / "Sudah Terima dari"), Nilai Kwitansi (kosong → total
tagihan dikurangi DP yang dibalik & uang muka yang dialokasiin), Rekening Tujuan (Bank Account; default
dari Company), Untuk Pembayaran, dan section *Detail Progress* (SPP/SPK No. & tanggal, periode dari–s/d).

**SPP / SPK No. & tanggalnya diambil dari Customer's Purchase Order.** Isian *SPP / SPK No.* & *Tanggal
SPP / SPK* di tab Kwitansi tetap bisa diisi buat nimpa; kalau kosong, kwitansi nyetak **Customer's
Purchase Order** (`po_no`) & tanggalnya (`po_date`) dari invoice itu — yang udah kesalin sendiri dari
Sales Order. Kalau di invoice juga kosong, diambil dari Sales Order-nya (buat PO No. yang baru diisi di
SO setelah invoice kebentuk). Nomor & tanggal diambil sepasang dari sumber yang sama.

Waktu invoice disimpan, isian itu juga ditulis ke tab Kwitansi kalau *SPP / SPK No.*-nya masih kosong
(hook `print_utils.set_spp_from_sales_order`), biar kelihatan di form. Isian yang udah ada gak ditimpa.

Dulu Sales Order punya field SPP / SPK sendiri — udah dibuang (patch `drop_sales_order_spp`; isian
lamanya dipindah ke Customer's Purchase Order kalau field itu masih kosong).

Sisanya diambil otomatis: nama customer, nama project, Faktur No. (*Nomor Faktur Pajak*), nomor invoice
& DO (ditambahin di belakang Untuk Pembayaran di Kwitansi biasa, kalau belum ditulis sendiri),
terbilang & tanggal bahasa Indonesia, dan dari **Company** (section *Kwitansi*): kota, rekening default,
nama & jabatan penandatangan. *Atas Nama* rekening = nama company.

Implementasi: `get_kwitansi`, `terbilang`, `tanggal` di `vic_addon/vic/print_utils.py` (helper Jinja),
template di `vic_addon/vic/print_format/kwitansi*/`.

#### Payment Terms panjang pindah ke Note

Tempat term pembayaran di kop print format sempit. Kalau term-nya **lebih dari 20 karakter**
(mis. "20% DP, 30% Copy BL, 30% MOS Gudang, 10% Sebelum Material Onsite, 5% Commisioning, 5%
Retensi"), di tempatnya ditulis **"Lihat di Note"** dan teks lengkapnya dicetak jadi **poin pertama
baris Note** — baris terakhir tabel item, di kolom Description. Term ≤ 20 karakter (mis. "CASH")
tetap di tempatnya.

| Print format | Tempat term | Note |
| --- | --- | --- |
| Proforma Invoice | kotak Payment Terms | baris Note baru |
| Quotation (VIC) | Payment Terms (kanan) | baris Note baru |
| Purchase Order (VIC) | Payment Terms (kanan) | paling atas di Note yang udah ada (T&C, Penalty Clause) |
| Costing (Sales) | Terms & Conditions "3. Payment" | paling atas di Note yang udah ada |

Batasnya satu konstanta `PAYMENT_TERMS_LIMIT` di `split_payment_terms` (`vic/print_utils.py`).

#### Print Format: Proforma Invoice (Sales Order)

Print format **Proforma Invoice** di Sales Order, ngikut formulir `performa invoice.pdf`: kop VIC,
judul **PROFORMA INVOICE** (Invoice No. = nomor SO, Date = tanggal SO huruf besar), kotak customer
(nama tebal, alamat, `EMAIL : ` dari kontak / master Customer), di kanannya **Payment Terms** (nama
Payment Terms Template, dikotakin), **Tax No** (NPWP customer), **DO No.** (Delivery Note submitted
dari SO ini); **PO No.** customer di bawah kotak. Tabel item sama kayak Quotation (VIC) — termasuk
judul Header 2 / Header 1.

Ringkasan di bawah tabel (`get_proforma` di `vic/print_utils.py`):

| Baris | Isi |
| --- | --- |
| In Words | Grand Total di bawah, bahasa Inggris gaya formulir: "Sixteen million six hundred seventy-six thousand six hundred forty rupiah" |
| TOTAL | Total (sebelum diskon tambahan) |
| DISCOUNT | Total − Net Total |
| DOWN PAYMENT | DPP Invoice DP (skema Item DP) order ini yang udah submit |
| SUB TOTAL | Net Total − Down Payment |
| PPN | PPN SO; kalau ada DP dihitung ulang sebanding Sub Total; Show VAT for WAPU tanpa baris PPN → 11% × Sub Total |
| GRAND TOTAL | Sub Total + PPN |

Bawah: *Best Regards,* + `( nama )` di kiri, kotak **"Please remit the total payable to our account
at :"** di kanan (bank - cabang, Acc. Name = nama company, Acc. No. + mata uang). Rekening &
penandatangan ikut setting **Kwitansi** di Company (*Rekening Kwitansi*, *Penandatangan Kwitansi*);
kotak rekening gak dicetak kalau rekeningnya belum di-set.

Dites pakai angka formulir (3 × 3.650.000 + 6 × 679.000, PPN 11%): Total 15.024.000, PPN 1.652.640,
Grand Total 16.676.640, terbilang sama persis. Dengan DP 20%: Down Payment 3.004.800, Sub Total
12.019.200, PPN 1.322.112, Grand Total 13.341.312.


**Invoice (VIC)** (Sales Invoice) pakai formulir yang sama (`INV-09260155.pdf`): judul **INVOICE**, Date =
Posting Date, kotak **Customer** (judulnya nempel di garis), **Payment Terms** = Due Date dikotakin +
jumlah harinya dari Posting Date (mis. `18-Oct-2026  30 Days`), Tax No (NPWP customer), DO No. dari baris
item, PO No. Ringkasannya sama persis (`get_invoice_summary`), bedanya **DOWN PAYMENT** = DPP DP yang
dibalik di invoice itu (kolom *Allocated* di tabel DP Allocations). Terbilangnya huruf besar + "ONLY".
Implementasi: `get_sales_invoice_print` di `vic/print_utils.py`, template di `vic/print_format/invoice/`.

**Barang Tambahan.** Checkbox **Barang Tambahan** (`custom_is_additional_item`) di baris item Sales Order,
Delivery Note, dan Sales Invoice — nama field-nya sama, jadi tandanya kebawa sendiri SO → SI maupun
SO → DN → SI (mapper ERPNext). Bisa dicentang/dilepas setelah submit. Baris yang dicentang **gak dicetak**
di dua print format Sales Invoice:

| Print Format (Sales Invoice) | Isinya |
| --- | --- |
| **Invoice (VIC)** | Invoice biasa, baris barang tambahan dilewat |
| **Delivery Order (Invoice)** | "DO asli" — bentuknya sama kayak Delivery Order di Delivery Note, tapi dicetak dari invoice: DO No. = Delivery Note di baris item (kosong → nomor invoice), tanggal & Vehicle No. dari DN pertama, Serial No dari baris invoice (kosong → dari baris DN-nya) |

Cuma barisnya yang disembunyiin — qty, stok, nilai, dan **total di invoice tetap total dokumen**
(barang tambahan yang ada harganya tetap ikut kejumlah). Nomor urut item ngelompatin baris yang
disembunyiin. Print format Delivery Order di Delivery Note gak kena. Tanda yang dicentang di SO setelah
invoice-nya kebentuk gak ikut nyusul — centang langsung di baris invoice-nya.

Implementasi: `get_printed_items` & `get_invoice_delivery_order` di `vic/print_utils.py`, template di
`vic/print_format/delivery_order_invoice/`.

#### Print Format: Delivery Order (Delivery Note)

Lima blok tanda tangan (Issued By — diisi nama user
pembuat —, Approved by, Warehouse, Delivered by, Received by) sejajar satu baris, **tanpa kotak
maupun garis**.

Ngikutin form DO yang selama ini dipakai VIC: kop surat + logo, kotak judul **DELIVERY ORDER**
dengan DO No. & Date di bawahnya, blok bergaris **Customer** (nama + alamat) dan **Delivered To**,
di kanannya Vehicle No. & PO No. Tabel itemnya Item / Description / Qty / Remarks — kolom Remarks
sengaja dikosongin buat ditulis tangan.

Isinya diambil dari data yang emang udah ada di Delivery Note:

| Di kertas | Sumbernya |
| --- | --- |
| Date | **Print Format Date** kalau diisi, kalau enggak Posting Date |
| Customer | `customer_name` + `address_display` |
| Delivered To | Field **Delivered To** di Delivery Note (`custom_delivered_to`, di bawah Shipping Address, teks bebas, bisa diubah setelah submit — sama kayak di Purchase Order). Keisi otomatis tiap Shipping Address dipilih, kalau alamatnya beda dari alamat customer; kalau sama, dikosongin. Kosong → alamat pengiriman (kalau beda dari alamat customer), lalu nama Project, lalu nama customer. Dipakai juga di Delivery Order (Stock Only) dan Delivery Order (Invoice) (diambil dari DN pertama) |
| Vehicle No. / PO No. | `vehicle_no` / `po_no` bawaan Delivery Note |
| Size | Field **Size** di master Item, dicetak cuma kalau item-nya punya |
| Serial Number | Serial No baris itu, dilist di bawah deskripsi |
| Qty | Angka bulat tanpa desimal (`1 Nos`), pecahan tetap 2 desimal (`47.52 Nos`) |

Baris tanda tangannya 5 kolom — Issued By / Approved by / Warehouse / Delivered by / Received by.
Nama di bawah **Issued By** diambil dari pembuat dokumen; empat sisanya sengaja kosong buat tanda
tangan basah (nama otomatisnya nyusul bareng tiket signature Purchasing Manager & Warehouse
Captain).

**Delivery Order (Stock Only)** — print format kedua di Delivery Note, buat gudang: isinya sama
persis kayak Delivery Order (kop, kotak Customer/Delivered To, Vehicle No/PO No, serial number,
tanda tangan), bedanya:

- item yang **gak Maintain Stock** (jasa, ongkir, Item DP, dll) gak dicetak — dicek dari master
  Item (`is_stock_item`), nomor urutnya cuma ngitung barang stok;
- tabelnya **rata**, tanpa judul Header 2 / Header 1.

Catatan: Product Bundle (item induknya non-stok) ikut kesaring — kalau nanti dipakai, isi
bundle-nya (`packed_items`) perlu ditambahin. File: `vic_addon/vic/print_format/delivery_order_stock/`.

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

#### Print Format: Receipt Note (Purchase Invoice)

Tanda terima **tukar faktur** — dikasih ke supplier waktu nyerahin invoice + faktur pajaknya. Niru
formulir kertas **"RECEIPT NOTE"**: tanpa kop surat, satu kotak bergaris, kertas melintang,
blok-bloknya dipisah garis dobel.

| Bagian | Isinya |
| --- | --- |
| DATE / NO | Posting Date & nomor Purchase Invoice |
| RECEIVED FROM | Kotak yang dicentang: invoice subkon (*Is Subcontracted*) atau Supplier Group-nya mengandung "subcon/subkon" → **Subcontractor**; Supplier Group "ekspedisi/expedi/forwarder/logistic/cargo" → **Expedite**; sisanya **Supplier**. Di bawahnya nama supplier |
| AMOUNT / In Words | Rounded/Grand Total invoice + terbilangnya (`in_words`) |
| Invoice No. / Date | **Supplier Invoice No** & **Supplier Invoice Date** — dua-duanya **bisa diubah setelah submit** (property setter `allow_on_submit`). Kosong → dibiarin kosong buat ditulis tangan |
| Nominal | Rounded/Grand Total |
| Tax Invoice No. | Field baru **Nomor Faktur Pajak** (`custom_faktur_pajak_no`, di bawah Supplier Invoice Date, bisa diisi setelah submit) |
| DO No. | Field baru **Supplier DO No.** (`custom_supplier_do_no`, teks bebas, di bawah Nomor Faktur Pajak, bisa diisi setelah submit); kosong → *Supplier Delivery Note* dari Purchase Receipt yang nyambung ke baris item invoice |
| PO No. | Nomor Purchase Order di baris item |
| RECEIVED BY / DATE / SIGN | Dikosongin buat diisi tangan |

Supplier Invoice No yang diganti setelah submit tetap dicek gak dobel (cek bawaan ERPNext, kalau
*Check Supplier Invoice Number Uniqueness* nyala) — `vic_addon/vic/purchase_invoice.py`, hook
`before_update_after_submit`. Yang **gak** ikut berubah kalau diganti setelah submit: Remarks
("Against Supplier Invoice ...") dan jatuh tempo Payment Schedule yang dihitung dari Supplier Invoice
Date — dua-duanya keisi waktu submit.

Implementasi: `get_receipt_note` di `vic_addon/vic/print_utils.py` (helper Jinja), template di
`vic_addon/vic/print_format/receipt_note/`.

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
