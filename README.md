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
