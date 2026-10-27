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
	"total_after_discount_amount",
	"total_profit_after_discount_amount",
	"total_profit_after_discount_percentage",
];

frappe.ui.form.on("Costing", {
	setup(frm) {
		// pilihan SQTN dibatesin ke penawaran submitted yang beneran ada item baris itu -
		// milih penawaran yang gak nawarin itemnya bikin harganya gak ketarik
		frm.set_query("supplier_quotation", "items", (doc, cdt, cdn) => ({
			query: "vic_addon.vic.sales_order.supplier_quotation_query",
			filters: { item_code: locals[cdt][cdn].item_code },
		}));
	},

	refresh(frm) {
		bold_total_fields(frm);

		frm.add_custom_button(__("Get Items from Supplier Quotation"), () =>
			get_items_from_supplier_quotation(frm)
		);

		if (!frm.doc.__islocal) {
			frm.add_custom_button(__("Send Email"), () => send_costing_email(frm));

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

	// Diskon diisi persen atau nominal - yang terakhir diketik yang dipegang, satunya ngikut
	discount_percentage(frm) {
		frm.doc.discount_amount_manually_set = 0;
		calculate(frm);
	},
	discount_amount(frm) {
		frm.doc.discount_amount_manually_set = 1;
		calculate(frm);
	},

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

	// ganti SQTN = ganti penawaran yang dipakai, jadi harga + suppliernya ikut ganti.
	// Dikosongin = baris ini jadi barang stok, harganya balik ke valuation gudang.
	supplier_quotation(frm, cdt, cdn) {
		const item = locals[cdt][cdn];

		if (!item.supplier_quotation) {
			frappe.model.set_value(cdt, cdn, {
				supplier: null,
				supplier_quotation_item: null,
				rate: 0,
			});
			fetch_stock_item_details(frm, cdt, cdn, { keep_warehouse: true });
			return;
		}

		if (!item.item_code) return;

		frappe.call({
			method: "vic_addon.vic.doctype.costing.costing.get_quotation_item_details",
			args: {
				supplier_quotation: item.supplier_quotation,
				item_code: item.item_code,
			},
			callback({ message }) {
				if (!message) return;

				frappe.model.set_value(cdt, cdn, message).then(() => calculate(frm));
			},
		});
	},

	qty: calculate,
	rate: calculate,
	margin_percentage: calculate,

	// diisi user = jadi harga nego, gak ngikut selling rate lagi - termasuk kalau diisi 0
	// (mis. barang tambahan yang gak ditagih). Dikosongin = balik ngikut selling rate.
	quotation_rate(frm, cdt, cdn) {
		const item = locals[cdt][cdn];
		item.quotation_rate_manually_set = is_null(item.quotation_rate) ? 0 : 1;
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

	calculate_discount(frm);

	frm.refresh_fields();
}

// Simulasi diskon atas Total Quotation Amount - rumusnya sama kayak `calculate_discount` di server
function calculate_discount(frm) {
	const doc = frm.doc;
	const base = flt(doc.total_quotation_amount);

	if (doc.discount_amount_manually_set) {
		doc.discount_amount = flt(doc.discount_amount, precision("discount_amount"));
		doc.discount_percentage = base
			? flt((doc.discount_amount / base) * 100, precision("discount_percentage"))
			: 0;
	} else {
		doc.discount_amount = flt(
			(base * flt(doc.discount_percentage)) / 100,
			precision("discount_amount")
		);
	}

	doc.total_after_discount_amount = flt(
		base - flt(doc.discount_amount),
		precision("total_after_discount_amount")
	);
	doc.total_profit_after_discount_amount = flt(
		doc.total_after_discount_amount - flt(doc.total_hpp_amount),
		precision("total_profit_after_discount_amount")
	);
	doc.total_profit_after_discount_percentage = doc.total_hpp_amount
		? flt(
			(doc.total_profit_after_discount_amount / doc.total_hpp_amount) * 100,
			precision("total_profit_after_discount_percentage")
		)
		: 0;
}

// Ngambil item dari penawaran supplier. Satu dialog buat tiga hal: nyaring penawaran ke satu
// Request for Quotation, ngintip item + qty-nya dulu (qty bisa diubah sebelum masuk Costing),
// dan opsi ambil harga termurah - aturannya sama persis kayak tabel Supplier Comparison.
function get_items_from_supplier_quotation(frm) {
	// dideklarasiin duluan: `get_data` di bawah kepanggil pas dialognya masih dibangun, jadi
	// kalau pakai `const dialog = new ...` variabelnya belum ada waktu dipakai
	let dialog;

	dialog = new frappe.ui.Dialog({
		title: __("Get Items from Supplier Quotation"),
		size: "extra-large",
		fields: [
			{
				fieldtype: "Link",
				fieldname: "request_for_quotation",
				label: __("Request for Quotation"),
				options: "Request for Quotation",
				description: __("Only quotations created from this RFQ are listed."),
				onchange: () => {
					dialog.set_value("supplier_quotations", []);
					reload_items(frm, dialog);
				},
			},
			{ fieldtype: "Column Break" },
			{
				fieldtype: "Check",
				fieldname: "only_cheapest",
				label: __("Take the cheapest price only"),
				description: __(
					"One row per item, taken from the cheapest offer — same rule as the Supplier Comparison."
				),
				onchange: () => reload_items(frm, dialog),
			},
			{ fieldtype: "Section Break" },
			{
				fieldtype: "MultiSelectPills",
				fieldname: "supplier_quotations",
				label: __("Supplier Quotation"),
				// pas ambil termurah, sumbernya semua penawaran terakhir di RFQ itu - gak usah dipilih
				depends_on: "eval:!doc.only_cheapest || !doc.request_for_quotation",
				get_data(txt) {
					// yang udah kepilih dibuang dari daftar. Frappe niatnya nyaring ini juga, cuma
					// hasil `data.filter(...)`-nya kebuang (multiselect_pills.js), jadi disaring sini
					const chosen = (dialog && dialog.get_value("supplier_quotations")) || [];

					return frappe
						.xcall("vic_addon.vic.doctype.costing.costing.get_supplier_quotations", {
							// pas pertama dibangun dialognya belum ada, filter RFQ-nya nyusul
							request_for_quotation: dialog && dialog.get_value("request_for_quotation"),
							company: frm.doc.company,
							txt: txt,
						})
						.then((rows) => rows.filter((row) => !chosen.includes(row.value)));
				},
				onchange: () => reload_items(frm, dialog),
			},
			{ fieldtype: "Section Break" },
			{
				fieldtype: "Table",
				fieldname: "items",
				label: __("Items"),
				cannot_add_rows: true,
				cannot_delete_rows: true,
				in_place_edit: false,
				data: [],
				fields: [
					{
						fieldtype: "Link",
						fieldname: "item_code",
						label: __("Item"),
						options: "Item",
						read_only: 1,
						in_list_view: 1,
						columns: 2,
					},
					{
						fieldtype: "Data",
						fieldname: "item_name",
						label: __("Item Name"),
						read_only: 1,
						in_list_view: 1,
						columns: 2,
					},
					{
						fieldtype: "Float",
						fieldname: "qty",
						label: __("Qty"),
						// angka ini yang beneran masuk ke Costing
						in_list_view: 1,
						columns: 1,
						reqd: 1,
					},
					{
						fieldtype: "Link",
						fieldname: "uom",
						label: __("UOM"),
						options: "UOM",
						read_only: 1,
						in_list_view: 1,
						columns: 1,
					},
					{
						fieldtype: "Currency",
						fieldname: "rate",
						label: __("Rate"),
						read_only: 1,
						in_list_view: 1,
						columns: 2,
					},
					{
						fieldtype: "Link",
						fieldname: "supplier",
						label: __("Supplier"),
						options: "Supplier",
						read_only: 1,
						in_list_view: 1,
						columns: 2,
					},
					{
						fieldtype: "Link",
						fieldname: "supplier_quotation",
						label: __("Supplier Quotation"),
						options: "Supplier Quotation",
						read_only: 1,
						in_list_view: 1,
						columns: 2,
					},
					{
						fieldtype: "Data",
						fieldname: "supplier_quotation_item",
						label: __("Row"),
						hidden: 1,
					},
				],
			},
		],
		primary_action_label: __("Get Items"),
		primary_action() {
			const selected = dialog.fields_dict.items.grid.get_selected_children();

			if (!selected.length) {
				frappe.msgprint(__("Select at least one item"));
				return;
			}

			selected.forEach((row) => {
				Object.assign(frm.add_child("items"), {
					item_code: row.item_code,
					item_name: row.item_name,
					uom: row.uom,
					qty: flt(row.qty),
					rate: flt(row.rate),
					supplier: row.supplier,
					supplier_quotation: row.supplier_quotation,
					supplier_quotation_item: row.supplier_quotation_item,
				});
			});

			frm.refresh_field("items");
			calculate(frm);
			dialog.hide();
			fill_header_from_inquiry(frm, selected);
		},
	});

	dialog.show();
}

// Customer, RFQ, Project, dan Subject diambil dari Inquiry asal baris yang baru ditarik - cuma
// yang masih kosong. Server ngisi lagi waktu disimpan; ini biar udah kelihatan sebelum disimpan.
function fill_header_from_inquiry(frm, rows) {
	const names = rows.map((row) => row.supplier_quotation_item).filter(Boolean);
	if (!names.length) return;

	frappe.call({
		method: "vic_addon.vic.doctype.costing.costing.get_header_from_supplier_quotation_items",
		args: { supplier_quotation_items: names },
		callback({ message }) {
			const values = message || {};
			// centangan Show ... in Print cuma ikut kalau nilainya ikut keisi
			const pairs = { project: "show_project_in_print", subject: "show_subject_in_print" };
			Object.entries(values).forEach(([field, value]) => {
				if (Object.values(pairs).includes(field)) return;
				if (frm.doc[field]) return;
				frm.set_value(field, value);
				if (pairs[field]) frm.set_value(pairs[field], values[pairs[field]] || 0);
			});
		},
	});
}

// Kirim Costing (Import) lewat email ke internal (review harga): composer email bawaan Frappe,
// PDF Costing (Import) langsung kelampir.
function send_costing_email(frm) {
	const composer = new frappe.views.CommunicationComposer({
		doc: frm.doc,
		frm: frm,
		subject: __("Costing {0}", [frm.doc.name]) + (frm.doc.subject ? ` - ${frm.doc.subject}` : ""),
		attach_document_print: true,
		recipients: "",
	});
	$(composer.dialog.fields_dict.select_print_format.input).val("Costing (Import)");
}

// Isi tabelnya ditarik ulang tiap pilihan di atas berubah.
function reload_items(frm, dialog) {
	const values = dialog.get_values(true);
	const quotations = values.supplier_quotations || [];

	if (!quotations.length && !(values.only_cheapest && values.request_for_quotation)) {
		set_dialog_items(dialog, []);
		return;
	}

	frappe.call({
		method: "vic_addon.vic.doctype.costing.costing.get_costing_items",
		args: {
			supplier_quotations: quotations,
			request_for_quotation: values.request_for_quotation,
			only_cheapest: values.only_cheapest ? 1 : 0,
		},
		callback({ message }) {
			set_dialog_items(dialog, message || []);
		},
	});
}

function set_dialog_items(dialog, rows) {
	const grid = dialog.fields_dict.items.grid;
	grid.df.data = rows;
	grid.refresh();

	// semua baris dicentang duluan, tinggal user yang ngurangin
	dialog.wrapper.find(".grid-heading-row .grid-row-check").prop("checked", false).click();
}

// Section Realization: rencana Costing vs realisasi SO & PO per item (vic/costing_realization.py).
// Report lengkapnya: Costing Realization.
frappe.ui.form.on("Costing", {
	refresh(frm) {
		render_realization(frm);
	},
});

function render_realization(frm) {
	const field = frm.get_field("realization_html");
	if (!field || frm.is_new()) return;

	frappe.call({
		method: "vic_addon.vic.costing_realization.get_costing_realization",
		args: { costing: frm.doc.name },
		callback({ message }) {
			if (!message) return;
			field.$wrapper.html(realization_table(message));
		},
	});
}

function realization_table(data) {
	const money = (value) => format_currency(value, frappe.defaults.get_default("currency"));
	const pct = (value) => `${flt(value, 1)}%`;
	const variance = (value, more_is_good = true) => {
		const color = !flt(value) ? "" : (value > 0) === more_is_good ? "var(--green-600)" : "var(--red-600)";
		return `<span style="color: ${color}">${money(value)}</span>`;
	};
	const status = (value) =>
		value === "Lengkap" ? value : `<span style="color: var(--orange-600)">${value}</span>`;

	const row = (r, total) => `
		<tr${total ? ' style="font-weight: 600; background: var(--subtle-fg)"' : ""}>
			<td>${total ? __("Total") : frappe.utils.escape_html(r.item_code || "")}</td>
			<td>${status(r.po_status)}</td>
			<td class="text-right">${flt(r.plan_qty)} / ${flt(r.so_qty)} / ${flt(r.po_qty)}</td>
			<td class="text-right">${money(r.plan_sell_amount)}<br>${money(r.so_amount)}<br>${variance(r.sell_variance)}</td>
			<td class="text-right">${money(r.plan_buy_amount)}<br>${money(r.real_buy_amount)}<br>${variance(r.buy_variance, false)}</td>
			<td class="text-right">${money(r.plan_profit)}<br>${money(r.real_profit)}<br>${variance(r.profit_variance)}</td>
			<td class="text-right">${pct(r.plan_margin)}<br>${pct(r.real_margin)}</td>
		</tr>`;

	const links = (doctype, names) =>
		names.length ? names.map((name) => frappe.utils.get_form_link(doctype, name, true)).join(", ") : "-";

	if (!data.sales_orders.length) {
		return `<div class="text-muted">${__("No submitted Sales Order from this Costing's Quotation yet.")}</div>`;
	}

	return `
		<div class="small text-muted" style="margin-bottom: 6px">
			${__("Sales Order")}: ${links("Sales Order", data.sales_orders)} &middot;
			${__("Purchase Order")}: ${links("Purchase Order", data.purchase_orders)} &middot;
			<a href="/desk/query-report/Costing Realization?costing=${encodeURIComponent(data.costing || "")}">${__("Open report")}</a>
		</div>
		<table class="table table-bordered table-sm" style="font-size: 12px">
			<thead>
				<tr>
					<th>${__("Item")}</th>
					<th>${__("PO Status")}</th>
					<th class="text-right">${__("Qty")}<br><small>${__("Costing / SO / PO")}</small></th>
					<th class="text-right">${__("Jual")}<br><small>${__("Rencana / SO / Selisih")}</small></th>
					<th class="text-right">${__("Beli")}<br><small>${__("Rencana / Realisasi / Selisih")}</small></th>
					<th class="text-right">${__("Profit")}<br><small>${__("Rencana / Realisasi / Selisih")}</small></th>
					<th class="text-right">${__("Margin")}<br><small>${__("Rencana / Realisasi")}</small></th>
				</tr>
			</thead>
			<tbody>
				${data.rows.map((r) => row(r)).join("")}
				${row(data.total, true)}
			</tbody>
		</table>
		<div class="small text-muted">${__("Qty not yet ordered is costed at the planned buying price (estimate).")}</div>`;
}
