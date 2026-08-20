// Tombol alur peminjaman: statusnya yang nentuin tombol mana yang muncul.

frappe.ui.form.on("Loan Memo", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		const status = frm.doc.loan_memo_status;

		if (status === "Approved to Deliver") {
			frm.add_custom_button(
				__("Stock Entry (Customer Loan)"),
				() => make_stock_entry(frm, "make_loan_stock_entry"),
				__("Create")
			);
		}

		if (status === "Delivered") {
			// satu-satunya percabangan yang diputusin user: barangnya dibeli atau dibalikin
			frm.add_custom_button(__("Approve to Sell"), () => set_decision(frm, "approve_to_sell"));
			frm.add_custom_button(__("Approve to Return"), () => set_decision(frm, "approve_to_return"));
		}

		if (status === "Approved to Sell") {
			frm.add_custom_button(__("Sales Order"), () => make_sales_order(frm), __("Create"));
		}

		if (status === "Approved to Return") {
			frm.add_custom_button(
				__("Stock Entry (Customer Loan Return)"),
				() => make_stock_entry(frm, "make_return_stock_entry"),
				__("Create")
			);
		}
	},
});

function set_decision(frm, method) {
	frappe.call({
		method: `vic_addon.vic.doctype.loan_memo.loan_memo.${method}`,
		args: { loan_memo: frm.doc.name },
		freeze: true,
		callback() {
			frm.reload_doc();
		},
	});
}

function make_stock_entry(frm, method) {
	frappe.model.open_mapped_doc({
		method: `vic_addon.vic.doctype.loan_memo.loan_memo.${method}`,
		frm: frm,
	});
}

function make_sales_order(frm) {
	frappe.model.open_mapped_doc({
		method: "vic_addon.vic.doctype.loan_memo.loan_memo.make_sales_order",
		frm: frm,
	});
}
