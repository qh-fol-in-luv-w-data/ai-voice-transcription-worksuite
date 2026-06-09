frappe.db.sql("DELETE FROM `tabVoice Speaker` WHERE name = 'null'")
frappe.db.commit()
