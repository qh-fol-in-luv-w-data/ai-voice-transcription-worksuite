import frappe

def execute():
    doctype_name = "Voice App Settings"
    if not frappe.db.exists("DocType", doctype_name):
        doc = frappe.get_doc({
            "doctype": "DocType",
            "name": doctype_name,
            "module": "Voice App",
            "custom": 0,
            "issingle": 1,
            "fields": [
                {
                    "fieldname": "whisper_url",
                    "fieldtype": "Data",
                    "label": "Whisper URL",
                    "default": "http://localhost:8080/inference"
                },
                {
                    "fieldname": "hf_token",
                    "fieldtype": "Password",
                    "label": "HuggingFace Token"
                },
                {
                    "fieldname": "elevenlabs_api_key",
                    "fieldtype": "Password",
                    "label": "ElevenLabs API Key"
                }
            ],
            "permissions": [
                {
                    "role": "System Manager",
                    "read": 1,
                    "write": 1
                }
            ]
        })
        doc.insert(ignore_permissions=True)
        print(f"Created DocType: {doctype_name}")
    else:
        print(f"DocType {doctype_name} already exists.")
