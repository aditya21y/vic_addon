// Skema DP pakai Item DP - lihat vic_addon/vic/dp_item_invoice.py.
//
// Invoice DP: centang "Is DP Invoice", pilih order + DP Term (baris Payment Schedule order).
// Item-nya diganti satu baris Item DP waktu disimpan.
// Invoice progress: tombol "Get DP Invoices" narik DP dari order yang sama ke tabel DP Allocations;
// waktu submit, porsi itu dibalik lewat Reverse Journal yang ngurangin tagihan invoice ini.

const DP_SIDE = {
	"Sales Invoice": { order_doctype: "Sales Order", order_field: "sales_order" },
	"Purchase Invoice": { order_doctype: "Purchase Order", order_field: "purchase_order" },
};

["Sales Invoice", "Purchase Invoice"].forEach((doctype) => {
	frappe.ui.form.on(doctype, {
		refresh(frm) {
			load_dp_terms(frm);
			add_get_dp_button(frm);
			auto_get_dp_invoices(frm);
		},

		custom_is_dp(frm) {
			if (frm.doc.custom_is_dp && !frm.doc.custom_dp_order) {
				const field = DP_SIDE[frm.doctype].order_field;
				const row = (frm.doc.items || []).find((item) => item[field]);
				if (row) frm.set_value("custom_dp_order", row[field]);
			}
			load_dp_terms(frm);
			add_get_dp_button(frm);
		},

		custom_dp_order(frm) {
			frm.set_value("custom_dp_term", "");
			frm.set_value("custom_dp_percentage", 0);
			load_dp_terms(frm);
		},

		custom_dp_term(frm) {
			const term = (frm.__dp_terms || []).find((row) => row.label === frm.doc.custom_dp_term);
			if (!term) return;

			frm.set_value("custom_dp_percentage", term.portion);
			if (term.used_in) {
				frappe.msgprint({
					title: __("DP Term Already Billed"),
					indicator: "orange",
					message: __("This term is already billed in {0}.", [term.used_in]),
				});
			}
		},
	});
});

function load_dp_terms(frm) {
	if (!frm.doc.custom_is_dp || !frm.doc.custom_dp_order) {
		frm.set_df_property("custom_dp_term", "options", [""]);
		return;
	}

	frappe.call({
		method: "vic_addon.vic.dp_item_invoice.get_dp_terms",
		args: {
			order_doctype: DP_SIDE[frm.doctype].order_doctype,
			order: frm.doc.custom_dp_order,
			invoice: frm.is_new() ? null : frm.doc.name,
		},
		callback({ message }) {
			frm.__dp_terms = message || [];
			const options = [""].concat(frm.__dp_terms.map((row) => row.label));
			// nilai yang udah kesimpan tetap jadi pilihan, walau payment schedule-nya berubah
			if (frm.doc.custom_dp_term && !options.includes(frm.doc.custom_dp_term)) {
				options.push(frm.doc.custom_dp_term);
			}
			frm.set_df_property("custom_dp_term", "options", options);
		},
	});
}

function add_get_dp_button(frm) {
	frm.remove_custom_button(__("Get DP Invoices"));
	if (frm.doc.docstatus !== 0 || frm.doc.custom_is_dp || frm.doc.is_return) return;

	frm.add_custom_button(__("Get DP Invoices"), () => get_dp_invoices(frm, true));
}

// dokumen baru dari order: DP-nya langsung ditarik sekali, biar gak kelupaan
function auto_get_dp_invoices(frm) {
	if (!frm.is_new() || frm.__dp_auto_loaded || frm.doc.custom_is_dp || frm.doc.is_return) return;
	if ((frm.doc.custom_dp_allocations || []).length) return;

	const field = DP_SIDE[frm.doctype].order_field;
	if (!(frm.doc.items || []).some((item) => item[field])) return;

	frm.__dp_auto_loaded = true;
	get_dp_invoices(frm, false);
}

function get_dp_invoices(frm, notify) {
	frappe.call({
		method: "vic_addon.vic.dp_item_invoice.get_dp_allocations",
		args: { doc: frm.doc },
		freeze: notify,
		callback({ message }) {
			const rows = message || [];
			frm.clear_table("custom_dp_allocations");
			rows.forEach((row) => frm.add_child("custom_dp_allocations", row));
			frm.refresh_field("custom_dp_allocations");

			const total = rows.reduce((sum, row) => sum + flt(row.total_amount), 0);
			frm.set_value("custom_total_dp_allocated", total);

			if (notify && !rows.length) {
				frappe.msgprint({
					title: __("No DP Invoice"),
					indicator: "orange",
					message: __("There is no unused DP Invoice for the orders in this invoice."),
				});
			} else if (rows.length) {
				frappe.show_alert({
					message: __("{0} DP Invoice(s) will be reversed on submit", [rows.length]),
					indicator: "green",
				});
			}
		},
	});
}

// Retensi (cuma Sales Invoice) - lihat vic_addon/vic/retention.py.
// Invoice progress: centang "Is Progress Invoice" + pilih Progress Term (ngisi Progress Percentage,
// boleh diubah); waktu disimpan rate item = rate SO x persen dan baris Retensi (minus) ketambah
// sendiri. Invoice retensi: centang "Is Retention Invoice" + pilih Sales Order; item diganti baris
// Retensi (plus) dan sisa DP-nya langsung ditarik.
frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		load_progress_terms(frm);
	},

	custom_is_progress(frm) {
		if (frm.doc.custom_is_progress) {
			const row = (frm.doc.items || []).find((item) => item.sales_order);
			if (row && frm.doc.custom_dp_order !== row.sales_order) frm.set_value("custom_dp_order", row.sales_order);
			// DP order ini ditarik ulang: yang ketarik otomatis waktu form kebuka masih ngitung
			// tagihan penuh, belum ngikut Progress Percentage
			if (frm.doc.docstatus === 0) get_dp_invoices(frm, false);
		}
		load_progress_terms(frm);
	},

	custom_progress_term(frm) {
		const term = (frm.__progress_terms || []).find((row) => row.label === frm.doc.custom_progress_term);
		if (term) frm.set_value("custom_progress_percentage", term.percentage);
	},

	// persen berubah = nilai tagihan berubah, jadi porsi DP yang dibalik ikut dihitung ulang
	custom_progress_percentage(frm) {
		if (frm.doc.custom_is_progress && frm.doc.docstatus === 0) get_dp_invoices(frm, false);
	},

	custom_dp_order(frm) {
		frm.set_value("custom_progress_term", "");
		load_progress_terms(frm);
		// invoice retensi: sisa DP order ini langsung ditarik ke tabel DP Invoices
		if (frm.doc.custom_is_retention && frm.doc.custom_dp_order && frm.doc.docstatus === 0) {
			get_dp_invoices(frm, false);
		}
	},
});

function load_progress_terms(frm) {
	if (!frm.doc.custom_is_progress || !frm.doc.custom_dp_order) {
		frm.set_df_property("custom_progress_term", "options", [""]);
		return;
	}

	frappe.call({
		method: "vic_addon.vic.retention.get_progress_terms",
		args: { order: frm.doc.custom_dp_order },
		callback({ message }) {
			frm.__progress_terms = message || [];
			const options = [""].concat(frm.__progress_terms.map((row) => row.label));
			if (frm.doc.custom_progress_term && !options.includes(frm.doc.custom_progress_term)) {
				options.push(frm.doc.custom_progress_term);
			}
			frm.set_df_property("custom_progress_term", "options", options);
		},
	});
}
