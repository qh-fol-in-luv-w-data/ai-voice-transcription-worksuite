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


def apply_font_to_cell(cell, size_pt=12):
    """Áp dụng font Times New Roman lên toàn bộ paragraph/run trong một cell."""
    for p in cell.paragraphs:
        for run in p.runs:
            set_font_times(run, size_pt)
        # Nếu paragraph chưa có run (text set trực tiếp)
        if not p.runs and p.text:
            run = p.add_run(p.text)
            for prev_r in p.runs[:-1]:  # xoá các run cũ
                prev_r._element.getparent().remove(prev_r._element)
            set_font_times(run, size_pt)


def _clean_speaker(raw):
    """Loại bỏ icon emoji, email, %, khoảng trắng thừa để lấy tên thuần."""
    s = re.sub(r'[\U0001F464\U0001F465\U0001F466\U0001F467\U0001F468\U0001F469👤]', '', str(raw))
    s = re.sub(r'\(.*?\)', '', s)      # bỏ (email@...) hoặc (score%)
    s = re.sub(r'-\s*\d+%', '', s)    # bỏ - 69%
    return normalize_whitespace(s)


# ── MAIN FUNCTION ──────────────────────────────────────────────────────────────

def get_template_path():
    return frappe.get_app_path("voice_app", "public", "files", "template_v2.docx")


def save_to_docx(results, title="Biên bản họp", speaker_roles=None, start_time=None, end_time=None, location=None, chairperson=None):
    """
    results: list of tuples (start, end, speaker_label, text)
    speaker_roles: dict { speaker_name: designation } lấy từ CTERP
    """
    if speaker_roles is None:
        speaker_roles = {}

    template_path = get_template_path()

    if os.path.exists(template_path):
        doc = docx.Document(template_path)

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
                
                # Di chuyển toàn bộ nội dung header vào phần nội dung chính (body)
                elements_to_move = []
                for e in section.header._element:
                    elements_to_move.append(e)
                
                for e in elements_to_move:
                    section.header._element.remove(e)
                    
                for e in reversed(elements_to_move):
                    doc._body._element.insert(0, e)
                    
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

        # ── Cập nhật bảng Thành phần tham dự (Table 0) ───────────────────────
        if len(doc.tables) > 0:
            attendee_table = doc.tables[0]

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

            # Xóa các hàng cũ
            while len(attendee_table.rows) > 0:
                tr = attendee_table.rows[-1]._element
                tr.getparent().remove(tr)

            # Thêm các hàng mới với font Times New Roman 12
            for i, spk_name in enumerate(unique_speakers):
                row_cells = attendee_table.add_row().cells
                row_cells[0].text = f"{i + 1}."
                row_cells[1].text = spk_name
                if len(row_cells) > 2:
                    designation = (
                        speaker_roles.get(spk_name)
                        or roles_lower.get(spk_name.lower())
                        or "Thành viên"
                    )
                    row_cells[2].text = designation
                for cell in row_cells:
                    apply_font_to_cell(cell, 12)

        # ── Chèn nội dung biên bản vào phần "II. Nội dung chi tiết" ──────────
        start_idx = -1
        for i, p in enumerate(doc.paragraphs):
            if "II. Nội dung chi tiết cuộc họp" in p.text:
                start_idx = i
                break

        if start_idx != -1 and start_idx + 1 < len(doc.paragraphs):
            target_p = doc.paragraphs[start_idx + 1]

            for start, end, spk, txt in results:
                txt = normalize_whitespace(txt)
                txt = clean_xml_text(txt)
                clean_spk = _clean_speaker(spk)

                p = target_p.insert_paragraph_before("")
                r_spk = p.add_run(f"{clean_spk}: ")
                r_spk.bold = True
                set_font_times(r_spk, 12)

                r_txt = p.add_run(txt)
                set_font_times(r_txt, 12)

            # Xóa các đoạn mẫu (slice [:-1] để tránh xóa sectPr)
            num_inserted = len(results)
            current_paragraphs = doc.paragraphs
            for p in current_paragraphs[start_idx + 1 + num_inserted:-1]:
                p._element.getparent().remove(p._element)

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
