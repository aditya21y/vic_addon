"""Angka notifikasi belum dibaca + notifikasi terbaru, buat badge lonceng di sidebar.

Dipanggil `public/js/notification_badge.js` waktu halaman kebuka, tiap ada event realtime
`notification` (dikirim Notification Log waktu dibikin), dan tiap 60 detik sebagai cadangan kalau
koneksi socket-nya putus.
"""

import frappe


@frappe.whitelist()
def get_unread_notifications():
	user = frappe.session.user
	if user == "Guest":
		return {"count": 0, "latest": None}

	filters = {"for_user": user, "read": 0}
	latest = frappe.get_all(
		"Notification Log",
		filters=filters,
		fields=["name", "subject", "from_user", "document_type", "document_name", "link", "type", "creation"],
		order_by="creation desc",
		limit=1,
	)

	return {
		"count": frappe.db.count("Notification Log", filters),
		"latest": latest[0] if latest else None,
	}
