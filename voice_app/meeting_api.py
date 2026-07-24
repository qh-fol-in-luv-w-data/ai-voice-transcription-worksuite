import frappe

def _can_access_meeting(meeting_owner):
    if frappe.session.user == meeting_owner:
        return True
    return "System Manager" in frappe.get_roles()

@frappe.whitelist(allow_guest=False)
def rename_meeting(meeting_name, new_title):
    if not meeting_name or not new_title:
        frappe.throw("Thiếu thông tin cuộc họp hoặc tên mới")
    
    meeting = frappe.get_doc("Voice Meeting", meeting_name)
    if meeting:
        if not _can_access_meeting(meeting.owner):
            frappe.throw("Không có quyền đổi tên cuộc họp này", frappe.PermissionError)
        meeting.title = new_title
        meeting.save()
        frappe.db.commit()
        return {"status": "success", "message": "Đã đổi tên thành công"}
    return {"status": "error", "message": "Không tìm thấy cuộc họp"}
