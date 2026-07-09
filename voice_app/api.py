import json
import frappe
import os
import traceback
import pandas as pd
import requests
import urllib.parse
from voice_app.utils.activity_logger import ActivityLogger
from frappe.utils.file_manager import save_file
from voice_app.elevenlabs_client import call_elevenlabs_stt, check_elevenlabs_balance
from voice_app.gemini_stt_client import call_gemini_stt
from voice_app.task_extractor import extract_tasks_only, create_tasks_to_erp
from voice_app.docx_utils import save_to_docx
from voice_app.audio_utils import convert_to_wav
from voice_app.speaker_manager import get_segment_embedding, SpeakerDB

_logger = ActivityLogger("VOICE", "voice_app")

@frappe.whitelist(allow_guest=False)
def transcribe_audio(language="vi", filter_speakers=None, stt_mode="google", num_speakers=None, custom_vocabulary=""):
    if 'file' not in frappe.request.files:
        frappe.throw("Thiếu file âm thanh")

    audio_file = frappe.request.files['file']
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": audio_file.filename,
        "is_private": 1,
        "content": audio_file.read()
    })
    file_doc.insert(ignore_permissions=True)
    
    file_path = frappe.get_site_path(file_doc.file_url.strip('/'))
    file_url = file_doc.file_url
    
    from datetime import datetime
    meeting_title = f"Meeting - {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    meeting_doc = frappe.get_doc({
        "doctype": "Voice Meeting",
        "title": meeting_title,
        "date": frappe.utils.now(),
        "status": "Processing",
        "audio_file": file_url,
    })
    meeting_doc.insert(ignore_permissions=True)
    frappe.db.commit()
    
    session_id_header = frappe.request.headers.get("X-App-Session-Id", "")

    frappe.enqueue(
        'voice_app.api._transcribe_audio_async',
        queue='long',
        timeout=3600,
        file_path=file_path,
        file_url=file_url,
        language=language,
        filter_speakers=filter_speakers,
        stt_mode=stt_mode,
        num_speakers=num_speakers,
        custom_vocabulary=custom_vocabulary,
        meeting_name=meeting_doc.name,
        session_id_header=session_id_header
    )

    return {"status": "processing", "meeting_name": meeting_doc.name}

@frappe.whitelist(allow_guest=False)
def check_meeting_status(meeting_name):
    meeting = frappe.get_doc("Voice Meeting", meeting_name)
    if meeting.status == "Completed":
        from voice_app.constants import get_worksuite_url, get_worksuite_token
        import requests
        employees = []
        try:
            token = get_worksuite_token()
            session = requests.Session()
            base_url = get_worksuite_url()
            session.headers.update({"Authorization": f"token {token}", "Accept": "application/json"})
            if True:
                emp_resp = session.get(
                    f"{base_url}/api/resource/Employee",
                    params={
                        "fields": '["name","employee_name","user_id"]',
                        "filters": '[["status","=","Active"]]',
                        "limit_page_length": 5000,
                    },
                    timeout=10,
                )
                if emp_resp.status_code == 200:
                    employees = [e for e in emp_resp.json().get("data", []) if e.get("user_id")]
        except Exception:
            pass

        raw_results = []
        try:
            if meeting.raw_results:
                raw_results = json.loads(meeting.raw_results)
        except:
            pass
            
        return {
            "status": "success",
            "results": raw_results,
            "final_text": meeting.transcript,
            "employees": employees,
            "meeting_name": meeting.name
        }
    elif meeting.status == "Error":
        # Check custom field if exists
        error_msg = meeting.get("error_message") or "Có lỗi xảy ra khi xử lý âm thanh."
        return {"status": "error", "message": error_msg}
    else:
        progress_info = frappe.cache().get_value(f"transcribe_progress_{meeting.name}")
        return {"status": "processing", "meeting_name": meeting.name, "progress_info": progress_info}


