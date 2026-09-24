// Filter laporan Arus Uang dan Barang + tombol unduh versi Excel.
// Lihat vic_addon/vic/report/arus_uang_dan_barang/arus_uang_dan_barang.py

frappe.query_reports["Arus Uang dan Barang"] = {
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
			reqd: 1,
			default: frappe.datetime.year_start(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.year_end(),
		},
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
		},
	],

	// baris judul proyek dibedain biar kelompoknya kelihatan
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (data && data.is_group) {
			value = `<span style="font-weight: 700">${value || ""}</span>`;
		}

		return value;
	},

	onload(report) {
		report.page.add_inner_button(__("Download Excel"), () => {
			const filters = report.get_values();
			if (!filters) return;

			// dibuka lewat URL biar file-nya langsung keunduh browser
			const args = new URLSearchParams({ filters: JSON.stringify(filters) });
			window.open(
				`/api/method/vic_addon.vic.arus_uang_dan_barang.download?${args.toString()}`
			);
		});
	},
};
