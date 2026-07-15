import frappe

@frappe.whitelist(allow_guest=True)
def rename_meeting(meeting_name, new_title):
    if not meeting_name or not new_title:
        frappe.throw("Thiếu thông tin cuộc họp hoặc tên mới")
    
    meeting = frappe.get_doc("Voice Meeting", meeting_name)
    if meeting:
        meeting.title = new_title
        meeting.save(ignore_permissions=True)
        frappe.db.commit()
        return {"status": "success", "message": "Đã đổi tên thành công"}
    return {"status": "error", "message": "Không tìm thấy cuộc họp"}
