# Copyright (c) 2026, aditya and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class SerialNumberSettings(Document):
	def validate(self):
		self.validate_naming_series()

	def validate_naming_series(self):
		"""Seri nomornya harus punya bagian nomor urut, biar Serial No-nya gak kembar."""
		if not self.auto_create_serial_no:
			return

		if "#" not in (self.serial_no_naming_series or ""):
			frappe.throw(
				_("Serial No Naming Series must contain at least one {0} as the running number.").format(
					frappe.bold("#")
				),
				title=_("Running Number Missing"),
			)

		from vic_addon.vic.serial_no import get_unknown_placeholders

		unknown = get_unknown_placeholders(self.serial_no_naming_series)
		if unknown:
			frappe.throw(
				_("Unknown variable in Serial No Naming Series: {0}").format(
					frappe.bold(", ".join(sorted(unknown)))
				),
				title=_("Invalid Naming Series"),
			)
