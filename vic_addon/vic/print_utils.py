"""Helper Jinja buat print format VIC."""

from frappe.utils import strip_html


def get_item_description(item):
	"""Isi kolom Description di tabel item: description dulu, kalau kosong baru item name.

	Description itu Text Editor (HTML), jadi dicetak apa adanya - format tebal/baris barunya ikut.
	Editor sering nyimpen tag kosong (`<p></p>`, `<br>`) waktu isinya dihapus; yang kayak gitu
	dianggap kosong. Doctype yang barisnya gak punya description (mis. Costing Item) langsung jatuh
	ke item name.
	"""
	description = item.get("description") or ""
	if strip_html(description).replace("&nbsp;", " ").strip():
		return description

	return item.get("item_name") or item.get("item_code") or ""
