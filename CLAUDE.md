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

### Trạng thái hiện tại (`v0.1.0` — 2026-10-19):
- **Đã hoàn thành nền tảng Giai đoạn 1** gồm đủ 2 chức năng cốt lõi:
  1. **Trình đọc PDF chuyên nghiệp**: Đa tab tài liệu, kết xuất High-DPI có bộ nhớ đệm `LRU Cache`, cuộn liên tục & từng trang, thu phóng `25%–400%` (`Ctrl+Wheel`), xoay trang, mục lục (`TOC`), tìm kiếm toàn văn tiếng Việt có tô sáng trên trang, và **Lớp phủ Soi bố cục (`Layout Inspector Overlay`)** vẽ khung nhận diện Văn bản / Bảng biểu / Hình ảnh / Vector trực tiếp lên trang PDF.
  2. **Engine chuyển đổi PDF sang DOCX đa chế độ**:
     - `hybrid` (Mặc định): `pdf2docx` cấu hình chuẩn xác + Bộ Hậu xử lý Chuẩn xác OpenXML (`core/openxml_fixer.py`) sửa phông 4 thuộc tính, chuẩn hoá tiếng Việt NFC/TCVN3, khoá lề bảng `fixed`, tắt `snapToGrid`.
     - `exact` (Vị trí tuyệt đối 1:1): Tách lớp nền đồ hoạ vector/ảnh (`apply_redactions` giữ nguyên ảnh & vector) neo dưới chữ (`wp:anchor behindDoc="1"`) + đặt từng dòng chữ vào khung toạ độ `<w:framePr>` tính bằng `twips`.
     - `word_com`: Cầu nối Microsoft Word Native Reflow qua COM + hậu xử lý OpenXML.
     - `auto`: Tự động chọn `hybrid` hoặc `exact` dựa trên phân tích bố cục trang.
     - Kèm **Bộ Kiểm định Độ chính xác (`core/fidelity.py`)** chấm điểm bảo toàn từ vựng, ký tự, bảng biểu, hình ảnh ngay sau khi chuyển đổi.
- **Tất cả bài kiểm thử tự động (`tests/`) đã chạy qua 100%**.

---

## 2. Quy tắc bắt buộc cho mọi Agent

1. **Sau mỗi phiên làm việc phải Commit và Push lên GitHub**:
   - Trước khi kết thúc phiên: chạy `python -m pytest -q tests` đảm bảo xanh 100% → cập nhật [CHANGELOG.md](CHANGELOG.md) (mục mới ở trên cùng) và mục 1, 6, 7 của tệp `CLAUDE.md` này → `git add` → `git commit -m "..."` (bằng tiếng Việt rõ nghĩa) → `git push`.
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
| `qtpdfpro/core/layout_analyzer.py` | Phân tích cấu trúc trang | Trích xuất `LayoutElement` (`text`, `table`, `image`, `vector`), đếm thành phần, gợi ý `recommended_mode` (`hybrid` vs `exact`) |
| `qtpdfpro/core/reader.py` | Engine đọc PDF | Bọc `fitz.Document`; kết xuất trang sang bộ đệm RGB (`RenderedPageBuffer`) có `LRU Cache` 24 trang; lấy mục lục (`get_bookmarks`); tìm kiếm toàn văn (`search`) trả về `bbox` + ngữ cảnh |
| `qtpdfpro/core/openxml_fixer.py` | Hậu xử lý chuẩn xác OpenXML | Dùng `lxml` sửa trực tiếp `word/document.xml` & `word/styles.xml`: đồng bộ 4 thuộc tính `w:rFonts` (`ascii`, `hAnsi`, `cs`, `eastAsia`), khôi phục `w:b`/`w:i`, tắt `w:snapToGrid`, khoá `w:tblLayout="fixed"`, thu gọn `w:tcMar` (`36 dxa`), vi chỉnh `w:spacing` |
| `qtpdfpro/core/exact_layout_engine.py` | Engine vị trí tuyệt đối 1:1 | Xoá chữ trên bản sao trang PDF bằng `apply_redactions(images=PDF_REDACT_IMAGE_NONE, graphics=PDF_REDACT_LINE_ART_NONE)` để lấy ảnh nền đồ hoạ neo dưới chữ (`wp:anchor behindDoc="1"`), đặt từng dòng chữ vào `<w:framePr>` theo toạ độ `twips` |
| `qtpdfpro/core/word_com_bridge.py` | Cầu nối MS Word Reflow | Gọi `Word.Application` qua PowerShell không giao diện khi máy có cài Office; thất bại thì tự lùi về `hybrid` |
| `qtpdfpro/core/converter.py` | Điều phối chuyển đổi | Hàm chính `convert_pdf_to_docx(pdf_path, docx_path, options, progress_cb)` và `parse_page_range` |
| `qtpdfpro/core/fidelity.py` | Kiểm định độ chính xác | So sánh từ vựng/ký tự (Multiset Bag-of-Words), cỡ trang, số bảng/khung/ảnh giữa PDF và DOCX, chấm điểm `overall_score` (thang 100) |
| `qtpdfpro/ui/pdf_canvas.py` | Khung vẽ & Cuộn PDF | `PDFScrollViewer`: kết xuất theo vùng nhìn (lazy viewport), hỗ trợ High-DPI (`devicePixelRatioF`), vẽ tô sáng tìm kiếm và khung `Layout Inspector Overlay` |
| `qtpdfpro/ui/convert_dialog.py` | Hộp thoại chuyển đổi | Chạy `_ConversionWorker(QThread)`, thanh tiến trình, hiển thị báo cáo `FidelityReport` và nút mở tệp Word ngay |
| `qtpdfpro/ui/main_window.py` | Cửa sổ chính đa tab | Quản lý `PDFDocumentTab`, Sidebar 4 ngăn (`Trang`, `Mục lục`, `Tìm kiếm`, `Soi bố cục`), kéo-thả tệp PDF |

