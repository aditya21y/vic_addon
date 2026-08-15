from frappe import _


def get_data():
	"""Tab Connections di form Costing.

	Dua arah link-nya beda:

	- **Quotation** nyimpen nomor costing di field `custom_costing`, jadi cukup dicari lewat
	  fieldname biasa.
	- **Supplier Quotation** gak nyimpen apa-apa soal costing - justru Costing yang nyimpen
	  nomor SQTN di tiap baris item (`Costing Item.supplier_quotation`). Link kayak gini dibaca
	  frappe lewat `internal_links`: ambil nilainya dari child table dokumen ini.
	"""
	return {
		"fieldname": "custom_costing",
		"internal_links": {
			"Supplier Quotation": ["items", "supplier_quotation"],
		},
		"transactions": [
			{"label": _("Selling"), "items": ["Quotation"]},
			{"label": _("Buying"), "items": ["Supplier Quotation"]},
		],
	}
