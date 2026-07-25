// DPP Nilai Lain (PMK 131/2024) = 11/12 x net total.
// Nilai finalnya tetap dihitung server pas save (vic_addon/vic/dpp_nilai_lain.py),
// di sini cuma biar angkanya keupdate langsung waktu item/diskon/pajak diubah.

const DPP_NILAI_LAIN_RATIO = 11 / 12;

const DPP_NILAI_LAIN_DOCTYPES = [
	"Sales Order",
	"Sales Invoice",
	"Purchase Order",
	"Purchase Invoice",
];

function update_dpp_nilai_lain(frm) {
	frm.doc.custom_dpp_nilai_lain = flt(
		flt(frm.doc.net_total) * DPP_NILAI_LAIN_RATIO,
		precision("custom_dpp_nilai_lain", frm.doc)
	);
	frm.doc.custom_base_dpp_nilai_lain = flt(
		flt(frm.doc.base_net_total) * DPP_NILAI_LAIN_RATIO,
		precision("custom_base_dpp_nilai_lain", frm.doc)
	);
	frm.refresh_field("custom_dpp_nilai_lain");
	frm.refresh_field("custom_base_dpp_nilai_lain");
}

// erpnext gak punya event setelah kalkulasi total, jadi kita nebeng
// calculate_taxes_and_totals milik form ini (per form, bukan global)
function watch_totals(frm) {
	if (frm.__dpp_nilai_lain_watched || !frm.cscript?.calculate_taxes_and_totals) return;

	const calculate_taxes_and_totals = frm.cscript.calculate_taxes_and_totals.bind(frm.cscript);
	frm.cscript.calculate_taxes_and_totals = async function (...args) {
		const result = await calculate_taxes_and_totals(...args);
		update_dpp_nilai_lain(frm);
		return result;
	};

	frm.__dpp_nilai_lain_watched = true;
}

DPP_NILAI_LAIN_DOCTYPES.forEach((doctype) => {
	frappe.ui.form.on(doctype, {
		onload: watch_totals,
		refresh(frm) {
			watch_totals(frm);
			update_dpp_nilai_lain(frm);
		},
	});
});
