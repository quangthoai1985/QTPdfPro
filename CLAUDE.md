# CLAUDE.md — Bàn giao dự án QT PDF Pro cho Agent

> **ĐỌC TỆP NÀY TRƯỚC KHI LÀM BẤT CỨ VIỆC GÌ.**
> - Lịch sử chi tiết từng phiên làm việc: [CHANGELOG.md](CHANGELOG.md).
> - Nghiên cứu & đề xuất công nghệ: [docs/NGHIEN_CUU_CONG_NGHE.md](docs/NGHIEN_CUU_CONG_NGHE.md).
> - Thiết kế kiến trúc chi tiết: [docs/THIET_KE.md](docs/THIET_KE.md).
> - Người dùng viết tiếng Việt → trả lời tiếng Việt; chuỗi giao diện và tài liệu viết tiếng Việt có dấu chuẩn xác.

---

## 1. Dự án là gì & Trạng thái hiện tại

**QT PDF Pro** là ứng dụng chuyên đọc tệp PDF tốc độ cao kèm chức năng chủ đạo **chuyển đổi PDF sang Word (`.docx`) chuẩn xác từng thành phần** dành cho Windows.
- **Công nghệ**: **Python 3.14 + PySide6 (Qt6) + PyMuPDF (`fitz`) + `pdf2docx` + `python-docx` + `lxml` (OpenXML Precision Post-Processor)**.
- **Giấy phép**: Mã nguồn mở **MIT License** ([LICENSE](LICENSE)).
- **Kho GitHub**: `https://github.com/quangthoai1985/QTPdfPro`

