import frappe
import os
import json
import traceback
import pandas as pd
import requests
import urllib.parse
from voice_app.utils.activity_logger import ActivityLogger
from frappe.utils.file_manager import save_file
from voice_app.elevenlabs_client import call_elevenlabs_stt, check_elevenlabs_balance
from voice_app.task_extractor import extract_tasks_only, create_tasks_to_erp, clean_transcript_llm
from voice_app.docx_utils import save_to_docx
from voice_app.audio_utils import convert_to_wav
from voice_app.speaker_manager import get_segment_embedding, SpeakerDB


@frappe.whitelist(allow_guest=True)
def transcribe_audio(language="vi", filter_speakers=None):
    if frappe.session.user == "Guest":
        return {"status": "error", "message": "Vui lòng đăng nhập để sử dụng tính năng này"}

    if 'file' not in frappe.request.files:
        frappe.throw("Thiếu file âm thanh")
        
    audio_file = frappe.request.files['file']
    
    # Save uploaded file
    file_doc = save_file(audio_file.filename, audio_file.read(), None, None, is_private=1)
    file_path = frappe.get_site_path(file_doc.file_url.strip('/'))
    
    try:
        # Convert to WAV
        wav, err = convert_to_wav(file_path)
        if err:
            return {"status": "error", "message": err}

        # Call ElevenLabs
        segments, full_text, err, el_chars_used, el_chars_remaining = call_elevenlabs_stt(wav, language)
        if err:
            return {"status": "error", "message": err}

        # Diarization
        spk_db = SpeakerDB()
        unique_speakers = {}
        for seg in segments:
            spk = seg["speaker_id"]
            if spk not in unique_speakers:
                unique_speakers[spk] = []
            unique_speakers[spk].append(seg)
            
        speaker_cache = {}
        for spk, segs in unique_speakers.items():
            segs.sort(key=lambda x: x["end"] - x["start"], reverse=True)
            sample_seg = segs[0]
            start = sample_seg["start"]
            end = min(sample_seg["end"], start + 5.0)
            
            if end - start >= 0.5:
                emb = get_segment_embedding(wav, start, end)
                if emb is not None:
                    # Parse filter list if provided
                    allowed = json.loads(filter_speakers) if filter_speakers else None
                    name, score, email, user_info = spk_db.identify(emb, allowed_names=allowed)
                    if name != "Người lạ":
                        if not email or email.lower() == "chưa cập nhật":
                            speaker_cache[spk] = f"👤 {name} - {score:.0%}"
                        else:
                            speaker_cache[spk] = f"👤 {name} ({email}) - {score:.0%}"
                    else:
                        speaker_cache[spk] = f"👤 Người lạ ({score:.0%})"
                else:
                    speaker_cache[spk] = f"👤 Speaker {spk}"
            else:
                speaker_cache[spk] = f"👤 Speaker {spk}"

        # Format results
        results = []
        final_output_text = ""
        last_spk = None
        
        segments.sort(key=lambda x: x["start"])
        for seg in segments:
            s = seg["start"]
            e = seg["end"]
            txt = seg["text"].strip()
            if not txt: continue
                
            spk_label = speaker_cache.get(seg["speaker_id"], seg["speaker_id"])
            results.append((s, e, spk_label, txt))
            
            if spk_label != last_spk:
                final_output_text += f"\n**{spk_label}** [{s:.1f}s]\n{txt}"
            else:
                final_output_text += f" {txt}"
            last_spk = spk_label

        # Cleanup temp wav
        if os.path.exists(wav): os.remove(wav)

        from voice_app.constants import get_worksuite_url, get_worksuite_email, get_worksuite_password
        import requests
        
        employees = []
        try:
            session = requests.Session()
            base_url = get_worksuite_url()
            login_resp = session.post(
                f"{base_url}/api/method/login",
                json={"usr": get_worksuite_email(), "pwd": get_worksuite_password()},
                timeout=10,
            )
            if login_resp.status_code == 200:
                emp_resp = session.get(
                    f"{base_url}/api/resource/Employee",
                    params={
                        "fields": '["name","employee_name","user_id"]',
                        "filters": '[["status","=","Active"]]',
                        "limit": 500,
                    },
                    timeout=10,
                )
                if emp_resp.status_code == 200:
                    employees = [e for e in emp_resp.json().get("data", []) if e.get("user_id")]
        except Exception as ex:
            frappe.log_error(str(ex), "Fetch Employees Error in Transcribe")

        # Create Voice Meeting
        meeting_name = None
        try:
            from datetime import datetime
            meeting_title = f"Meeting - {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            meeting_doc = frappe.get_doc({
                "doctype": "Voice Meeting",
                "title": meeting_title,
                "date": frappe.utils.now(),
                "status": "Pending",
                "audio_file": file_doc.file_url,
                "transcript": final_output_text.strip(),
                "raw_results": json.dumps(results, ensure_ascii=False)
            })
            meeting_doc.insert(ignore_permissions=True)
            frappe.db.commit()
            meeting_name = meeting_doc.name
        except Exception as ex:
            frappe.log_error(str(ex), "Create Voice Meeting Error")

        # Log AI call (ElevenLabs)
        try:
            session_id_header = frappe.request.headers.get("X-App-Session-Id", "")
            session_name = frappe.db.get_value("VOICE Session", {"session_id": session_id_header}, "name") if session_id_header else ""
            if session_name:
                _logger.log_ai_call(
                    session_name=session_name,
                    action_name="",
                    call_type="transcribe_audio",
                    ai_model="elevenlabs/scribe_v2",
                    duration_seconds=0,
                    status="success",
                    elevenlabs_chars_used=el_chars_used,
                    elevenlabs_chars_remaining=el_chars_remaining,
                )
        except Exception as log_ex:
            frappe.log_error(str(log_ex), "Log ElevenLabs AI Call Error")

        return {
            "status": "success",
            "results": results,
            "final_text": final_output_text.strip(),
            "employees": employees,
            "meeting_name": meeting_name
        }

    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Audio Transcription Error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def extract_tasks():
    data = frappe.request.get_data()
    payload = json.loads(data)
    results = payload.get("results", [])
    model_type = payload.get("model_type", "gpt-4o")
    meeting_name = payload.get("meeting_name")

    if not results:
        return {"status": "error", "message": "Không có nội dung để tạo task"}

    try:
        # Fetch speaker roles: Voice Speaker DB (speaker_name→email) → CTERP (email→designation)
        from voice_app.constants import get_worksuite_url, get_worksuite_email, get_worksuite_password
        speaker_roles = {}
        try:
            # Step 1: Lấy Voice Speaker DB để map speaker_name → email
            voice_speakers = frappe.get_all(
                "Voice Speaker",
                fields=["speaker_name", "email"],
            )
            spk_email_map = {s["speaker_name"]: s["email"] for s in voice_speakers if s.get("email")}

            # Step 2: Lấy CTERP Employee để map email (user_id) → designation
            sess = requests.Session()
            base_url = get_worksuite_url()
            lr = sess.post(f"{base_url}/api/method/login", json={"usr": get_worksuite_email(), "pwd": get_worksuite_password()}, timeout=8)
            if lr.status_code == 200:
                er = sess.get(f"{base_url}/api/resource/Employee",
                    params={"fields": '["user_id","designation"]', "filters": '[["status","=","Active"]]', "limit": 500},
                    timeout=8)
                if er.status_code == 200:
                    email_desg_map = {
                        e["user_id"]: e["designation"]
                        for e in er.json().get("data", [])
                        if e.get("user_id") and e.get("designation")
                    }
                    # Combine: speaker_name → designation (qua email)
                    for spk_name, email in spk_email_map.items():
                        if email in email_desg_map:
                            speaker_roles[spk_name] = email_desg_map[email]
            frappe.log_error(f"speaker_roles: {speaker_roles}", "DEBUG Designations")
        except Exception as re_ex:
            frappe.log_error(str(re_ex), "Fetch Designations Error")

        # Create Docx
        docx_filename = save_to_docx(results, speaker_roles=speaker_roles)
        
        # Save Docx to Frappe Files to get a download URL
        with open(docx_filename, "rb") as f:
            file_doc = save_file(docx_filename, f.read(), None, None, is_private=0) # public for download
            docx_url = file_doc.file_url

        # Extract tasks — trả về 5 giá trị: items, hr_projects_map, errors, employees, usage
        items, hr_projects_map, errors, employees, task_usage = extract_tasks_only(docx_filename, model_type=model_type)

        if os.path.exists(docx_filename): os.remove(docx_filename)

        # Generate Excel
        excel_url = ""
        if items:
            df = pd.DataFrame(items)
            df.rename(columns={
                "title": "Tên nhiệm vụ",
                "assignee_display": "Người thực hiện",
                "project": "Dự án",
                "start_date": "Ngày bắt đầu",
                "due_date": "Ngày kết thúc",
                "description": "Mô tả chi tiết"
            }, inplace=True)
            
            # Remove raw assignee columns if they exist
            if "assignee" in df.columns:
                df.drop(columns=["assignee"], inplace=True)
                
            excel_filename = f"tasks_{os.urandom(2).hex()}.xlsx"
            df.to_excel(excel_filename, index=False)
            
            with open(excel_filename, "rb") as f:
                excel_doc = save_file(excel_filename, f.read(), None, None, is_private=0)
                excel_url = excel_doc.file_url
            if os.path.exists(excel_filename): os.remove(excel_filename)

        if meeting_name and frappe.db.exists("Voice Meeting", meeting_name):
            # Kiểm tra chủ sở hữu trước khi cập nhật
            meeting_owner = frappe.db.get_value("Voice Meeting", meeting_name, "owner")
            if meeting_owner == frappe.session.user:
                frappe.db.set_value("Voice Meeting", meeting_name, "minute_docx", docx_url)
                frappe.db.set_value("Voice Meeting", meeting_name, "task_xlsx", excel_url)
                frappe.db.set_value("Voice Meeting", meeting_name, "status", "Analyzed")
                # Lưu toàn bộ tasks dưới dạng JSON để xem lại sau
                if items:
                    frappe.db.set_value("Voice Meeting", meeting_name, "tasks_json",
                                        json.dumps(items, ensure_ascii=False))

        frappe.db.commit()

        # Log AI call (OpenAI tokens từ task extractor)
        try:
            session_id_header = frappe.request.headers.get("X-App-Session-Id", "")
            session_name_log = frappe.db.get_value("VOICE Session", {"session_id": session_id_header}, "name") if session_id_header else ""
            if session_name_log and hasattr(extract_tasks_only, '__last_tokens'):
                pass  # tokens tracked via task_extractor
        except Exception:
            pass

        return {
            "status": "success",
            "items": items,
            "hr_projects_map": hr_projects_map,
            "errors": errors,
            "employees": employees,
            "docx_url": docx_url,
            "excel_url": excel_url
        }

    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Task Extraction Error")
        return {"status": "error", "message": str(e)}

