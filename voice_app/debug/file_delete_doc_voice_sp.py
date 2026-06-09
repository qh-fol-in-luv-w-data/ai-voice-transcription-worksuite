import frappe

try:
    # Xóa bản ghi bằng SQL thô để vượt qua các validation của Frappe (tránh lỗi 'cannot be a list' khi Frappe gọi doc.delete())
    rows_deleted = frappe.db.sql("DELETE FROM `tabVoice Speaker` WHERE name = 'null'")
    frappe.db.commit()
    print("✅ Đã xóa thành công bản ghi Voice Speaker có ID là 'null' bằng lệnh SQL trực tiếp.")
except Exception as e:
    frappe.db.rollback()
    print(f"❌ Có lỗi xảy ra khi xóa: {e}")
