// Payment Entry: isi tabel "Deductions or Loss" -> Paid/Received Amount dihitung ulang otomatis,
// Allocated Amount tetap sebesar Outstanding.
//
// Bawaannya user mesti ngitung sendiri berapa yang dibayar biar Difference Amount nol. Dan kalau
// Paid Amount-nya diubah, ERPNext ngalokasiin ulang (`allocate_amount_to_references`) - dengan
// setelan default, semua Allocated Amount malah di-nol-in. Di sini angkanya dipasang langsung ke
// dokumen (tanpa nyalain trigger paid_amount / received_amount), jadi alokasinya gak kesentuh.
//
// Rumusnya ngikut validasi server (`PaymentEntry.set_difference_amount`), yang nentuin Difference
// Amount harus nol waktu submit. Baris potongan selalu didebit:
//
//   Receive:  Received = Allocated + pajak termasuk - Total Deduction
//   Pay:      Paid     = Allocated + pajak termasuk + Total Deduction
//
// Cuma jalan kalau akun asal & tujuannya satu mata uang - multi currency dibiarin kayak bawaan.

frappe.ui.form.on("Payment Entry Deduction", {
	amount(frm) {
		recalculate_paid_amount_from_deductions(frm);
	},
	deductions_remove(frm) {
		recalculate_paid_amount_from_deductions(frm);
	},
});

function recalculate_paid_amount_from_deductions(frm) {
	const doc = frm.doc;
	if (doc.docstatus !== 0 || !["Receive", "Pay"].includes(doc.payment_type)) return;
	if (!(doc.references || []).length) return;
	if (doc.paid_from_account_currency !== doc.paid_to_account_currency) return;

	// Allocated Amount tetap sebesar Outstanding (yang sempat ke-nol-in diisi lagi)
	(doc.references || []).forEach((row) => {
		if (!flt(row.allocated_amount) && flt(row.outstanding_amount)) {
			row.allocated_amount = flt(row.outstanding_amount);
		}
	});
	frm.refresh_field("references");

	const rate = flt(doc.payment_type === "Receive" ? doc.source_exchange_rate : doc.target_exchange_rate) || 1;
	const base_allocated = (doc.references || []).reduce(
		(sum, row) => sum + flt(flt(row.allocated_amount) * rate, precision("base_paid_amount")),
		0
	);
	const deductions = (doc.deductions || []).reduce((sum, row) => sum + flt(row.amount), 0);
	const included_taxes = (doc.taxes || []).reduce((sum, row) => {
		if (!row.included_in_paid_amount) return sum;
		return sum + (row.add_deduct_tax === "Deduct" ? -1 : 1) * flt(row.base_tax_amount);
	}, 0);

	const base_amount = flt(
		doc.payment_type === "Receive"
			? base_allocated + included_taxes - deductions
			: base_allocated + included_taxes + deductions,
		precision("base_paid_amount")
	);
	if (base_amount < 0) return;

	// satu mata uang: paid & received selalu sama nilainya
	const amount = flt(base_amount / rate, precision("paid_amount"));
	doc.paid_amount = amount;
	doc.received_amount = amount;
	doc.base_paid_amount = base_amount;
	doc.base_received_amount = base_amount;
	frm.refresh_fields(["paid_amount", "received_amount", "base_paid_amount", "base_received_amount"]);
	frm.dirty();

	frm.events.set_total_allocated_amount(frm);
}
