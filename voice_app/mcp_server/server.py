#!/usr/bin/env python3
"""
MCP server cho voice_app — cho ChatGPT (hoặc bất kỳ MCP client nào) xem danh
sách và nội dung các cuộc họp đã phiên âm, CHỈ ĐỌC (không tạo meeting mới,
không gọi Gemini STT nên không tốn tiền).

Chạy ĐỘC LẬP với Frappe (không phải @frappe.whitelist trong api.py) — đây là
một tiến trình HTTP riêng, dùng httpx gọi ngược vào REST API sẵn có của
voice_app. Lý do tách riêng thay vì nhét thẳng vào Frappe: MCP SDK cần vòng
lặp asyncio riêng của nó (anyio), chạy chung với Werkzeug dev server hoặc
gunicorn worker của Frappe sẽ xung đột.

── PHÂN QUYỀN ───────────────────────────────────────────────────────────────
Server này KHÔNG có khái niệm "user" riêng. Mỗi người dùng tự cấu hình API Key
Frappe CỦA CHÍNH HỌ (User > Settings > API Access > Generate Keys) vào phần
xác thực (Bearer/API key) khi thêm connector trong ChatGPT. Toàn bộ tool ở
đây chỉ ĐỌC header Authorization của từng request rồi CHUYỂN TIẾP NGUYÊN VẸN
sang Frappe — Frappe tự xác định user thật từ key đó và tự áp dụng đúng logic
phân quyền đã có sẵn (_can_access_meeting trong api.py: chỉ thấy meeting của
mình, trừ khi có role System Manager/Administrator). Server MCP này không tự
quyết định ai được xem gì — nó chỉ là đường ống, quyền hạn nằm hoàn toàn ở
phía Frappe.

── CHẠY THỬ LOCAL ───────────────────────────────────────────────────────────
    VOICE_APP_BASE_URL=http://ct-datalake.localhost:8002 \
    python voice_app/mcp_server/server.py

── DEPLOY LÊN SERVER (vd. devapp.ctpai.vn) ─────────────────────────────────
Xem README.md cùng thư mục để biết cách chạy như systemd service + trỏ qua
nginx reverse proxy tại path /mcp.
"""

import os
from enum import Enum
from typing import Any, Mapping, Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

