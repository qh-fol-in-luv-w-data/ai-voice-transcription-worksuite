import frappe

def run():
    # 1. Delete old Voice Speaker
    speaker_name = "Hồ Đắc Quân"
    if frappe.db.exists("Voice Speaker", speaker_name):
        frappe.delete_doc("Voice Speaker", speaker_name, ignore_permissions=True)
        print(f"✅ Đã xoá Voice Speaker: {speaker_name}")
    else:
        print(f"ℹ️ Không tìm thấy Voice Speaker: {speaker_name}")
        
    # 2. Create Frappe User
    email = "quan.ho.e@ctmcorp.com.vn"
    if not frappe.db.exists("User", email):
        user = frappe.new_doc("User")
        user.email = email
        user.first_name = "Quân"
        user.last_name = "Hồ Đắc"
        user.send_welcome_email = 0
        user.insert(ignore_permissions=True)
        
        # Set password
        from frappe.utils.password import update_password
        update_password(email, "123456")
        
        # Add roles (System Manager to ensure access to APIs)
        user.add_roles("System Manager", "All")
        print(f"✅ Đã tạo User: {email} (Mật khẩu: 123456)")
    else:
        print(f"ℹ️ User đã tồn tại: {email}")
        from frappe.utils.password import update_password
        update_password(email, "123456")
        print(f"✅ Đã reset mật khẩu về: 123456")
        
    frappe.db.commit()
