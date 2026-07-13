import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field
frappe.init(site="ct-datalake.localhost")
frappe.connect()

create_custom_field("Voice Meeting", dict(fieldname="location", label="Location", fieldtype="Data", insert_after="date"))
create_custom_field("Voice Meeting", dict(fieldname="chairperson", label="Chairperson", fieldtype="Data", insert_after="location"))
frappe.db.commit()
print("Custom fields added.")
