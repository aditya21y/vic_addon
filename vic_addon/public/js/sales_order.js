// Bikin draft PO dari Sales Order, satu PO per supplier.
// Supplier & harga belinya diambil dari SQTN yang nempel di tiap baris item.

frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		frm.add_custom_button(
			__("Purchase Order (per Supplier)"),
			() => create_purchase_orders(frm),
			__("Create")
		);
	},
});

// Tombol bawaan Create > Purchase Order udah gak dipakai - diganti Purchase Order (per Supplier).
// Dicopot lewat `custom_refresh`, bukan handler `refresh` di atas: tombolnya dipasang controller
// ERPNext (`cscript.refresh`) yang jalannya setelah handler `frappe.ui.form.on`, sedangkan
// `custom_refresh` dipanggil Frappe sesudah controller itu.
cur_frm.cscript.custom_refresh = function () {
	this.frm.remove_custom_button(__("Purchase Order"), __("Create"));
};

// Modal: user ngecek dulu baris mana yang mau di-PO, dari penawaran siapa, dan berapa banyak.
// Satu PO per supplier. Supplier ngikut Supplier Quotation yang dipilih; mau ganti supplier
// sendiri, kosongin dulu SQTN-nya - barang habis di supplier pertama itu kasus normal.
function create_purchase_orders(frm) {
	frappe.call({
		method: "vic_addon.vic.sales_order.get_items_for_purchase_order",
		args: { sales_order: frm.doc.name },
		freeze: true,
		callback({ message }) {
			const rows = message || [];

			if (!rows.length) {
				frappe.msgprint({
					title: __("Nothing to Order"),
					indicator: "orange",
					message: __("Every item in this Sales Order already has an active Purchase Order."),
				});
				return;
			}

			show_purchase_order_dialog(frm, rows);
		},
	});
}

function show_purchase_order_dialog(frm, rows) {
	const dialog = new frappe.ui.Dialog({
		title: __("Create Purchase Order (per Supplier)"),
		size: "large",
		fields: [
			{
				fieldname: "items",
				fieldtype: "Table",
				label: __("Items"),
				cannot_add_rows: true,
				cannot_delete_rows: true,
				in_place_edit: false,
				data: rows,
				fields: [
					{
						fieldtype: "Data",
						fieldname: "sales_order_item",
						label: __("Row"),
						hidden: 1,
					},
					{
						fieldtype: "Data",
						fieldname: "sales_order_quotation",
						label: __("Sales Order Quotation"),
						hidden: 1,
					},
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
						fieldtype: "Float",
						fieldname: "pending_qty",
						label: __("Qty"),
						// boleh dikurangin kalau mau mesen sebagian dulu - sama aja kayak ngedit
						// qty di draft PO-nya, cuma lebih cepat
						in_list_view: 1,
						columns: 1,
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
						fieldtype: "Data",
						fieldname: "transaction_type",
						label: __("Type"),
						read_only: 1,
						in_list_view: 1,
						columns: 1,
					},
					{
						fieldtype: "Link",
						fieldname: "supplier",
						label: __("Supplier"),
						options: "Supplier",
						in_list_view: 1,
						columns: 3,
						// supplier itu turunan penawarannya; mau isi sendiri, kosongin dulu SQTN-nya
						read_only_depends_on: "eval:doc.supplier_quotation",
					},
					{
						fieldtype: "Link",
						fieldname: "supplier_quotation",
						label: __("Supplier Quotation"),
						options: "Supplier Quotation",
						in_list_view: 1,
						columns: 2,
						// cuma penawaran yang beneran ada item baris ini
						get_query(row) {
							return {
								query: "vic_addon.vic.sales_order.supplier_quotation_query",
								filters: { item_code: row.item_code },
							};
						},
						onchange() {
							set_supplier_from_quotation(this.doc, this.grid_row);
						},
					},
				],
			},
		],
		primary_action_label: __("Create"),
		primary_action() {
			const selected = dialog.fields_dict.items.grid.get_selected_children();

			if (!selected.length) {
				frappe.msgprint(__("Select at least one item"));
				return;
			}

			const without_supplier = selected.filter((row) => !row.supplier);
			if (without_supplier.length) {
				frappe.msgprint({
					title: __("Supplier Required"),
					indicator: "orange",
					message: __("Fill the Supplier for: {0}", [
						without_supplier.map((row) => row.item_code).join(", "),
					]),
				});
				return;
			}

			const replaced = selected.filter(
				(row) => row.sales_order_quotation && row.supplier_quotation !== row.sales_order_quotation
			);

			if (replaced.length) {
				confirm_replaced_quotation(frm, dialog, selected, replaced);
				return;
			}

			dialog.hide();
			submit_purchase_orders(frm, selected);
		},
	});

	dialog.show();
	// semua baris dicentang duluan, tinggal user yang ngurangin
	dialog.wrapper.find(".grid-heading-row .grid-row-check").click();
}

