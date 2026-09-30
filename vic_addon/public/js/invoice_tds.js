// "Consider for Tax Withholding" di Purchase / Sales Invoice default mati.
//
// PPh sekarang diakui di Payment Entry (uang muka lewat Advance Invoice, pelunasan lewat
// centangan "Potong PPh atas Invoice") - lihat vic_addon/vic/tax_withholding.py. Kalau invoice-nya
// ikut motong, PPh-nya kepotong dua kali. User masih boleh nyentang manual buat kasus khusus;
// Payment Entry-nya bakal ngelewatin invoice yang udah motong sendiri.
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
