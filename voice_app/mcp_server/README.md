# voice_app MCP server

Cho ChatGPT (hoặc bất kỳ MCP client nào) **xem** danh sách và nội dung các
cuộc họp đã phiên âm trong voice_app. Chỉ đọc — không tạo meeting mới, không
gọi Gemini STT, nên không phát sinh chi phí khi dùng.

Có 2 tool:
- `voice_app_list_meetings` — liệt kê meeting (lọc theo tên, phân trang)
- `voice_app_get_meeting_transcript` — xem transcript + tóm tắt/kết luận/task của 1 meeting

## Phân quyền hoạt động thế nào

Server này **không tự quyết định ai xem được gì**. Mỗi người dùng tự tạo API
Key + API Secret của chính họ trong Frappe (Desk → avatar góc phải → **My
Settings** → tab **API Access** → **Generate Keys**), rồi dán
`<api_key>:<api_secret>` đó vào phần xác thực khi thêm connector trong
ChatGPT. Server chỉ đọc header `Authorization` của từng request và **chuyển
tiếp nguyên vẹn** sang Frappe qua REST API — Frappe tự nhận ra đúng user thật
từ key đó và áp dụng logic phân quyền đã có sẵn trong `voice_app/api.py`
(hàm `_can_access_meeting`): mỗi người chỉ thấy meeting của chính mình, trừ
khi có role System Manager/Administrator.

Nói cách khác: đổi/thu hồi quyền = vào Frappe xoá/tạo lại API Key của người
đó, không cần đụng gì tới server MCP.

## Chạy thử local

```bash
cd voice_app/mcp_server
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

VOICE_APP_BASE_URL=http://ct-datalake.localhost:8002 \
  .venv/bin/python server.py
```

Server lắng nghe ở `http://127.0.0.1:8010/mcp`. Test nhanh bằng curl:

```bash
# Lấy API key/secret của chính bạn trước (Desk > My Settings > API Access)
curl -X POST http://127.0.0.1:8010/mcp \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer <api_key>:<api_secret>" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"voice_app_list_meetings","arguments":{"params":{"limit":5}}}}'
```

Hoặc dùng MCP Inspector chính thức để có giao diện:
```bash
npx @modelcontextprotocol/inspector
```

## Deploy lên devapp.ctpai.vn

**1. Cài đặt (trên server, không phải máy local):**
```bash
cd /path/to/frappe-bench/apps/voice_app/voice_app/mcp_server
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**2. Chạy như systemd service** (`/etc/systemd/system/voice-app-mcp.service`):
```ini
[Unit]
Description=voice_app MCP server
After=network.target

[Service]
Type=simple
User=frappe
WorkingDirectory=/path/to/frappe-bench/apps/voice_app/voice_app/mcp_server
Environment=VOICE_APP_BASE_URL=https://devapp.ctpai.vn
Environment=VOICE_APP_MCP_HOST=127.0.0.1
Environment=VOICE_APP_MCP_PORT=8010
ExecStart=/path/to/frappe-bench/apps/voice_app/voice_app/mcp_server/.venv/bin/python server.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now voice-app-mcp
sudo systemctl status voice-app-mcp
```

**3. Trỏ qua nginx** (thêm vào block server hiện có của devapp.ctpai.vn,
CHỈ thêm location mới — không đụng các location khác đang phục vụ site
Frappe):
```nginx
location /mcp {
    proxy_pass http://127.0.0.1:8010/mcp;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header Authorization $http_authorization;
    # Streamable HTTP giữ kết nối mở lâu hơn request thường
    proxy_read_timeout 300s;
    proxy_buffering off;
}
```
```bash
sudo nginx -t && sudo systemctl reload nginx
```

Sau bước này, MCP server có ở `https://devapp.ctpai.vn/mcp`.

**Lưu ý bảo mật:** dòng `proxy_set_header Authorization $http_authorization;`
là bắt buộc — nginx mặc định vẫn chuyển tiếp header Authorization, nhưng nếu
site đã có cấu hình xoá header này ở chỗ khác (một số setup reverse-proxy
làm vậy để tự chèn auth riêng) thì phải thêm dòng này tường minh, nếu không
mọi request sẽ rơi vào nhánh "Thiếu Authorization".

## Thêm vào ChatGPT

ChatGPT (Settings → Connectors → thêm connector tuỳ chỉnh) hiện hỗ trợ cấu
hình MCP server qua URL, kèm một trong vài kiểu xác thực (No auth / API key /
OAuth) tuỳ phiên bản ChatGPT đang dùng — **giao diện chính xác có thể khác
với những gì tài liệu này mô tả vì đó là quyết định của phía OpenAI, không
kiểm soát được từ đây.** Các bước chung:

1. URL server: `https://devapp.ctpai.vn/mcp`
2. Chọn kiểu xác thực có gửi được header `Authorization` tuỳ chỉnh (thường
   gọi là "API key" hoặc "Bearer token") — dán `<api_key>:<api_secret>` của
   chính bạn (lấy từ Desk → My Settings → API Access → Generate Keys)
3. Nếu ChatGPT chỉ cho chọn OAuth mà không có tuỳ chọn API key tĩnh, server
   này CHƯA hỗ trợ — cần triển khai thêm OAuth 2.1 Authorization Server
   (ngoài phạm vi bản hiện tại, xem mục "Giới hạn hiện tại" bên dưới).

Sau khi kết nối, thử hỏi ChatGPT: *"Liệt kê các cuộc họp gần đây của tôi"*
hoặc *"Nội dung cuộc họp MEETING-2088 nói gì?"*.

## Giới hạn hiện tại

- **Chỉ đọc**: không có tool tạo meeting mới / upload audio / trích xuất
  task. Nếu cần các tính năng đó qua MCP, phải bổ sung thêm tool và cân nhắc
  kỹ vì chúng tốn tiền Gemini mỗi lần gọi.
- **Không có OAuth**: xác thực dựa trên việc người dùng tự dán API key của
  Frappe vào ChatGPT. Nếu ChatGPT bắt buộc OAuth cho custom connector, bản
  này chưa dùng được ngay — cần thêm `AuthSettings` + Authorization Server
  của SDK MCP.
- **Chưa test thật với ChatGPT** — mới verify bằng curl trực tiếp tới JSON-RPC
  endpoint. Hành vi thực tế khi ChatGPT gọi vào có thể khác đôi chút (cách nó
  gửi header, cách nó hiển thị lỗi) và cần kiểm chứng khi có tài khoản
  ChatGPT hỗ trợ MCP connector để thử trực tiếp.
