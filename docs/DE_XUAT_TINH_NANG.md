# Lộ trình & Đề xuất Tính năng Mở rộng cho QT PDF Pro

> Giai đoạn 1 (hiện tại) tập trung hoàn thiện **2 chức năng cốt lõi**: **Trình đọc PDF chuyên nghiệp** và **Chuyển đổi PDF sang DOCX chuẩn xác**. Tài liệu này ghi lại lộ trình các giai đoạn tiếp theo để các Agent sau phát triển nối tiếp.

---

## Giai đoạn 1 (v0.1.x – v1.0.0): Đọc PDF & Chuyển đổi PDF sang DOCX Chuẩn xác *(Đang thực hiện)*

- [x] **Trình đọc PDF tốc độ cao**:
  - Mở nhiều tệp PDF trên nhiều tab (`QTabWidget`), kéo-thả tệp vào cửa sổ.
  - Chế độ cuộn liên tục (`Continuous Scroll`) và xem từng trang (`Single Page`).
  - Thu phóng linh hoạt (`25%` – `400%`, Vừa chiều ngang, Vừa trang, `Ctrl + Cuộn chuột`), xoay trang `90°`.
  - Sidebar 4 ngăn: **Trang thu nhỏ (Thumbnails)**, **Mục lục (Bookmarks/TOC)**, **Tìm kiếm toàn văn (Full-text Search)** có tô sáng vị trí trên trang, và **Phân tích bố cục (Layout Inspector)** hiển thị khung nhận diện Văn bản / Bảng biểu / Hình ảnh / Vector trực tiếp trên trang PDF.
  - Chọn & sao chép văn bản trên trang, xem thông tin metadata tài liệu, giao diện Sáng / Tối hiện đại.
- [x] **Engine chuyển đổi PDF sang DOCX đa chế độ**:
  - **Chế độ 1 (`Hybrid Structural Flow`)**: Tái tạo cấu trúc đoạn văn, bảng biểu, cột, hình ảnh + Bộ hậu xử lý `OpenXML Precision Fixer` (chuẩn hoá phông chữ 4 thuộc tính, sửa lỗi tiếng Việt NFC/TCVN3/VNI, khoá lề bảng, tắt `snapToGrid` chống tràn trang).
  - **Chế độ 2 (`Exact Visual Layout 1:1`)**: Giữ nguyên vị trí từng thành phần tuyệt đối 1:1 bằng khung toạ độ `w:framePr` kết hợp lớp nền đồ hoạ vector/ảnh.
  - **Chế độ 3 (`MS Word Native Reflow Bridge`)**: Tích hợp bộ chuyển đổi của Microsoft Word (khi máy có cài Office) + hậu xử lý OpenXML.
  - **Bộ Kiểm định Độ chính xác (`Fidelity Inspector`)**: Chấm điểm độ chính xác sau khi chuyển đổi (tỷ lệ giữ chữ, số trang, bảng biểu, hình ảnh, phông chữ).

---

## Giai đoạn 2 (v1.1.0): OCR Tiếng Việt cho PDF Scan & Công thức Toán học

1. **Tích hợp OCR thông minh cho PDF ảnh quét (Scanned PDF)**:
   - Tự động phát hiện trang PDF không có lớp văn bản (chỉ có ảnh scan).
   - Kết hợp `Tesseract OCR (vie+eng)` + `VietOCR` / `Surya Layout` để nhận diện chữ tiếng Việt in và bảng biểu trên trang scan, sau đó xuất ra DOCX có đúng bố cục.
2. **Nhận diện Công thức Toán học (OMML)**:
   - Chuyển các ký hiệu toán học/phân số/căn thức trong PDF sang định dạng phương trình gốc của Word (`Office MathML - <m:oMath>`) thay vì ảnh tĩnh.
3. **Chuyển đổi hàng loạt (Batch Conversion)**:
   - Cho phép kéo-thả hàng chục tệp PDF để chuyển đổi song song sang DOCX với báo cáo tổng hợp.

---

## Giai đoạn 3 (v1.2.0): Công cụ Biên tập & Tổ chức Trang PDF

1. **Ghép, Tách, Xoay, Xoá, Sắp xếp lại trang PDF** bằng giao diện kéo-thả trực quan trên lưới trang thu nhỏ.
2. **Chú thích & Đánh dấu (Annotations)**:
   - Tô sáng văn bản (Highlight), gạch chân, thêm ghi chú (Sticky Note), vẽ khung, đóng dấu (Stamp "ĐÃ DUYỆT", "BẢN SAO") và lưu trực tiếp vào PDF.
3. **Chuyển đổi đa chiều**:
   - Xuất PDF sang Excel (`.xlsx` chuyên cho bảng biểu tài chính), PowerPoint (`.pptx`), hoặc ảnh chất lượng cao (`.png`/`.tiff`).

---

## Giai đoạn 4 (v2.0.0): Chữ ký số (USB Token / VGCA) & Bảo mật PDF

1. **Ký số PDF chuẩn PAdES**: Hỗ trợ hiển thị và kiểm tra chữ ký số Việt Nam (VGCA, Viettel-CA, VNPT-CA).
2. **Đặt mật khẩu bảo vệ / Gỡ mật khẩu PDF** (khi biết mật khẩu) và xoá thông tin nhạy cảm (`Redaction`).