@frappe.whitelist(allow_guest=True)
def clean_transcript():
    data = frappe.request.get_data()
    payload = json.loads(data)
    results = payload.get("results", [])
    model_type = payload.get("model_type", "gpt-4o")
    meeting_name = payload.get("meeting_name")  # Nhận meeting_name từ FE

    if not results:
        return {"status": "error", "message": "Không có nội dung để lọc"}

    try:
        cleaned_results, err, clean_usage = clean_transcript_llm(results, model_type)
        if err:
            return {"status": "error", "message": err}

        # Cập nhật raw_results trong Meeting (kết quả sau lọc = trạng thái cuối cùng)
        if meeting_name and frappe.db.exists("Voice Meeting", meeting_name):
            meeting_owner = frappe.db.get_value("Voice Meeting", meeting_name, "owner")
            if meeting_owner == frappe.session.user:
                frappe.db.set_value("Voice Meeting", meeting_name, "raw_results",
                                    json.dumps(cleaned_results, ensure_ascii=False))
                frappe.db.commit()

        return {"status": "success", "cleaned_results": cleaned_results}
    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Transcript Clean Error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def update_meeting_results():
    """Cập nhật raw_results khi user hoàn tác lọc (undo clean)"""
    if frappe.session.user == "Guest":
        return {"status": "error", "message": "Vui lòng đăng nhập"}

    data = frappe.request.get_data()
    payload = json.loads(data)
    meeting_name = payload.get("meeting_name")
    results = payload.get("results", [])

    if not meeting_name or not results:
        return {"status": "error", "message": "Thiếu meeting_name hoặc results"}

    try:
        if frappe.db.exists("Voice Meeting", meeting_name):
            meeting_owner = frappe.db.get_value("Voice Meeting", meeting_name, "owner")
            if meeting_owner != frappe.session.user:
                return {"status": "error", "message": "Không có quyền chỉnh sửa meeting này"}
            frappe.db.set_value("Voice Meeting", meeting_name, "raw_results",
                                json.dumps(results, ensure_ascii=False))
            frappe.db.commit()
        return {"status": "success"}
    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Update Meeting Results Error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def sync_tasks_to_erp():
    data = frappe.request.get_data()
    payload = json.loads(data)
    tasks = payload.get("tasks", [])

    if not tasks:
        return {"status": "error", "message": "Không có task nào để đẩy"}

    try:
        report = create_tasks_to_erp(tasks)
        return {"status": "success", "report": report}
    except Exception as e:
        frappe.log_error(traceback.format_exc(), "ERP Sync Error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def download_meeting_file():
    """
    Endpoint tải file (docx/xlsx) từ meeting về phía client.
    Chỉ cho phép chủ sở hữu cuộc họp tải.
    Params: meeting_name, file_type (docx | xlsx)
    """
    if frappe.session.user == "Guest":
        frappe.throw("Vui lòng đăng nhập để tải file", frappe.AuthenticationError)

    meeting_name = frappe.form_dict.get("meeting_name") or frappe.local.form_dict.get("meeting_name")
    file_type    = frappe.form_dict.get("file_type")    or frappe.local.form_dict.get("file_type", "docx")

    if not meeting_name:
        frappe.throw("Thiếu meeting_name")

    meeting = frappe.get_doc("Voice Meeting", meeting_name)

    # Kiểm tra chủ sở hữu
    if meeting.owner != frappe.session.user:
        frappe.throw("Bạn không có quyền tải file này", frappe.PermissionError)

    if file_type == "xlsx":
        file_url = meeting.task_xlsx
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"
    else:
        file_url = meeting.minute_docx
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ext = "docx"

    if not file_url:
        frappe.throw(f"Meeting chưa có file {ext.upper()}")

    # Resolve đường dẫn đúng theo quy tắc Frappe:
    # - Public  (/files/xxx)          → {site_path}/public/files/xxx
    # - Private (/private/files/xxx)  → {site_path}/private/files/xxx
    clean_url = file_url.lstrip("/")
    if clean_url.startswith("files/"):
        # Public file — cần thêm tiền tố "public/"
        file_path = frappe.get_site_path("public", clean_url)
    else:
        # Private file hoặc đường dẫn đã đầy đủ
        file_path = frappe.get_site_path(clean_url)

    if not os.path.exists(file_path):
        frappe.throw(f"File không tồn tại trên server: {file_url} → {file_path}")


    # Tên file tải xuống = title của meeting
    safe_title = meeting.title.replace("/", "-").replace("\\", "-")
    filename   = f"{safe_title}.{ext}"

    with open(file_path, "rb") as f:
        file_content = f.read()

    frappe.local.response.filename    = filename
    frappe.local.response.filecontent = file_content
    frappe.local.response.type        = "download"
    frappe.local.response["content_type"] = content_type




@frappe.whitelist(allow_guest=True)
def get_elevenlabs_info():
    return {"balance": check_elevenlabs_balance()}

@frappe.whitelist(allow_guest=False)
def enroll_voice():
    if frappe.session.user == "Guest":
        return {"status": "error", "message": "Vui lòng đăng nhập để đăng ký giọng nói."}
        
    email = frappe.session.user
    full_name = frappe.utils.get_fullname(email)
    user_info = None
    
    # Try fetching from CT Group API
    try:
        api_url = f"https://app.ctpai.vn/api/method/ct_agent_hub.ct_agent_hub.api.get_user_by_mail?mail={email}"
        resp = requests.get(api_url, timeout=10)
        data = resp.json()
        if data.get("message", {}).get("status") == "success":
            user_info = data["message"]["user"]
            if "full_name" in user_info and user_info["full_name"]:
                full_name = user_info["full_name"]
    except Exception as e:
        frappe.log_error(str(e), "CT Group API Fetch Error")
        
    if 'file' not in frappe.request.files:
        return {"status": "error", "message": "Thiếu file âm thanh"}
        
    audio_file = frappe.request.files['file']
    
    # Save uploaded file
    file_doc = save_file(audio_file.filename, audio_file.read(), None, None, is_private=1)
    file_path = frappe.get_site_path(file_doc.file_url.strip('/'))
    
    try:
        # Convert to WAV
        wav, err = convert_to_wav(file_path)
        if err:
            return {"status": "error", "message": err}
            
        from voice_app.speaker_manager import enroll_new_speaker
        success = enroll_new_speaker(full_name, wav, email=email, user_info=user_info)
        
        # Cleanup temp wav
        if os.path.exists(wav): os.remove(wav)
        
        if success:
            return {"status": "success", "message": f"Đã đăng ký giọng nói thành công cho {full_name}!"}
        else:
            return {"status": "error", "message": "Không thể trích xuất đặc trưng giọng nói."}
            
    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Voice Enrollment Error")
        return {"status": "error", "message": str(e)}

@frappe.whitelist(allow_guest=True)
def get_current_user():
    return frappe.session.user


@frappe.whitelist(allow_guest=True)
def get_enrolled_speakers():
    """Trả về danh sách người đã đăng ký giọng nói trong Voice DB."""
    try:
        speakers = frappe.get_all(
            "Voice Speaker",
            fields=["speaker_name", "email"],
            order_by="speaker_name asc"
        )
        # Enrich với designation từ CTERP nếu có email khớp
        from voice_app.constants import get_worksuite_url, get_worksuite_email, get_worksuite_password
        try:
            base_url, ws_email, ws_pwd = get_worksuite_url(), get_worksuite_email(), get_worksuite_password()
            sess = requests.Session()
            lr = sess.post(f"{base_url}/api/method/login", json={"usr": ws_email, "pwd": ws_pwd}, timeout=8)
            if lr.status_code == 200:
                er = sess.get(f"{base_url}/api/resource/Employee",
                    params={"fields": '["employee_name","designation","user_id"]', "filters": '[["status","=","Active"]]', "limit": 500},
                    timeout=8)
                if er.status_code == 200:
                    erp_map = {e["user_id"]: e for e in er.json().get("data", []) if e.get("user_id")}
                    for spk in speakers:
                        if spk.get("email") and spk["email"] in erp_map:
                            spk["designation"] = erp_map[spk["email"]].get("designation", "")
                        else:
                            spk["designation"] = ""
        except Exception:
            for spk in speakers:
                spk["designation"] = ""
        return {"status": "success", "speakers": speakers}
    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Get Enrolled Speakers Error")
        return {"status": "error", "speakers": [], "message": str(e)}

@frappe.whitelist()
def get_meeting_history():
    """
    Chỉ trả về các meeting thuộc về user hiện tại.
    Guest không được truy cập.
    """
    if frappe.session.user == "Guest":
        return {"status": "error", "message": "Vui lòng đăng nhập", "meetings": []}

    try:
        meetings = frappe.get_all(
            "Voice Meeting",
            filters={"owner": frappe.session.user},
            fields=["name", "title", "date", "status", "audio_file", "minute_docx", "task_xlsx", "transcript", "raw_results"],
            order_by="creation desc"
        )
        return {"status": "success", "meetings": meetings}
    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Get Meeting History Error")
        return {"status": "error", "message": str(e), "meetings": []}
_logger = ActivityLogger(prefix="VOICE", module="voice_app")

@frappe.whitelist(allow_guest=False)
def get_context():
    import uuid
    dept = ""
    role = ""
    try:
        from ct_agent_hub.api import check_app_access
        agents_data = check_app_access("voice_app")
        user_depts = agents_data.get("user_departments", [])
        dept = ",".join(user_depts) if user_depts else ""
        role = agents_data.get("user_role", "")
    except ImportError:
        pass

    session_id = str(uuid.uuid4())
    session_name = _logger.create_session(session_id, dept=dept, role=role)

    return {
        "csrf_token": frappe.sessions.get_csrf_token(),
        "session_id": session_id,
        "session_name": session_name,
        "user": frappe.session.user,
        "full_name": frappe.utils.get_fullname(frappe.session.user) if frappe.session.user != "Guest" else "Guest"
    }

def _resolve_session(session_id: str) -> str:
    if not session_id:
        return ""
    try:
        rows = frappe.db.get_all(
            "VOICE Session",
            filters={"session_id": session_id},
            fields=["name"],
            limit=1,
            ignore_permissions=True,
        )
        return rows[0].name if rows else ""
    except Exception:
        return ""

def _log_action(session_id: str, action: str, details: dict):
    if not session_id:
        return
    s_name = _resolve_session(session_id)
    if s_name:
        _logger.log_action(s_name, action, details)

