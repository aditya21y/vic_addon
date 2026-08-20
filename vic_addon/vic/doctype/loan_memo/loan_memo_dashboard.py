from frappe import _


def get_data():
	return {
		"fieldname": "custom_loan_memo",
		"transactions": [
			{"label": _("Stock"), "items": ["Stock Entry"]},
			{"label": _("Selling"), "items": ["Sales Order"]},
		],
	}
