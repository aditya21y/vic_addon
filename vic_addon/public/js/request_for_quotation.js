// Penawaran yang masuk dari RFQ ini dibandingin di satu tabel Excel: dua penawaran terakhir
// tiap supplier (Lama vs Baru), terus penawaran terakhir antar supplier dibanding yang termurah.
// Lihat vic_addon/vic/supplier_comparison.py.

frappe.ui.form.on("Request for Quotation", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		frm.add_custom_button(
			__("Download Comparison"),
			() =>
				open_url_post(
					"/api/method/vic_addon.vic.supplier_comparison.download_comparison",
					{ request_for_quotation: frm.doc.name },
					true
				),
			__("Actions")
		);

		frm.add_custom_button(__("Share to WhatsApp"), () => share_to_whatsapp(frm), __("Actions"));
	},
});

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
