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
        segments, full_text, err = call_elevenlabs_stt(wav, language)
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

        # Extract tasks
        items, hr_projects_map, errors, employees, usage = extract_tasks_only(docx_filename, model_type=model_type)

        if os.path.exists(docx_filename): os.remove(docx_filename)

        # Record Usage
        session_id = frappe.request.headers.get("X-App-Session-Id")
        if session_id and frappe.db.exists("VOICE Session", session_id):
            session_doc = frappe.get_doc("VOICE Session", session_id)
            session_doc.total_actions += 1
            session_doc.total_ai_calls += 1
            session_doc.total_tokens_used += usage.get("tokens_used", 0)
            session_doc.total_prompt_tokens += usage.get("prompt_tokens", 0)
            session_doc.total_completion_tokens += usage.get("completion_tokens", 0)
            session_doc.last_active_at = frappe.utils.now()
            session_doc.save(ignore_permissions=True)
            
            # Log AI Call
            ai_log = frappe.get_doc({
                "doctype": "VOICE AI Call Log",
                "voice_session": session_id,
                "action": "Extract Tasks",
                "ai_service": "OpenAI",
                "model_used": model_type,
                "tokens_used": usage.get("tokens_used", 0),
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
            })
            ai_log.insert(ignore_permissions=True)

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
            frappe.db.set_value("Voice Meeting", meeting_name, "minute_docx", docx_url)
            frappe.db.set_value("Voice Meeting", meeting_name, "task_xlsx", excel_url)
            frappe.db.set_value("Voice Meeting", meeting_name, "status", "Analyzed")

        frappe.db.commit()

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

    meeting_name = payload.get("meeting_name")

    if not results:
        return {"status": "error", "message": "Không có nội dung để lọc"}

    try:
        cleaned_results, err, usage = clean_transcript_llm(results, model_type)
        if err:
            return {"status": "error", "message": err}

        # Record Usage
        session_id = frappe.request.headers.get("X-App-Session-Id")
        if session_id and frappe.db.exists("VOICE Session", session_id):
            session_doc = frappe.get_doc("VOICE Session", session_id)
            session_doc.total_actions += 1
            session_doc.total_ai_calls += 1
            session_doc.total_tokens_used += usage.get("tokens_used", 0)
            session_doc.total_prompt_tokens += usage.get("prompt_tokens", 0)
            session_doc.total_completion_tokens += usage.get("completion_tokens", 0)
            session_doc.last_active_at = frappe.utils.now()
            session_doc.save(ignore_permissions=True)
            
            # Log AI Call
            ai_log = frappe.get_doc({
                "doctype": "VOICE AI Call Log",
                "voice_session": session_id,
                "action": "Clean Transcript",
                "ai_service": "OpenAI",
                "model_used": model_type,
                "tokens_used": usage.get("tokens_used", 0),
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
            })
            ai_log.insert(ignore_permissions=True)

        if meeting_name and frappe.db.exists("Voice Meeting", meeting_name):
            meeting = frappe.get_doc("Voice Meeting", meeting_name)
            
            # Save original results if not saved yet
            if not meeting.original_raw_results:
                meeting.original_raw_results = meeting.raw_results
                
            meeting.raw_results = json.dumps(cleaned_results, ensure_ascii=False)
            meeting.save(ignore_permissions=True)

        return {"status": "success", "cleaned_results": cleaned_results}
    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Transcript Clean Error")
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
    try:
        meetings = frappe.get_all(
            "Voice Meeting",
            fields=["name", "title", "date", "status", "audio_file", "minute_docx", "task_xlsx", "transcript"],
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

