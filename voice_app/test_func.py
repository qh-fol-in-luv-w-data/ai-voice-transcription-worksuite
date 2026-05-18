import frappe
from frappe.utils.file_manager import save_file
import os

def run():
    excel_filename = f"tasks_{os.urandom(2).hex()}.xlsx"
    with open(excel_filename, "wb") as f:
        f.write(b"dummy excel data")
    
    file_doc = save_file(excel_filename, b"dummy excel data", None, None, is_private=0)
    print("File URL:", file_doc.file_url)
    print("Dict:", file_doc.as_dict())
