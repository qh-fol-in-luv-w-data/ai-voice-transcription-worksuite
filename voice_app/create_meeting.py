import frappe

def execute():
    if not frappe.db.exists("DocType", "Voice Meeting"):
        doc = frappe.get_doc({
            "doctype": "DocType",
            "name": "Voice Meeting",
            "module": "Voice App",
            "custom": 0,
            "fields": [
                {"fieldname": "title", "label": "Title", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
                {"fieldname": "date", "label": "Date", "fieldtype": "Datetime", "in_list_view": 1},
                {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "Pending\nAnalyzed\nSynced", "default": "Pending", "in_list_view": 1},
                {"fieldname": "audio_file", "label": "Audio File", "fieldtype": "Attach"},
                {"fieldname": "transcript", "label": "Transcript", "fieldtype": "Text Editor"},
                {"fieldname": "raw_results", "label": "Raw AI Results (JSON)", "fieldtype": "Code", "options": "JSON"},
                {"fieldname": "minute_docx", "label": "Minute Docx", "fieldtype": "Attach"},
                {"fieldname": "task_xlsx", "label": "Task Excel", "fieldtype": "Attach"}
            ],
            "permissions": [{"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1}],
            "autoname": "format:MEETING-{####}"
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        print("Successfully created Voice Meeting DocType")
    else:
        print("Voice Meeting DocType already exists")