def _transcribe_audio_async(file_path, file_url, language, filter_speakers, stt_mode, num_speakers, custom_vocabulary, meeting_name, session_id_header):
    try:
    
    
        pass
    
        try:
            def update_progress(stt_percent, stt_msg, spk_percent, spk_msg):
                frappe.cache().set_value(f"transcribe_progress_{meeting_name}", {
                    "stt": {"progress": stt_percent, "msg": stt_msg},
                    "speaker": {"progress": spk_percent, "msg": spk_msg}
                })

            update_progress(5, "Đang chuẩn bị file âm thanh...", 0, "Chờ dịch văn bản...")

            # Convert to WAV
            wav, err = convert_to_wav(file_path)
            if err:
                if segments:
                    results_json = json.dumps(segments, ensure_ascii=False)
                    frappe.db.set_value("Voice Meeting", meeting_name, {
                        "status": "Partial Error",
                        "error_message": err,
                        "raw_results": results_json,
                        "original_raw_results": results_json
                    })
                else:
                    frappe.db.set_value("Voice Meeting", meeting_name, {"status": "Error", "error_message": err})
                frappe.db.commit()
                return

                frappe.db.set_value("Voice Meeting", meeting_name, {"status": "Error", "error_message": err}); frappe.db.commit(); return
    
            # Xác định num_speakers: ưu tiên user nhập → filter_speakers count → None
            auto_num_speakers = None
            if num_speakers:
                try:
                    auto_num_speakers = int(num_speakers)
                except Exception:
                    pass
            if not auto_num_speakers and filter_speakers:
                try:
                    names = json.loads(filter_speakers)
                    if isinstance(names, list) and len(names) >= 2:
                        auto_num_speakers = len(names)
                except Exception:
                    pass
    
            # Call STT theo mode
            def stt_cb(percent, msg):
                update_progress(percent, msg, 0, "Chờ dịch văn bản...")

            if stt_mode == "google":
                # Lấy existing_segments nếu đang resume
                existing_segments = None
                try:
                    meeting_doc = frappe.get_doc("Voice Meeting", meeting_name)
                    if meeting_doc.status == "Partial Error" and meeting_doc.raw_results:
                        existing_segments = json.loads(meeting_doc.raw_results)
                except: pass

                segments, raw_words, full_text, err, el_chars_used, el_chars_remaining = call_gemini_stt(
                    wav, language, num_speakers=auto_num_speakers, 
                    custom_vocabulary=custom_vocabulary, progress_callback=stt_cb, 
                    existing_segments=existing_segments
                )
            else:
                segments, raw_words, full_text, err, el_chars_used, el_chars_remaining = call_elevenlabs_stt(wav, language, num_speakers=auto_num_speakers, custom_vocabulary=custom_vocabulary)
            if err:
                frappe.db.set_value("Voice Meeting", meeting_name, {"status": "Error", "error_message": err}); frappe.db.commit(); return
    
            stt_label = "Google Gemini" if stt_mode == "google" else "ElevenLabs"
            el_speakers = set(s["speaker_id"] for s in segments)
            print(f"[{stt_label}] {len(segments)} segments, {len(el_speakers)} speakers: {sorted(el_speakers)}")
    
            # ── SPEAKER IDENTIFICATION ─────────────────────────────────────────────
            update_progress(100, "Đã dịch xong văn bản!", 10, "Bắt đầu trích xuất đặc trưng giọng nói...")
            spk_db = SpeakerDB()
            unique_speakers = {}
            for seg in segments:
                spk = seg["speaker_id"]
                if spk not in unique_speakers:
                    unique_speakers[spk] = []
                unique_speakers[spk].append(seg)
    
            # Trích xuất embedding cho mỗi speaker_id từ ElevenLabs
            # Dùng concat nhiều đoạn → embedding đại diện hơn 1 đoạn ngắn
            from scipy.spatial.distance import cosine as cos_dist
            from voice_app.audio_utils import concat_speaker_segments
            spk_embeddings = {}  # speaker_id -> embedding
            spk_identified = {}  # speaker_id -> (name, score, email, user_info)
    
            total_spk = len(unique_speakers)
            completed_spk = 0

            for spk, segs in unique_speakers.items():
                # Ghép nhiều đoạn của speaker để embedding đại diện hơn 1 đoạn đơn lẻ
                concat_wav = concat_speaker_segments(wav, segs, max_total_sec=25.0, min_seg_sec=1.0)
                if concat_wav is None:
                    segs_sorted = sorted(segs, key=lambda x: x["end"] - x["start"], reverse=True)
                    sample = segs_sorted[0]
                    start = sample["start"]
                    end = min(sample["end"], start + 5.0)
                    if end - start < 0.5:
                        completed_spk += 1
                        continue
                    emb = get_segment_embedding(wav, start, end)
                else:
                    from voice_app.audio_utils import get_duration
                    dur = get_duration(concat_wav)
                    emb = get_segment_embedding(concat_wav, 0.0, dur)
                    try: os.remove(concat_wav)
                    except: pass
    
                if emb is not None:
                    spk_embeddings[spk] = emb
                
                completed_spk += 1
                spk_prog = 10 + int((completed_spk / total_spk) * 80) # reserve 10% for final assignment
                update_progress(100, "Đã dịch xong văn bản!", spk_prog, f"Đang nhận diện giọng {completed_spk}/{total_spk}...")
    
            update_progress(100, "Đã dịch xong văn bản!", 95, "Đang đối chiếu dữ liệu nhân sự...")
            # Greedy assignment: mỗi tên chỉ gán cho 1 speaker (score cao nhất giành trước)
            # identify_ranked() đã filter >= SIMILARITY_THRESHOLD (0.65) rồi
            # → fallback candidate nào cũng đảm bảo trên ngưỡng, không cần check lại
            allowed = json.loads(filter_speakers) if filter_speakers else None
    
            # Lấy ranked candidates cho mỗi speaker (tất cả đều >= threshold)
            spk_ranked = {}  # speaker_id -> [(name, score, email, user_info), ...]
            for spk, emb in spk_embeddings.items():
                spk_ranked[spk] = spk_db.identify_ranked(emb, allowed_names=allowed)
    
            # Greedy: sắp xếp tất cả (spk, name, score) theo score giảm dần
            all_candidates = []
            for spk, ranked in spk_ranked.items():
                for name, score, email, user_info in ranked:
                    all_candidates.append((score, spk, name, email, user_info))
            all_candidates.sort(key=lambda x: x[0], reverse=True)
    
            claimed_names_by_chunk = {}   # chunk_prefix -> {name: spk}
            claimed_spks  = set()  # spk đã được gán tên
            spk_identified = {}
    
            for score, spk, name, email, user_info in all_candidates:
                if spk in claimed_spks:
                    continue  # speaker này đã có tên rồi
                
                chunk_prefix = "all"
                if spk.startswith("c") and "_" in spk:
                    prefix = spk.split("_")[0]
                    if prefix[1:].isdigit():
                        chunk_prefix = prefix

                if chunk_prefix not in claimed_names_by_chunk:
                    claimed_names_by_chunk[chunk_prefix] = {}

                if name in claimed_names_by_chunk[chunk_prefix]:
                    print(f"[Speaker] Greedy: {spk}({score:.3f}) muốn '{name}' nhưng đã bị {claimed_names_by_chunk[chunk_prefix][name]} trong cùng chunk {chunk_prefix} claim → thử tiếp")
                    continue  # tên này đã bị người khác lấy trong cùng chunk, thử candidate tiếp theo
                    
                claimed_names_by_chunk[chunk_prefix][name] = spk
                claimed_spks.add(spk)
                spk_identified[spk] = (name, score, email, user_info)
    
            # Các speaker không match được tên nào → Người lạ
            for spk in spk_embeddings:
                if spk not in spk_identified:
                    best_score = spk_ranked[spk][0][1] if spk_ranked.get(spk) else 0.0
                    spk_identified[spk] = ("Người lạ", best_score, "", None)
    
            # Log kết quả greedy assignment
            summary = ", ".join(f"{spk}→'{info[0]}'({info[1]:.3f})" for spk, info in spk_identified.items())
            print(f"[Speaker] Greedy result ({len(spk_identified)} speakers): {summary}")
    
            # Gộp các "Người lạ" có giọng giống nhau giữa các chunk (cosine sim >= 0.5)
            # Vì nhiều chunk trả ra nhiều speaker độc lập, nên phải so khớp để gán chung
            MERGE_THRESHOLD = 0.5
            stranger_groups = {}
            strangers = [spk for spk, info in spk_identified.items() if info[0] == "Người lạ"]
    
            for spk in strangers:
                merged = False
                for rep in list(stranger_groups.keys()):
                    if rep in spk_embeddings and spk in spk_embeddings:
                        sim = 1 - cos_dist(spk_embeddings[spk], spk_embeddings[rep])
                        if sim >= MERGE_THRESHOLD:
                            stranger_groups[spk] = stranger_groups[rep]
                            merged = True
                            break
                if not merged:
                    stranger_groups[spk] = spk
    
            # Đánh số "Người lạ N" theo thứ tự xuất hiện
            group_label = {}  # group_id -> "Người lạ N"
            unknown_counter = 1
            for spk in strangers:
                group_id = stranger_groups.get(spk, spk)
                if group_id not in group_label:
                    group_label[group_id] = f"Người lạ {unknown_counter}"
                    unknown_counter += 1
    
            # Tạo speaker_cache với nhãn hiển thị sạch
            speaker_cache = {}
            for spk, info in spk_identified.items():
                name, score, email, user_info = info
                if name != "Người lạ":
                    if not email or email.lower() == "chưa cập nhật":
                        speaker_cache[spk] = f"👤 {name}"
                    else:
                        speaker_cache[spk] = f"👤 {name} ({email})"
                else:
                    group_id = stranger_groups.get(spk, spk)
                    label = group_label.get(group_id, f"Người lạ {unknown_counter}")
                    speaker_cache[spk] = f"👤 {label}"
    
            # Fallback cho những spk không có embedding
            for spk in unique_speakers:
                if spk not in speaker_cache:
                    speaker_cache[spk] = f"👤 Người lạ {unknown_counter}"
                    unknown_counter += 1
    
            # ── LỌC SEGMENT VÔ NGHĨA ──────────────────────────────────────────────
            def is_meaningful(text):
                """Lọc bỏ segment quá ngắn hoặc không có nội dung hữu ích."""
                import re
                t = text.strip()
                if not t:
                    return False
                # Loại bỏ câu chỉ có dấu câu / ký tự đặc biệt
                if re.fullmatch(r'[\W\d]+', t):
                    return False
                words = t.split()
                # Loại bỏ câu <= 2 từ đơn lẻ không có nghĩa
                if len(words) <= 2:
                    # Cho phép nếu là tên riêng hoặc câu trả lời ngắn có nghĩa
                    meaningful_short = {'vâng', 'dạ', 'có', 'không', 'rồi', 'ừ', 'okay', 'ok',
                                        'được', 'đúng', 'đồng ý', 'yes', 'no', 'sure'}
                    joined = ' '.join(words).lower().strip('.,!?')
                    if joined not in meaningful_short:
                        return False
                return True
    
            # ── GỘP SEGMENT LIỀN KỀ CÙNG SPEAKER ─────────────────────────────────
            # Nếu 2 segment liên tiếp của cùng 1 speaker và khoảng gap < 1.5s → gộp lại
            MERGE_GAP = 1.5  # giây
    
            merged_segments = []
            segments.sort(key=lambda x: x["start"])
    
            for seg in segments:
                txt = " ".join(seg["text"].split())
                if not txt or not is_meaningful(txt):
                    continue
                spk_label = " ".join(speaker_cache.get(seg["speaker_id"], seg["speaker_id"]).split())
    
                if (merged_segments
                        and merged_segments[-1][2] == spk_label
                        and seg["start"] - merged_segments[-1][1] <= MERGE_GAP):
                    # Gộp vào segment trước
                    prev_s, prev_e, prev_spk, prev_txt = merged_segments[-1]
                    merged_segments[-1] = (prev_s, seg["end"], prev_spk, prev_txt + " " + txt)
                else:
                    merged_segments.append((seg["start"], seg["end"], spk_label, txt))
    
            # Format results
            results = merged_segments[:]
            final_output_text = ""
            last_spk = None
    
            for s, e, spk_label, txt in results:
                if spk_label != last_spk:
                    final_output_text += f"\n**{spk_label}** [{s:.1f}s]\n{txt}"
                else:
                    final_output_text += f" {txt}"
                last_spk = spk_label
    
            # Cleanup temp wav
            if os.path.exists(wav): os.remove(wav)
    
            from voice_app.constants import get_worksuite_url, get_worksuite_token
            import requests
            
            employees = []
            try:
                token = get_worksuite_token()
                session = requests.Session()
                base_url = get_worksuite_url()
                session.headers.update({"Authorization": f"token {token}", "Accept": "application/json"})
                if True:
                    emp_resp = session.get(
                        f"{base_url}/api/resource/Employee",
                        params={
                            "fields": '["name","employee_name","user_id"]',
                            "filters": '[["status","=","Active"]]',
                            "limit_page_length": 5000,
                        },
                        timeout=10,
                    )
                    if emp_resp.status_code == 200:
                        employees = [e for e in emp_resp.json().get("data", []) if e.get("user_id")]
            except Exception as ex:
                frappe.log_error(str(ex), "Fetch Employees Error in Transcribe")
    
            # Update Voice Meeting
            frappe.db.set_value("Voice Meeting", meeting_name, {
                "status": "Completed",
                "transcript": final_output_text.strip(),
                "raw_results": json.dumps(results, ensure_ascii=False)
            })
            frappe.db.commit()
    
            # Log AI call (ElevenLabs)
            try:
                session_id_header = frappe.request.headers.get("X-App-Session-Id", "")
                session_name = frappe.db.get_value("VOICE Session", {"session_id": session_id_header}, "name") if session_id_header else ""
                if session_name:
                    ai_model_log = "google/speech-to-text" if stt_mode == "google" else "elevenlabs/scribe_v2"
                    action_name = _logger.start_action(session_name, action_type="transcribe_audio", input_summary=f"Transcribe with {stt_label}")
                    _logger.log_ai_call(
                        session_name=session_name,
                        action_name=action_name,
                        call_type="transcribe_audio",
                        ai_model=ai_model_log,
                        duration_seconds=0,
                        status="success",
                        elevenlabs_chars_used=el_chars_used,
                        elevenlabs_chars_remaining=el_chars_remaining,
                    )
                    _logger.finish_action(action_name, status="success")
            except Exception as log_ex:
                if getattr(frappe.db, "_cursor", None):
                    frappe.db._cursor.execute("ROLLBACK")
                frappe.db.rollback()
                frappe.log_error(str(log_ex), "Log ElevenLabs AI Call Error")
    
            return {
                "status": "success",
                "results": results,
                "final_text": final_output_text.strip(),
                "employees": employees,
                "meeting_name": meeting_name
            }
    
        except Exception as e:
            if getattr(frappe.db, "_cursor", None):
                frappe.db._cursor.execute("ROLLBACK")
            frappe.db.rollback()
            frappe.log_error(traceback.format_exc(), "Audio Transcription Error")
            frappe.db.set_value("Voice Meeting", meeting_name, {"status": "Error", "error_message": str(e)}); frappe.db.commit(); return
    
    
    
    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Transcribe Async Error")
        frappe.db.set_value("Voice Meeting", meeting_name, {"status": "Error", "error_message": str(e)})
        frappe.db.commit()

