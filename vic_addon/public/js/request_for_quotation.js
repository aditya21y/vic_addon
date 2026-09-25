// Penawaran yang masuk dari RFQ ini dibandingin di satu tabel Excel: dua penawaran terakhir
// tiap supplier (Lama vs Baru), terus penawaran terakhir antar supplier dibanding yang termurah.
// Lihat vic_addon/vic/supplier_comparison.py.

frappe.ui.form.on("Request for Quotation", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		frm.add_custom_button(
			__("Download Excel Price Comparison"),
			() =>
				open_url_post(
					"/api/method/vic_addon.vic.supplier_comparison.download_comparison",
					{ request_for_quotation: frm.doc.name },
					true
				),
			__("Actions")
		);

		frm.add_custom_button(__("Share to WhatsApp PDF Price Comparison"), () => share_to_whatsapp(frm), __("Actions"));

		// pilih supplier + item dulu, baru kirim atau unduh
		frm.add_custom_button(__("Send Inquiry"), () => send_inquiry(frm), __("Actions"));

		hide_native_tools(frm);
	},
});

// Grup Tools bawaan isinya dua tombol yang udah digantiin Send Inquiry:
//   Send Emails to Suppliers - ngirim link portal biar supplier ngisi harga di web
//   Download PDF             - nanya print format + supplier, terus diunduh
// Dua-duanya gak kepake lagi dan bikin bingung kalau dibiarin sebelahan.
// Dicopot di refresh, bukan di setup: tombolnya baru dipasang ERPNext waktu refresh jalan.
function hide_native_tools(frm) {
	["Send Emails to Suppliers", "Download PDF"].forEach((label) =>
		frm.remove_custom_button(__(label), __("Tools"))
	);
}

// Satu pop up buat semua cara ngirim: supplier dipilih duluan, terus item mana aja yang
// dimintain harganya. Barang sering dipecah per jenis supplier, jadi jarang satu supplier
// dimintain semua item di dokumen.
function send_inquiry(frm) {
	const suppliers = (frm.doc.suppliers || []).filter((row) => row.supplier);
	if (!suppliers.length) {
		frappe.msgprint(__("Add at least one supplier first."));
		return;
	}

	const dialog = new frappe.ui.Dialog({
		title: __("Send Inquiry"),
		size: "large",
		fields: [
			{
				fieldtype: "Select",
				fieldname: "supplier",
				label: __("Supplier"),
				reqd: 1,
				options: suppliers.map((row) => ({
					value: row.supplier,
					// emailnya ditempel di label biar kelihatan mana yang belum punya email
					label: row.email_id ? `${row.supplier} (${row.email_id})` : `${row.supplier} — ${__("no email")}`,
				})),
				default: suppliers[0].supplier,
			},
			{
				fieldtype: "Select",
				fieldname: "file_format",
				label: __("Attachment"),
				options: ["Excel", "PDF"],
				default: "Excel",
			},
			{ fieldtype: "Section Break", label: __("Items") },
			{
				fieldtype: "Table",
				fieldname: "items",
				cannot_add_rows: true,
				cannot_delete_rows: true,
				in_place_edit: false,
				data: (frm.doc.items || []).map((row) => ({
					row_name: row.name,
					item_code: row.item_code,
					description: row.description || row.item_name || row.item_code,
					qty: row.qty,
					uom: row.uom,
				})),
				fields: [
					{ fieldtype: "Data", fieldname: "row_name", hidden: 1 },
					{ fieldtype: "Data", fieldname: "item_code", label: __("Item"), read_only: 1, in_list_view: 1, columns: 2 },
					{ fieldtype: "Data", fieldname: "description", label: __("Description"), read_only: 1, in_list_view: 1, columns: 5 },
					{ fieldtype: "Float", fieldname: "qty", label: __("Qty"), read_only: 1, in_list_view: 1, columns: 1 },
					{ fieldtype: "Data", fieldname: "uom", label: __("UOM"), read_only: 1, in_list_view: 1, columns: 1 },
				],
			},
			{ fieldtype: "Section Break", label: __("Email") },
			{
				fieldtype: "Data",
				fieldname: "subject",
				label: __("Subject"),
				default: __("Inquiry {0}", [frm.doc.name]),
			},
			{ fieldtype: "Text Editor", fieldname: "message", label: __("Message") },
		],
		primary_action_label: __("Send Email"),
		primary_action: () => run(dialog, frm, "email"),
	});

	dialog.add_custom_action(__("Send WhatsApp"), () => run(dialog, frm, "whatsapp"));
	dialog.add_custom_action(__("Download Excel"), () => run(dialog, frm, "excel"));
	dialog.add_custom_action(__("Download PDF"), () => run(dialog, frm, "pdf"));

	dialog.show();
	// semua item dicentang duluan, tinggal user yang ngurangin
	dialog.wrapper.find(".grid-heading-row .grid-row-check").click();
}

