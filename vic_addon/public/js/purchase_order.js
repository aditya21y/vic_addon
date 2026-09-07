// PO bisa campur: sebagian barang dikirim supplier langsung ke lapangan (Dropship), sebagian
// masuk gudang sendiri (Reguler), dan baris Mixed dipecah dua-duanya. Karena itu dua dokumen
// turunannya dibikin lewat modal - user yang nentuin baris mana dan berapa qty-nya.
//
// Delivery Note  -> barang yang dikirim ke customer (Purchase Receipt-nya nyusul otomatis waktu
//                   DN disubmit, masuk gudang transit dropship - lihat vic_addon/vic/dropship.py)
// Purchase Receipt -> porsi yang masuk gudang sendiri

const DROPSHIP_TYPES = ["Dropship", "Mixed"];

frappe.ui.form.on("Purchase Order", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		const items = frm.doc.items || [];
		const has_delivery = items.some((item) => DROPSHIP_TYPES.includes(item.custom_transaction_type));
		if (!has_delivery) return;

		// tombol bawaan narik semua baris termasuk yang dropship - barang yang gak pernah mampir
		// ke gudang jadi kecatat diterima
		frm.remove_custom_button(__("Purchase Receipt"), __("Create"));

		frm.add_custom_button(
			__("Delivery Note"),
			() =>
				open_items_dialog(frm, {
					title: __("Create Delivery Note"),
					fetch: "vic_addon.vic.dropship.get_items_for_delivery_note",
					make: "vic_addon.vic.dropship.make_delivery_note",
					empty: __("Every Dropship item in this Purchase Order is already delivered."),
					extra_columns: [
						{
							fieldtype: "Data",
							fieldname: "transaction_type",
							label: __("Type"),
							read_only: 1,
							in_list_view: 1,
							columns: 1,
						},
					],
				}),
			__("Create")
		);

		if (items.some((item) => item.custom_transaction_type !== "Dropship")) {
			frm.add_custom_button(
				__("Purchase Receipt"),
				() =>
					open_items_dialog(frm, {
						title: __("Create Purchase Receipt"),
						fetch: "vic_addon.vic.dropship.get_items_for_purchase_receipt",
						make: "vic_addon.vic.dropship.make_purchase_receipt",
						empty: __("Every item in this Purchase Order is already received."),
						extra_columns: [
							{
								fieldtype: "Link",
								fieldname: "warehouse",
								label: __("Warehouse"),
								options: "Warehouse",
								read_only: 1,
								in_list_view: 1,
								columns: 2,
							},
						],
					}),
				__("Create")
			);
		}
	},
});

// Satu modal dipakai bareng dua tombol: isinya sama-sama "baris mana, berapa qty".
function open_items_dialog(frm, options) {
	frappe.call({
		method: options.fetch,
		args: { purchase_order: frm.doc.name },
		freeze: true,
		callback({ message }) {
			const rows = message || [];

			if (!rows.length) {
				frappe.msgprint({
					title: __("Nothing to Create"),
					indicator: "orange",
					message: options.empty,
				});
				return;
			}

			show_items_dialog(frm, rows, options);
		},
	});
}

function show_items_dialog(frm, rows, options) {
	const dialog = new frappe.ui.Dialog({
		title: options.title,
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
						fieldname: "purchase_order_item",
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
						columns: 3,
					},
					{
						fieldtype: "Float",
						fieldname: "order_qty",
						label: __("Order Qty"),
						read_only: 1,
						in_list_view: 1,
						columns: 1,
					},
					{
						fieldtype: "Float",
						fieldname: "qty",
						label: __("Qty"),
						// baris Mixed dipecah di sini: sebagian dikirim ke customer,
						// sisanya diterima ke gudang lewat tombol satunya
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
					...(options.extra_columns || []),
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

			const empty = selected.filter((row) => !flt(row.qty));
			if (empty.length) {
				frappe.msgprint({
					title: __("Qty Required"),
					indicator: "orange",
					message: __("Fill the Qty for: {0}", [
						empty.map((row) => row.item_code).join(", "),
					]),
				});
				return;
			}

			dialog.hide();
			open_target_doc(frm, selected, options);
		},
	});

	dialog.show();
	// semua baris dicentang duluan, tinggal user yang ngurangin
	dialog.wrapper.find(".grid-heading-row .grid-row-check").click();
}

function open_target_doc(frm, selected, options) {
	frappe.call({
		method: options.make,
		args: {
			source_name: frm.doc.name,
			selected_items: selected.map((row) => ({
				purchase_order_item: row.purchase_order_item,
				qty: row.qty,
			})),
		},
		freeze: true,
		callback({ message }) {
			if (!message) return;

			frappe.model.sync(message);
			frappe.set_route("Form", message.doctype, message.name);
		},
	});
}