@frappe.whitelist(allow_guest=False)
def extract_tasks():
    data = frappe.request.get_data()
    payload = json.loads(data)
    meeting_name = payload.get("meeting_name")
    if not meeting_name:
        return {"status": "error", "message": "Thiếu meeting_name"}

    session_id_header = frappe.request.headers.get("X-App-Session-Id", "")
    frappe.enqueue(
        "voice_app.api._extract_tasks_async",
        queue="long",
        timeout=1500,
        payload=payload,
        user=frappe.session.user,
        session_id_header=session_id_header
    )
    return {"status": "processing"}

@frappe.whitelist(allow_guest=False)
def check_extract_status(meeting_name):
    # Dùng frappe.cache()
    key = f"extract_result_{meeting_name}"
    result = frappe.cache().get_value(key)
    if result:
        frappe.cache().delete_value(key)
        return result
    return {"status": "processing"}

def _extract_tasks_async(payload, user, session_id_header):
    frappe.session.user = user
    results = payload.get("results", [])
    model_type = payload.get("model_type", "gpt-4o")
    meeting_name = payload.get("meeting_name")
    start_time = payload.get("start_time")
    end_time = payload.get("end_time")
    location = payload.get("location")
    chairperson = payload.get("chairperson")

    cache_key = f"extract_result_{meeting_name}"

    if not results and meeting_name:
        try:
            # Check if it's the primary key
            raw_results = frappe.db.get_value("Voice Meeting", meeting_name, "raw_results")
            if not raw_results:
                # Fallback to searching by title
                doc_name = frappe.db.get_value("Voice Meeting", {"title": meeting_name, "owner": frappe.session.user}, "name")
                if doc_name:
                    meeting_name = doc_name
                    raw_results = frappe.db.get_value("Voice Meeting", doc_name, "raw_results")
            
            if raw_results:
                results = json.loads(raw_results)
        except Exception:
            pass

    if not results:
        frappe.cache().set_value(cache_key, {"status": "error", "message": "Không có nội dung để tạo task"}, expires_in_sec=86400)
        return

    try:
        from voice_app.constants import get_worksuite_url, get_worksuite_token
        speaker_roles = {}
        try:
            voice_speakers = frappe.get_all(
                "Voice Speaker",
                fields=["speaker_name", "email"],
            )
            spk_email_map = {s["speaker_name"]: s["email"] for s in voice_speakers if s.get("email")}

            sess = requests.Session()
            base_url = get_worksuite_url()
            token = get_worksuite_token()
            sess.headers.update({"Authorization": f"token {token}", "Accept": "application/json"})
            if True:
                er = sess.get(f"{base_url}/api/resource/Employee",
                    params={"fields": '["user_id","designation","employee_name"]', "filters": '[["status","=","Active"]]', "limit_page_length": 5000},
                    timeout=8)
                if er.status_code == 200:
                    data = er.json().get("data", [])
                    email_desg_map = {
                        e["user_id"]: e["designation"]
                        for e in data
                        if e.get("user_id") and e.get("designation")
                    }
                    name_desg_map = {
                        e["employee_name"]: e["designation"]
                        for e in data
                        if e.get("employee_name") and e.get("designation")
                    }
                    for spk_name, email in spk_email_map.items():
                        if email in email_desg_map:
                            speaker_roles[spk_name] = email_desg_map[email]
                    
                    for emp_name, desg in name_desg_map.items():
                        speaker_roles[emp_name] = desg
                        speaker_roles[emp_name.strip().lower()] = desg
                        alt_name_1 = emp_name.replace('úy', 'uý').replace('ủy', 'uỷ').replace('ũy', 'uỹ').replace('ụy', 'uỵ').replace('ùy', 'uỳ')
                        alt_name_2 = emp_name.replace('uý', 'úy').replace('uỷ', 'ủy').replace('uỹ', 'ũy').replace('uỵ', 'ụy').replace('uỳ', 'ùy')
                        speaker_roles[alt_name_1] = desg
                        speaker_roles[alt_name_1.strip().lower()] = desg
                        speaker_roles[alt_name_2] = desg
                        speaker_roles[alt_name_2.strip().lower()] = desg

        except Exception as re_ex:
            frappe.log_error(str(re_ex), "Fetch Designations Error")

        docx_filename = save_to_docx(
            results, 
            speaker_roles=speaker_roles,
            start_time=start_time,
            end_time=end_time,
            location=location,
            chairperson=chairperson
        )
        
        with open(docx_filename, "rb") as f:
            file_doc = save_file(docx_filename, f.read(), None, None, is_private=0)
            docx_url = file_doc.file_url

        items, hr_projects_map, errors, employees, task_usage = extract_tasks_only(docx_filename, model_type="gpt-4o-mini")

        if os.path.exists(docx_filename): os.remove(docx_filename)

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
            
            if "assignee" in df.columns:
                df.drop(columns=["assignee"], inplace=True)
                
            excel_filename = f"tasks_{os.urandom(2).hex()}.xlsx"
            df.to_excel(excel_filename, index=False)
            
            with open(excel_filename, "rb") as f:
                excel_doc = save_file(excel_filename, f.read(), None, None, is_private=0)
                excel_url = excel_doc.file_url
            if os.path.exists(excel_filename): os.remove(excel_filename)

        if meeting_name and frappe.db.exists("Voice Meeting", meeting_name):
            meeting_owner = frappe.db.get_value("Voice Meeting", meeting_name, "owner")
            if meeting_owner == user:
                frappe.db.set_value("Voice Meeting", meeting_name, "minute_docx", docx_url)
                frappe.db.set_value("Voice Meeting", meeting_name, "task_xlsx", excel_url)
                frappe.db.set_value("Voice Meeting", meeting_name, "status", "Analyzed")
                if items:
                    frappe.db.set_value("Voice Meeting", meeting_name, "tasks_json",
                                        json.dumps(items, ensure_ascii=False))

        frappe.db.commit()

        try:
            session_name_log = frappe.db.get_value("VOICE Session", {"session_id": session_id_header}, "name") if session_id_header else ""
            if session_name_log and task_usage:
                action_name = _logger.start_action(session_name_log, action_type="extract_tasks", input_summary="Extract tasks from text")
                _logger.log_ai_call(
                    session_name=session_name_log,
                    action_name=action_name,
                    call_type="extract_tasks",
                    ai_model=model_type,
                    duration_seconds=0,
                    status="success",
                    prompt_tokens=task_usage.get("prompt_tokens", 0),
                    completion_tokens=task_usage.get("completion_tokens", 0)
                )
                _logger.finish_action(action_name, status="success")
        except Exception as log_ex:
            frappe.log_error(str(log_ex), "Log OpenAI AI Call Error")

        frappe.cache().set_value(cache_key, {
            "status": "success",
            "items": items,
            "hr_projects_map": hr_projects_map,
            "errors": errors,
            "employees": employees,
            "docx_url": docx_url,
            "excel_url": excel_url
        }, expires_in_sec=86400)

    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Task Extraction Error")
        frappe.cache().set_value(cache_key, {"status": "error", "message": str(e)}, expires_in_sec=86400)