---

## 5. Rào cản kỹ thuật đã gặp & Cách đã xử lý (Đừng vấp lại)

| Vấn đề | Nguyên nhân | Cách đã xử lý trong QT PDF Pro |
|---|---|---|
| Mở DOCX trong Word bị đổi phông chữ sang Calibri làm tràn dòng | PDF lưu tên phông dạng `BCDEFG+TimesNewRomanPS-BoldMT`; Word không nhận ra tên PostScript/Subset | `font_resolver.py` gỡ tiền tố `ABCDEF+`, ánh xạ về tên chuẩn (`Times New Roman`, `Arial`...) và `openxml_fixer.py` ghi đủ cả 4 thuộc tính `w:ascii`, `w:hAnsi`, `w:cs`, `w:eastAsia` + xoá `asciiTheme`/`cstheme` |
| Chữ trong bảng bị ép xuống dòng thứ 2 dù trên PDF nằm gọn 1 dòng | Word mặc định cộng thêm `108 dxa` (`5.4pt`) đệm trái/phải cho mỗi ô bảng | `openxml_fixer.py` đặt `w:tblLayout="fixed"` và giảm `w:tblCellMar` trái/phải xuống `36 dxa` (`1.8pt`) |
| Trang PDF 1 trang khi sang Word bị tràn 2–3 dòng cuối sang trang thứ 2 | Word bật mặc định `w:snapToGrid="1"` và chừa khoảng `header`/`footer` 0.5 inch | Đặt `<w:snapToGrid w:val="0"/>` trên mọi đoạn văn, đặt `<w:docGrid w:type="default"/>` và `w:header="0" w:footer="0"` trong `w:sectPr` |
| Chế độ 1:1 nếu chèn ảnh toàn trang rồi đặt chữ đè lên sẽ bị bóng chữ đôi (double text) | Ảnh chụp trang PDF gốc vẫn còn chữ bên dưới lớp khung văn bản Word | Dùng `page.add_redact_annot(rect, fill=False)` + `apply_redactions(images=PDF_REDACT_IMAGE_NONE, graphics=PDF_REDACT_LINE_ART_NONE)` trên bản sao trang trong bộ nhớ để xoá sạch 100% chữ mà giữ nguyên 100% đường kẻ vector và hình ảnh |
| Mất dòng *"Độc lập - Tự do - Hạnh phúc"* khi bên dưới có tiêu đề *"QUYẾT ĐỊNH"* căn giữa | Lỗi nội bộ của `pdf2docx` (`RawPage._create_section`): khi `group_by_columns()` tách ra 3 cụm X (cột trái, tiêu đề giữa, cột phải), `pdf2docx` chỉ lấy dải Y của `cols[1]` nên loại bỏ `cols[2]` | Vá `RawPage._create_section` trong `converter.py` (`_install_pdf2docx_patches`) gộp toàn bộ chiều cao `y_top = min(c.bbox[1])` .. `y_bot = max(c.bbox[3])` của mọi cụm cột |
| Phông chữ TrueType (`times.ttf`) trên PDF xuất khoảng trắng thành `\u00a0` (NBSP) và dấu `-` thành `\u00ad` (Soft Hyphen) | Bảng `ToUnicode` CMap của PDF ánh xạ `0x20` → `U+00A0` khiến Word coi cả đoạn văn là 1 từ duy nhất không ngắt dòng được và tìm kiếm trượt | Chuẩn hoá `\u00a0` → `' '` và `\u00ad` → `'-'` trong `normalize_vietnamese_text` (`font_resolver.py`) và hỗ trợ tìm kiếm cả hai dạng trong `reader.py` |
| `page.find_tables()` của PyMuPDF in dòng quảng cáo `pymupdf_layout` ra `stdout` làm hỏng kết quả `--json` của CLI | `PyMuPDF 1.27+` tự `print()` thông báo gợi ý cài gói phụ ra `stdout` ở lần gọi đầu tiên | Bọc `find_tables()` và `pdf2docx` trong `contextlib.redirect_stdout` ở `layout_analyzer.py` và `converter.py` |
| Lỗi `UnicodeEncodeError` khi chạy CLI in tiếng Việt trên Windows | Console chuyển hướng của Windows mặc định dùng `cp1252` | Gọi `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` ở đầu `cli.py` |
| Tên tệp PDF có dấu `&` làm mất ký tự `&` trên tiêu đề tab Qt | Qt hiểu `&` là phím tắt gạch chân (mnemonic) | Thay `&` bằng `&&` khi đặt tiêu đề tab và menu Tệp mở gần đây |

