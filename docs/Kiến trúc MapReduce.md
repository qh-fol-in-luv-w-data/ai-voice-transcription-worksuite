# STT MapReduce Architecture Walkthrough

Chào bạn, tôi đã hoàn thành toàn bộ yêu cầu của bạn, bao gồm cả những đóng góp tối ưu thêm của bạn! Dưới đây là tóm tắt những thay đổi đã được áp dụng vào hệ thống `2AS-Worksuite`.

## 🛠 Những Thay Đổi Chính

### 1. Kiến Trúc "Voice Meeting Chunk" (MapReduce)
- **Tạo DocType Mới:** Đã tạo `Voice Meeting Chunk` (schema JSON và class Python). Mỗi đoạn cắt 15 phút sẽ được ánh xạ thành 1 bản ghi độc lập trên cơ sở dữ liệu Frappe với trạng thái riêng (`Pending`, `Processing`, `Completed`, `Error`).
- **Lưu File Vật Lý:** Thay vì dùng file tạm (tempfile), thuật toán cắt âm thanh (`split_audio_by_silence`) giờ đây lưu các file `.wav` trực tiếp vào thư mục `[site]/private/files/voice_chunk/{meeting_name}`.
- **Tính Chịu Lỗi (Fault-Tolerance):** Cơ chế `resume_transcription` đã được làm mới. Thay vì rà soát lộn xộn từ chuỗi trả về, hệ thống chỉ cần đọc DB và **chỉ gửi lại các chunk có trạng thái `Pending` hoặc `Error`**. Các chunk đã `Completed` sẽ được tái sử dụng 100%.

### 2. Tối Ưu Hóa Gemini STT (Upload Song Song)
Theo đúng thông số gói Paid Tier của bạn:
- **Semaphore(4) & max_workers=4:** Đã điều chỉnh cả Semaphore bảo vệ File Upload và luồng xử lý đồng thời (Thread Pool) xuống `4`. Việc này cho phép 4 chunk được upload *cùng lúc* lên máy chủ Google mà không gặp tình trạng thắt cổ chai lãng phí như phiên bản trước.
- **Giảm Kích Thước Chunk:** `chunk_length_sec` được hạ từ 30 phút xuống **15 phút (900 giây)**. Các đoạn chia nhỏ hơn sẽ ít lỗi Context Limit và Smart Resume chạy cũng nhanh hơn.

### 3. Tự Động Dọn Dẹp (Garbage Collection)
Để tiết kiệm tối đa dung lượng ổ cứng, 2 cơ chế dọn dẹp đã được thêm vào `api.py`:
- **Dọn Dẹp Nóng:** Ngay sau khi tất cả các chunk hoàn thành và ghép nối thành công, hàm `cleanup_chunk_files` sẽ tự động xóa ngay lập tức toàn bộ các file wav 15 phút của meeting đó.
- **Cronjob Daily:** Một cronjob (Chạy theo lịch hàng ngày) `voice_app.api.cleanup_old_chunks` đã được đăng ký vào `hooks.py`. Nó sẽ đi quét thư mục `private/files/voice_chunk` để xóa sạch những thư mục rác (bị sập giữa chừng không kịp xóa nóng) nếu meeting đã hoàn tất hoặc đã để quá 3 ngày.

## 🚀 Hướng Dẫn Sử Dụng / Kiểm Tra

> [!WARNING]
> Vì có một DocType mới tinh được tạo ra, bạn hãy mở Terminal của máy chủ và chạy lệnh sau để cập nhật cơ sở dữ liệu trước khi test:
> ```bash
> bench --site devapp.ctpai.vn migrate
> ```
> *(Thay `devapp.ctpai.vn` bằng tên site chính xác của bạn nếu dùng site khác)*

**Cách Kiểm Tra Lỗi:**
1. Upload một file ghi âm dài (~30 phút).
2. Vào giao diện Frappe Desk, tìm DocType **Voice Meeting Chunk**. Bạn sẽ thấy các bản ghi được tạo ra và chuyển dần từ `Pending` -> `Processing` -> `Completed`.
3. Tắt server ngang chừng để cố tình ép lỗi.
4. Bật server lên và bấm nút Resume trên frontend. Bạn sẽ thấy hệ thống bỏ qua ngay lập tức các Chunk đã xong và chỉ chạy lại đoạn còn thiếu!
5. Kiểm tra ổ cứng tại `frappe-bench/sites/devapp.ctpai.vn/private/files/voice_chunk/` xem khi chạy xong hệ thống có dọn sạch không nhé!
