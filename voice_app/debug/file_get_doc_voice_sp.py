import frappe
import json

try:
    # Truy vấn trực tiếp từ database để tránh các lỗi validation của Frappe Document
    data = frappe.db.sql("SELECT * FROM `tabVoice Speaker` WHERE name = 'null'", as_dict=True)
    
    if not data:
        print("Không tìm thấy dữ liệu Voice Speaker nào có ID là 'null'")
    else:
        doc_data = data[0]
        
        # Rút gọn các chuỗi quá lớn (ví dụ: file âm thanh base64, embedding vector...)
        for key, value in doc_data.items():
            if isinstance(value, str) and len(value) > 1000:
                doc_data[key] = f"<Chuỗi quá dài, độ dài: {len(value)} ký tự. Đã được rút gọn>"

        # Xuất ra file JSON
        output_file = 'voice_speaker_null_raw.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(doc_data, f, ensure_ascii=False, indent=4, default=str)
            
        print(f"✅ Đã xuất dữ liệu raw thành công ra file: {output_file}")

except Exception as e:
    print(f"❌ Có lỗi xảy ra: {e}")
