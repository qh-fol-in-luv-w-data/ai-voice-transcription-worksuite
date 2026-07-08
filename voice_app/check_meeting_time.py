import frappe
def run():
    doc = frappe.get_doc("Voice Meeting", "MEETING-0641")
    print(f"Meeting: {doc.name}")
    print(f"Created at: {doc.creation}")
    print(f"Modified at: {doc.modified}")
