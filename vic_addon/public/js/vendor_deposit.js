// Deposit ke supplier - lihat vic_addon/vic/vendor_deposit.py.
// PO: tombol Pay Deposit selama deposit belum lunas. Payment Entry deposit: Account Paid To
// disaring ke akun deposit (bawaannya cuma akun hutang).

frappe.ui.form.on("Purchase Order", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || flt(frm.doc.custom_deposit_amount) <= 0) return;

		show_deposit_status(frm);

		if (flt(frm.doc.custom_deposit_amount) - flt(frm.doc.custom_deposit_paid) > 0.005) {
			frm.add_custom_button(__("Pay Deposit"), () =>
				frappe.call({
					method: "vic_addon.vic.vendor_deposit.make_deposit_payment",
					args: { purchase_order: frm.doc.name },
					freeze: true,
					callback({ message }) {
						if (!message) return;
						const doc = frappe.model.sync(message)[0];
						frappe.set_route("Form", doc.doctype, doc.name);
					},
				})
			);
		}
	},
});

// Status deposit sebagai indikator dashboard, nilainya bisa diklik langsung ke Payment Entry
// deposit-nya. Deposit PE gak punya baris References, jadi gak nongol di Connections bawaan PO -
// makanya ditarik sendiri (filter custom_deposit_purchase_order).
function show_deposit_status(frm) {
	const amount = flt(frm.doc.custom_deposit_amount);
	const paid = flt(frm.doc.custom_deposit_paid);
	const money = (v) => format_currency(v, frm.doc.currency);

	// PE deposit-nya diambil dulu, nomornya ditempelin di label indikator + nilainya bisa diklik ke PE.
	frappe.db
		.get_list("Payment Entry", {
			filters: { custom_deposit_purchase_order: frm.doc.name, docstatus: 1 },
			fields: ["name"],
			order_by: "posting_date desc, creation desc",
			limit: 0,
		})
		.then((rows) => {
			rows = rows || [];
			const extra = rows.length ? " · " + rows[0].name + (rows.length > 1 ? " (+" + (rows.length - 1) + ")" : "") : "";

			let color, label;
			if (paid <= 0.005) {
				[color, label] = ["orange", __("Deposit Unpaid: {0}", [money(amount)])];
			} else if (paid + 0.005 < amount) {
				[color, label] = ["blue", __("Deposit Partial: {0} / {1}", [money(paid), money(amount)]) + extra];
			} else {
				[color, label] = ["green", __("Deposit Paid: {0}", [money(paid)]) + extra];
			}
			const $indicator = frm.dashboard.add_indicator(label, color);

			if (!rows.length) return;
			$indicator
				.css("cursor", "pointer")
				.attr("title", __("Open deposit Payment Entry"))
				.on("click", () => {
					if (rows.length === 1) {
						frappe.set_route("Form", "Payment Entry", rows[0].name);
					} else {
						frappe.set_route("List", "Payment Entry", {
							custom_deposit_purchase_order: frm.doc.name,
							docstatus: 1,
						});
					}
				});
		});
}

frappe.ui.form.on("Payment Entry", {
	refresh(frm) {
		if (!frm.doc.custom_deposit_purchase_order) return;

		frm.set_query("paid_to", () => ({
			filters: { company: frm.doc.company, is_group: 0, root_type: "Asset" },
		}));
	},
});
