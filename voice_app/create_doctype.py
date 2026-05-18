import frappe

def run():
    doctype_name = "Voice Speaker"
    
    if not frappe.db.exists("DocType", doctype_name):
        doc = frappe.new_doc("DocType")
        doc.name = doctype_name
        doc.module = "Voice App"
        doc.custom = 1
        doc.autoname = "field:speaker_name"
        for f in [
            {"fieldname": "speaker_name", "fieldtype": "Data", "label": "Tên Người Nói", "reqd": 1, "unique": 1},
            {"fieldname": "email", "fieldtype": "Data", "label": "Email"},
            {"fieldname": "embedding", "fieldtype": "JSON", "label": "Đặc trưng giọng nói (Embedding)"}
        ]:
            doc.append("fields", f)
            
        doc.append("permissions", {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1})

        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        print(f"Created DocType: {doctype_name}")
    else:
        print(f"DocType {doctype_name} already exists.")
