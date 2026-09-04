// Angka estimasinya langsung kelihatan pas isian diubah, tanpa nunggu disimpan.
// Hitungannya tetap diulang di server waktu simpan - ini cuma biar enak dipakai.

frappe.ui.form.on("Selling Price Estimate", {
	item_code: fetch_last_purchase,
	warehouse: fetch_last_purchase,

	with_last_lcv(frm) {
		if (frm.doc.with_last_lcv) {
			fetch_landed_costs(frm);
		} else {
			frm.set_value("landed_costs", []);
			calculate(frm);
		}
	},

	margin_percentage: calculate,
});

frappe.ui.form.on("Costing Additional Cost", {
	amount: calculate,
	additional_costs_remove: calculate,
});

function fetch_last_purchase(frm) {
	if (!frm.doc.item_code) return;

	frappe.call({
		method: "vic_addon.vic.doctype.selling_price_estimate.selling_price_estimate.get_last_purchase",
		args: { item_code: frm.doc.item_code, warehouse: frm.doc.warehouse },
		callback({ message }) {
			frm.set_value({
				last_purchase_rate: message ? message.rate : 0,
				last_purchase_qty: message ? message.qty : 0,
				last_purchase_receipt: message ? message.purchase_receipt : null,
				last_purchase_date: message ? message.posting_date : null,
			});

			if (frm.doc.with_last_lcv) {
				fetch_landed_costs(frm);
			} else {
				calculate(frm);
			}
		},
	});
}

function fetch_landed_costs(frm) {
	if (!frm.doc.last_purchase_receipt) {
		frm.set_value("landed_costs", []);
		calculate(frm);
		return;
	}

	frappe.call({
		method: "vic_addon.vic.doctype.selling_price_estimate.selling_price_estimate.get_landed_costs",
		args: { purchase_receipt: frm.doc.last_purchase_receipt, item_code: frm.doc.item_code },
		callback({ message }) {
			frm.set_value("landed_costs", message || []);
			calculate(frm);
		},
	});
}

function calculate(frm) {
	const rows = frm.doc.with_last_lcv ? frm.doc.landed_costs || [] : frm.doc.additional_costs || [];
	const field = frm.doc.with_last_lcv ? "rate" : "amount";
	const total = rows.reduce((sum, row) => sum + flt(row[field]), 0);

	frm.set_value("total_additional_cost", total);

	const margin = flt(frm.doc.margin_percentage);
	if (margin >= 100) return;

	const cost = flt(frm.doc.last_purchase_rate) + total;
	frm.set_value("estimated_selling_rate", cost / (1 - margin / 100));
}
