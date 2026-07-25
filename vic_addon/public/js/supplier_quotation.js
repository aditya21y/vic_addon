// Diskon bertingkat per item (max 3 level).
// Diskonnya berantai, bukan dijumlah: 10% + 5% + 2% -> 1 - (0.9 x 0.95 x 0.98) = 16.21%
// Hasilnya masuk ke field standar discount_percentage (Discount on Price List Rate),
// jadi rate / amount / taxes / diskon tambahan atas net total tetap dihitung ERPNext.

const DISCOUNT_LEVELS = [
	"custom_discount_level_1",
	"custom_discount_level_2",
	"custom_discount_level_3",
];

function apply_discount_levels(cdt, cdn) {
	const item = locals[cdt][cdn];

	let net_factor = 1.0;
	DISCOUNT_LEVELS.forEach((fieldname) => {
		net_factor *= 1 - flt(item[fieldname]) / 100.0;
	});

	// mirrors erpnext's own discount_percentage handler in buying.js
	item.discount_amount = 0.0;
	frappe.model.set_value(
		cdt,
		cdn,
		"discount_percentage",
		flt((1 - net_factor) * 100.0, precision("discount_percentage", item))
	);
}

frappe.ui.form.on("Supplier Quotation Item", {
	custom_discount_level_1: (frm, cdt, cdn) => apply_discount_levels(cdt, cdn),
	custom_discount_level_2: (frm, cdt, cdn) => apply_discount_levels(cdt, cdn),
	custom_discount_level_3: (frm, cdt, cdn) => apply_discount_levels(cdt, cdn),

	// price list rate bisa di-refetch (ganti item / price list / currency),
	// re-derive biar diskon bertingkat tetap jadi acuan barisnya
	price_list_rate(frm, cdt, cdn) {
		const item = locals[cdt][cdn];
		if (DISCOUNT_LEVELS.some((fieldname) => flt(item[fieldname]))) {
			apply_discount_levels(cdt, cdn);
		}
	},
});
