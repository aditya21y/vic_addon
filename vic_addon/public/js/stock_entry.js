// Repack Percentage: rate item hasil Repack dihitung server dari persentase (vic/stock_entry.py),
// jadi begitu persennya diisi, Set Basic Rate Manually dicopot - Basic Rate balik read only.
// Rate-nya kelihatan setelah Save.

frappe.ui.form.on("Stock Entry Detail", {
	custom_repack_percentage(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (flt(row.custom_repack_percentage) && row.set_basic_rate_manually) {
			frappe.model.set_value(cdt, cdn, "set_basic_rate_manually", 0);
		}
	},
});
