import os
import frappe
from unittest.mock import patch, MagicMock
from voice_app.voice_app.api import voice_to_task
import json

def test_auto_assignee():
    # Giả lập user hiện tại
    frappe.session = MagicMock()
    frappe.session.user = "test_user@ctmcorp.com.vn"
    # Giả lập requests.Session để mock API trả về Projects và Employees
    mock_session = MagicMock()
    
    def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "Project" in url:
            resp.json.return_value = {"data": [{"name": "PROJ-001", "project_name": "Dự án Alpha"}]}
        elif "Employee" in url:
            resp.json.return_value = {
                "data": [
                    {
                        "name": "HR-EMP-001", 
                        "employee_name": "Nguyen Van Test", 
                        "user_id": "test_user@ctmcorp.com.vn",
                        "designation": "Software Engineer"
                    },
                    {
                        "name": "HR-EMP-002", 
                        "employee_name": "Tran Thi B", 
                        "user_id": "user_b@ctmcorp.com.vn",
                        "designation": "Manager"
                    }
                ]
            }
        return resp

    mock_session.get = mock_get

    with patch("voice_app.api.requests.Session", return_value=mock_session), \
         patch("voice_app.api.frappe.request", MagicMock(files={"audio": "dummy"})):

        # Mock voice extraction
        with patch("voice_app.api.OpenAI") as MockOpenAI:
            mock_openai_instance = MagicMock()
            MockOpenAI.return_value = mock_openai_instance
            
            # 1. Mock text extraction
            mock_audio_response = MagicMock()
            mock_audio_response.text = "Tạo task viết unit test cho dự án Alpha hạn chót là thứ sáu tuần này."
            mock_openai_instance.audio.transcriptions.create.return_value = mock_audio_response
            
            # 2. Mock chat completion
            mock_chat_response = MagicMock()
            mock_chat_response.choices[0].message.content = json.dumps({
                "task_name": "Viết unit test",
                "project_id": "PROJ-001",
                "project_name": "Dự án Alpha",
                "assignee_display": "Nguyen Van Test (HR-EMP-001)", # Mong đợi AI tự gán vì đây là người nói
                "start_date": "2024-05-20",
                "end_date": "2024-05-24",
                "description": "",
                "missing_fields": [],
                "clarification_question": None
            })
            mock_openai_instance.chat.completions.create.return_value = mock_chat_response

            # Chạy hàm
            print("Đang gửi yêu cầu với giả định không nhắc tên ai thực hiện...")
            res = voice_to_task()
            print("\nKết quả JSON trả về từ voice_to_task:")
            print(json.dumps(res, indent=2, ensure_ascii=False))

            # In thử prompt được tạo để xem user có được truyền vào không
            call_args = mock_openai_instance.chat.completions.create.call_args[1]
            prompt_sent = call_args['messages'][0]['content']
            print("\n--- TRÍCH XUẤT PROMPT GỬI ĐI ---")
            for line in prompt_sent.split('\n'):
                if "Thông tin Người đang tạo Task" in line or "Tên:" in line or "Email/ID:" in line or "Chức vụ:" in line or "LƯU Ý QUAN TRỌNG" in line:
                    print(line)

if __name__ == "__main__":
    test_auto_assignee()