@frappe.whitelist(allow_guest=False)
def clean_transcript():
    data = frappe.request.get_data()
    payload = json.loads(data)
    meeting_name = payload.get("meeting_name")
    if not meeting_name:
        return {"status": "error", "message": "Thiếu meeting_name"}
    
    session_id_header = frappe.request.headers.get("X-App-Session-Id", "")
    frappe.enqueue(
        "voice_app.api._clean_transcript_async",
        queue="long",
        timeout=1500,
        payload=payload,
        user=frappe.session.user,
        session_id_header=session_id_header
    )
    return {"status": "processing"}

@frappe.whitelist(allow_guest=False)
def check_clean_status(meeting_name):
    key = f"clean_result_{meeting_name}"
    result = frappe.cache().get_value(key)
    if result:
        frappe.cache().delete_value(key)
        return result
    return {"status": "processing"}

def _clean_transcript_async(payload, user, session_id_header):
    frappe.session.user = user
    results = payload.get("results", [])
    model_type = payload.get("model_type", "gpt-4o")
    meeting_name = payload.get("meeting_name")
    custom_vocabulary = payload.get("custom_vocabulary", "")
    
    cache_key = f"clean_result_{meeting_name}"

    if not results:
        frappe.cache().set_value(cache_key, {"status": "error", "message": "Không có nội dung để lọc"}, expires_in_sec=86400)
        return

    try:
        cleaned_results, err, clean_usage = clean_transcript_llm(results, model_type, custom_vocabulary)
        if err:
            frappe.cache().set_value(cache_key, {"status": "error", "message": err}, expires_in_sec=86400)
            return

        if clean_usage:
            p_tokens = clean_usage.get("prompt_tokens", 0)
            c_tokens = clean_usage.get("completion_tokens", 0)
            cost = (p_tokens * 2.5 + c_tokens * 10.0) / 1000000
            print(f"💰 [Chi phí OpenAI Clean] Model: {model_type} | Input: {p_tokens} tokens | Output: {c_tokens} tokens | Ước tính: ${cost:.4f}")

            try:
                session_name = _resolve_session(session_id_header)
                if session_name:
                    action_name = _logger.start_action(
                        session_name,
                        action_type="clean_transcript",
                        input_summary=f"Clean transcript with {model_type}",
                    )
                    _logger.log_ai_call(
                        session_name=session_name,
                        action_name=action_name,
                        call_type="clean_transcript",
                        ai_model=model_type,
                        prompt_tokens=p_tokens,
                        completion_tokens=c_tokens,
                        status="success",
                    )
                    _logger.finish_action(
                        action_name,
                        status="success",
                        ai_model=model_type,
                        prompt_tokens=p_tokens,
                        completion_tokens=c_tokens,
                    )
            except Exception as log_ex:
                try:
                    frappe.db.rollback()
                except Exception:
                    pass
                frappe.log_error(str(log_ex), "Log Clean Transcript AI Call Error")

        if meeting_name and frappe.db.exists("Voice Meeting", meeting_name):
            meeting_owner = frappe.db.get_value("Voice Meeting", meeting_name, "owner")
            if meeting_owner == user:
                frappe.db.set_value("Voice Meeting", meeting_name, "raw_results",
                                    json.dumps(cleaned_results, ensure_ascii=False))
                frappe.db.commit()

        frappe.cache().set_value(cache_key, {"status": "success", "cleaned_results": cleaned_results}, expires_in_sec=86400)
    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Transcript Clean Error")
        frappe.cache().set_value(cache_key, {"status": "error", "message": str(e)}, expires_in_sec=86400)

