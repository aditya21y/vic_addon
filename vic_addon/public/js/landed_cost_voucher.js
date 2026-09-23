// Tarik biaya dari Journal Entry: yang keambil cuma baris yang dicentang
// "Biaya yang masuk nilai barang". Lihat vic_addon/vic/landed_cost.py.

frappe.ui.form.on("Landed Cost Voucher", {
	refresh(frm) {
		if (frm.doc.docstatus !== 0) return;

		frm.add_custom_button(
			__("Journal Entry"),
			() => pull_from_journal_entry(frm),
			__("Get Expenses From")
		);
	},
});

function pull_from_journal_entry(frm) {
	if (!frm.doc.company) {
		frappe.msgprint(__("Select the Company first"));
		return;
	}

	const dialog = new frappe.ui.Dialog({
		title: __("Get Expenses from Journal Entry"),
		fields: [
			{
				fieldtype: "Link",
				fieldname: "journal_entry",
				label: __("Journal Entry"),
				options: "Journal Entry",
				reqd: 1,
				// cuma jurnal yang punya baris bercentang
				get_query: () => ({
					query: "vic_addon.vic.landed_cost.journal_entry_query",
					filters: { company: frm.doc.company },
				}),
			},
		],
		primary_action_label: __("Get Expenses"),
		primary_action({ journal_entry }) {
			const sudah = (frm.doc.taxes || []).some((row) => row.custom_journal_entry === journal_entry);
			if (sudah) {
				frappe.msgprint({
					title: __("Already Added"),
					indicator: "orange",
					message: __("Expenses from {0} are already in this voucher.", [journal_entry]),
				});
				return;
			}

			frappe.call({
				method: "vic_addon.vic.landed_cost.get_expenses_from_journal_entry",
				args: { journal_entry },
				freeze: true,
				callback({ message }) {
					if (!message || !message.length) return;

					dialog.hide();
					add_rows(frm, message);
				},
			});
		},
	});

	dialog.show();
}

function add_rows(frm, rows) {
	// expense_account dipasang duluan, baru amount: dua-duanya punya trigger bawaan
	// (mata uang akun, lalu nilai dalam mata uang perusahaan) yang mesti jalan urut
	const pending = rows.map((data) => {
		const row = frm.add_child("taxes");

		return frappe.model
			.set_value(row.doctype, row.name, {
				expense_account: data.expense_account,
				description: data.description,
				custom_journal_entry: data.custom_journal_entry,
			})
			.then(() => frappe.model.set_value(row.doctype, row.name, "amount", data.amount));
	});

	Promise.all(pending).then(() => {
		frm.refresh_field("taxes");
		frappe.show_alert({
			message: __("{0} expense row(s) added", [rows.length]),
			indicator: "green",
		});
	});
}
