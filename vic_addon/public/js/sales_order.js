// Bikin draft PO dari Sales Order, satu PO per supplier.
// Supplier & harga belinya diambil dari SQTN yang nempel di tiap baris item.

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

function create_purchase_orders(frm) {
	frappe.call({
		method: "vic_addon.vic.sales_order.make_purchase_orders",
		args: { sales_order: frm.doc.name },
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