@frappe.whitelist(allow_guest=False)
def get_employees():
    import requests
    from voice_app.constants import get_worksuite_url, get_worksuite_token

    if frappe.session.user == "Guest":
        return {"status": "error", "message": "Vui lòng đăng nhập"}

    employees = []
    try:
        base_url, token = get_worksuite_url(), get_worksuite_token()
        
        if not base_url or not token:
            return {"status": "error", "message": "Vui lòng cấu hình Sync API URL và Sync API Token trong Voice App Settings."}
            
        if not base_url.startswith("http"):
            base_url = "https://" + base_url
            
        url = f"{base_url.rstrip('/')}/api/method/ct_agent_hub.api.admin.get_admin_users"
        
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/json"
        }
        data = {
            "page": "1",
            "limit": "9999999999"
        }
        
        response = requests.post(url, headers=headers, data=data, timeout=30)
        
        if response.status_code == 401:
            return {"status": "error", "message": "Xác thực thất bại (401). Token có thể đã hết hạn hoặc không hợp lệ."}
            
        response.raise_for_status()
        resp_json = response.json()
        
        resp_data = resp_json.get("message", {}) if "message" in resp_json else resp_json
        users = resp_data.get("users", [])
        
        for u in users:
            email = (u.get("email") or "").strip()
            if not email:
                continue
                
            full_name = (u.get("full_name") or "").strip()
            job_title = (u.get("job_title") or "").strip()
            
            # departments = u.get("departments") or []
            # dept = str(departments[0]).strip() if departments else ""
            
            # designation = job_title if job_title else dept
            designation = job_title 

            employees.append({
                "name": email,
                "employee_name": full_name,
                "user_id": email,
                "designation": designation
            })

    except requests.RequestException as e:
        frappe.log_error(message=str(e), title="Fetch Employees Error in get_employees")
        return {"status": "error", "message": f"Lỗi khi gọi API hệ thống ngoài: {str(e)}"}
    except Exception as e:
        frappe.log_error(message=str(e), title="Fetch Employees Error in get_employees")
        return {"status": "error", "message": f"Lỗi xử lý dữ liệu đồng bộ: {str(e)}"}
        
    return {"status": "success", "employees": employees}


@frappe.whitelist(allow_guest=False)
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
        if not frappe.db.exists("Voice Meeting", meeting_name):
            doc_name = frappe.db.get_value("Voice Meeting", {"title": meeting_name, "owner": frappe.session.user}, "name")
            if doc_name:
                meeting_name = doc_name
                
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


@frappe.whitelist(allow_guest=False)
def update_transcript_text():
    """Cập nhật nội dung transcript khi user chỉnh sửa thủ công"""
    if frappe.session.user == "Guest":
        return {"status": "error", "message": "Vui lòng đăng nhập"}

    data = frappe.request.get_data()
    payload = json.loads(data)
    meeting_name = payload.get("meeting_name")
    results = payload.get("results", [])

    if not meeting_name or not results:
        return {"status": "error", "message": "Thiếu meeting_name hoặc results"}

    try:
        if not frappe.db.exists("Voice Meeting", meeting_name):
            doc_name = frappe.db.get_value("Voice Meeting", {"title": meeting_name, "owner": frappe.session.user}, "name")
            if doc_name:
                meeting_name = doc_name
                
        if frappe.db.exists("Voice Meeting", meeting_name):
            meeting_owner = frappe.db.get_value("Voice Meeting", meeting_name, "owner")
            if meeting_owner != frappe.session.user:
                return {"status": "error", "message": "Không có quyền chỉnh sửa meeting này"}
            
            # Gộp lại nội dung text
            final_text = " ".join([seg[3].strip() for seg in results if len(seg) > 3 and seg[3] and seg[3].strip()])
            
            frappe.db.set_value("Voice Meeting", meeting_name, "raw_results",
                                json.dumps(results, ensure_ascii=False))
            frappe.db.set_value("Voice Meeting", meeting_name, "transcript", final_text)
            frappe.db.commit()
        return {"status": "success", "final_text": final_text}
    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Update Transcript Error")
        return {"status": "error", "message": str(e)}



@frappe.whitelist(allow_guest=False)
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


@frappe.whitelist(allow_guest=False)
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

    if not meeting_name or not file_type:
        frappe.throw("Thiếu tham số meeting_name hoặc file_type")

    if not frappe.db.exists("Voice Meeting", meeting_name):
        doc_name = frappe.db.get_value("Voice Meeting", {"title": meeting_name, "owner": frappe.session.user}, "name")
        if doc_name:
            meeting_name = doc_name

    if not frappe.db.exists("Voice Meeting", meeting_name):
        frappe.throw("Meeting không tồn tại")
        
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




@frappe.whitelist(allow_guest=False)
def get_elevenlabs_info():
    return {"balance": check_elevenlabs_balance()}

@frappe.whitelist(allow_guest=False)
def enroll_voice():
    if frappe.session.user == "Guest":
        return {"status": "error", "message": "Vui lòng đăng nhập để đăng ký giọng nói."}
        
    email = frappe.session.user
    full_name = frappe.utils.get_fullname(email)
    user_info = None

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

