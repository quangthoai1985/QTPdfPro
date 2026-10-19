# Lịch sử thay đổi (Changelog)

Định dạng theo [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/); phiên bản theo [SemVer](https://semver.org/lang/vi/).
**Quy tắc bắt buộc cho mọi Agent**: Sau mỗi phiên làm việc, phải cập nhật mục mới **ở trên cùng** của tệp này (ngày giờ, việc đã làm, kết quả test, lỗi gặp phải, việc còn dở), cập nhật [CLAUDE.md](CLAUDE.md), rồi `git commit` và `git push` lên GitHub.

---

## [Chưa phát hành]

### Việc còn dở / Ưu tiên kế tiếp cho Agent phiên sau
1. **Kiểm thử thực tế với bộ mẫu PDF đa dạng ngoài đời thực**:
   - Thử nghiệm chuyển đổi ≥ 15 tệp PDF phức tạp thật (công văn/nghị định hành chính nhà nước có Quốc hiệu – Tiêu ngữ 2 cột, bảng biểu tài chính nhiều cột hẹp, hợp đồng nhiều trang, biểu mẫu có con dấu đỏ đè lên chữ).
   - Mở trực tiếp các tệp `.docx` đầu ra bằng Microsoft Word (`WINWORD.EXE`) và đối chiếu ảnh chụp từng trang để tinh chỉnh thêm hệ số `line_spacing` và `tcMar` trong `core/openxml_fixer.py`.
2. **Tái tạo nâng cao cho khối Quốc hiệu – Tiêu ngữ không viền**:
   - Bổ sung heuristic trong `core/layout_analyzer.py` và `core/openxml_fixer.py` để tự động gom 2 khối chữ song song ở đầu trang 1 của văn bản hành chính Việt Nam vào bảng ẩn viền 2 cột cân đối kèm đường kẻ chân dưới dòng *"Độc lập - Tự do - Hạnh phúc"*.
3. **Tích hợp OCR Tiếng Việt cho PDF ảnh quét (Scanned PDF)**:
   - Khi `PageLayoutSummary.is_scanned == True`, hiển thị gợi ý bật OCR (`Tesseract vie+eng` / `VietOCR`) để chuyển PDF scan sang DOCX chỉnh sửa được.
4. **Chuyển đổi hàng loạt (Batch PDF → DOCX)** và đóng gói bản phát hành `QTPdfPro-0.1.0-win64.zip` lên GitHub Releases.

---

## [0.1.0] — 2026-10-19 (Phiên khởi tạo dự án & Phát triển nền tảng Giai đoạn 1)

### Thêm mới
- **Khởi tạo dự án & Hệ thống tài liệu bàn giao Agent**:
  - Tạo kho lưu trữ GitHub `quangthoai1985/QTPdfPro` và cấu trúc dự án chuẩn mã nguồn mở MIT (`LICENSE`, `README.md`, `CLAUDE.md`, `AGENTS.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `THIRD_PARTY_NOTICES.md`).
  - Viết báo cáo nghiên cứu & đề xuất công nghệ chi tiết tại [docs/NGHIEN_CUU_CONG_NGHE.md](docs/NGHIEN_CUU_CONG_NGHE.md), thiết kế kiến trúc kỹ thuật tại [docs/THIET_KE.md](docs/THIET_KE.md) và lộ trình mở rộng tại [docs/DE_XUAT_TINH_NANG.md](docs/DE_XUAT_TINH_NANG.md).
- **Chức năng 1 — Trình đọc PDF chuyên nghiệp (`qtpdfpro/core/reader.py`, `qtpdfpro/ui/main_window.py`, `qtpdfpro/ui/pdf_canvas.py`)**:
  - Đọc và kết xuất trang PDF tốc độ cao bằng `PyMuPDF` (`fitz`) hỗ trợ màn hình High-DPI, có bộ nhớ đệm `LRU Cache` 24 trang.
  - Giao diện đa tab tài liệu (`QTabWidget`), hỗ trợ kéo-thả tệp `.pdf`, danh sách tệp mở gần đây, đổi chủ đề Sáng / Tối (`qtpdfpro/ui/theme.py`).
  - Hỗ trợ chế độ cuộn liên tục (`Continuous Scroll`) và từng trang (`Single Page`), thu phóng `25% – 400%` (`Ctrl + Cuộn chuột`), Vừa chiều ngang, Vừa trang, xoay trang `90°`.
  - Sidebar 4 ngăn: **Trang thu nhỏ (Thumbnails)**, **Mục lục (Bookmarks/TOC)**, **Tìm kiếm toàn văn tiếng Việt** (tô sáng vị trí từ khoá trên trang và tự cuộn tới đúng toạ độ), và **Soi bố cục (Layout Inspector)** vẽ trực tiếp khung nhận diện Văn bản / Bảng biểu / Hình ảnh / Vector lên trang PDF.
- **Chức năng 2 — Chuyển đổi PDF sang DOCX chuẩn xác đa chế độ (`qtpdfpro/core/converter.py`)**:
  - **Chế độ `hybrid` (Mặc định)**: Kết hợp `pdf2docx` tái tạo cấu trúc đoạn văn, bảng biểu, cột, hình ảnh với cấu hình dung sai tối ưu + **Bộ Hậu xử lý Chuẩn xác OpenXML (`qtpdfpro/core/openxml_fixer.py`)** can thiệp bằng `lxml`.
  - **Chế độ `exact` (`qtpdfpro/core/exact_layout_engine.py`)**: Giữ nguyên vị trí tuyệt đối 1:1 bằng cách tách riêng lớp đồ hoạ vector/ảnh làm nền (`apply_redactions` giữ nguyên ảnh & vector) neo dưới chữ (`wp:anchor behindDoc="1"`) và đặt từng dòng chữ vào khung toạ độ OpenXML `<w:framePr>` theo đơn vị `twips`.
  - **Chế độ `word_com` (`qtpdfpro/core/word_com_bridge.py`)**: Cầu nối gọi Microsoft Word Reflow qua COM (khi máy có cài Office) kết hợp hậu xử lý OpenXML.
  - **Chế độ `auto`**: Tự động phân tích trang PDF để chọn `hybrid` hoặc `exact`.
  - **Bộ Chuẩn hoá Phông chữ & Tiếng Việt (`qtpdfpro/core/font_resolver.py`)**: Gỡ tiền tố subset `ABCDEF+`, ánh xạ tên phông PostScript sang phông chuẩn Windows trên cả 4 thuộc tính (`w:ascii`, `w:hAnsi`, `w:cs`, `w:eastAsia`), chuẩn hoá Unicode NFD → NFC và chuyển mã TCVN3 (`.Vn*`) sang Unicode.
  - **Bộ Kiểm định Độ chính xác (`qtpdfpro/core/fidelity.py`)**: Đối chiếu PDF gốc và DOCX đầu ra, tính điểm chuẩn xác tổng hợp (`overall_score %`), tỷ lệ giữ từ vựng/ký tự, số bảng biểu, khung, hình ảnh.
  - **Giao diện dòng lệnh CLI (`qtpdfpro/cli.py`)**: Hỗ trợ các lệnh `convert`, `inspect`, `verify` kèm xuất JSON.
- **Kiểm thử tự động (`tests/`)**:
  - Xây dựng bộ test `pytest` gồm 5 tệp kiểm thử (`test_version.py`, `test_font_resolver.py`, `test_reader.py`, `test_converter_fidelity.py`, `test_ui.py`), 15/15 bài test vượt qua 100%, cô lập hoàn toàn dữ liệu qua biến môi trường `QT_PDF_PRO_DATA`.

### Sửa lỗi & Tinh chỉnh kỹ thuật phát hiện trong quá trình kiểm thử
- **Vá lỗi mất cột thứ 2/3 trong `pdf2docx` (`RawPage._create_section`)**: Khi trang PDF có Quốc hiệu – Tiêu ngữ 2 cột phía trên và tiêu đề *"QUYẾT ĐỊNH"* căn giữa phía dưới, `group_by_columns()` của `pdf2docx` tách thành 3 cụm X và chỉ lấy dải Y của cụm giữa, làm mất dòng *"Độc lập - Tự do - Hạnh phúc"*. Đã bổ sung bản vá `_install_pdf2docx_patches()` trong `qtpdfpro/core/converter.py` để hợp nhất dải Y của mọi cụm cột, giữ đủ 100% văn bản.
- **Xử lý khoảng trắng không ngắt (`\u00a0` NBSP) và gạch nối mềm (`\u00ad`) từ phông TrueType**: Nhiều tệp PDF nhúng phông `Times New Roman` ánh xạ khoảng trắng sang `U+00A0` khiến Word coi cả đoạn là 1 từ dài không ngắt dòng được. Đã chuẩn hoá về `U+0020` và `U+002D` trong `font_resolver.py`.
- **Ẩn thông báo phụ ra `stdout` của `PyMuPDF 1.27+` (`pymupdf_layout`)**: Bọc `page.find_tables()` bằng `redirect_stdout` để đầu ra `--json` của CLI luôn sạch tuyệt đối.
