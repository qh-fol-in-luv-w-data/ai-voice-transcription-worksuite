import os
import re
import shutil
from datetime import datetime
import docx
import frappe


# ── UTILS ──────────────────────────────────────────────────────────────────────

def normalize_whitespace(text):
    """
    Chuẩn hóa khoảng trắng:
    - Loại bỏ khoảng trắng đầu/cuối
    - Thay thế nhiều khoảng trắng liên tiếp (tab, xuống dòng, space) bằng 1 dấu cách
    - Loại bỏ ký tự điều khiển vô hình
    """
    if not text:
        return ""
    # Loại bỏ ký tự điều khiển (\x00-\x08, \x0b, \x0c, \x0e-\x1f)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(text))
    # Chuẩn hoá khoảng trắng
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def set_font_times(run, size_pt=12):
    """Áp dụng Times New Roman cỡ size_pt cho tất cả kiểu ký tự (Latin, CJK, Complex)."""
    from docx.shared import Pt
    from docx.oxml.ns import qn
    run.font.name = 'Times New Roman'
    run.font.size = Pt(size_pt)
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    rFonts.set(qn('w:ascii'),    'Times New Roman')
    rFonts.set(qn('w:hAnsi'),   'Times New Roman')
    rFonts.set(qn('w:eastAsia'), 'Times New Roman')
    rFonts.set(qn('w:cs'),      'Times New Roman')


def apply_font_to_cell(cell, size_pt=12, bold=False):
    """Áp dụng font Times New Roman lên toàn bộ paragraph/run trong một cell."""
    for p in cell.paragraphs:
        for run in p.runs:
            set_font_times(run, size_pt)
            if bold: run.bold = True
        # Nếu paragraph chưa có run (text set trực tiếp)
        if not p.runs and p.text:
            text = p.text
            p.text = ""
            run = p.add_run(text)
            set_font_times(run, size_pt)
            if bold: run.bold = True


def _clean_speaker(raw):
    """Loại bỏ icon emoji, email, %, khoảng trắng thừa để lấy tên thuần."""
    s = re.sub(r'[\U0001F464\U0001F465\U0001F466\U0001F467\U0001F468\U0001F469👤]', '', str(raw))
    s = re.sub(r'\(.*?\)', '', s)      # bỏ (email@...) hoặc (score%)
    s = re.sub(r'-\s*\d+%', '', s)    # bỏ - 69%
    return normalize_whitespace(s)


# ── MAIN FUNCTION ──────────────────────────────────────────────────────────────

def get_template_path():
    return frappe.get_app_path("voice_app", "public", "files", "template_v2.docx")


