# Lịch sử thay đổi (Changelog)

Định dạng theo [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/); phiên bản theo [SemVer](https://semver.org/lang/vi/).
**Quy tắc bắt buộc cho mọi Agent**: Sau mỗi phiên làm việc, phải cập nhật mục mới **ở trên cùng** của tệp này (ngày giờ, việc đã làm, kết quả test, lỗi gặp phải, việc còn dở), cập nhật [CLAUDE.md](CLAUDE.md), rồi `git commit` và `git push` lên GitHub.

---

## [Chưa phát hành]

### Việc còn dở / Ưu tiên kế tiếp cho Agent phiên sau
1. **Tích hợp OCR Tiếng Việt cho PDF ảnh quét (Scanned PDF)**:
   - Khi `PageLayoutSummary.is_scanned == True`, hiển thị gợi ý bật OCR (`Tesseract vie+eng` / `VietOCR`) để chuyển PDF scan sang DOCX chỉnh sửa được mà vẫn giữ nguyên con dấu đỏ và chữ ký.
2. **Chuyển đổi hàng loạt (Batch PDF → DOCX)**:
   - Thêm hộp thoại chuyển đổi hàng loạt nhiều công văn/quyết định PDF sang DOCX cùng lúc kèm bảng báo cáo điểm chuẩn xác (`FidelityReport`).
3. **Đóng gói bản phát hành độc lập**:
   - Đóng gói `QTPdfPro-0.2.0-win64.zip` bằng `build.bat` (PyInstaller) và đẩy lên GitHub Releases.

---

## [0.2.0] — 2026-10-19 (Hoàn thiện Chuyển đổi Văn bản Hành chính Việt Nam 100% & Giao diện PdfCraft Sáng/Tối)

### Thêm mới
- **Bảo toàn 100% thành phần văn bản hành chính Việt Nam có chữ ký số & đóng dấu (`qtpdfpro/core/converter.py`, `qtpdfpro/core/openxml_fixer.py`)**:
  - **Ghép tự động số hiệu & ngày tháng đóng dấu đè (`_splice_overlapping_stamped_text`)**: Trong các văn bản hành chính ký số (VGCA), số văn bản (`"3865"`) và ngày ban hành (`"14"`) được đóng dấu đè lên khoảng trắng của dòng mẫu (`"Số:           /QĐ-UBND"`, `"An Giang, ngày      tháng 8 năm 2026"`). Can thiệp trực tiếp vào `RawPageFitz._preprocess_text` để chèn các ký tự đóng dấu vào đúng khe khoảng trắng của dòng gốc trước khi `pdf2docx` chạy bước lọc chồng lấp.
  - **Trích xuất Chữ ký số, Con dấu đỏ UBND & Chữ ký nháy từ PDF Signature Widgets (`_extract_widget_overlays`)**: Duyệt cây đối tượng `/AP /N -> /FRM -> /n2` của mọi `page.widgets()`, giải mã ảnh gốc kết hợp kênh mặt nạ Alpha (`/SMask`) thành ảnh PNG RGBA trong suốt 100%, tính toạ độ trang chính xác từ ma trận biến đổi `cm`, và neo nổi phía trên văn bản Word (`<wp:anchor behindDoc="0" relativeFrom="page">`).
  - **Tái tạo đường kẻ chân Quốc hiệu / Tiêu ngữ & Tiêu đề (`_extract_standalone_horizontal_rules`)**: Tự động phát hiện các đường kẻ vector ngang độc lập dưới *"TỈNH AN GIANG"*, *"Độc lập - Tự do - Hạnh phúc"* và tiêu đề Quyết định; loại bỏ chúng khỏi luồng `shapes` của `pdf2docx` (tránh tạo đường viền bảng kéo dài hết trang) và neo đúng kích thước, đúng toạ độ trang trong Word.
  - **Bố cục chuẩn 2 cột cho Quốc hiệu – Tiêu ngữ và Khối Nơi nhận – Chữ ký (`_patched_parse_section`, `_patched_parse_line_break`)**: Tách khối tiêu đề căn giữa (*"QUYẾT ĐỊNH"*) khỏi khối 2 cột Quốc hiệu – Tiêu ngữ; giữ nguyên khối *"Nơi nhận"* và *"TM. ỦY BAN NHÂN DÂN / KT. CHỦ TỊCH"* trong cùng 1 section 2 cột chuẩn xác; bảo toàn ngắt dòng ở các khối căn giữa và danh sách gạch đầu dòng (`- Như Điều 4;`) mà không làm đứt dòng các đoạn văn căn đều (`JUSTIFY`).
  - **Kiểm định thực tế bằng Microsoft Word (`WINWORD.EXE`) trên Quyết định 3865/QĐ-UBND của UBND tỉnh An Giang**: Đạt **100.0/100 điểm chuẩn xác** (`1075/1075` từ, `3734/3734` ký tự, `7/7` lớp đồ hoạ con dấu/chữ ký/đường kẻ, giữ nguyên đúng **3 trang** như PDF gốc). Lưu tệp mẫu tại `samples/Quyet_dinh_3865_UBND_An_Giang.docx`.
- **Thiết kế lại Giao diện theo phong cách [storytold/pdfcraft](https://github.com/storytold/pdfcraft) & Chuyển đổi Sáng/Tối 1 chạm (`qtpdfpro/ui/main_window.py`, `qtpdfpro/ui/theme.py`, `qtpdfpro/ui/pdf_canvas.py`)**:
  - **Nút chuyển nhanh Giao diện Sáng / Tối (`☀️ Giao diện Sáng` / `🌙 Giao diện Tối`)** đặt nổi bật ngay góc phải thanh Header (`Ctrl+Shift+T`), đồng bộ tức thì toàn bộ cửa sổ, các bảng công cụ và cả màu nền vùng vẽ PDF (`#E2E8F0` ở chế độ Sáng / `#111318` ở chế độ Tối).
  - **Bố cục bàn làm việc 3 cột kiểu PdfCraft (`PDFDocumentTab`)**:
    1. **Cột trái (`Tất cả công cụ` — `F3`)**: Có ô lọc nhanh công cụ (`🔍 Tìm nhanh công cụ...`) và các thẻ thao tác 1 chạm chia theo nhóm (*Chuyển đổi sang Word*, *Soi bố cục & Văn bản*, *Thao tác trang & Tài liệu*).
    2. **Cột giữa (Khung đọc PDF + Thanh thông báo thông minh)**: Tự động phát hiện và hiển thị thanh thông báo số lượng chữ ký số / con dấu hành chính hoặc bảng biểu trong tài liệu kèm nút **⚡ Xuất Word chuẩn 1:1 ngay**.
    3. **Cột phải (Ngăn 4 tab `Trang`, `Mục lục`, `Tìm kiếm`, `Soi bố cục` + Thanh điều khiển dọc `Right Rail`)**: Thanh icon dọc bên phải cùng cho phép bật/tắt nhanh từng ngăn và điều khiển Trang (`▲`, `1/3`, `▼`), Thu phóng (`＋`, `100%`, `－`, `↔`, `↻`) chuẩn phong cách PdfCraft.
  - **Nhận diện khung Chữ ký số / Con dấu (`signature`) trong Layout Inspector (`F8`)**: Vẽ khung viền đỏ hồng (`#E11D48`) kèm nhãn trực tiếp lên các vùng chữ ký số và con dấu trên trang PDF.

### Kiểm thử
- Mở rộng bộ kiểm thử tự động `pytest` lên **16/16 bài test vượt qua 100%** (bao gồm kiểm thử ghép số văn bản đóng dấu đè `_splice_overlapping_stamped_text` và kiểm thử giao diện PdfCraft Sáng/Tối).

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
