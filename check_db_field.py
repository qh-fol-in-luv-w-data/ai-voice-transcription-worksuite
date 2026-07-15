import frappe

def check():
    frappe.init(site="devapp.ctpai.vn")
    frappe.connect()
    try:
        # Lấy cuộc họp mới nhất
        meeting = frappe.db.get_value("Voice Meeting", {"status": "Completed"}, ["name", "original_raw_results"], order_by="creation desc", as_dict=True)
        if meeting and meeting.original_raw_results:
            print(f"Meeting Name: {meeting.name}")
            print(f"Length of original_raw_results: {len(meeting.original_raw_results)} characters")
            print(f"Snippet: {meeting.original_raw_results[:200]}...")
        else:
            print("No completed meeting found with original_raw_results.")
    finally:
        frappe.destroy()

if __name__ == "__main__":
    check()
