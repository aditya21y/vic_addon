// Badge angka notifikasi belum dibaca di lonceng sidebar + pop-up pojok kanan bawah (pakai suara).
//
// Notifikasi baru (di-tag, di-assign, dll) dikirim Frappe lewat event realtime "notification"
// waktu Notification Log-nya dibikin. Bawaannya event itu cuma nyalain titik di lonceng; di sini
// ditambah angka, pop-up, dan suara. Polling tiap 60 detik jadi cadangan kalau socket-nya putus -
// client socket.io bawaan cuma nyoba nyambung ulang 3x, abis itu nyerah sampai halaman di-refresh,
// jadi batas itu juga dicabut. Angka & isi notifikasinya dari vic_addon/vic/notifications.py.

frappe.provide("vic.notifications");

vic.notifications = {
	POLL_INTERVAL: 60 * 1000,
	count: 0,
	last_seen: null,

	init() {
		if (this.started || frappe.session.user === "Guest") return;
		this.started = true;

		this.add_style();
		this.keep_socket_alive();

		this.refresh({ silent: true });
		frappe.realtime.on("notification", () => this.refresh());
		setInterval(() => this.refresh(), this.POLL_INTERVAL);

		// baca notifikasi / "mark all as read" di dropdown bawaan -> angkanya diitung ulang
		$(document).on("click", ".notifications-list", () => setTimeout(() => this.refresh({ silent: true }), 1000));
		frappe.realtime.on("indicator_hide", () => this.refresh({ silent: true }));
	},

	refresh({ silent = false } = {}) {
		return frappe
			.xcall("vic_addon.vic.notifications.get_unread_notifications", {}, "GET")
			.then(({ count, latest }) => {
				const is_new = latest && this.last_seen !== null && latest.name !== this.last_seen;
				this.count = count;
				this.last_seen = latest ? latest.name : this.last_seen || "";
				this.render_badge();

				if (is_new && !silent) this.show_popup(latest);
			})
			.catch(() => {});
	},

	render_badge() {
		const icon = $(".sidebar-notification .sidebar-item-icon");
		if (!icon.length) return;

		let badge = icon.find(".vic-notification-badge");
		if (!badge.length) {
			badge = $(`<span class="vic-notification-badge"></span>`).appendTo(icon);
		}

		badge.text(this.count > 99 ? "99+" : this.count).toggle(this.count > 0);
		$(".sidebar-notification").attr(
			"title",
			this.count ? __("Notification ({0} unread)", [this.count]) : __("Notification")
		);
	},

	show_popup(notification) {
		frappe.utils.play_sound("alert");

		const text = this.plain_text(notification.subject) || __("New notification");
		const link =
			notification.link ||
			(notification.document_type && notification.document_name
				? frappe.utils.get_form_link(notification.document_type, notification.document_name)
				: "/desk/List/Notification Log");
		const avatar = notification.from_user ? frappe.avatar(notification.from_user, "avatar-medium") : "";

		const container = this.get_container();
		// <a href> biasa, sama kayak item dropdown notifikasi bawaan - router desk yang nangkep kliknya
		const popup = $(`
			<a class="vic-notification-popup" role="alert" href="${frappe.utils.escape_html(link)}">
				<div class="vic-notification-avatar">${avatar}</div>
				<div class="vic-notification-body">
					<div class="vic-notification-title">${__("New notification")}</div>
					<div class="vic-notification-text">${frappe.utils.escape_html(text)}</div>
				</div>
				<button class="vic-notification-close" aria-label="${__("Close")}">&times;</button>
			</a>
		`).appendTo(container);

		popup.on("click", (e) => {
			if ($(e.target).closest(".vic-notification-close").length) {
				e.preventDefault();
				e.stopPropagation();
			}
			popup.remove();
		});

		setTimeout(() => popup.fadeOut(300, () => popup.remove()), 8000);
	},

	get_container() {
		let container = $(".vic-notification-stack");
		if (!container.length) {
			container = $(`<div class="vic-notification-stack"></div>`).appendTo("body");
		}
		return container;
	},

	// subject Notification Log isinya HTML (bisa memuat teks dari user) - diambil teksnya aja.
	// DOMParser gak ngejalanin script/handler apa pun, beda sama $(...).html().
	plain_text(html) {
		if (!html) return "";
		const doc = new DOMParser().parseFromString(html, "text/html");
		return (doc.body.textContent || "").replace(/\s+/g, " ").trim();
	},

	keep_socket_alive() {
		const manager = frappe.realtime && frappe.realtime.socket && frappe.realtime.socket.io;
		if (manager && manager.reconnectionAttempts) {
			manager.reconnectionAttempts(Infinity);
		}
	},

	add_style() {
		if ($("#vic-notification-style").length) return;
		$(`<style id="vic-notification-style">
			.sidebar-notification .sidebar-item-icon { position: relative; }
			.vic-notification-badge {
				position: absolute; top: -6px; right: -8px; min-width: 16px; height: 16px;
				padding: 0 4px; border-radius: 8px; background: var(--red-500, #e03636); color: #fff;
				font-size: 10px; font-weight: 600; line-height: 16px; text-align: center;
				pointer-events: none;
			}
			.vic-notification-stack {
				position: fixed; right: 20px; bottom: 20px; z-index: 1060;
				display: flex; flex-direction: column; gap: 8px; max-width: 360px;
			}
			.vic-notification-popup {
				display: flex; align-items: flex-start; gap: 10px; padding: 12px 14px;
				background: var(--card-bg, #fff); color: var(--text-color, #1f272e);
				border: 1px solid var(--border-color, #e2e6e9); border-radius: 10px;
				box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15); cursor: pointer; text-decoration: none !important;
				animation: vic-notification-in 0.25s ease-out;
			}
			.vic-notification-body { flex: 1; min-width: 0; }
			.vic-notification-title { font-weight: 600; font-size: 13px; margin-bottom: 2px; }
			.vic-notification-text {
				font-size: 12px; color: var(--text-muted, #687178);
				display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
			}
			.vic-notification-close {
				border: 0; background: none; font-size: 18px; line-height: 1; color: var(--text-muted, #687178);
				padding: 0 2px; cursor: pointer;
			}
			@keyframes vic-notification-in { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
		</style>`).appendTo("head");
	},
};

// sidebar (dan tombol Notification-nya) dibikin setelah desk siap - ditunggu sampai elemennya ada
$(document).on("startup", () => {
	const wait = setInterval(() => {
		if ($(".sidebar-notification").length) {
			clearInterval(wait);
			vic.notifications.init();
		}
	}, 500);
	setTimeout(() => {
		clearInterval(wait);
		vic.notifications.init();
	}, 15000);
});
