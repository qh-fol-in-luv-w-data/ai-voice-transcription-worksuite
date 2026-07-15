import frappe

def run():
    frappe.flags.ignore_permissions = True
    if frappe.db.exists("DocType", "Voice Meeting Chunk"):
        print("DocType Voice Meeting Chunk already exists.")
        return

    doc = frappe.get_doc({
        "doctype": "DocType",
        "name": "Voice Meeting Chunk",
        "module": "Voice App",
        "custom": 0,
        "autoname": "format:CHUNK-{####}",
        "fields": [
            {"fieldname": "meeting", "fieldtype": "Link", "options": "Voice Meeting", "label": "Meeting", "reqd": 1, "in_list_view": 1},
            {"fieldname": "chunk_index", "fieldtype": "Int", "label": "Chunk Index", "reqd": 1, "in_list_view": 1},
            {"fieldname": "status", "fieldtype": "Select", "options": "Pending\nProcessing\nCompleted\nError", "default": "Pending", "label": "Status", "in_list_view": 1},
            {"fieldname": "offset_sec", "fieldtype": "Float", "label": "Offset (Seconds)"},
            {"fieldname": "audio_file_path", "fieldtype": "Data", "label": "Audio File Path"},
            {"fieldname": "raw_segments", "fieldtype": "Code", "options": "JSON", "label": "Raw Segments"},
            {"fieldname": "error_message", "fieldtype": "Small Text", "label": "Error Message"},
            {"fieldname": "tokens_used", "fieldtype": "Float", "label": "Tokens Used"}
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1}
        ],
        "track_changes": 1
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    print("Successfully created Voice Meeting Chunk DocType")