@frappe.whitelist(allow_guest=False)
def map_and_enroll_speakers():
    """
    Tự động trích xuất và lưu mẫu giọng cho các 'Người lạ' được gán danh tính.
    Nếu nhân viên đã có mẫu giọng thì bỏ qua.
    Tìm đoạn hội thoại dài nhất của người đó trong meeting để làm mẫu.
    """
    import os
    from voice_app.api import convert_to_wav
    from voice_app.speaker_manager import _extract_embedding_subprocess, SpeakerDB
    from voice_app.constants import get_worksuite_url, get_worksuite_token
    import requests

    data = frappe.request.get_data()
    payload = json.loads(data)
    meeting_name = payload.get("meeting_name")
    mappings = payload.get("mappings", {})  # {"Speaker 0": "Nguyen Van A (EMP-001)"}
    
    if not meeting_name or not mappings:
        return {"status": "error", "message": "Thiếu dữ liệu meeting_name hoặc mappings"}
        
    meeting = frappe.get_doc("Voice Meeting", meeting_name)
    if not meeting or not meeting.raw_results:
        return {"status": "error", "message": "Không tìm thấy meeting hoặc dữ liệu raw_results"}
        
    results = json.loads(meeting.raw_results)
    audio_path = frappe.get_site_path(meeting.audio_file.strip('/'))
    
    # Lấy danh sách nhân viên từ CTERP để trích xuất email
    employees_dict = {}
    try:
        session = requests.Session()
        base_url = get_worksuite_url()
        token = get_worksuite_token()
        session.headers.update({"Authorization": f"token {token}", "Accept": "application/json"})
        if True:
            emp_resp = session.get(f"{base_url}/api/resource/Employee", params={"fields": '["name","employee_name","user_id"]', "limit_page_length": 5000}, timeout=10)
            if emp_resp.status_code == 200:
                for emp in emp_resp.json().get("data", []):
                    key = f"{emp.get('employee_name')} ({emp.get('name')})"
                    employees_dict[key] = emp.get('user_id') or "Chưa cập nhật"
    except Exception as e:
        frappe.log_error(str(e), "Fetch Employees Error in map_and_enroll")

    enrolled = []
    skipped = []
    errors = []
    
    # Check what needs to be enrolled first to avoid unnecessary wav conversion
    needs_enrollment = {}
    db = SpeakerDB()
    
    for old_speaker, new_speaker in mappings.items():
        existing = frappe.get_all("Voice Speaker", filters={"speaker_name": new_speaker}, fields=["name", "embedding"])
        if existing and existing[0].get("embedding"):
            skipped.append(new_speaker)
            continue
            
        longest_segment = None
        max_duration = 0
        for seg in results:
            if seg[2] == old_speaker:
                dur = seg[1] - seg[0]
                if dur > max_duration:
                    max_duration = dur
                    longest_segment = seg
        
        # Chỉ lấy nếu đoạn dài > 2.0s
        if longest_segment and max_duration >= 2.0:
            needs_enrollment[new_speaker] = longest_segment
        else:
            errors.append(f"{new_speaker} (Audio quá ngắn, cần > 2s)")
            
    if not needs_enrollment:
        return {
            "status": "success",
            "enrolled": enrolled,
            "skipped": skipped,
            "errors": errors
        }

    # Convert to wav
    wav_path, err = convert_to_wav(audio_path)
    if err:
        return {"status": "error", "message": f"Lỗi xử lý file âm thanh: {err}"}
        
    try:
        for new_speaker, seg in needs_enrollment.items():
            start, end = seg[0], seg[1]
            try:
                embedding = _extract_embedding_subprocess(wav_path, start, end)
                email = employees_dict.get(new_speaker, "")
                db.add_speaker(new_speaker, embedding, email=email, user_info=None)
                enrolled.append(new_speaker)
            except Exception as ex:
                frappe.log_error(str(ex), f"Enroll mapped speaker error for {new_speaker}")
                errors.append(new_speaker)
    finally:
        if os.path.exists(wav_path): os.remove(wav_path)
        
    return {
        "status": "success",
        "enrolled": enrolled,
        "skipped": skipped,
        "errors": errors
    }

@frappe.whitelist(allow_guest=False)
def get_current_user():
    return frappe.session.user


@frappe.whitelist(allow_guest=False)
def get_enrolled_speakers():
    """Trả về danh sách người đã đăng ký giọng nói trong Voice DB."""
    try:
        speakers = frappe.get_all(
            "Voice Speaker",
            fields=["speaker_name", "email"],
            order_by="speaker_name asc"
        )
        # Enrich với designation từ CTERP nếu có email khớp
        from voice_app.constants import get_worksuite_url, get_worksuite_token
        try:
            base_url, token = get_worksuite_url(), get_worksuite_token()
            sess = requests.Session()
            sess.headers.update({"Authorization": f"token {token}", "Accept": "application/json"})
            if True:
                emp_resp = sess.get(f"{base_url}/api/resource/Employee",
                    params={"fields": '["employee_name","designation","user_id"]', "filters": '[["status","=","Active"]]', "limit_page_length": 5000},
                    timeout=8)
                if emp_resp.status_code == 200:
                    erp_map = {e["user_id"]: e for e in emp_resp.json().get("data", []) if e.get("user_id")}
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

@frappe.whitelist(allow_guest=False)
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
            fields=["name", "title", "date", "status", "audio_file", "minute_docx", "task_xlsx", "transcript", "raw_results", "tasks_json"],
            order_by="creation desc"
        )
        return {"status": "success", "meetings": meetings}
    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Get Meeting History Error")
        return {"status": "error", "message": str(e), "meetings": []}
_logger = ActivityLogger(prefix="VOICE", module="voice_app")

@frappe.whitelist(allow_guest=False)
def get_context():
    if frappe.session.user == "Guest":
        frappe.throw("Vui lòng đăng nhập", frappe.AuthenticationError)

    import uuid
    dept = ""
    role = ""
    try:
        try:
            from ct_agent_hub.api.core import check_app_access
        except ImportError:
            from ct_agent_hub.api import check_app_access

        agents_data = check_app_access("2as_worksuite")
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

