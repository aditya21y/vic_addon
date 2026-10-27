// RFQ (Opportunity): kalau Customer-nya udah keisi, pilihan Project cuma project milik customer itu.
// Customer di Opportunity itu `party_name` - Link dinamis, isinya Customer cuma kalau
// Opportunity From = Customer (bisa juga Lead/Prospect, yang gak punya project).

frappe.ui.form.on("Opportunity", {
	setup(frm) {
		frm.set_query("project", () => {
			const customer = get_customer(frm);
			return customer ? { filters: { customer } } : {};
		});
	},

	party_name(frm) {
		clear_other_customer_project(frm);
	},

	opportunity_from(frm) {
		clear_other_customer_project(frm);
	},
});

// Rate item RFQ wajib diisi tapi ERPNext gak pernah ngambilin harganya - di tahap RFQ harganya
// emang belum ada, jadi langsung diisi 0. Baris baru udah 0 dari default (property setter
// `Opportunity Item-rate-default`, begitu juga Amount & versi Company Currency-nya); ini buat
// baris yang Rate-nya sempat dikosongin. Rate yang udah diisi user gak ditimpa.
frappe.ui.form.on("Opportunity Item", {
	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.item_code && is_null(row.rate)) {
			frappe.model.set_value(cdt, cdn, "rate", 0);
		}
	},
});

function get_customer(frm) {
	return frm.doc.opportunity_from === "Customer" ? frm.doc.party_name : null;
}

// Customer diganti: Project yang kepilih punya customer lain dikosongin, biar gak nyangkut
function clear_other_customer_project(frm) {
	const customer = get_customer(frm);
	if (!customer || !frm.doc.project) return;

	frappe.db.get_value("Project", frm.doc.project, "customer").then(({ message }) => {
		if (message && message.customer !== customer) {
			frm.set_value("project", null);
		}
	});
}
