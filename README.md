# QT PDF Pro

**QT PDF Pro** là ứng dụng chuyên đọc tài liệu PDF tốc độ cao kèm chức năng chủ đạo **chuyển đổi PDF sang Word (`.docx`) chuẩn xác từng thành phần** dành cho Windows, viết bằng **Python 3.14 + PySide6 (Qt6) + PyMuPDF + Hybrid OpenXML Engine**.

- **Giấy phép**: MIT License ([LICENSE](LICENSE))
- **Bàn giao cho AI Agent**: Đọc [CLAUDE.md](CLAUDE.md) và [AGENTS.md](AGENTS.md) trước khi bắt đầu phiên làm việc.
- **Nhật ký phiên bản**: [CHANGELOG.md](CHANGELOG.md)
- **Nghiên cứu & Đề xuất công nghệ**: [docs/NGHIEN_CUU_CONG_NGHE.md](docs/NGHIEN_CUU_CONG_NGHE.md)
- **Thiết kế kiến trúc**: [docs/THIET_KE.md](docs/THIET_KE.md)

---

## 1. Tính năng cốt lõi

### 1.0. Văn bản hành chính chuẩn Nghị định 30/2020/NĐ-CP (mới ở `v0.3.0`)
- **Chế độ `nd30`** (chế độ `auto` tự chọn khi phát hiện Quốc hiệu – Tiêu ngữ): dựng DOCX như người soạn thảo trong Word — lề, cỡ chữ, khoảng cách dòng, khoảng cách đoạn, thụt đầu dòng được **đo trên PDF rồi ước lượng về giá trị gốc** (vd lề trái đo 29,98 mm → 30 mm, giãn dòng 24,13 pt ở cỡ 14 → 1,5 lines); phần đầu văn bản và khối ký đặt trong **bảng 2 cột không viền**; đường kẻ dưới tên cơ quan / Tiêu ngữ / trích yếu **giữ đúng toạ độ và độ dài như PDF**; số trang là trường `PAGE` ở đầu trang, không hiện ở trang 1.
- **Giữ đúng bố cục PDF là ưu tiên số 1**: chính sách mặc định `faithful` chỉ làm tròn khi sai số đo nhỏ; chính sách `nd30` (tuỳ chọn) mới ép chuẩn hoá theo NĐ30.
- **Đối chiếu thể thức** 26 hạng mục (lề, phông, cỡ chữ, giãn dòng, cách đoạn ≥ 6 pt, Quốc hiệu, Tiêu ngữ, đường kẻ, số ký hiệu, ngày tháng, Nơi nhận, «Lưu: VT», số trang…).
- **Kiểm chứng bằng Microsoft Word**: dựng lại DOCX bằng Word và so vị trí từng dòng với PDF gốc (trên văn bản mẫu: 100% dòng khớp, lệch ≤ 0,84 pt ≈ 0,3 mm).

### 1.1. Chuyển đổi PDF sang Word (`.docx`) chuẩn xác (Chức năng chủ đạo)
Khắc phục triệt để hiện tượng *vỡ khung, nhảy dòng, tràn trang, lỗi phông tiếng Việt* thường gặp ở các công cụ chuyển đổi thông thường nhờ **Kiến trúc Đa Chế độ + Bộ Hậu xử lý Chuẩn xác OpenXML (`lxml`)**:

1. **Chế độ 1 — Chuẩn cấu trúc thông minh (`Hybrid Structural Flow` — Mặc định)**:
   - Tái tạo đầy đủ `Section` (1 cột / nhiều cột), `Paragraph`, `Table` (cả bảng có viền và bảng ẩn viền như Quốc hiệu – Tiêu ngữ, phần ký tên), màu nền ô, đường kẻ vector và hình ảnh độ phân giải gốc.
   - **Chuẩn hoá phông chữ 4 thuộc tính (`w:ascii`, `w:hAnsi`, `w:cs`, `w:eastAsia`)**: Tự động gỡ tiền tố subset (`ABCDEF+TimesNewRomanPSMT` → `Times New Roman`), khôi phục cờ Đậm/Nghiêng từ tên phông PostScript, ngăn Word tự thay phông lạ làm lệch độ rộng dòng.
   - **Chuẩn hoá tiếng Việt (`Unicode NFC` & `TCVN3 .Vn*`)**: Gộp dấu tổ hợp rời (NFD → NFC) và hỗ trợ chuyển mã TCVN3 sang Unicode dựng sẵn.
   - **Khoá lề bảng cố định (`w:tblLayout="fixed"`) & thu gọn đệm ô (`w:tcMar`)**: Giảm lề mặc định của ô bảng từ `108 dxa` (`5.4pt`) xuống `36 dxa` (`1.8pt`), ngăn chữ trong cột hẹp bị ép rớt dòng.
   - **Chống tràn trang (`w:snapToGrid="0"` & vi chỉnh khoảng cách chữ)**: Tắt bắt dính lưới dòng của Word, giữ nguyên số dòng trên mỗi trang đúng như PDF.
