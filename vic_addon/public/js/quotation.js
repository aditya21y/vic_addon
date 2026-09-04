// Harga final ke customer baru ketahuan di sini (setelah diskon per item / diskon atas total).
// Tombol ini yang mundurin harga itu ke Costing-nya, biar profit di Costing ngikut kenyataan.

frappe.ui.form.on("Quotation", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || !frm.doc.custom_costing) return;

		frm.add_custom_button(__("Update Costing Rate"), () => show_rate_changes(frm), __("Actions"));
	},
});

function show_rate_changes(frm) {
	frappe.call({
		method: "vic_addon.vic.doctype.costing.costing.get_costing_rate_changes",
		args: { quotation: frm.doc.name },
		freeze: true,
		callback({ message }) {
			const changes = message || [];

			if (!changes.length) {
				frappe.msgprint({
					title: __("Already Up to Date"),
					indicator: "green",
					message: __("Quotation Rate in {0} already matches this Quotation.", [
						frm.doc.custom_costing,
					]),
				});
				return;
			}

			confirm_update(frm, changes);
		},
	});
}

function confirm_update(frm, changes) {
	const rows = changes
		.map(
			(row) => `<tr>
				<td>#${row.idx} ${frappe.utils.escape_html(row.item_name || row.item_code)}</td>
				<td class="text-right">${format_currency(row.costing_rate, frm.doc.currency)}</td>
				<td class="text-right">${format_currency(row.quotation_rate, frm.doc.currency)}</td>
			</tr>`
		)
		.join("");

	const dialog = new frappe.ui.Dialog({
		title: __("Update Costing Rate"),
		fields: [
			{
				fieldtype: "HTML",
				options: `
					<p>${__("Quotation Rate in {0} will be replaced with the final rate from this Quotation:", [
						frm.doc.custom_costing,
					])}</p>
					<table class="table table-bordered">
						<thead>
							<tr>
								<th>${__("Item")}</th>
								<th class="text-right">${__("Costing")}</th>
								<th class="text-right">${__("Quotation")}</th>
							</tr>
						</thead>
						<tbody>${rows}</tbody>
					</table>`,
			},
		],
		primary_action_label: __("Update"),
		primary_action() {
			dialog.hide();

			frappe.call({
				method: "vic_addon.vic.doctype.costing.costing.update_costing_rates",
				args: { quotation: frm.doc.name },
				freeze: true,
				freeze_message: __("Updating Costing"),
				callback({ message }) {
					frappe.msgprint({
						title: __("{0} rate updated", [(message || []).length]),
						indicator: "green",
						message: __("Profit in {0} is recalculated with the final rate.", [
							`<a href="/app/costing/${encodeURIComponent(frm.doc.custom_costing)}">${
								frm.doc.custom_costing
							}</a>`,
						]),
					});
				},
			});
		},
	});

	dialog.show();
}
