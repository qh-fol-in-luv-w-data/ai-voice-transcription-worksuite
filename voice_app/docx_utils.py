import os
import re
import shutil
from datetime import datetime
import docx
import frappe

def normalize_whitespace(text):
    """Chuẩn hóa khoảng trắng: loại bỏ khoảng trắng thừa, thay thế bằng 1 dấu cách duy nhất."""
    if not text:
        return ""
    return re.sub(r'\s+', ' ', str(text)).strip()

def set_font_times(run, size_pt=12):
    from docx.shared import Pt
    from docx.oxml.ns import qn
    run.font.name = 'Times New Roman'
    run.font.size = Pt(size_pt)
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    rFonts.set(qn('w:eastAsia'), 'Times New Roman')
    rFonts.set(qn('w:cs'), 'Times New Roman')
    rFonts.set(qn('w:ascii'), 'Times New Roman')
    rFonts.set(qn('w:hAnsi'), 'Times New Roman')

def get_template_path():
    return frappe.get_app_path("voice_app", "public", "files", "template_v2.docx")

def save_to_docx(results, title="Biên bản họp", speaker_roles=None):
    """
    results: list of tuples (start, end, speaker_label, text)
    speaker_roles: dict { speaker_name: designation } lấy từ CTERP
    """
    if speaker_roles is None:
        speaker_roles = {}
    template_path = get_template_path()
    if os.path.exists(template_path):
        doc = docx.Document(template_path)
        
        # Cập nhật ngày ban hành trong header
        current_date = datetime.now().strftime("%d/%m/%Y")
        for section in doc.sections:
            if section.header:
                for t in section.header.tables:
                    for r in t.rows:
                        for c in r.cells:
                            for p in c.paragraphs:
                                if '{DATE}' in p.text:
                                    p.text = p.text.replace('{DATE}', current_date)
                                    # Restore font
                                    for run in p.runs:
                                        set_font_times(run, 10)

        # Cập nhật bảng Thành phần tham dự (Table 0)
        if len(doc.tables) > 0:
            attendee_table = doc.tables[0]

            def _clean_spk(raw):
                """Loại bỏ icon, email, %, khoảng trắng thừa để lấy tên thuần."""
                s = re.sub(r'[\U0001F464\U0001F465\U0001F466\U0001F467👤]', '', raw)
                s = re.sub(r'\(.*?\)', '', s)           # bỏ (email), (score%)
                s = re.sub(r'-\s*\d+%', '', s)         # bỏ - 69%
                return normalize_whitespace(s)

            # Build lowercase lookup từ speaker_roles để match linh hoạt hơn
            roles_lower = {k.strip().lower(): v for k, v in speaker_roles.items()}

            # Lấy danh sách tên người nói duy nhất
            unique_speakers = []
            for _, _, spk, _ in results:
                clean_spk = _clean_spk(spk)
                if clean_spk and clean_spk not in unique_speakers:
                    unique_speakers.append(clean_spk)
                    
            # Xóa các hàng cũ
            while len(attendee_table.rows) > 0:
                tr = attendee_table.rows[-1]._element
                tr.getparent().remove(tr)
                
            # Thêm các hàng mới, điền designation nếu có
            for i, spk_name in enumerate(unique_speakers):
                row_cells = attendee_table.add_row().cells
                row_cells[0].text = f"{i + 1}."
                row_cells[1].text = spk_name
                if len(row_cells) > 2:
                    # Tìm exact trước, rồi fallback lowercase
                    designation = (
                        speaker_roles.get(spk_name)
                        or roles_lower.get(spk_name.lower())
                        or "Thành viên"
                    )
                    row_cells[2].text = designation
                for cell in row_cells:
                    for p in cell.paragraphs:
                        for run in p.runs:
                            set_font_times(run, 12)
        
        # Tìm vị trí "II. Nội dung chi tiết cuộc họp:"
        start_idx = -1
        for i, p in enumerate(doc.paragraphs):
            if "II. Nội dung chi tiết cuộc họp" in p.text:
                start_idx = i
                break
                
        if start_idx != -1 and start_idx + 1 < len(doc.paragraphs):
            target_p = doc.paragraphs[start_idx + 1]
            
            # Chèn nội dung mới
            for start, end, spk, txt in results:
                txt = normalize_whitespace(txt)
                clean_spk = re.sub(r'[👤👤]', '', spk) # Bỏ icon
                clean_spk = re.sub(r'\(.*?\)', '', clean_spk) # Bỏ (email)
                clean_spk = re.sub(r'-\s*\d+%', '', clean_spk) # Bỏ - 100%
                clean_spk = normalize_whitespace(clean_spk)
                
                p = target_p.insert_paragraph_before("")
                r_spk = p.add_run(f"{clean_spk}: ")
                r_spk.bold = True
                set_font_times(r_spk, 12)
                
                r_txt = p.add_run(txt)
                set_font_times(r_txt, 12)
                
            # Xóa các đoạn hội thoại mẫu để file chỉ chứa kết quả AI mới
            # Slice [:-1] để CHẮC CHẮN không xóa paragraph cuối cùng (chứa <w:sectPr>), tránh lỗi file Word
            num_inserted = len(results)
            current_paragraphs = doc.paragraphs
            for p in current_paragraphs[start_idx + 1 + num_inserted:-1]:
                p._element.getparent().remove(p._element)
                
    else:
        # Fallback nếu không tìm thấy template
        doc = docx.Document()
        current_date = datetime.now().strftime("%d/%m/%Y")
        
        doc.add_heading(title, 0)
        doc.add_paragraph(f"Ngày họp: {current_date}")
        doc.add_paragraph(f"Tổng số lượt phát biểu: {len(results)}")
        
        table = doc.add_table(rows=1, cols=3)
        table.style = 'Table Grid'
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = 'Thời gian'
        hdr_cells[1].text = 'Người nói'
        hdr_cells[2].text = 'Nội dung'

        for start, end, spk, txt in results:
            txt = normalize_whitespace(txt)
            clean_spk = re.sub(r'[👤👤]', '', spk)
            clean_spk = re.sub(r'\(.*?\)', '', clean_spk)
            clean_spk = re.sub(r'-\s*\d+%', '', clean_spk)
            clean_spk = normalize_whitespace(clean_spk)

            row_cells = table.add_row().cells
            row_cells[0].text = f"{start:.1f}s"
            row_cells[1].text = clean_spk
            row_cells[2].text = txt
            
            for cell in row_cells:
                for p in cell.paragraphs:
                    for run in p.runs:
                        set_font_times(run, 12)

    filename = f"meeting_minutes_{os.urandom(2).hex()}.docx"
    doc.save(filename)
    return filename