2. **Chế độ 2 — Giữ nguyên vị trí tuyệt đối 1:1 (`Exact Visual Layout 1:1`)**:
   - Dành cho biểu mẫu (form), hoá đơn, văn bằng, tài liệu nhiều khung phức tạp.
   - Tách riêng lớp đồ hoạ vector/ảnh làm nền sắc nét phía sau (`wp:anchor behindDoc="1"`), đặt từng dòng văn bản vào khung toạ độ tuyệt đối OpenXML (`<w:framePr>`) tính bằng `twips` (`1 pt = 20 twips`). Khi mở trong Word, vị trí từng chữ trùng khít 100% tới từng milimet và vẫn chỉnh sửa được bình thường.
3. **Chế độ 3 — Cầu nối Microsoft Word Native Reflow (`MS Word COM Bridge`)**:
   - Tận dụng bộ chuyển đổi PDF Reflow thương mại của Microsoft Office (khi máy có cài MS Word) kết hợp với Bộ Hậu xử lý Chuẩn xác OpenXML.
4. **Bộ Kiểm định Độ chính xác (`Fidelity Inspector`)**:
   - Tự động đối chiếu PDF gốc và DOCX đầu ra sau mỗi lần chuyển đổi, chấm **Điểm chuẩn xác (%)**, thống kê tỷ lệ bảo toàn từ vựng, số bảng biểu, hình ảnh và danh sách phông chữ.

### 1.2. Trình đọc PDF chuyên nghiệp & Trang chủ kiểu PdfCraft
- **Trang chủ theo [storytold/pdfcraft](https://github.com/storytold/pdfcraft)**: cột «Tất cả công cụ» (tìm không dấu, lọc theo chế độ Đọc · Chuyển đổi · Chỉnh sửa · Ký số & Bảo mật), «Công cụ đề xuất», thẻ «Mở tệp» (kéo thả), «Gần đây», bảng lệnh `Ctrl+K`. Công cụ đang phát triển hiển thị **«Coming Soon»**.
- **Đa tab tài liệu**, hỗ trợ kéo-thả tệp `.pdf` trực tiếp vào cửa sổ.
- **Kết xuất sắc nét tốc độ cao** qua `PyMuPDF` (`fitz`), hỗ trợ màn hình High-DPI, bộ nhớ đệm trang thông minh (`LRU Cache`).
- **Chế độ xem linh hoạt**: Cuộn liên tục (`Continuous Scroll`), Từng trang (`Single Page`), Vừa chiều ngang (`Fit Width`), Vừa trang (`Fit Page`), thu phóng `25% – 400%` (`Ctrl + Cuộn chuột`), xoay trang `90°`.
- **Thanh bên (Sidebar) 4 ngăn**:
  1. **Trang**: Danh sách ảnh thu nhỏ (Thumbnails) của từng trang.
  2. **Mục lục**: Cây mục lục (Bookmarks / Outline) điều hướng nhanh.
  3. **Tìm kiếm**: Tìm kiếm toàn văn tiếng Việt, hiển thị ngữ cảnh và **tô sáng vị trí từ khoá** ngay trên trang PDF.
  4. **Soi bố cục (Layout Inspector)**: Hiển thị trực tiếp các khung nhận diện **Văn bản (Xanh dương)**, **Bảng biểu (Xanh lá)**, **Hình ảnh (Cam)**, **Vector (Tím)** trên trang PDF trước khi chuyển sang Word.
- Giao diện **Tối (Dark)** và **Sáng (Light)** hiện đại chuẩn Windows 11.

---

## 2. Cài đặt & Sử dụng

### Yêu cầu hệ thống
- Windows 10 / 11 (64-bit)
- Python 3.11+ (đã kiểm thử trên **Python 3.14.5**)

### Cài đặt thư viện
```bash
python -m pip install -r requirements.txt
```

### Khởi chạy giao diện đồ hoạ (GUI)
```bash
python -m qtpdfpro
# Hoặc chạy tệp batch trên Windows:
run.bat
# Mở trực tiếp một hoặc nhiều tệp PDF:
python -m qtpdfpro tailieu.pdf
```

### Sử dụng qua dòng lệnh (CLI)
```bash
# Chuyển đổi PDF sang DOCX (chế độ hybrid mặc định)
python -m qtpdfpro.cli convert tailieu.pdf -o tailieu.docx --mode hybrid

# Chuyển đổi giữ nguyên vị trí tuyệt đối 1:1 cho trang 1 đến 3
python -m qtpdfpro.cli convert bieumau.pdf -o bieumau.docx --mode exact --pages 1-3

# Phân tích cấu trúc bố cục tệp PDF
python -m qtpdfpro.cli inspect tailieu.pdf

# Kiểm định độ chính xác giữa PDF gốc và DOCX
python -m qtpdfpro.cli verify tailieu.pdf tailieu.docx
```

### Chạy kiểm thử tự động & Đóng gói `.exe`
```bash
python -m pytest -q tests
build.bat
```
