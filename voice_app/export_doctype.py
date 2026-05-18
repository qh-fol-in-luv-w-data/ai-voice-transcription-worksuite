import frappe

def run():
    doc = frappe.get_doc("DocType", "Voice Speaker")
    doc.custom = 0
    doc.save()
    frappe.db.commit()
    print("Converted Voice Speaker to standard DocType and exported to files.")