function get_selection(dialog) {
	const values = dialog.get_values();
	if (!values) return null;

	const selected = dialog.fields_dict.items.grid.get_selected_children();
	if (!selected.length) {
		frappe.msgprint(__("Select at least one item"));
		return null;
	}

	return { ...values, items: selected.map((row) => row.row_name) };
}

function run(dialog, frm, action) {
	const selection = get_selection(dialog);
	if (!selection) return;

	const args = {
		request_for_quotation: frm.doc.name,
		items: JSON.stringify(selection.items),
	};

	if (action === "excel" || action === "pdf") {
		const method =
			action === "excel"
				? "vic_addon.vic.request_for_quotation.download_inquiry"
				: "vic_addon.vic.request_for_quotation.download_inquiry_pdf";
		open_url_post(`/api/method/${method}`, args, true);
		return;
	}

	if (action === "email") {
		frappe.call({
			method: "vic_addon.vic.request_for_quotation.send_inquiry",
			args: {
				...args,
				supplier: selection.supplier,
				subject: selection.subject,
				message: selection.message,
				file_format: selection.file_format,
			},
			freeze: true,
			freeze_message: __("Sending"),
			callback({ message }) {
				if (!message) return;

				dialog.hide();
				frappe.show_alert({
					message: __("Inquiry for {0} item(s) sent to {1}", [message.items, message.email]),
					indicator: "green",
				});
				frm.reload_doc();
			},
		});
		return;
	}

	frappe.call({
		method: "vic_addon.vic.request_for_quotation.share_inquiry",
		args: { ...args, supplier: selection.supplier, file_format: selection.file_format },
		freeze: true,
		freeze_message: __("Preparing file"),
		callback({ message }) {
			if (!message) return;

			dialog.hide();
			show_whatsapp_dialog(frm, selection, message);
		},
	});
}

// Link-nya gak langsung dilempar ke WhatsApp: dialognya dulu, biar tombol WA-nya ditekan user -
// browser suka ngeblok jendela baru yang dibuka dari callback.
function show_whatsapp_dialog(frm, selection, file) {
	const text = `${selection.subject || frm.doc.name}\n${file.url}`;

	const dialog = new frappe.ui.Dialog({
		title: __("Send via WhatsApp"),
		fields: [
			{ fieldtype: "Small Text", fieldname: "link", label: __("Link"), read_only: 1, default: file.url },
			{
				fieldtype: "HTML",
				options: `<p class="text-muted small">${__(
					"Anyone holding this link can open the file without logging in. Removing the attachment from this document revokes it."
				)}</p>`,
			},
		],
		primary_action_label: __("Open WhatsApp"),
		primary_action() {
			window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank");
			dialog.hide();
			frm.reload_doc();
		},
		secondary_action_label: __("Copy Link"),
		secondary_action() {
			frappe.utils.copy_to_clipboard(file.url);
		},
	});

	dialog.show();
}

// PDF-nya disimpan sebagai lampiran publik di RFQ, jadi penerimanya bisa buka dari HP tanpa akun.
// Link-nya gak langsung dilempar ke WhatsApp: dialognya dulu, biar tombol WA-nya ditekan user -
// browser suka ngeblok jendela baru yang dibuka dari callback.
function share_to_whatsapp(frm) {
	frappe.call({
		method: "vic_addon.vic.supplier_comparison.share_comparison",
		args: { request_for_quotation: frm.doc.name },
		freeze: true,
		freeze_message: __("Preparing comparison PDF"),
		callback({ message }) {
			if (!message) return;

			show_share_dialog(frm, message);
		},
	});
}

function show_share_dialog(frm, file) {
	const subject = frm.doc.custom_subject || frm.doc.name;
	const cheapest = file.supplier
		? __("Penawaran terendah: {0}.", [file.supplier])
		: "";
	const text = `${__("Perbandingan penawaran supplier untuk {0}.", [subject])} ${cheapest}\n${file.url}`;

	const dialog = new frappe.ui.Dialog({
		title: __("Share to WhatsApp"),
		fields: [
			{
				fieldtype: "Small Text",
				fieldname: "link",
				label: __("Link"),
				read_only: 1,
				default: file.url,
			},
			{
				fieldtype: "HTML",
				options: `<p class="text-muted small">${__(
					"Anyone holding this link can open the PDF without logging in. Sharing again replaces this link with a new one, and removing the attachment from this Request for Quotation revokes it."
				)}</p>`,
			},
		],
		primary_action_label: __("Open WhatsApp"),
		primary_action() {
			window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank");
			dialog.hide();
		},
		secondary_action_label: __("Copy Link"),
		secondary_action() {
			frappe.utils.copy_to_clipboard(file.url);
		},
	});

	dialog.show();
}
