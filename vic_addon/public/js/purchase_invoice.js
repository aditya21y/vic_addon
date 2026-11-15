// PPN Tertunda: faktur pajak belum diterima, PPN-nya dicatat dulu di PPN Masukan Tertunda. Begitu
// fakturnya dateng, tombol ini bikin draft Journal Entry reklas ke PPN Masukan.
// Lihat vic_addon/vic/ppn_tertunda.py.

frappe.ui.form.on("Purchase Invoice", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || !frm.doc.custom_ppn_tertunda) return;

		frm.add_custom_button(__("Reklas PPN Tertunda"), () => make_ppn_reclass_entry(frm), __("Create"));
	},

	// Centang PPN Tertunda -> akun baris PPN pindah dari PPN Masukan ke PPN Masukan Tertunda (akun
	// COA Company), dilepas -> balik lagi. Server ngulang swap-nya waktu simpan (set_ppn_tertunda_account),
	// ini cuma biar langsung kelihatan di form.
	custom_ppn_tertunda(frm) {
		if (!frm.doc.company) return;

		frappe.db
			.get_value("Company", frm.doc.company, [
				"custom_ppn_masukan_account",
				"custom_ppn_masukan_tertunda_account",
			])
			.then(({ message }) => {
				const vat = message && message.custom_ppn_masukan_account;
				const deferred = message && message.custom_ppn_masukan_tertunda_account;
				if (!vat || !deferred) {
					frappe.show_alert({
						message: __("Set COA PPN Masukan & PPN Masukan Tertunda di Company dulu."),
						indicator: "orange",
					});
					return;
				}

				const [from, to] = frm.doc.custom_ppn_tertunda ? [vat, deferred] : [deferred, vat];
				let changed = false;
				(frm.doc.taxes || []).forEach((row) => {
					if (row.account_head === from) {
						row.account_head = to;
						changed = true;
					}
				});
				if (changed) frm.refresh_field("taxes");
			});
	},
});

function make_ppn_reclass_entry(frm) {
	frappe.call({
		method: "vic_addon.vic.ppn_tertunda.make_reclass_entry",
		args: { purchase_invoice: frm.doc.name },
		freeze: true,
		callback({ message }) {
			if (!message) return;

			// udah pernah dibikin: langsung dibuka, gak dibikin dobel
			frappe.show_alert({
				message: message.existing
					? __("Journal Entry {0} already exists for this invoice", [message.journal_entry])
					: __("Draft Journal Entry {0} created", [message.journal_entry]),
				indicator: message.existing ? "orange" : "green",
			});
			frappe.set_route("Form", "Journal Entry", message.journal_entry);
		},
	});
}
