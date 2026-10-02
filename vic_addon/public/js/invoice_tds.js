// "Consider for Tax Withholding" di Purchase / Sales Invoice selalu mati.
//
// PPh selalu diakui di Payment Entry - lihat vic_addon/vic/tax_withholding.py. Server juga
// matiin centangannya (`turn_off_invoice_tds`), jadi file ini cuma biar form-nya gak sempat
// nampilin centangan nyala sebelum disimpan.
//
// ERPNext nyalain centangannya di dua tempat: waktu dokumen baru kebuka, dan di callback
// pengambilan data supplier/customer yang jalannya asinkron. `after_ajax` nunggu callback itu
// kelar dulu, baru dimatiin - kalau langsung, keburu ketimpa lagi.

function turn_off_invoice_tds(frm) {
	frappe.after_ajax(() => {
		if (frm.doc.docstatus === 0 && frm.doc.apply_tds) {
			frm.set_value("apply_tds", 0);
		}
	});
}

["Purchase Invoice", "Sales Invoice"].forEach((doctype) => {
	frappe.ui.form.on(doctype, {
		onload_post_render(frm) {
			if (frm.is_new()) turn_off_invoice_tds(frm);
		},
		supplier: turn_off_invoice_tds,
		customer: turn_off_invoice_tds,
	});
});