@frappe.whitelist(allow_guest=False)
def voice_to_task(existing_task=None):
    """Tạo Task từ giọng nói — ElevenLabs STT → OpenAI GPT parse."""
    # ── Session & Action Logging ──
    session_id = frappe.get_request_header("X-App-Session-Id") or ""
    session_name = _resolve_session(session_id)
    if not session_name:
        import uuid as _uuid
        session_name = _logger.create_session(str(_uuid.uuid4()))
    action_name = _logger.start_action(
        session_name,
        action_type="voice_to_task",
        input_summary="audio upload",
    )

    if 'file' not in frappe.request.files:
        frappe.throw("Thiếu file âm thanh")
        
    audio_file = frappe.request.files['file']
    
    # Lưu file tải lên
    file_doc = save_file(audio_file.filename, audio_file.read(), None, None, is_private=1)
    file_path = frappe.get_site_path(file_doc.file_url.strip('/'))
    
    try:
        # Chuyển đổi sang WAV
        wav, err = convert_to_wav(file_path)
        if err:
            return {"status": "error", "message": err}

        # Gọi ElevenLabs Speech-to-Text
        segments, _raw_words, full_text, err, el_chars_used, el_chars_remaining = call_elevenlabs_stt(wav, "vi")
        if err:
            return {"status": "error", "message": err}
            
        # Xóa file wav tạm
        if os.path.exists(wav): 
            os.remove(wav)

        if not full_text.strip():
            return {"status": "error", "message": "Không thể trích xuất văn bản từ âm thanh."}

        # Lấy danh sách dự án và nhân viên từ ERPNext
        from voice_app.constants import get_worksuite_url, get_worksuite_token
        BASE_URL = get_worksuite_url()
        
        
        from voice_app.constants import get_openai_api_key
        OPENAI_API_KEY = get_openai_api_key()
        from openai import OpenAI
        from datetime import datetime, timedelta
        from voice_app.utils.activity_logger import Timer
        
        projects = []
        employees = []
        employees = []
        try:
            session = requests.Session()
            login_resp = session.post(
                f"{BASE_URL}/api/method/login",
                json={"usr": WS_EMAIL, "pwd": WS_PASSWORD},
                timeout=10,
            )
            if login_resp.status_code == 200:
                # Lấy CSRF token
                csrf_token = None
                try:
                    r = session.get(f"{BASE_URL}/api/method/frappe.utils.get_csrf_token", timeout=5)
                    if r.status_code == 200:
                        csrf_token = r.json().get("message") or session.cookies.get("csrf_token")
                except: 
                    pass
                if not csrf_token: 
                    csrf_token = session.cookies.get("csrf_token")
                if csrf_token:
                    session.headers.update({
                        "X-Frappe-CSRF-Token": csrf_token,
                        "X-Frappe-Site-Name":  BASE_URL.replace("https://", "").replace("http://", ""),
                    })

                # Lấy danh sách Projects active
                proj_resp = session.get(
                    f"{BASE_URL}/api/resource/Project",
                    params={"fields": '["name", "project_name"]', "limit_page_length": 5000},
                    timeout=10,
                )
                if proj_resp.status_code == 200:
                    projects = proj_resp.json().get("data", [])

                # Lấy danh sách Employees active
                emp_resp = session.get(
                    f"{BASE_URL}/api/resource/User",
                    params={
                        "fields": '["name","full_name","email","enabled"]',
                        "filters": '[["enabled","=",1]]',
                        "limit_page_length": 5000,
                    },
                    timeout=10,
                )
                if emp_resp.status_code == 200:
                    employees = []
                    for u in emp_resp.json().get("data", []):
                        if u.get("email") or u.get("name"):
                            employees.append({
                                "name": u.get("name"),
                                "employee_name": u.get("full_name"),
                                "user_id": u.get("email") or u.get("name")
                            })
        except Exception as ex:
            frappe.log_error(str(ex), "Fetch Projects/Employees Error in Voice to Task")

        current_user_email = frappe.session.user
        current_employee = None
        for e in employees:
            if e.get("user_id") == current_user_email:
                current_employee = e
                break

        assignee_default = f"{current_employee.get('employee_name')} ({current_employee.get('name')})" if current_employee else ""

        # ── Limit list size to avoid prompt overflow ──
        projects = projects[:100]
        employees = employees[:100]

        # Gọi OpenAI để phân tích câu lệnh
        if not OPENAI_API_KEY:
            return {"status": "error", "message": "Thiếu OPENAI_API_KEY"}

        client = OpenAI(api_key=OPENAI_API_KEY)
        
        now = datetime.now()
        current_date_str = now.strftime("%Y-%m-%d")
        current_day_of_week = now.strftime("%A")
        
        days_vi = {
            "Monday": "Thứ Hai",
            "Tuesday": "Thứ Ba",
            "Wednesday": "Thứ Tư",
            "Thursday": "Thứ Năm",
            "Friday": "Thứ Sáu",
            "Saturday": "Thứ Bảy",
            "Sunday": "Chủ Nhật"
        }
        day_vi = days_vi.get(current_day_of_week, current_day_of_week)

        # Phân tích existing_task gửi từ frontend nếu có
        parsed_existing = None
        if existing_task:
            try:
                parsed_existing = json.loads(existing_task)
            except Exception as e:
                frappe.log_error(f"Error parsing existing_task: {str(e)}", "Voice to Task JSON Parse Error")

        prompt = f"""
Bạn là trợ lý AI chuyên nghiệp giúp trích xuất và tinh chỉnh thông tin tạo nhiệm vụ (Task) từ đoạn hội thoại/giọng nói.
Hôm nay là {day_vi}, ngày {current_date_str} (định dạng YYYY-MM-DD).

Thông tin Người đang tạo Task (Current User):
- Tên: {current_employee.get('employee_name') if current_employee else 'Không rõ'}
- Email/ID: {current_user_email}
- Chức vụ: {current_employee.get('designation') if current_employee and current_employee.get('designation') else 'Không rõ'}

Hãy đọc đoạn văn bản được chuyển từ giọng nói sau đây:
Văn bản bổ sung mới: "{full_text}"

{"Thông tin Task hiện tại đang có trước khi bổ sung: " + json.dumps(parsed_existing, ensure_ascii=False) if parsed_existing else "Đây là lượt khởi tạo Task đầu tiên."}

Danh sách các dự án khả dụng (Project List):
{json.dumps(projects, ensure_ascii=False)}

Danh sách nhân viên khả dụng (Employee List) để giao nhiệm vụ:
{json.dumps([{"employee_name": e.get("employee_name"), "name": e.get("name")} for e in employees], ensure_ascii=False)}

Yêu cầu nhiệm vụ:
1. Kết hợp thông tin mới từ "Văn bản bổ sung mới" vào "Thông tin Task hiện tại" để hoàn thiện hoặc cập nhật các trường dưới đây.
2. Các trường cần trả về trong JSON:
   - "task_name": Tên nhiệm vụ cốt lõi mà người nói muốn thực hiện. ĐẶC BIỆT CHÚ Ý: 
     + Người dùng có thể nói lộn xộn, tự đính chính trong lúc nói (ví dụ: "à không", "sửa lại là..."). Phải lấy quyết định cuối cùng của họ.
     + Nếu họ nói ngọng hoặc nhầm lẫn giữa "tên dự án" và "tên nhiệm vụ", hãy tự suy luận ngữ cảnh để tách ra Hành động/Công việc (Task) và Tên dự án.
     + Nếu không có hành động rõ ràng (chỉ nói "test" hoặc một cụm từ), hãy lấy cụm từ đó làm tên nhiệm vụ. TUYỆT ĐỐI không để trống, nếu mập mờ hãy tự tóm tắt thành 1 cụm động từ.
   - "project_id": So sánh tên dự án được nhắc tới trong hội thoại với danh sách dự án ở trên. Chọn "name" của dự án khớp nhất. Nếu không khớp bất kỳ dự án nào, trả về null (hoặc giữ nguyên dự án cũ từ thông tin Task hiện tại).
   - "project_name": Tên dự án được nói tới (nhớ cập nhật theo ý đính chính cuối cùng của người nói).
   - "assignee_display": So sánh tên người thực hiện được nhắc tới với danh sách nhân viên khả dụng. Nếu khớp, điền 'employee_name (name)'. LƯU Ý QUAN TRỌNG: Nếu người dùng xưng "tôi", "mình", hoặc KHÔNG nhắc tới ai thực hiện, hãy tự động lấy "Người đang tạo Task" ở trên làm người thực hiện (điền '{assignee_default if assignee_default else "null"}' nếu có thông tin, ngược lại để null). Nếu nhắc tới tên không có trong danh sách, điền tên đó. Nếu không nhắc tới và không có Người đang tạo Task, trả về null (hoặc giữ nguyên người cũ từ thông tin Task hiện tại).
   - "start_date": Ngày bắt đầu (định dạng YYYY-MM-DD). Tính toán dựa trên ngày hôm nay ({current_date_str}). Ví dụ: "ngày mai" là ngày {(now + timedelta(days=1)).strftime("%Y-%m-%d")}. Nếu không nhắc tới, mặc định lấy ngày hôm nay ({current_date_str}).
   - "end_date": Ngày kết thúc / Hạn chót (định dạng YYYY-MM-DD). Tính toán dựa trên ngày hôm nay ({current_date_str}). Nếu không nhắc tới, trả về null (hoặc giữ nguyên hạn chót cũ từ thông tin Task hiện tại).
   - "task_type": Phân loại mục này là "task" (Nhiệm vụ cần làm) hay "noti" (Thông báo thông tin chung). Hãy xác định rõ dựa vào ngữ nghĩa (VD: giao việc là task, báo cáo trạng thái / thông tin là noti).
   - "description": Mô tả chi tiết nhiệm vụ (nếu có chi tiết hơn). Lọc bỏ các từ thừa, ậm ừ.
3. Kiểm tra tính đầy đủ của thông tin cốt lõi:
   - Một nhiệm vụ được coi là thiếu thông tin cốt lõi nếu:
     - Chưa xác định được dự án cụ thể (`project_id` là null hoặc "")
     - Hoặc chưa có người thực hiện (`assignee_display` là null hoặc "" hoặc chưa khớp với nhân viên nào dạng 'employee_name (name)')
     - Hoặc chưa có ngày kết thúc / hạn chót (`end_date` là null hoặc "")
   - "missing_fields": Hãy trả về danh sách các trường bị thiếu, có thể gồm: "project" (nếu thiếu dự án), "assignee" (nếu thiếu người thực hiện), "end_date" (nếu thiếu hạn chót). Lưu ý: Nếu `assignee_display` đã được gán tự động cho "Người đang tạo Task", thì KHÔNG bị tính là thiếu "assignee". Nếu không thiếu trường nào, trả về mảng rỗng [].
   - "clarification_question": Nếu có ít nhất một trường bị thiếu trong `missing_fields`, hãy viết một câu hỏi gợi ý rất ngắn gọn, tự nhiên, lịch sự bằng tiếng Việt để nhắc người dùng bổ sung các thông tin còn thiếu này qua giọng nói (Ví dụ: 'Nhiệm vụ này chưa có dự án cụ thể. Bạn muốn tạo task này cho dự án nào?' hoặc 'Nhiệm vụ này chưa có hạn chót. Hạn chót khi nào?'). Nếu thông tin đã đầy đủ hoặc không thiếu gì, trả về null.

Hãy trả về kết quả dưới dạng JSON duy nhất, KHÔNG chứa markdown (```json), KHÔNG giải thích thêm:
{{
  "task_name": "...",
  "task_type": "...",
  "project_id": "...",
  "project_name": "...",
  "assignee_display": "...",
  "start_date": "...",
  "end_date": "...",
  "description": "...",
  "missing_fields": [...],
  "clarification_question": "..."
}}
"""
        with Timer() as t:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                response_format={"type": "json_object"}
            )
        
        parsed_data = json.loads(response.choices[0].message.content.strip())
        if "task_type" in parsed_data and parsed_data["task_type"]:
            loai_raw = str(parsed_data["task_type"]).lower()
            parsed_data["task_type"] = "noti" if "noti" in loai_raw or "thông báo" in loai_raw else "task"
        usage = response.usage
        p_tok = usage.prompt_tokens if usage else 0
        c_tok = usage.completion_tokens if usage else 0

        # ── AI Call Log ──
        _logger.log_ai_call(
            session_name, action_name,
            call_type="voice_to_task", ai_model="gpt-4o",
            prompt_tokens=p_tok, completion_tokens=c_tok,
            duration_seconds=t.elapsed, status="success",
        )
        _logger.finish_action(
            action_name, status="success",
            output_summary=f"task={parsed_data.get('task_name','')}",
            ai_model="gpt-4o",
            prompt_tokens=p_tok, completion_tokens=c_tok,
            duration_seconds=t.elapsed,
        )

        return {
            "status": "success",
            "transcript": full_text,
            "task": parsed_data,
            "projects": projects,
            "employees": employees
        }

    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Voice to Task Error")
        _logger.finish_action(action_name, status="failed", error_message=str(e)[:500])
        return {"status": "error", "message": str(e)}
    finally:
        # ── Cleanup temp files ──
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass




