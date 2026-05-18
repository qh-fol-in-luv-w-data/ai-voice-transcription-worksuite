import frappe
import json
import os

def run():
    db_path = "/Users/_qh.fol_/frappe-bench/apps/voice_app/voice_app/speaker_db.json"
    if not os.path.exists(db_path):
        print("No speaker_db.json found.")
        return
        
    with open(db_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    for name, info in data.items():
        if frappe.db.exists("Voice Speaker", name):
            print(f"Speaker {name} already exists.")
            continue
            
        doc = frappe.new_doc("Voice Speaker")
        doc.speaker_name = name
        
        if isinstance(info, list):
            doc.embedding = json.dumps(info)
            doc.email = "Chưa cập nhật"
        else:
            doc.embedding = json.dumps(info.get("embedding", []))
            doc.email = info.get("email", "Chưa cập nhật")
            
        doc.insert(ignore_permissions=True)
        print(f"Migrated speaker: {name}")
        
    frappe.db.commit()
    print("Migration complete.")