---

## 6. Việc cần làm tiếp theo (Theo thứ tự ưu tiên cho Agent phiên sau)

1. **Kiểm thử & Tinh chỉnh trên bộ tài liệu PDF phức tạp thực tế**:
   - Thu thập / tạo bộ mẫu kiểm thử nâng cao gồm: văn bản hành chính nhà nước nhiều trang, bảng tài chính 8–10 cột, hợp đồng 2 cột song ngữ, biểu mẫu hành chính có khung điền thông tin.
   - Chạy chuyển đổi và kiểm tra trực tiếp trên Microsoft Word (`WINWORD.EXE`), tinh chỉnh thêm bộ lọc nhận diện trong `core/openxml_fixer.py`.
2. **Tái tạo chuyên biệt cho khối Quốc hiệu – Tiêu ngữ và Khối Chữ ký cuối văn bản**:
   - Viết bộ nhận diện thông minh cho cặp khối văn bản song song không viền ở đầu/cuối văn bản hành chính Việt Nam để luôn đóng khung vào bảng ẩn viền 2 cột cân đối tuyệt đối.
3. **Tích hợp OCR Tiếng Việt (`Tesseract` / `VietOCR`) cho PDF Scan**:
   - Tự động nhận diện trang scan (`is_scanned=True`) và chuyển đổi sang văn bản Word có giữ định dạng.
4. **Chuyển đổi hàng loạt (Batch Conversion)**:
   - Thêm hộp thoại chuyển đổi cùng lúc nhiều tệp PDF sang DOCX.

---

## 7. Danh sách kiểm tra bắt buộc trước khi báo "Xong"

- [ ] `python -m pytest -q tests` chạy qua 100% không có lỗi.
- [ ] Nếu sửa giao diện (`qtpdfpro/ui/`): chạy thử cửa sổ với `QT_PDF_PRO_DATA` tạm và kiểm tra hiển thị tiếng Việt.
- [ ] Cập nhật [CHANGELOG.md](CHANGELOG.md) và tệp `CLAUDE.md` này.
- [ ] Thực hiện `git commit` và `git push` lên kho lưu trữ GitHub `quangthoai1985/QTPdfPro`.
