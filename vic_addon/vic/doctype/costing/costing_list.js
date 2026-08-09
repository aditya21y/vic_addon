frappe.listview_settings["Costing"] = {
	add_fields: ["status"],

	get_indicator(doc) {
		return doc.status === "Quoted"
			? [__("Quoted"), "green", "status,=,Quoted"]
			: [__("Not Quoted"), "orange", "status,=,Not Quoted"];
	},
};