# ── CẤU HÌNH ──────────────────────────────────────────────────────────────
VOICE_APP_BASE_URL = os.environ.get("VOICE_APP_BASE_URL", "https://devapp.ctpai.vn").rstrip("/")
MCP_HOST = os.environ.get("VOICE_APP_MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.environ.get("VOICE_APP_MCP_PORT", "8010"))
REQUEST_TIMEOUT = 30.0
# Danh sách Host header được chấp nhận, cách nhau bằng dấu phẩy — MCP SDK bật
# sẵn chống DNS-rebinding, chặn mọi Host header lạ theo mặc định (kể cả
# localhost:PORT nếu không khai rõ). Khi chạy thử qua ngrok, set biến này ra
# đúng domain ngrok cấp (vd. VOICE_APP_MCP_ALLOWED_HOSTS=xxxx.ngrok-free.dev).
_allowed_hosts_env = os.environ.get("VOICE_APP_MCP_ALLOWED_HOSTS", "")
MCP_ALLOWED_HOSTS = [f"{MCP_HOST}:{MCP_PORT}", "localhost", "127.0.0.1"] + [
    h.strip() for h in _allowed_hosts_env.split(",") if h.strip()
]

mcp = MCPServer("voice_app_mcp")


class ResponseFormat(str, Enum):
    """Định dạng trả về của tool."""
    MARKDOWN = "markdown"
    JSON = "json"


# ── XÁC THỰC: chuyển tiếp Authorization của người gọi sang Frappe ──────────

def _normalize_frappe_auth(raw_value: str) -> str:
    """Đổi giá trị header Authorization người dùng cấu hình trong ChatGPT
    thành đúng định dạng Frappe REST yêu cầu: 'token <api_key>:<api_secret>'.

    ChatGPT (và hầu hết UI cấu hình API key của các MCP client) chỉ cho nhập
    MỘT chuỗi, thường tự thêm tiền tố 'Bearer '. Chấp nhận cả 3 dạng để đỡ
    phải dặn người dùng nhớ đúng cú pháp Frappe:
      - 'token key:secret'   (đúng chuẩn Frappe, dùng thẳng)
      - 'Bearer key:secret'  (kiểu OAuth quen thuộc) -> đổi tiền tố
      - 'key:secret'         (không tiền tố)         -> thêm tiền tố
    """
    value = raw_value.strip()
    if value.lower().startswith("token "):
        return value
    if value.lower().startswith("bearer "):
        value = value[len("bearer "):].strip()
    return f"token {value}"


def _get_auth_header(ctx: Context) -> str:
    """Lấy Authorization từ request hiện tại, báo lỗi rõ ràng nếu thiếu."""
    headers: Optional[Mapping[str, str]] = ctx.headers
    raw = None
    if headers:
        # Mapping của Starlette Headers không phân biệt hoa/thường, nhưng
        # phòng khi transport khác trả về dict thường thì tự dò thêm.
        raw = headers.get("authorization") or headers.get("Authorization")
    if not raw:
        raise ToolError(
            "Thiếu Authorization. Vào User > My Settings > API Access trong "
            "Frappe để tạo API Key + API Secret của chính bạn, rồi dán "
            "'<api_key>:<api_secret>' vào ô xác thực (Bearer/API key) khi "
            "thêm connector này trong ChatGPT."
        )
    return _normalize_frappe_auth(raw)


async def _call_frappe_method(ctx: Context, method: str, params: Optional[dict] = None) -> dict:
    """Gọi một hàm @frappe.whitelist qua REST, dùng danh tính người gọi thật.

    Mọi logic phân quyền (ai thấy meeting nào) nằm hết ở phía Frappe — hàm
    này chỉ chuyển tiếp, không tự lọc/diễn giải gì thêm.
    """
    auth = _get_auth_header(ctx)
    url = f"{VOICE_APP_BASE_URL}/api/method/{method}"
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        resp = await client.get(url, params=params or {}, headers={"Authorization": auth})

    if resp.status_code == 403:
        raise ToolError(
            "Frappe từ chối quyền truy cập (403). API Key/Secret có thể sai, "
            "hết hạn, hoặc user đó không có quyền vào voice_app."
        )
    if resp.status_code == 401:
        raise ToolError("Frappe từ chối xác thực (401). Kiểm tra lại API Key:Secret đã dán đúng chưa.")
    resp.raise_for_status()

    data = resp.json()
    # Frappe bọc kết quả @frappe.whitelist trong {"message": ...}
    return data.get("message", data)


def _to_tool_error(e: Exception) -> ToolError:
    """Đổi một exception bất kỳ (từ httpx, JSON decode, v.v.) thành ToolError.

    Raise ToolError từ tool khiến MCPServer trả is_error=True KÈM message
    thật cho client đọc; mọi exception khác đều bị SDK thay bằng thông báo
    chung chung "Error executing tool <name>" (che luôn message gốc) — nên
    bất cứ lỗi nào lọt ra khỏi _call_frappe_method cũng phải đi qua đây
    trước khi raise tiếp, trừ ToolError (đã có message tốt, giữ nguyên).
    """
    if isinstance(e, ToolError):
        return e
    if isinstance(e, httpx.TimeoutException):
        return ToolError(f"Hết thời gian chờ Frappe server ({VOICE_APP_BASE_URL}). Thử lại sau.")
    if isinstance(e, httpx.HTTPStatusError):
        return ToolError(f"Frappe trả về lỗi HTTP {e.response.status_code}.")
    if isinstance(e, httpx.RequestError):
        return ToolError(f"Không kết nối được tới {VOICE_APP_BASE_URL} ({type(e).__name__}).")
    return ToolError(f"Lỗi không xác định ({type(e).__name__}): {e}")


# ── voice_app_list_meetings ─────────────────────────────────────────────────

class ListMeetingsInput(BaseModel):
    """Tham số cho tool liệt kê meeting."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    search: Optional[str] = Field(
        default=None,
        description="Lọc theo tiêu đề meeting, khớp gần đúng, không phân biệt hoa/thường (ví dụ: 'nghiệm thu')",
        max_length=200,
    )
    limit: int = Field(default=20, description="Số kết quả tối đa mỗi trang", ge=1, le=100)
    offset: int = Field(default=0, description="Bỏ qua bao nhiêu kết quả đầu (để phân trang)", ge=0)
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="'markdown' để đọc trực tiếp, 'json' để xử lý bằng chương trình",
    )


@mcp.tool(
    name="voice_app_list_meetings",
    annotations=ToolAnnotations(
        title="Liệt kê cuộc họp",
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
async def voice_app_list_meetings(params: ListMeetingsInput, ctx: Context) -> str:
    """Liệt kê các cuộc họp đã phiên âm mà người gọi (theo API key của họ)
    có quyền xem — chỉ meeting của chính họ, trừ khi họ có quyền quản trị.

    Dùng tool này TRƯỚC khi gọi voice_app_get_meeting_transcript, vì bạn cần
    'name' (mã meeting, ví dụ 'MEETING-2088') để tra nội dung chi tiết.

    Args:
        params (ListMeetingsInput): search (lọc theo tiêu đề, tuỳ chọn),
            limit (1-100, mặc định 20), offset (mặc định 0), response_format.

    Returns:
        str: Markdown liệt kê meeting (tiêu đề, mã, ngày, trạng thái) hoặc
            JSON với schema:
            {
                "total": int,        # tổng số meeting khớp filter
                "count": int,        # số lượng trong trang này
                "offset": int,
                "has_more": bool,
                "next_offset": int | null,
                "meetings": [
                    {"name": str, "title": str, "date": str, "status": str}
                ]
            }

    Examples:
        - "Liệt kê các cuộc họp gần đây" -> params rỗng, dùng limit mặc định
        - "Tìm cuộc họp về nghiệm thu" -> params={"search": "nghiệm thu"}

    Error Handling:
        - Báo lỗi rõ nếu thiếu/sai Authorization (xem hướng dẫn trong lỗi)
        - Trả danh sách rỗng nếu người dùng chưa có meeting nào
    """
    try:
        result = await _call_frappe_method(ctx, "voice_app.api.get_meeting_history")
    except Exception as e:
        raise _to_tool_error(e) from e

    if result.get("status") != "success":
        return f"Error: {result.get('message', 'Không lấy được danh sách meeting')}"

    meetings = result.get("meetings") or []
    if params.search:
        needle = params.search.lower()
        meetings = [m for m in meetings if needle in (m.get("title") or "").lower()]

    total = len(meetings)
    page = meetings[params.offset: params.offset + params.limit]
    has_more = params.offset + len(page) < total

    if params.response_format == ResponseFormat.JSON:
        import json
        return json.dumps(
            {
                "total": total,
                "count": len(page),
                "offset": params.offset,
                "has_more": has_more,
                "next_offset": params.offset + len(page) if has_more else None,
                "meetings": page,
            },
            ensure_ascii=False,
            indent=2,
        )

    if not page:
        return "Không tìm thấy cuộc họp nào." + (f" (lọc: '{params.search}')" if params.search else "")

    lines = [f"# Danh sách cuộc họp ({total} tổng, hiển thị {len(page)})", ""]
    for m in page:
        date_str = m.get("date") or "?"
        lines.append(f"- **{m.get('title') or '(không tên)'}** ({m.get('name')}) — {date_str} — trạng thái: {m.get('status')}")
    if has_more:
        lines.append("")
        lines.append(f"_Còn thêm kết quả — gọi lại với offset={params.offset + len(page)} để xem tiếp._")
    return "\n".join(lines)


# ── voice_app_get_meeting_transcript ────────────────────────────────────────

class GetMeetingTranscriptInput(BaseModel):
    """Tham số cho tool lấy nội dung chi tiết một meeting."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    meeting_name: str = Field(
        ...,
        description="Mã meeting, lấy từ voice_app_list_meetings (ví dụ 'MEETING-2088')",
        min_length=1,
        max_length=50,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="'markdown' để đọc trực tiếp, 'json' để xử lý bằng chương trình",
    )


