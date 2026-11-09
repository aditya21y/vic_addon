// Delivered To (isian kotak di print format Delivery Order) keisi otomatis tiap Shipping Address
// dipilih, terus bebas diedit - sama kayak Delivered To di Purchase Order. Yang didengerin field
// alamat lengkapnya (`shipping_address`), bukan link-nya: ganti customer ngisi alamatnya langsung
// tanpa lewat event `shipping_address_name`.
//
// Aturannya ngikut print format: alamat kirim cuma dipakai kalau beda dari alamat customer. Kalau
// sama, field-nya dikosongin biar kotaknya jatuh ke nama project / customer.
frappe.ui.form.on("Delivery Note", {
	shipping_address(frm) {
		const differs =
			frm.doc.shipping_address_name && frm.doc.shipping_address_name !== frm.doc.customer_address;

		frm.set_value("custom_delivered_to", differs ? address_to_text(frm.doc.shipping_address) : "");
	},
});

// Alamat lengkap itu HTML (`Jl. ...<br>Jakarta<br>`) - field-nya Small Text, jadi tiap <br>
// dijadiin baris baru dan tag lainnya dibuang. Sama kayak di purchase_order.js.
function address_to_text(html) {
	const text = frappe.utils.html2text((html || "").replace(/<br\s*\/?>/gi, "\n"));
	return text
		.split("\n")
		.map((line) => line.trim())
		.filter(Boolean)
		.join("\n");
}

// DN dropship & PR-nya saling nge-link. Dialog "Cancel All" bawaan Frappe bakal ngebatalin PR-nya
// duluan - gagal (stok gudang transit minus, DN masih nge-link). PR/PI dropship dibatalin server
// sesudah DN-nya (vic/dropship.py, vic/dropship_return.py), jadi gak usah ditawarin di dialog.
frappe.ui.form.on("Delivery Note", {
	refresh(frm) {
		if (!frm.doc.custom_dropship_purchase_receipt) return;

		frm.ignore_doctypes_on_cancel_all = [
			...new Set([...(frm.ignore_doctypes_on_cancel_all || []), "Purchase Receipt", "Purchase Invoice"]),
		];
	},
});

// Tarik barang dropship dari beberapa PO sekaligus (Dropship & Mixed). Dua langkah: pilih PO-nya,
// terus pilih baris + qty yang dikirim. Barisnya ditambahin ke DN yang lagi dibuka - dirakit di
// server (`build_delivery_note` di vic/dropship.py) lewat Sales Order masing-masing.
frappe.ui.form.on("Delivery Note", {
	refresh(frm) {
		if (frm.doc.docstatus !== 0 || frm.doc.is_return) return;

		frm.add_custom_button(
			__("Purchase Order (Dropship)"),
			() => select_dropship_purchase_orders(frm),
			__("Get Items From")
		);
	},
});

function select_dropship_purchase_orders(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Select Purchase Orders (Dropship / Mixed)"),
		fields: [
			{
				fieldtype: "MultiSelectList",
				fieldname: "purchase_orders",
				label: __("Purchase Orders"),
				reqd: 1,
				get_data(txt) {
					return frappe.xcall("vic_addon.vic.dropship.search_dropship_purchase_orders", {
						customer: frm.doc.customer || null,
						txt: txt || null,
					});
				},
			},
			{
				fieldtype: "HTML",
				options: `<p class="text-muted small">${__(
					"Only submitted Purchase Orders with Dropship or Mixed items that are not fully delivered yet{0}.",
					[frm.doc.customer ? __(" for {0}", [frappe.utils.escape_html(frm.doc.customer)]) : ""]
				)}</p>`,
			},
		],
		primary_action_label: __("Next"),
		primary_action({ purchase_orders }) {
			frappe.call({
				method: "vic_addon.vic.dropship.get_items_from_purchase_orders",
				args: { purchase_orders },
				freeze: true,
				callback({ message }) {
					const rows = message || [];
					if (!rows.length) {
						frappe.msgprint({
							title: __("Nothing to Deliver"),
							indicator: "orange",
							message: __("Every Dropship / Mixed item in these Purchase Orders is already delivered."),
						});
						return;
					}

					dialog.hide();
					select_dropship_items(frm, rows);
				},
			});
		},
	});

	dialog.show();
}

function select_dropship_items(frm, rows) {
	const dialog = new frappe.ui.Dialog({
		title: __("Get Items from Purchase Orders"),
		size: "extra-large",
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
					{ fieldtype: "Data", fieldname: "purchase_order_item", label: __("Row"), hidden: 1 },
					{
						fieldtype: "Link",
						fieldname: "purchase_order",
						label: __("Purchase Order"),
						options: "Purchase Order",
						read_only: 1,
						in_list_view: 1,
						columns: 2,
					},
					{
						fieldtype: "Link",
						fieldname: "sales_order",
						label: __("Sales Order"),
						options: "Sales Order",
						read_only: 1,
						in_list_view: 1,
						columns: 2,
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
						fieldtype: "Data",
						fieldname: "transaction_type",
						label: __("Type"),
						read_only: 1,
						in_list_view: 1,
						columns: 1,
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
						// baris Mixed dipecah di sini: sebagian dikirim ke customer, sisanya diterima ke
						// gudang lewat Create > Purchase Receipt di PO-nya
						fieldtype: "Float",
						fieldname: "qty",
						label: __("Qty"),
						reqd: 1,
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

			const empty = selected.filter((row) => !flt(row.qty));
			if (empty.length) {
				frappe.msgprint({
					title: __("Qty Required"),
					indicator: "orange",
					message: __("Fill the Qty for: {0}", [empty.map((row) => row.item_code).join(", ")]),
				});
				return;
			}

			frappe.call({
				method: "vic_addon.vic.dropship.make_delivery_note_from_purchase_orders",
				args: {
					selected_items: selected.map((row) => ({
						purchase_order_item: row.purchase_order_item,
						qty: row.qty,
					})),
					target_doc: frm.doc,
				},
				freeze: true,
				callback({ message }) {
					if (!message) return;

					dialog.hide();
					frappe.model.sync(message);
					frm.dirty();
					frm.refresh();
				},
			});
		},
	});

	dialog.show();
	// semua baris dicentang duluan, tinggal user yang ngurangin
	dialog.wrapper.find(".grid-heading-row .grid-row-check").click();
}
