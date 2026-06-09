import frappe

def execute():
    try:
        frappe.db.sql("DELETE FROM `tabVoice Speaker` WHERE name = 'null'")
        frappe.db.commit()
        print("✅ Đã xóa thành công bản ghi Voice Speaker có ID là 'null' bằng SQL trực tiếp.")
    except Exception as e:
        print(f"❌ Có lỗi xảy ra: {e}")

if __name__ == "__main__":
    execute()
