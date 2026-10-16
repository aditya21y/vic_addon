// Costing Realization: rencana Costing vs realisasi SO & PO, per item.
// Lihat vic_addon/vic/report/costing_realization/costing_realization.py

frappe.query_reports["Costing Realization"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -3),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "costing", label: __("Costing"), fieldtype: "Link", options: "Costing" },
		{
			fieldname: "only_with_sales_order",
			label: __("Only with Sales Order"),
			fieldtype: "Check",
			default: 1,
		},
	],

	// baris Costing (total) di atas, item di bawahnya
	tree: true,
	name_field: "id",
	parent_field: "parent_id",
	initial_depth: 1,

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;

		// selisih: jual/profit minus = merah; beli plus (lebih mahal) = merah
		const bad =
			(["sell_variance", "profit_variance"].includes(column.fieldname) && data[column.fieldname] < 0) ||
			(column.fieldname === "buy_variance" && data[column.fieldname] > 0);
		const good =
			(["sell_variance", "profit_variance"].includes(column.fieldname) && data[column.fieldname] > 0) ||
			(column.fieldname === "buy_variance" && data[column.fieldname] < 0);
		if (bad) value = `<span style="color: var(--red-600)">${value}</span>`;
		if (good) value = `<span style="color: var(--green-600)">${value}</span>`;

		if (column.fieldname === "po_status" && data.po_status && data.po_status !== "Lengkap") {
			value = `<span style="color: var(--orange-600)">${value}</span>`;
		}
		if (data.indent === 0) value = `<b>${value}</b>`;
		return value;
	},
};
