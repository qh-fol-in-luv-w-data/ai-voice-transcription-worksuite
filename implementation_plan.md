# Tích hợp AI cập nhật hàng loạt giọng nói từ một chỉnh sửa (Inline Edit)

Tính năng này cho phép người dùng khi sửa tên trên một dòng hội thoại (inline edit) có thể chọn "Học giọng & Quét lại" để hệ thống tự động nhận diện mẫu giọng từ dòng đó và dùng AI quét lại toàn bộ file âm thanh, gán lại tên cho tất cả những đoạn hội thoại có chất giọng tương tự.

## User Review Required

- Việc "quét lại toàn bộ" sẽ tốn thời gian (có thể mất từ vài chục giây đến vài phút tùy theo độ dài cuộc họp) vì hệ thống phải trích xuất và so sánh đặc trưng giọng nói (embedding) của từng đoạn hội thoại trong file. Bạn có muốn xử lý tác vụ này chạy ngầm (background job) và hiển thị thanh tiến trình không, hay chỉ cần hiển thị một vòng xoay loading ở giao diện cho đến khi hoàn tất?
- Nút bấm mới sẽ được thêm vào ngay cạnh nút "Lưu" khi bạn sửa tên. Gợi ý tên nút: **Lưu & Quét lại AI**.

## Proposed Changes

---

### Backend (Python API)

#### [MODIFY] [api.py](file:///Users/_qh.fol_/frappe-bench/apps/voice_app/voice_app/api.py)
- Thêm endpoint mới `@frappe.whitelist()` `reassign_speaker_from_segment`.
- **Tham số nhận vào:** `meeting_name`, `segment_index`, `new_speaker_name`.
- **Logic:**
  1. Lấy dữ liệu `raw_results` hiện tại và lấy ra segment tại vị trí `segment_index`.
  2. Dùng `_extract_embedding_subprocess` cắt âm thanh từ `start` tới `end` của segment đó để lấy mẫu (embedding).
  3. Đăng ký mẫu giọng đó vào Database `Voice Speaker` với tên `new_speaker_name`.
  4. Duyệt qua tất cả các segments còn lại trong cuộc họp. Tính cosine similarity giữa embedding của từng segment với mẫu giọng mới.
  5. Nếu độ tương đồng (similarity) vượt ngưỡng `SIMILARITY_THRESHOLD` thì đổi tên đoạn đó thành `new_speaker_name`.
  6. Lưu lại `raw_results` và `transcript`, trả về kết quả mới nhất cho giao diện.

---

### Frontend (Vue.js)

#### [MODIFY] [VoiceTranscribe.vue](file:///Users/_qh.fol_/frappe-bench/apps/voice_app/frontend/src/views/VoiceTranscribe.vue)
- Thêm một nút **"Lưu & Quét lại AI"** (hoặc một biểu tượng quét) trong chế độ chỉnh sửa (khi biến `editingSpeaker === idx` được bật).
- Viết hàm `saveAndRescanSpeaker(idx)` để gọi API `reassign_speaker_from_segment`.
- Bật trạng thái loading toàn màn hình (hoặc loading nội bộ bảng) khi gọi API vì thao tác quét lại có thể mất thời gian.
- Nhận mảng `results` trả về và cập nhật lại giao diện ngay lập tức.

#### [MODIFY] [api.js](file:///Users/_qh.fol_/frappe-bench/apps/voice_app/frontend/src/api.js)
- Định nghĩa hàm API gọi đến backend `reassign_speaker_from_segment`.

## Verification Plan

### Manual Verification
1. Mở một biên bản họp có các đoạn thoại bị gán nhầm người ("Trần Kim Chung" nhưng thực tế là người khác).
2. Nhấn nút "Sửa" (biểu tượng cây bút) trên dòng bị gán sai, chọn tên người nói đúng.
3. Nhấn nút "Lưu & Quét lại AI".
4. Đợi hệ thống xử lý xong, quan sát xem các đoạn hội thoại khác trong cùng file có giọng nói giống vậy có tự động chuyển đổi thành tên vừa sửa không.