@frappe.whitelist()
def resume_transcription(meeting_name):
    try:
        meeting_doc = frappe.get_doc("Voice Meeting", meeting_name)
        if meeting_doc.status != "Partial Error":
            return {"status": "error", "message": "Chỉ có thể tiếp tục với meeting có trạng thái Lỗi một phần."}
        
        # Get attached audio
        files = frappe.get_all("File", filters={"attached_to_doctype": "Voice Meeting", "attached_to_name": meeting_name}, fields=["file_url"])
        if not files:
            return {"status": "error", "message": "Không tìm thấy file âm thanh đính kèm."}
            
        file_url = files[0].file_url
        site_path = frappe.utils.get_site_path()
        if file_url.startswith('/private'):
            local_path = os.path.join(site_path, 'private', 'files', file_url.split('/')[-1])
        else:
            local_path = os.path.join(site_path, 'public', 'files', file_url.split('/')[-1])
            
        if not os.path.exists(local_path):
            return {"status": "error", "message": "File âm thanh không tồn tại trên hệ thống."}
            
        # Re-enqueue transcription
        frappe.db.set_value("Voice Meeting", meeting_name, "status", "Processing")
        frappe.db.commit()
        
        frappe.enqueue(
            _transcribe_audio_async,
            queue='long',
            timeout=7200,
            wav_path=local_path,
            language=meeting_doc.language or "vi",
            filter_speakers=meeting_doc.filter_speakers,
            meeting_name=meeting_name,
            stt_mode=meeting_doc.stt_mode or "elevenlabs",
            num_speakers=meeting_doc.num_speakers,
            custom_vocabulary=meeting_doc.custom_vocabulary or ""
        )
        
        return {"status": "processing", "meeting_name": meeting_name}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "resume_transcription_error")
        return {"status": "error", "message": str(e)}

@frappe.whitelist()
def undo_mapping(meeting_name):
    try:
        meeting_doc = frappe.get_doc("Voice Meeting", meeting_name)
        if not meeting_doc.original_raw_results:
            return {"status": "error", "message": "Không có dữ liệu gốc để hoàn tác."}
            
        frappe.db.set_value("Voice Meeting", meeting_name, "raw_results", meeting_doc.original_raw_results)
        frappe.db.commit()
        
        return {"status": "success", "results": json.loads(meeting_doc.original_raw_results)}
    except Exception as e:
        return {"status": "error", "message": str(e)}