### Trạng thái hiện tại (`v0.2.0` — 2026-10-19):
- **Đã hoàn thành Giai đoạn 1 & Giai đoạn 2 (Hoàn thiện Văn bản Hành chính Việt Nam 100% + Giao diện PdfCraft Sáng/Tối)**:
  1. **Trình đọc PDF chuyên nghiệp theo bố cục 3 cột kiểu [storytold/pdfcraft](https://github.com/storytold/pdfcraft)**:
     - **Nút chuyển nhanh Giao diện Sáng / Tối (`☀️ Giao diện Sáng` / `🌙 Giao diện Tối`)** ngay góc phải thanh Header (`Ctrl+Shift+T`), đồng bộ cả giao diện ứng dụng lẫn nền vùng vẽ PDF (`#E2E8F0` / `#111318`).
     - **Cột trái (`Tất cả công cụ` — `F3`)**: Có ô tìm nhanh công cụ và các thẻ thao tác 1 chạm (*Xuất Word Chuẩn hành chính*, *Xuất Word Giữ vị trí 1:1*, *Bật/Tắt khung soi bố cục*, *Trích xuất văn bản*, *Xoay trang*).
     - **Cột giữa (Khung đọc PDF + Thanh thông báo thông minh)**: Tự động phát hiện số lượng chữ ký số / con dấu hành chính hoặc bảng biểu trong tài liệu và hiển thị nút **⚡ Xuất Word chuẩn 1:1 ngay**.
     - **Cột phải (Ngăn 4 tab `Trang`, `Mục lục`, `Tìm kiếm`, `Soi bố cục` + Thanh điều khiển dọc `Right Rail`)**: Cụm icon dọc và thanh điều khiển Trang / Thu phóng ở góc phải giống PdfCraft.
  2. **Engine chuyển đổi PDF sang DOCX đa chế độ đạt 100.0/100 điểm trên văn bản hành chính ký số VGCA**:
     - `hybrid` (Mặc định): Tự động ghép số hiệu & ngày tháng đóng dấu đè (`_splice_overlapping_stamped_text`), trích xuất con dấu đỏ UBND & chữ ký số PNG RGBA trong suốt từ `/AP /N` Form XObject của `page.widgets()` (`_extract_widget_overlays`), tái tạo đường kẻ chân Quốc hiệu / Tiêu ngữ (`_extract_standalone_horizontal_rules`), tách riêng khối 2 cột Quốc hiệu – Tiêu ngữ và Nơi nhận – Chữ ký (`_patched_parse_section`), kết hợp Bộ Hậu xử lý Chuẩn xác OpenXML (`core/openxml_fixer.py`).
     - `exact` (Vị trí tuyệt đối 1:1): Tách lớp nền đồ hoạ vector/ảnh (`apply_redactions` giữ nguyên ảnh & vector) neo dưới chữ (`wp:anchor behindDoc="1"`) + đặt từng dòng chữ vào khung toạ độ `<w:framePr>` tính bằng `twips`.
     - `word_com`: Cầu nối Microsoft Word Native Reflow qua COM + hậu xử lý OpenXML.
     - `auto`: Tự động chọn `hybrid` hoặc `exact` dựa trên phân tích bố cục trang.
     - Kèm **Bộ Kiểm định Độ chính xác (`core/fidelity.py`)** chấm điểm bảo toàn từ vựng, ký tự, bảng biểu, hình ảnh ngay sau khi chuyển đổi.
- **Tất cả 16/16 bài kiểm thử tự động (`tests/`) đã chạy qua 100%**.

---

## 2. Quy tắc bắt buộc cho mọi Agent

1. **Sau mỗi phiên làm việc phải Commit và Push lên GitHub**:
   - Trước khi kết thúc phiên: chạy `python -m pytest -q tests` đảm bảo xanh 100% → cập nhật [CHANGELOG.md](CHANGELOG.md) (mục mới ở trên cùng) và mục 1, 5, 6, 7 của tệp `CLAUDE.md` này → `git add` → `git commit -m "..."` (bằng tiếng Việt rõ nghĩa) → `git push`.
2. **Tách biệt hoàn toàn Engine và Giao diện**:
   - Không bao giờ import `PySide6` bên trong `qtpdfpro/core/`. Mọi tính năng mới về đọc PDF hoặc chuyển đổi DOCX phải viết trong `qtpdfpro/core/` trước, có hàm gọi được từ `qtpdfpro/cli.py` và có bài test trong `tests/`.
3. **Cô lập dữ liệu khi kiểm thử**:
   - Dữ liệu cấu hình thật của người dùng nằm ở `%LOCALAPPDATA%\QTPdfPro\`. Khi chạy test hoặc chạy thử nghiệm từ Agent, **luôn đặt biến môi trường `QT_PDF_PRO_DATA`** trỏ vào thư mục tạm (`tests/conftest.py` đã tự động làm việc này cho `pytest`).
4. **Quy tắc tệp Windows & Tiếng Việt**:
   - Tệp `.bat` (`run.bat`, `build.bat`) bắt buộc phải là **pure ASCII + CRLF** (test `tests/test_version.py` sẽ báo lỗi nếu có ký tự tiếng Việt trong `.bat`).
   - Mọi script CLI in tiếng Việt ra console phải gọi `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`.
   - Khi đặt tên tệp hoặc chuỗi có dấu `&` lên `QTabWidget` / `QAction` / `QPushButton` của Qt, phải nhân đôi `&&` để Qt không biến thành phím tắt gạch chân (mnemonic).

---

## 3. Lệnh chạy, kiểm thử và đóng gói

```bash
# 1. Cài đặt phụ thuộc
python -m pip install -r requirements.txt

# 2. Chạy giao diện đồ hoạ (GUI)
python -m qtpdfpro                          # Mở cửa sổ chào mừng (hoặc chạy run.bat)
python -m qtpdfpro duong_dan_tep.pdf        # Mở thẳng tệp PDF vào tab đọc

# 3. Chạy qua dòng lệnh (CLI)
python -m qtpdfpro.cli convert in.pdf -o out.docx --mode hybrid
python -m qtpdfpro.cli convert in.pdf -o out_1to1.docx --mode exact --pages 1-2
python -m qtpdfpro.cli inspect in.pdf --json
python -m qtpdfpro.cli verify in.pdf out.docx --json

# 4. Chạy toàn bộ kiểm thử tự động (bắt buộc qua 100% trước khi commit)
python -m pytest -q tests

# 5. Đóng gói tệp thực thi độc lập (.exe) bằng PyInstaller
cmd.exe /c ".\build.bat"                    # Xuất ra dist\QTPdfPro\QTPdfPro.exe
```

---

## 4. Kiến trúc & Bảng phân vai các tệp mã nguồn

| Tệp | Vai trò | Điểm kỹ thuật quan trọng cần nhớ |
|---|---|---|
| `qtpdfpro/__init__.py` | Metadata & Phiên bản | Định nghĩa `__version__`, `__app_name__`, `__github_repo__`. Đổi phiên bản tại đây phải cập nhật `CHANGELOG.md` |
| `qtpdfpro/cli.py` | Giao diện dòng lệnh | Lệnh `convert`, `inspect`, `verify` hỗ trợ cờ `--json` để script/Agent kiểm tra tự động |
| `qtpdfpro/core/settings.py` | Cấu hình & Tệp gần đây | Lưu tại `%LOCALAPPDATA%\QTPdfPro\settings.json`; đọc bằng `utf-8-sig` (chịu BOM); hỗ trợ `QT_PDF_PRO_DATA` |
| `qtpdfpro/core/font_resolver.py` | Chuẩn hoá phông & Tiếng Việt | Gỡ tiền tố subset `^[A-Z]{6}\+`; ánh xạ tên phông PostScript (`TimesNewRomanPSMT` → `Times New Roman`, v.v.); gộp dấu rời NFD → NFC; chuyển mã TCVN3 (`.Vn*`) sang Unicode |
| `qtpdfpro/core/layout_analyzer.py` | Phân tích cấu trúc trang | Trích xuất `LayoutElement` (`text`, `table`, `image`, `signature`, `vector`), đếm thành phần (`signature_count`), gợi ý `recommended_mode` (`hybrid` vs `exact`) |
| `qtpdfpro/core/reader.py` | Engine đọc PDF | Bọc `fitz.Document`; kết xuất trang sang bộ đệm RGB (`RenderedPageBuffer`) có `LRU Cache` 24 trang; lấy mục lục (`get_bookmarks`); tìm kiếm toàn văn (`search`) trả về `bbox` + ngữ cảnh |
| `qtpdfpro/core/openxml_fixer.py` | Hậu xử lý chuẩn xác OpenXML | Dùng `lxml` sửa trực tiếp `word/document.xml` & `word/styles.xml`: đồng bộ 4 thuộc tính `w:rFonts`, khôi phục `w:b`/`w:i`, tắt `w:snapToGrid`, khoá `w:tblLayout="fixed"`, thu gọn `w:tcMar`, điều chỉnh `line_spacing_factor` (`0.93`), và neo ảnh con dấu/chữ ký/đường kẻ theo toạ độ trang (`anchor_page_overlays` với `<wp:anchor relativeFrom="page">`) |
| `qtpdfpro/core/exact_layout_engine.py` | Engine vị trí tuyệt đối 1:1 | Xoá chữ trên bản sao trang PDF bằng `apply_redactions(images=PDF_REDACT_IMAGE_NONE, graphics=PDF_REDACT_LINE_ART_NONE)` để lấy ảnh nền đồ hoạ neo dưới chữ (`wp:anchor behindDoc="1"`), đặt từng dòng chữ vào `<w:framePr>` theo toạ độ `twips` |
| `qtpdfpro/core/word_com_bridge.py` | Cầu nối MS Word Reflow | Gọi `Word.Application` qua PowerShell không giao diện khi máy có cài Office; thất bại thì tự lùi về `hybrid` |
| `qtpdfpro/core/converter.py` | Điều phối chuyển đổi | Hàm chính `convert_pdf_to_docx`, kèm bộ bản vá `_install_pdf2docx_patches()` xử lý số văn bản đóng dấu đè, trích xuất chữ ký số/con dấu đỏ (`_extract_widget_overlays`), và đường kẻ chân Quốc hiệu (`_extract_standalone_horizontal_rules`) |
| `qtpdfpro/core/fidelity.py` | Kiểm định độ chính xác | So sánh từ vựng/ký tự (Multiset Bag-of-Words), cỡ trang, số bảng/khung/ảnh giữa PDF và DOCX, chấm điểm `overall_score` (thang 100) |
| `qtpdfpro/ui/pdf_canvas.py` | Khung vẽ & Cuộn PDF | `PDFScrollViewer`: kết xuất theo vùng nhìn (lazy viewport), đổi màu nền Sáng/Tối (`set_canvas_theme`), vẽ tô sáng tìm kiếm và khung `Layout Inspector Overlay` (gồm cả `signature` màu đỏ hồng `#E11D48`) |
| `qtpdfpro/ui/convert_dialog.py` | Hộp thoại chuyển đổi | Chạy `_ConversionWorker(QThread)`, thanh tiến trình, hiển thị báo cáo `FidelityReport` và nút mở tệp Word ngay |
| `qtpdfpro/ui/main_window.py` | Cửa sổ chính đa tab | Bố cục 3 cột kiểu PdfCraft (`tools_panel` bên trái, `viewer` + `signature_banner` ở giữa, `sidebar_tabs` + `right_rail` bên phải) và nút chuyển Sáng/Tối 1 chạm (`btn_theme_toggle`) |

---

## 5. Rào cản kỹ thuật đã gặp & Cách đã xử lý (Đừng vấp lại)

| Vấn đề | Nguyên nhân | Cách đã xử lý trong QT PDF Pro |
|---|---|---|
| Mất số hiệu văn bản (`"3865"`) và ngày ban hành (`"14"`) trong văn bản hành chính ký số VGCA | Phần mềm ký số đóng dấu `"3865"` đè lên khoảng trắng `"         "` của dòng mẫu `"Số:           /QĐ-UBND"`. `Blocks._remove_overlapped_lines` của `pdf2docx` xoá dòng có `bbox` nhỏ hơn | Viết hàm `_splice_overlapping_stamped_text` can thiệp vào `RawPageFitz._preprocess_text`: tìm dải khoảng trắng liên tiếp trong dòng chủ (`host_line`) và chèn các ký tự đóng dấu vào đúng vị trí trước khi `pdf2docx` lọc trùng |
| Mất con dấu đỏ UBND, chữ ký số và chữ ký nháy khi chuyển sang Word | Con dấu & chữ ký nằm trong PDF Signature Widgets (`page.widgets()`), không phải ảnh thông thường trong `page.get_images()` | Viết hàm `_extract_widget_overlays`: duyệt cây `/AP /N -> /FRM -> /n2` của widget, kết hợp ảnh gốc và kênh `/SMask` thành PNG RGBA trong suốt 100%, tính toạ độ trang từ ma trận `cm` và neo nổi bằng `<wp:anchor behindDoc="0" relativeFrom="page">` |
| Đường kẻ ngắn dưới *"TỈNH AN GIANG"* bị biến thành đường viền bảng kéo dài ngang hết trang | `pdf2docx` coi nét vẽ vector đơn lẻ gần khối chữ là đường viền ô bảng (`<w:tcBorders>`). Lưu ý: trong `RawPageFitz._preprocess_shapes`, nét vẽ (`stroke`) lưu toạ độ ở khoá `"start"` và `"end"` chứ chưa có `"bbox"` | Viết `_extract_standalone_horizontal_rules` lọc các nét ngang độc lập bằng cả `"bbox"` lẫn `("start", "end")` khỏi `pdf2docx` và neo ảnh PNG nét vẽ mảnh tại đúng toạ độ trang |
| Tiêu đề *"QUYẾT ĐỊNH"* căn giữa bị hút lệch vào cột phải của Quốc hiệu – Tiêu ngữ, hoặc phần *"Nơi nhận"* cuối văn bản bị tách làm 2 section lệch dòng | `Pages._parse_section` của `pdf2docx` gộp nhầm dòng đơn căn giữa vào khối 2 cột liền kề, và tách rời từng hàng của khối 2 cột khi lệch cao độ | Vá `_patched_parse_section` trong `converter.py` để giữ nguyên dòng đơn căn giữa làm khối 1 cột độc lập và gom toàn bộ các dòng liên tiếp của khối *"Nơi nhận / Chữ ký"* vào chung 1 section 2 cột |
| Mở DOCX trong Word bị đổi phông chữ sang Calibri làm tràn dòng | PDF lưu tên phông dạng `BCDEFG+TimesNewRomanPS-BoldMT`; Word không nhận ra tên PostScript/Subset | `font_resolver.py` gỡ tiền tố `ABCDEF+`, ánh xạ về tên chuẩn (`Times New Roman`, `Arial`...) và `openxml_fixer.py` ghi đủ cả 4 thuộc tính `w:ascii`, `w:hAnsi`, `w:cs`, `w:eastAsia` + xoá `asciiTheme`/`cstheme` |
| Chữ trong bảng bị ép xuống dòng thứ 2 dù trên PDF nằm gọn 1 dòng | Word mặc định cộng thêm `108 dxa` (`5.4pt`) đệm trái/phải cho mỗi ô bảng | `openxml_fixer.py` đặt `w:tblLayout="fixed"` và giảm `w:tblCellMar` trái/phải xuống `36 dxa` (`1.8pt`) |
| Trang PDF 3 trang khi sang Word bị tràn vài dòng sang trang thứ 4 | Word mặc định cộng dồn khoảng cách dòng lớn hơn PDF | Đặt `<w:snapToGrid w:val="0"/>`, `w:header="0" w:footer="0"` và nhân hệ số `line_spacing_factor = 0.93` trong `openxml_fixer.py` để giữ nguyên đúng 3 trang như PDF gốc |

---

## 6. Việc cần làm tiếp theo (Theo thứ tự ưu tiên cho Agent phiên sau)

1. **Tích hợp OCR Tiếng Việt (`Tesseract` / `VietOCR`) cho PDF Scan**:
   - Tự động nhận diện trang scan (`is_scanned=True`) và chuyển đổi sang văn bản Word có giữ định dạng kèm trích xuất con dấu đỏ.
2. **Chuyển đổi hàng loạt (Batch Conversion)**:
   - Thêm hộp thoại chuyển đổi cùng lúc nhiều tệp PDF hành chính sang DOCX.
3. **Đóng gói bản phát hành độc lập (`QTPdfPro-0.2.0-win64.zip`)**:
   - Đóng gói bằng `build.bat` (PyInstaller) và phát hành lên GitHub Releases.

---

## 7. Danh sách kiểm tra bắt buộc trước khi báo "Xong"

- [x] `python -m pytest -q tests` chạy qua 100% không có lỗi.
- [x] Nếu sửa giao diện (`qtpdfpro/ui/`): chạy thử cửa sổ với `QT_PDF_PRO_DATA` tạm và kiểm tra hiển thị tiếng Việt.
- [x] Cập nhật [CHANGELOG.md](CHANGELOG.md) và tệp `CLAUDE.md` này.
- [x] Thực hiện `git commit` và `git push` lên kho lưu trữ GitHub `quangthoai1985/QTPdfPro`.
