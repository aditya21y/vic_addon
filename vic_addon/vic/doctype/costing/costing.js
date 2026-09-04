// Copyright (c) 2026, aditya and contributors
// For license information, please see license.txt

// Perhitungan finalnya tetap di server (costing.py), yang di sini biar angkanya langsung
// keupdate waktu rate / qty / margin / additional cost diubah.

// Angka ringkasan yang ditebelin di section Totals
const BOLD_FIELDS = [
	"total_hpp_amount",
	"total_selling_amount",
	"total_quotation_amount",
	"total_profit_amount",
	"total_profit_percentage",
	"total_quotation_profit_amount",
	"total_quotation_profit_percentage",
];

frappe.ui.form.on("Costing", {
	refresh(frm) {
		bold_total_fields(frm);

		frm.add_custom_button(__("Get Items from Supplier Quotation"), () =>
			get_items_from_supplier_quotation(frm)
		);

		if (!frm.doc.__islocal) {
			frm.add_custom_button(
				__("Quotation"),
				() =>
					frappe.model.open_mapped_doc({
						method: "vic_addon.vic.doctype.costing.costing.make_quotation",
						frm: frm,
					}),
				__("Create")
			);
		}

		calculate(frm);
	},

	additional_percentage: calculate,
	items_remove: calculate,
	additional_costs_remove: calculate,
});

frappe.ui.form.on("Costing Item", {
	// Item stok yang gak lewat SQTN: gudang + harga pokoknya diambil dari nilai persediaan
	// gudang itu, biar kelihatan langsung tanpa nunggu disimpan (server ngisi ulang tiap simpan).
	item_code(frm, cdt, cdn) {
		fetch_stock_item_details(frm, cdt, cdn);
	},

	// ganti gudang = ganti sumber harga, jadi rate-nya ditarik ulang
	warehouse(frm, cdt, cdn) {
		fetch_stock_item_details(frm, cdt, cdn, { keep_warehouse: true });
	},

	qty: calculate,
	rate: calculate,
	margin_percentage: calculate,

	// diisi user = jadi harga nego, gak ngikut selling rate lagi.
	// dikosongin = balik ngikut selling rate.
	quotation_rate(frm, cdt, cdn) {
		const item = locals[cdt][cdn];
		item.quotation_rate_manually_set = flt(item.quotation_rate) ? 1 : 0;
		calculate(frm);
	},
});

function fetch_stock_item_details(frm, cdt, cdn, { keep_warehouse = false } = {}) {
	const item = locals[cdt][cdn];

	// baris dari Supplier Quotation harganya udah dikunci ke penawaran, jangan diutak-atik
	if (!item.item_code || item.supplier_quotation) return;
	if (keep_warehouse && !item.warehouse) return;

	frappe.call({
		method: "vic_addon.vic.doctype.costing.costing.get_stock_item_details",
		args: {
			item_code: item.item_code,
			company: frm.doc.company,
			warehouse: keep_warehouse ? item.warehouse : null,
		},
		callback({ message }) {
			if (!message) return;

			if (!keep_warehouse && message.warehouse) {
				frappe.model.set_value(cdt, cdn, "warehouse", message.warehouse);
			}

			if (message.rate) {
				frappe.model.set_value(cdt, cdn, "rate", message.rate);
			}
		},
	});
}

frappe.ui.form.on("Costing Additional Cost", {
	amount: calculate,
});

// Tebelin angka totalnya.
//
// Class-nya ditempel ke wrapper field (`.frappe-control`), bukan ke elemen nilainya: tiap
// kalkulasi manggil `frm.refresh_fields()` yang nge-render ulang isi tiap field, jadi apa pun
// yang nempel di elemen nilai (termasuk properti `bold` bawaan frappe) bakal keganti. Wrapper-nya
// sendiri gak ikut dibikin ulang selama form kebuka.
//
// Style-nya disuntik dari sini juga, bukan lewat app_include_css, biar gak perlu restart bench
// buat kepakai.
function bold_total_fields(frm) {
	if (!document.getElementById("vic-bold-style")) {
		$(`<style id="vic-bold-style">
			.vic-bold-value .control-value,
			.vic-bold-value .like-disabled-input,
			.vic-bold-value input.form-control { font-weight: 700 !important; }
		</style>`).appendTo("head");
	}

	BOLD_FIELDS.forEach((fieldname) => {
		const field = frm.get_field(fieldname);
		if (field) field.$wrapper.addClass("vic-bold-value");
	});
}