@mcp.tool(
    name="voice_app_get_meeting_transcript",
    annotations=ToolAnnotations(
        title="Xem nội dung cuộc họp",
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
async def voice_app_get_meeting_transcript(params: GetMeetingTranscriptInput, ctx: Context) -> str:
    """Lấy transcript đầy đủ (từng lượt nói, có gán tên người nói khi đã
    nhận diện được) cùng tóm tắt/kết luận/task (nếu đã trích xuất) của MỘT
    cuộc họp cụ thể. KHÔNG gọi lại Gemini STT — chỉ đọc dữ liệu đã lưu sẵn,
    nên không tốn chi phí.

    Args:
        params (GetMeetingTranscriptInput): meeting_name (bắt buộc, lấy từ
            voice_app_list_meetings), response_format.

    Returns:
        str: Markdown gồm transcript theo từng lượt nói + tóm tắt/kết luận
            (nếu có), hoặc JSON với schema:
            {
                "name": str, "title": str, "date": str, "status": str,
                "segments": [{"start": float, "end": float, "speaker": str, "text": str}],
                "meeting_summary": str | null,
                "conclusion": str | null,
                "tasks": list | null
            }

    Examples:
        - "Nội dung cuộc họp MEETING-2088 nói gì?" -> params={"meeting_name": "MEETING-2088"}
        - Don't use when: chưa biết mã meeting -> gọi voice_app_list_meetings trước

    Error Handling:
        - "Không có quyền xem meeting này" nếu meeting thuộc người khác
        - "Không tìm thấy meeting" nếu sai mã
    """
    import json as _json

    try:
        result = await _call_frappe_method(
            ctx, "voice_app.api.get_meeting_detail", {"meeting_name": params.meeting_name}
        )
    except Exception as e:
        raise _to_tool_error(e) from e

    if result.get("status") != "success":
        return f"Error: {result.get('message', 'Không lấy được nội dung meeting')}"

    meeting = result.get("meeting") or {}
    raw_results = meeting.get("raw_results")
    segments = []
    if raw_results:
        try:
            parsed = _json.loads(raw_results)
            for row in parsed:
                if isinstance(row, dict):
                    segments.append({
                        "start": row.get("start"), "end": row.get("end"),
                        "speaker": row.get("speaker"), "text": row.get("text"),
                    })
                elif isinstance(row, (list, tuple)) and len(row) >= 4:
                    segments.append({"start": row[0], "end": row[1], "speaker": row[2], "text": row[3]})
        except (ValueError, TypeError):
            pass

    tasks = None
    if meeting.get("tasks_json"):
        try:
            tasks = _json.loads(meeting["tasks_json"])
        except (ValueError, TypeError):
            tasks = None

    if params.response_format == ResponseFormat.JSON:
        return _json.dumps(
            {
                "name": meeting.get("name"),
                "title": meeting.get("title"),
                "date": meeting.get("date"),
                "status": meeting.get("status"),
                "segments": segments,
                "meeting_summary": meeting.get("meeting_summary"),
                "conclusion": meeting.get("conclusion"),
                "tasks": tasks,
            },
            ensure_ascii=False,
            indent=2,
        )

    lines = [f"# {meeting.get('title') or meeting.get('name')}", ""]
    lines.append(f"- Mã: {meeting.get('name')}")
    lines.append(f"- Ngày: {meeting.get('date') or '?'}")
    lines.append(f"- Trạng thái: {meeting.get('status')}")
    lines.append("")

    if meeting.get("meeting_summary"):
        lines.append("## Tóm tắt")
        lines.append(meeting["meeting_summary"])
        lines.append("")

    if meeting.get("conclusion"):
        lines.append("## Kết luận")
        lines.append(meeting["conclusion"])
        lines.append("")

    lines.append(f"## Nội dung chi tiết ({len(segments)} lượt nói)")
    if not segments:
        lines.append("_Chưa có transcript (meeting có thể đang xử lý hoặc bị lỗi)._")
    for seg in segments:
        speaker = seg.get("speaker") or "?"
        text = seg.get("text") or ""
        lines.append(f"**{speaker}**: {text}")

    if tasks:
        lines.append("")
        lines.append(f"## Danh sách task ({len(tasks)})")
        for t in tasks:
            if isinstance(t, dict):
                lines.append(f"- {t.get('task') or t.get('title') or t}")

    return "\n".join(lines)


if __name__ == "__main__":
    from mcp.server.streamable_http_manager import TransportSecuritySettings

    mcp.run(
        transport="streamable-http",
        host=MCP_HOST,
        port=MCP_PORT,
        streamable_http_path="/mcp",
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=MCP_ALLOWED_HOSTS,
            allowed_origins=["*"],
        ),
    )
