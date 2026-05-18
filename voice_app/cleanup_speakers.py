import frappe

def run():
    to_delete = ["Quân", "An", "Chiến", "Tuấn - tester lỏ", "Em chiến", "a Tuấn", "a Long", "Ngochaiisme"]
    
    for name in to_delete:
        frappe.db.sql("DELETE FROM `tabVoice Speaker` WHERE name = %s", (name,))
        print(f"Deleted: '{name}'")
    
    frappe.db.commit()
    
    remaining = frappe.db.sql("SELECT name FROM `tabVoice Speaker`", as_dict=True)
    print(f"\nRemaining ({len(remaining)}):")
    for s in remaining:
        print(f"  - {s.name}")
