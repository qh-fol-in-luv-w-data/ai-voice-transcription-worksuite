"""
CT Group — Template: get_context() endpoint
============================================
Copy file nay vao endpoint chinh cua app (VD: voice_app/api/{module}_api.py)
roi thay the voice_app, VOICE, {MODULE}, voice_app.

CONTEXT_URL tuong ung: /api/method/voice_app.api.{module}_api.get_context
"""

import frappe
import uuid
from voice_app.utils.activity_logger import ActivityLogger

_logger = ActivityLogger(prefix="VOICE", module="{MODULE}")


@frappe.whitelist(allow_guest=False)
def get_context():
    """
    Entry point cho Frontend (initSession).
    - Xac thuc quyen qua ct_agent_hub.check_app_access (cookie-based)
    - Tao session moi
    - Tra ve csrf_token + session_id
    """
    # Buoc 1: Xac thuc quyen (System Manager tu dong duoc bypass)
    dept = ""
    role = ""
    try:
        try:
            from ct_agent_hub.api.core import check_app_access
        except ImportError:
            from ct_agent_hub.api import check_app_access

        agents_data = check_app_access("voice_app")
        user_depts = agents_data.get("user_departments", [])
        dept = ",".join(user_depts) if user_depts else ""
        role = agents_data.get("user_role", "")
    except ImportError:
        pass  # ct_agent_hub chua duoc cai dat

    # Buoc 2: Tao session
    session_id   = str(uuid.uuid4())
    session_name = _logger.create_session(session_id, dept=dept, role=role)

    return {
        "csrf_token":   frappe.sessions.get_csrf_token(),
        "session_id":   session_id,
        "session_name": session_name,
    }


def _resolve_session(session_id: str) -> str:
    """Tim session_name tu session_id. Fallback tra ve chuoi rong."""
    if not session_id:
        return ""
    try:
        rows = frappe.db.get_all(
            "VOICE Session",
            filters={"session_id": session_id},
            fields=["name"],
            limit=1,
            ignore_permissions=True,  # bat buoc: bypass DocType read permission
        )
        return rows[0].name if rows else ""
    except Exception:
        return ""