// SQTN yang dipakai beda dari yang dipilih waktu penawaran ke customer disusun - itu keputusan
// yang mengubah harga beli, jadi dimintakan persetujuan dulu sebelum PO dibuat.
function confirm_replaced_quotation(frm, dialog, selected, replaced) {
	const rows = replaced
		.map(
			(row) => `<tr>
				<td>${frappe.utils.escape_html(row.item_code)}</td>
				<td>${frappe.utils.escape_html(row.sales_order_quotation)}</td>
				<td>${frappe.utils.escape_html(row.supplier_quotation || __("(none)"))}</td>
			</tr>`
		)
		.join("");

	const message = `
		<p>${__(
			"Sales Order {0} refers to a different Supplier Quotation for the following items:",
			[frm.doc.name]
		)}</p>
		<table class="table table-bordered">
			<thead>
				<tr>
					<th>${__("Item")}</th>
					<th>${__("On Sales Order")}</th>
					<th>${__("Will Be Used")}</th>
				</tr>
			</thead>
			<tbody>${rows}</tbody>
		</table>
		<p>${__(
			"The Purchase Order will be created using the Supplier Quotation selected above, so the buying rate follows that quotation. Do you wish to continue?"
		)}</p>`;

	frappe.confirm(message, () => {
		dialog.hide();
		submit_purchase_orders(frm, selected);
	});
}

// Supplier itu turunan dari penawaran yang dipakai - biar PO gak dikirim ke supplier yang beda
// dari pemilik harga yang ditarik.
function set_supplier_from_quotation(row, grid_row) {
	if (!row.supplier_quotation) {
		grid_row && grid_row.refresh();
		return;
	}

	frappe.db.get_value("Supplier Quotation", row.supplier_quotation, "supplier").then(({ message }) => {
		if (message && message.supplier) {
			row.supplier = message.supplier;
		}

		grid_row && grid_row.refresh();
	});
}

function submit_purchase_orders(frm, selected_items) {
	frappe.call({
		method: "vic_addon.vic.sales_order.make_purchase_orders",
		args: {
			sales_order: frm.doc.name,
			selected_items: selected_items.map((row) => ({
				sales_order_item: row.sales_order_item,
				supplier: row.supplier,
				supplier_quotation: row.supplier_quotation,
				qty: row.pending_qty,
			})),
		},
		freeze: true,
		freeze_message: __("Creating Purchase Orders"),
		callback({ message }) {
			if (!message || !message.length) return;

			frappe.msgprint({
				title: __("{0} draft Purchase Order created", [message.length]),
				indicator: "green",
				message: message
					.map((name) => `<a href="/app/purchase-order/${encodeURIComponent(name)}">${name}</a>`)
					.join("<br>"),
			});

			frm.reload_doc();
		},
	});
}

// Invoice retensi: SO yang barangnya udah ketagih semua gak bisa bikin Sales Invoice lewat tombol
// bawaan, jadi dibikin dari tombol ini - muncul kalau masih ada retensi yang ditahan di invoice
// progress tapi belum ditagih. Lihat vic_addon/vic/retention.py.
frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		frappe.call({
			method: "vic_addon.vic.retention.get_unbilled_retention",
			args: { sales_order: frm.doc.name },
			callback({ message }) {
				if (!flt(message)) return;
				frm.add_custom_button(
					__("Retention Invoice"),
					() =>
						frappe.model.open_mapped_doc({
							method: "vic_addon.vic.retention.make_retention_invoice",
							frm: frm,
						}),
					__("Create")
				);
			},
		});
	},
});
