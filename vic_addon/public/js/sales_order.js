// Bikin draft PO dari Sales Order, satu PO per supplier.
// Supplier & harga belinya diambil dari SQTN yang nempel di tiap baris item.

// Modal bawaan "Create > Purchase Order" ngisi kolom Supplier-nya dari field `supplier` bawaan
// SO Item (punya skema dropship bawaan ERPNext, yang di sini disembunyiin), sedangkan supplier
// hasil costing kita simpen di `custom_supplier`. Nilainya dioper tepat sebelum modalnya kebuka
// - cuma di memori, jadi dokumen Sales Order-nya sendiri gak ikut berubah.
//
// Item yang gak punya SQTN tetap kosong, biar user yang milih suppliernya di modal. Supplier di
// modal juga bebas diganti: PO-nya ngikut pilihan user, dan link SQTN yang gak nyambung sama
// supplier baru bakal dilepas otomatis (lihat vic/purchase_order.py).
if (erpnext.selling?.SalesOrderController) {
	const make_purchase_order = erpnext.selling.SalesOrderController.prototype.make_purchase_order;

	erpnext.selling.SalesOrderController.prototype.make_purchase_order = function () {
		(this.frm.doc.items || []).forEach((item) => {
			if (!item.supplier) item.supplier = item.custom_supplier;
		});

		make_purchase_order.call(this);
	};
}

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

// Modal: user ngecek dulu baris mana yang mau di-PO dan suppliernya siapa, baru PO-nya dibikin
// (satu PO per supplier, kepisah lagi per tipe transaksi). Supplier keisi dari SQTN di baris
// item, tapi bebas diganti - barang habis di supplier pertama itu kasus normal.
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
				fieldname: "set_supplier",
				fieldtype: "Link",
				label: __("Set Supplier for Selected Rows"),
				options: "Supplier",
				onchange() {
					const supplier = dialog.get_value("set_supplier");
					if (!supplier) return;

					const grid = dialog.fields_dict.items.grid;
					grid.get_selected_children().forEach((row) => (row.supplier = supplier));
					grid.refresh();
				},
			},
			{ fieldtype: "Section Break" },
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
						label: __("Pending Qty"),
						read_only: 1,
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

			dialog.hide();
			submit_purchase_orders(frm, selected);
		},
	});

	dialog.show();
	// semua baris dicentang duluan, tinggal user yang ngurangin
	dialog.wrapper.find(".grid-heading-row .grid-row-check").click();
}

function submit_purchase_orders(frm, selected_items) {
	frappe.call({
		method: "vic_addon.vic.sales_order.make_purchase_orders",
		args: {
			sales_order: frm.doc.name,
			selected_items: selected_items.map((row) => ({
				sales_order_item: row.sales_order_item,
				supplier: row.supplier,
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
