// Delivered To (isian kotak di print format Delivery Order) keisi otomatis tiap Shipping Address
// dipilih, terus bebas diedit - sama kayak Delivered To di Purchase Order. Yang didengerin field
// alamat lengkapnya (`shipping_address`), bukan link-nya: ganti customer ngisi alamatnya langsung
// tanpa lewat event `shipping_address_name`.
//
// Aturannya ngikut print format: alamat kirim cuma dipakai kalau beda dari alamat customer. Kalau
// sama, field-nya dikosongin biar kotaknya jatuh ke nama project / customer.
frappe.ui.form.on("Delivery Note", {
	shipping_address(frm) {
		const differs =
			frm.doc.shipping_address_name && frm.doc.shipping_address_name !== frm.doc.customer_address;

		frm.set_value("custom_delivered_to", differs ? address_to_text(frm.doc.shipping_address) : "");
	},
});

// Alamat lengkap itu HTML (`Jl. ...<br>Jakarta<br>`) - field-nya Small Text, jadi tiap <br>
// dijadiin baris baru dan tag lainnya dibuang. Sama kayak di purchase_order.js.
function address_to_text(html) {
	const text = frappe.utils.html2text((html || "").replace(/<br\s*\/?>/gi, "\n"));
	return text
		.split("\n")
		.map((line) => line.trim())
		.filter(Boolean)
		.join("\n");
}