function calculate(frm) {
	const items = frm.doc.items || [];

	// Total Buying Amount
	let total_buying_amount = 0;
	items.forEach((item) => {
		item.amount = flt(flt(item.rate) * flt(item.qty), precision("amount", item));
		total_buying_amount += flt(item.amount);
	});

	// Additional Cost Percentage = Total Additional Costs / Total Buying Amount
	const total_additional_costs = (frm.doc.additional_costs || []).reduce(
		(total, cost) => total + flt(cost.amount),
		0
	);
	const additional_cost_percentage = total_buying_amount
		? flt(
			(total_additional_costs / total_buying_amount) * 100,
			precision("additional_cost_percentage")
		)
		: 0;

	// additional cost yang dibebankan ke tiap rupiah harga beli
	const cost_factor =
		(additional_cost_percentage / 100) * (1 + flt(frm.doc.additional_percentage) / 100);

	const totals = {
		total_distributed_cost_amount: 0,
		total_hpp_amount: 0,
		total_selling_amount: 0,
		total_quotation_amount: 0,
		total_profit_amount: 0,
	};

	items.forEach((item) => {
		item.distributed_cost_rate = flt(
			flt(item.rate) * cost_factor,
			precision("distributed_cost_rate", item)
		);
		item.distributed_cost_amount = flt(
			flt(item.distributed_cost_rate) * flt(item.qty),
			precision("distributed_cost_amount", item)
		);

		item.hpp_rate = flt(
			flt(item.rate) + flt(item.distributed_cost_rate),
			precision("hpp_rate", item)
		);
		item.hpp_amount = flt(flt(item.hpp_rate) * flt(item.qty), precision("hpp_amount", item));

		const margin = flt(item.margin_percentage);
		item.selling_rate =
			margin >= 100
				? 0
				: flt(flt(item.hpp_rate) / (1 - margin / 100), precision("selling_rate", item));
		item.margin_rate = flt(
			flt(item.selling_rate) - flt(item.hpp_rate),
			precision("margin_rate", item)
		);
		item.margin_amount = flt(
			flt(item.margin_rate) * flt(item.qty),
			precision("margin_amount", item)
		);
		item.selling_amount = flt(
			flt(item.selling_rate) * flt(item.qty),
			precision("selling_amount", item)
		);

		// quotation rate default ngikut selling rate, kecuali user isi manual
		if (!item.quotation_rate_manually_set) {
			item.quotation_rate = item.selling_rate;
		}

		item.quotation_amount = flt(
			flt(item.quotation_rate) * flt(item.qty),
			precision("quotation_amount", item)
		);

		item.profit_amount = flt(
			flt(item.selling_amount) - flt(item.hpp_amount),
			precision("profit_amount", item)
		);
		item.profit_percentage = item.hpp_amount
			? flt(
				(flt(item.profit_amount) / flt(item.hpp_amount)) * 100,
				precision("profit_percentage", item)
			)
			: 0;

		totals.total_distributed_cost_amount += flt(item.distributed_cost_amount);
		totals.total_hpp_amount += flt(item.hpp_amount);
		totals.total_selling_amount += flt(item.selling_amount);
		totals.total_quotation_amount += flt(item.quotation_amount);
		totals.total_profit_amount += flt(item.profit_amount);
	});

	frm.doc.total_buying_amount = flt(total_buying_amount, precision("total_buying_amount"));
	frm.doc.total_additional_costs = flt(total_additional_costs, precision("total_additional_costs"));
	frm.doc.additional_cost_percentage = additional_cost_percentage;

	Object.entries(totals).forEach(([fieldname, value]) => {
		frm.doc[fieldname] = flt(value, precision(fieldname));
	});

	frm.doc.total_profit_percentage = frm.doc.total_hpp_amount
		? flt(
			(frm.doc.total_profit_amount / frm.doc.total_hpp_amount) * 100,
			precision("total_profit_percentage")
		)
		: 0;

	frm.refresh_fields();
}

function get_items_from_supplier_quotation(frm) {
	const dialog = new frappe.ui.form.MultiSelectDialog({
		doctype: "Supplier Quotation",
		target: frm,
		setters: { supplier: undefined },
		add_filters_group: 1,
		date_field: "transaction_date",
		get_query: () => ({
			filters: { docstatus: 1, company: frm.doc.company, currency: frm.doc.currency },
		}),
		action(selections) {
			if (!selections.length) {
				frappe.msgprint(__("Please select at least one Supplier Quotation"));
				return;
			}

			frappe.call({
				method: "vic_addon.vic.doctype.costing.costing.get_supplier_quotation_items",
				args: { supplier_quotations: selections },
				freeze: true,
				callback({ message }) {
					(message || []).forEach((row) => Object.assign(frm.add_child("items"), row));
					frm.refresh_field("items");
					calculate(frm);
				},
			});

			dialog.dialog.hide();
		},
	});
}