def save_to_docx(results, title="Biên bản họp", speaker_roles=None, start_time=None, end_time=None, location=None, chairperson=None, meeting_summary=None, conclusion=None, tasks=None):
    """
    results: list of tuples (start, end, speaker_label, text)
    speaker_roles: dict { speaker_name: designation }
    tasks: list of dict representing tasks
    """
    if speaker_roles is None:
        speaker_roles = {}

    template_path = get_template_path()

    if os.path.exists(template_path):
        doc = docx.Document(template_path)
        attendee_table = doc.tables[0] if len(doc.tables) > 0 else None

        # ── Chỉ hiện header ở trang đầu tiên thôi ────────────────────────────
        current_date = "17/11/2025"
        for section in doc.sections:
            if section.header:
                # Thay thế {DATE}
                for p in section.header.paragraphs:
                    if '{DATE}' in p.text:
                        p.text = p.text.replace('{DATE}', current_date)
                        for run in p.runs:
                            set_font_times(run, 10)
                for t in section.header.tables:
                    for r in t.rows:
                        for c in r.cells:
                            for p in c.paragraphs:
                                if '{DATE}' in p.text:
                                    p.text = p.text.replace('{DATE}', current_date)
                                    for run in p.runs:
                                        set_font_times(run, 10)
                
                # Fix lỗi ảnh bị "The picture can't be displayed" khi chuyển từ Header sang Body
                from docx.opc.constants import RELATIONSHIP_TYPE as RT
                import io
                
                header_part = section.header.part
                doc_part = doc.part
                rId_map = {}
                
                for rel in header_part.rels.values():
                    if rel.reltype == RT.IMAGE:
                        new_rId = doc_part.get_or_add_image(io.BytesIO(rel.target_part.blob))[0]
                        rId_map[rel.rId] = new_rId

                elements_to_move = []
                for e in section.header._element:
                    elements_to_move.append(e)
                
                for e in elements_to_move:
                    # Update rId trong XML để ảnh hiển thị đúng
                    for img_elem in e.xpath('.//*[@r:embed]'):
                        old_id = img_elem.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')
                        if old_id in rId_map:
                            img_elem.set('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed', rId_map[old_id])
                            
                    for img_elem in e.xpath('.//*[@r:id]'):
                        old_id = img_elem.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
                        if old_id in rId_map:
                            img_elem.set('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id', rId_map[old_id])
                            
                    section.header._element.remove(e)
                    
                for e in reversed(elements_to_move):
                    doc._body._element.insert(0, e)
                
                # Thêm một paragraph rỗng vào header để tránh lỗi cấu trúc XML (Word crash nếu w:hdr rỗng)
                section.header.add_paragraph("")
                    
            section.different_first_page_header_footer = False


        # ── Chèn thông tin cuộc họp (Thời gian, Địa điểm, Chủ trì) ───────────
        for p in doc.paragraphs:
            if "Thành phần tham dự" in p.text or "THÀNH PHẦN THAM DỰ" in p.text:
                if start_time:
                    p1 = p.insert_paragraph_before(f"Thời gian bắt đầu: {start_time}")
                    if p1.runs: set_font_times(p1.runs[0], 12)
                if end_time:
                    p2 = p.insert_paragraph_before(f"Thời gian kết thúc: {end_time}")
                    if p2.runs: set_font_times(p2.runs[0], 12)
                if location:
                    p3 = p.insert_paragraph_before(f"Địa điểm: {location}")
                    if p3.runs: set_font_times(p3.runs[0], 12)
                if chairperson:
                    p4 = p.insert_paragraph_before(f"Chủ trì: {chairperson}")
                    if p4.runs: set_font_times(p4.runs[0], 12)
                break

        # ── Cập nhật bảng Thành phần tham dự ───────────────────────
        if attendee_table is not None:

            roles_lower = {k.strip().lower(): v for k, v in speaker_roles.items()}

            # Lấy danh sách tên người nói duy nhất
            unique_speakers = []
            
            def clean_xml_text(text):
                return re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]', '', text)

            for _, _, spk, txt in results:
                # Nếu txt chứa ký tự điều khiển không hợp lệ -> Word crash (Text Recovery converter)
                txt = clean_xml_text(txt)
                clean_spk = _clean_speaker(spk)
                if clean_spk and clean_spk not in unique_speakers:
                    unique_speakers.append(clean_spk)

            num_old_rows = len(attendee_table.rows)

            # Thêm hàng tiêu đề (Header)
            header_cells = attendee_table.add_row().cells
            header_cells[0].text = "STT"
            header_cells[1].text = "Người tham dự"
            if len(header_cells) > 2:
                header_cells[2].text = "Chức vụ"
            for cell in header_cells:
                apply_font_to_cell(cell, 12)
                for p in cell.paragraphs:
                    for r in p.runs:
                        r.bold = True

            # Thêm các hàng mới với font Times New Roman 12
            for i, spk_name in enumerate(unique_speakers):
                row_cells = attendee_table.add_row().cells
                row_cells[0].text = f"{i + 1}."
                spk_display = spk_name
                designation_display = ""
                
                parts = spk_name.split(" - ")
                if len(parts) == 3 and "@" in parts[1]:
                    spk_display = parts[0].strip()
                    designation_display = parts[2].strip()
                elif len(parts) > 1 and "@" in parts[1]:
                    spk_display = parts[0].strip()
                    
                desg = speaker_roles.get(spk_display) or roles_lower.get(spk_display.lower())
                
                # Fetch directly from Employee if not in speaker_roles
                if not desg and not spk_display.lower().startswith("người lạ"):
                    try:
                        db_desg = frappe.db.get_value("Employee", {"employee_name": spk_display}, "designation")
                        if db_desg:
                            desg = db_desg
                    except Exception:
                        pass
                
                if spk_display.lower().startswith("người lạ"):
                    designation_display = desg or "Khách"
                else:
                    # Ưu tiên desg thật từ database, nếu không có mới dùng text "thành viên" mặc định
                    if desg:
                        designation_display = desg
                    elif designation_display.lower() == "thành viên":
                        designation_display = ""
                        
                row_cells[1].text = spk_display
                if len(row_cells) > 2:
                    row_cells[2].text = designation_display
                    
                for cell in row_cells:
                    apply_font_to_cell(cell, 12)

            # Xóa các hàng mẫu ban đầu
            for _ in range(num_old_rows):
                tr = attendee_table.rows[0]._element
                tr.getparent().remove(tr)

        # ── Chèn nội dung biên bản vào phần "II. Nội dung chi tiết" ──────────
        start_idx = -1
        for i, p in enumerate(doc.paragraphs):
            if "II. Nội dung chi tiết cuộc họp" in p.text:
                start_idx = i
                break

        if start_idx != -1 and start_idx + 1 < len(doc.paragraphs):
            heading_p = doc.paragraphs[start_idx]
            old_transcript_start_p = doc.paragraphs[start_idx + 1]
            
            # 1. Insert Transcript AFTER heading_p (BEFORE old_transcript_start_p)
            for start, end, spk, txt in results:
                txt = normalize_whitespace(txt)
                txt = clean_xml_text(txt)
                clean_spk = _clean_speaker(spk)

                p = old_transcript_start_p.insert_paragraph_before("")
                r_spk = p.add_run(f"{clean_spk}: ")
                r_spk.bold = True
                set_font_times(r_spk, 12)

                r_txt = p.add_run(txt)
                set_font_times(r_txt, 12)

            old_transcript_start_p.insert_paragraph_before("") # spacing
            
            # 2. Summary
            if meeting_summary:
                p_sum_head = old_transcript_start_p.insert_paragraph_before("Tóm tắt nội dung chính")
                if p_sum_head.runs:
                    p_sum_head.runs[0].bold = True
                    set_font_times(p_sum_head.runs[0], 12)
                p_sum = old_transcript_start_p.insert_paragraph_before(meeting_summary)
                if p_sum.runs: set_font_times(p_sum.runs[0], 12)
                old_transcript_start_p.insert_paragraph_before("") # spacing
                
            # 3. Conclusion
            if conclusion:
                p_con_head = old_transcript_start_p.insert_paragraph_before("Kết luận cuộc họp")
                if p_con_head.runs:
                    p_con_head.runs[0].bold = True
                    set_font_times(p_con_head.runs[0], 12)
                p_con = old_transcript_start_p.insert_paragraph_before(conclusion)
                if p_con.runs: set_font_times(p_con.runs[0], 12)
                old_transcript_start_p.insert_paragraph_before("") # spacing
                
            # 4. Tasks Table
            if tasks and len(tasks) > 0:
                p_task_head = old_transcript_start_p.insert_paragraph_before("Danh sách công việc cần thực hiện (Action Items)")
                if p_task_head.runs:
                    p_task_head.runs[0].bold = True
                    set_font_times(p_task_head.runs[0], 12)
                    
                table = old_transcript_start_p.insert_paragraph_before("").insert_paragraph_before("")._parent.add_table(rows=1, cols=5, width=docx.shared.Inches(6.0))
                table.style = 'Table Grid'
                table.autofit = False
                table.allow_autofit = False
                
                hdr_cells = table.rows[0].cells
                headers = ['STT', 'Tên nhiệm vụ', 'Người thực hiện (PIC)', 'Ngày hoàn thành', 'Ghi chú']
                for j, text in enumerate(headers):
                    hdr_cells[j].text = text
                    apply_font_to_cell(hdr_cells[j], 12, bold=True)
                
                for j, t in enumerate(tasks):
                    row_cells = table.add_row().cells
                    row_cells[0].text = str(j + 1)
                    row_cells[1].text = t.get("title") or t.get("noi_dung") or ""
                    row_cells[2].text = t.get("assignee_display") or t.get("nguoi_thuc_hien") or ""
                    row_cells[3].text = t.get("due_date") or t.get("end_date") or t.get("ngay_ket_thuc") or ""
                    row_cells[4].text = t.get("description") or t.get("note") or ""
                    
                    for cell in row_cells:
                        apply_font_to_cell(cell, 12)
                        
                # Set column widths
                widths = [docx.shared.Inches(0.4), docx.shared.Inches(2.2), docx.shared.Inches(1.2), docx.shared.Inches(1.0), docx.shared.Inches(1.2)]
                for row in table.rows:
                    for idx, width in enumerate(widths):
                        row.cells[idx].width = width
                
                # Di chuyển table lên trước old_transcript_start_p
                tbl_element = table._element
                tbl_element.getparent().remove(tbl_element)
                old_transcript_start_p._element.addprevious(tbl_element)
                old_transcript_start_p.insert_paragraph_before("") # spacing
            
            # 5. Clear old transcript paragraphs safely by comparing underlying XML element
            current_idx = -1
            for i, p in enumerate(doc.paragraphs):
                if p._element is old_transcript_start_p._element:
                    current_idx = i
                    break
            
            if current_idx != -1:
                # slice [:-1] to avoid deleting the section properties in the last paragraph
                for p in doc.paragraphs[current_idx:-1]:
                    p.text = ""

        # ── Thêm chữ ký ở cuối biên bản ──────────────────────────────────────
        doc.add_paragraph("")
        sig_table = doc.add_table(rows=2, cols=2)
        sig_table.alignment = 1 # Center
        r0 = sig_table.rows[0].cells
        r0[0].text = "THƯ KÝ CUỘC HỌP"
        r0[1].text = "CHỦ TRÌ CUỘC HỌP"
        r0[0].paragraphs[0].alignment = 1
        r0[1].paragraphs[0].alignment = 1
        
        r1 = sig_table.rows[1].cells
        r1[0].text = "(Ký, ghi rõ họ tên)"
        r1[1].text = "(Ký, ghi rõ họ tên)"
        r1[0].paragraphs[0].alignment = 1
        r1[1].paragraphs[0].alignment = 1
        
        for row in sig_table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    for run in p.runs:
                        set_font_times(run, 12)
                        if "THƯ KÝ" in run.text or "CHỦ TRÌ" in run.text:
                            run.bold = True

    else:
        # ── Fallback nếu không tìm thấy template ─────────────────────────────
        doc = docx.Document()
        current_date = "17/11/2025"
        doc.add_heading(title, 0)
        doc.add_paragraph(f"Ngày họp: {current_date}")
        doc.add_paragraph(f"Tổng số lượt phát biểu: {len(results)}")

        table = doc.add_table(rows=1, cols=3)
        table.style = 'Table Grid'
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = 'Thời gian'
        hdr_cells[1].text = 'Người nói'
        hdr_cells[2].text = 'Nội dung'
        for cell in hdr_cells:
            apply_font_to_cell(cell, 12)

        for start, end, spk, txt in results:
            txt = normalize_whitespace(txt)
            clean_spk = _clean_speaker(spk)

            row_cells = table.add_row().cells
            row_cells[0].text = f"{start:.1f}s"
            row_cells[1].text = clean_spk
            row_cells[2].text = txt
            for cell in row_cells:
                apply_font_to_cell(cell, 12)

        # ── Thêm chữ ký ở cuối biên bản (Fallback) ───────────────────────────
        doc.add_paragraph("")
        sig_table = doc.add_table(rows=2, cols=2)
        sig_table.alignment = 1 # Center
        r0 = sig_table.rows[0].cells
        r0[0].text = "THƯ KÝ CUỘC HỌP"
        r0[1].text = "CHỦ TRÌ CUỘC HỌP"
        r0[0].paragraphs[0].alignment = 1
        r0[1].paragraphs[0].alignment = 1
        
        r1 = sig_table.rows[1].cells
        r1[0].text = "(Ký, ghi rõ họ tên)"
        r1[1].text = "(Ký, ghi rõ họ tên)"
        r1[0].paragraphs[0].alignment = 1
        r1[1].paragraphs[0].alignment = 1
        
        for row in sig_table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    for run in p.runs:
                        set_font_times(run, 12)
                        if "THƯ KÝ" in run.text or "CHỦ TRÌ" in run.text:
                            run.bold = True

    filename = f"meeting_minutes_{os.urandom(2).hex()}.docx"
    doc.save(filename)
    return filename
