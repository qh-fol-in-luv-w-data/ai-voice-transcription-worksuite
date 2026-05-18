import frappe

def run():
    errors = frappe.get_all("Error Log", fields=["method", "error", "creation"], limit=3, order_by="creation desc")
    for e in errors:
        print(f"[{e.creation}] {e.method}")
        print(e.error[:500])
        print("-" * 50)
