import frappe
def run():
    doc = frappe.get_doc("Voice Meeting", "MEETING-0641")
    print(doc.raw_results)
