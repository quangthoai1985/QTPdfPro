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

### Trạng thái hiện tại (`v0.3.0` — đã phát hành [GitHub Release](https://github.com/quangthoai1985/QTPdfPro/releases/tag/v0.3.0) 2026-10-20):
- **Có trong bản phát hành v0.3.0 (gộp vào trước khi phát hành)**: **Chuyển đổi hàng loạt** — `core/batch.py` (`convert_batch`, mặc định `auto` → `nd30`/`faithful`, không kiểm chứng Word), lệnh `cli batch`, hộp thoại «Chuyển đổi hàng loạt» (kéo thả nhiều PDF/thư mục, bảng điểm chuẩn xác & thể thức NĐ30 từng tệp, báo cáo CSV/JSON, Ctrl+Shift+B). **Sửa theme**: radio đang chọn hiện chấm, checkbox có khung + dấu ✔ ở cả giao diện Sáng/Tối.
- **Mới ở v0.3.0**:
  1. **Chế độ chuyển đổi `nd30`** (mặc định qua `auto` khi phát hiện Quốc hiệu – Tiêu ngữ): tái dựng văn bản hành chính như người soạn trong Word — lề / cỡ chữ / giãn dòng / cách đoạn / thụt đầu dòng **đo trên PDF rồi ước lượng về giá trị gốc**, phần đầu & khối ký trong **bảng 2 cột không viền**, đường kẻ là viền dưới đoạn văn đúng toạ độ PDF, số trang là trường `PAGE`. Chính sách `faithful` (mặc định, giữ đúng bố cục PDF) hoặc `nd30` (ép chuẩn hoá).
  2. **Đối chiếu thể thức NĐ30** 26 hạng mục (`cli nd30`, hộp thoại «Kiểm tra thể thức NĐ30») và **Kiểm chứng bố cục bằng Microsoft Word** (`--verify-layout`, `verify --render`): đã đạt 100% dòng khớp, lệch ≤ 0,84 pt trên 3 văn bản mẫu `samples/nd30/`.
  3. **Trang chủ & header theo PdfCraft**: dải tab tài liệu + thanh chế độ (Tất cả công cụ · Đọc · Chuyển đổi · Chỉnh sửa · Ký số & Bảo mật), cột «Tất cả công cụ», «Công cụ đề xuất», «Gần đây», Ctrl+K; công cụ chưa có hiển thị **«Coming Soon»**.
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
- **Tất cả 40/40 bài kiểm thử tự động (`tests/`) đã chạy qua 100%** (bài kiểm chứng bằng MS Word tự bỏ qua nếu máy không có Word).

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
python -m qtpdfpro.cli convert in.pdf -o out.docx --mode auto --verify-layout   # văn bản hành chính → nd30
python -m qtpdfpro.cli convert in.pdf -o out.docx --mode nd30 --nd30-policy faithful
python -m qtpdfpro.cli nd30 in.pdf                       # đối chiếu thể thức NĐ30 (26 hạng mục)
python -m qtpdfpro.cli convert in.pdf -o out.docx --mode hybrid
python -m qtpdfpro.cli convert in.pdf -o out_1to1.docx --mode exact --pages 1-2
python -m qtpdfpro.cli inspect in.pdf --json
python -m qtpdfpro.cli verify in.pdf out.docx --json
python -m qtpdfpro.cli verify in.pdf out.docx --render   # dựng DOCX bằng MS Word, so vị trí từng dòng
python -m qtpdfpro.cli batch thu_muc_pdf a.pdf -o thu_muc_docx [--verify-layout] [--report bc.csv] [--json]

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
| `qtpdfpro/cli.py` | Giao diện dòng lệnh | Lệnh `convert`, `inspect`, `nd30`, `verify`, `batch` hỗ trợ cờ `--json` để script/Agent kiểm tra tự động; `batch` thoát mã 1 nếu có tệp lỗi |
| `qtpdfpro/core/settings.py` | Cấu hình & Tệp gần đây | Lưu tại `%LOCALAPPDATA%\QTPdfPro\settings.json`; đọc bằng `utf-8-sig` (chịu BOM); hỗ trợ `QT_PDF_PRO_DATA` |
| `qtpdfpro/core/font_resolver.py` | Chuẩn hoá phông & Tiếng Việt | Gỡ tiền tố subset `^[A-Z]{6}\+`; ánh xạ tên phông PostScript (`TimesNewRomanPSMT` → `Times New Roman`, v.v.); gộp dấu rời NFD → NFC; chuyển mã TCVN3 (`.Vn*`) sang Unicode |
| `qtpdfpro/core/layout_analyzer.py` | Phân tích cấu trúc trang | Trích xuất `LayoutElement` (`text`, `table`, `image`, `signature`, `vector`), đếm thành phần (`signature_count`), gợi ý `recommended_mode` (`hybrid` vs `exact`) |
| `qtpdfpro/core/reader.py` | Engine đọc PDF | Bọc `fitz.Document`; kết xuất trang sang bộ đệm RGB (`RenderedPageBuffer`) có `LRU Cache` 24 trang; lấy mục lục (`get_bookmarks`); tìm kiếm toàn văn (`search`) trả về `bbox` + ngữ cảnh |
| `qtpdfpro/core/openxml_fixer.py` | Hậu xử lý chuẩn xác OpenXML | Dùng `lxml` sửa trực tiếp `word/document.xml` & `word/styles.xml`: đồng bộ 4 thuộc tính `w:rFonts`, khôi phục `w:b`/`w:i`, tắt `w:snapToGrid`, khoá `w:tblLayout="fixed"`, thu gọn `w:tcMar`, điều chỉnh `line_spacing_factor` (`0.93`), và neo ảnh con dấu/chữ ký/đường kẻ theo toạ độ trang (`anchor_page_overlays` với `<wp:anchor relativeFrom="page">`) |
| `qtpdfpro/core/exact_layout_engine.py` | Engine vị trí tuyệt đối 1:1 | Xoá chữ trên bản sao trang PDF bằng `apply_redactions(images=PDF_REDACT_IMAGE_NONE, graphics=PDF_REDACT_LINE_ART_NONE)` để lấy ảnh nền đồ hoạ neo dưới chữ (`wp:anchor behindDoc="1"`), đặt từng dòng chữ vào `<w:framePr>` theo toạ độ `twips` |
| `qtpdfpro/core/word_com_bridge.py` | Cầu nối MS Word Reflow | Gọi `Word.Application` qua PowerShell không giao diện khi máy có cài Office; thất bại thì tự lùi về `hybrid` |
| `qtpdfpro/core/pdf_primitives.py` | Hàm nền dùng chung | `splice_overlapping_stamped_text` (ghép số/ngày đóng dấu đè), `extract_widget_overlays` (con dấu, chữ ký số PNG RGBA từ widget) |
| `qtpdfpro/core/admin_layout.py` | Phân tích văn bản hành chính | Dòng trực quan (`TextLine`, mép phải theo ký tự thật), đường kẻ `l`/`re`, ảnh, bảng; nhận diện phần đầu 2 cột & khối ký (`TwoColBlock`), gom đoạn (`ParaBlock`), đo lề/giãn dòng/cách đoạn (`MeasuredLayout`); mô hình hình học Word: Multiple → phần giãn nằm dưới dòng, Exactly → baseline = 0,8 × h (`EXACT_BASELINE_RATIO`) |
| `qtpdfpro/core/nd30_standard.py` | Chuẩn NĐ30 | `ND30_SPEC`, `check_nd30_compliance` (26 hạng mục), `build_docx_plan` (chính sách `faithful`/`nd30`), `snap_margin_mm` |
| `qtpdfpro/core/nd30_engine.py` | Dựng DOCX chuẩn NĐ30 | `convert_pdf_nd30`: `compatibilityMode=15`, bảng không viền + thụt lề căn tâm theo PDF, đường kẻ = `w:pBdr/w:bottom`, bảng dữ liệu (`trHeight atLeast` trừ nét viền), ảnh neo `relativeFrom=paragraph`, header `PAGE` + `titlePg` |
| `qtpdfpro/core/layout_verify.py` | Kiểm chứng bằng MS Word | `verify_docx_layout` (Word xuất PDF qua PowerShell COM) + `compare_pdf_layouts` (difflib theo dòng, lệch dọc/ngang pt) |
| `qtpdfpro/core/converter.py` | Điều phối chuyển đổi | Hàm chính `convert_pdf_to_docx`, kèm bộ bản vá `_install_pdf2docx_patches()` xử lý số văn bản đóng dấu đè, trích xuất chữ ký số/con dấu đỏ (`_extract_widget_overlays`), và đường kẻ chân Quốc hiệu (`_extract_standalone_horizontal_rules`) |
| `qtpdfpro/core/batch.py` | Chuyển đổi hàng loạt | `convert_batch` tuần tự (bộ vá `pdf2docx` dùng biến toàn cục → không chạy song song trong 1 tiến trình), lỗi 1 tệp không dừng cả lượt, `should_cancel`; sự kiện `BatchProgress` mang **bản sao** `BatchItemResult`; `collect_pdf_paths`, `plan_output_paths` (hậu tố `_2` khi trùng tên), `write_batch_report` (.csv UTF-8 BOM / .json) |
| `qtpdfpro/core/fidelity.py` | Kiểm định độ chính xác | So sánh từ vựng/ký tự (Multiset Bag-of-Words), cỡ trang, số bảng/khung/ảnh giữa PDF và DOCX, chấm điểm `overall_score` (thang 100) |
| `qtpdfpro/ui/pdf_canvas.py` | Khung vẽ & Cuộn PDF | `PDFScrollViewer`: kết xuất theo vùng nhìn (lazy viewport), đổi màu nền Sáng/Tối (`set_canvas_theme`), vẽ tô sáng tìm kiếm và khung `Layout Inspector Overlay` (gồm cả `signature` màu đỏ hồng `#E11D48`) |
| `qtpdfpro/ui/convert_dialog.py` | Hộp thoại chuyển đổi | Chạy `_ConversionWorker(QThread)`, thanh tiến trình, hiển thị báo cáo `FidelityReport` và nút mở tệp Word ngay; `MODE_CHOICES`/`POLICY_CHOICES` dùng chung |
| `qtpdfpro/ui/batch_dialog.py` | Hộp thoại hàng loạt | `BatchConvertDialog`: kéo thả PDF/thư mục, `_BatchWorker(QThread)` + cờ `_running` (đợi luồng thoát trong `_on_finished` để không huỷ QThread đang chạy), bảng điểm từng tệp, «Dừng», mở thư mục kết quả, lưu báo cáo; nơi lưu chọn bằng `QComboBox` |
| `qtpdfpro/ui/theme.py` | QSS Sáng/Tối | `_DARK_QSS`/`_LIGHT_QSS` + `_SHELL_TEMPLATE` điền theo bảng màu `@token` (khoá dài thay trước); tự vẽ `QRadioButton`/`QCheckBox::indicator` (kiểu `windows11` không vẽ radio đang chọn khi có QSS); dấu ✔ là SVG ghi vào `<thư mục dữ liệu>/theme/` (QSS không nhận ảnh nhúng) |
| `qtpdfpro/ui/main_window.py` | Cửa sổ chính đa tab | Header 2 tầng kiểu PdfCraft (`doc_tab_bar` ở dải tiêu đề đồng bộ với `doc_tabs` ẩn thanh tab; thanh chế độ `mode_buttons` lọc công cụ; menu nằm trong nút «☰ Menu» nên mọi `QAction` phải `self.addActions` để phím tắt chạy); `run_tool(key)` điều phối công cụ; khung tài liệu 3 cột (`tools_panel`, `viewer` + `signature_banner`, `sidebar_tabs` + `right_rail`) |
| `qtpdfpro/ui/home_page.py` | Trang chủ PdfCraft | `ToolCatalogPanel` (cột «Tất cả công cụ»), `ToolCard` (công cụ đề xuất), `OpenFileCard`, `RecentRow`; lưới thẻ tự đổi số cột theo chiều rộng |
| `qtpdfpro/ui/tool_catalog.py` | Danh mục công cụ | `TOOLS` (35 công cụ — 15 dùng được, `ready=False` → «Coming Soon» + `milestone`), `RECOMMENDED`, tìm không dấu `tools_for()` |
| `qtpdfpro/ui/command_palette.py`, `nd30_dialog.py` | Ctrl+K & NĐ30 | Bảng lệnh; hộp thoại báo cáo NĐ30 & kiểm chứng DOCX (chạy `QThread`) |

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
| DOCX dựng bằng `python-docx` ngắt dòng khác PDF dù cùng lề, cùng phông | Mẫu mặc định của `python-docx` đặt `compatibilityMode=14` (Word 2010) — thuật toán ngắt dòng/căn đều khác Word 2013+ | `nd30_engine._set_modern_compat()` đặt `compatibilityMode=15`, xoá `w:useFELayout` |
| Đoạn văn lệch dọc vài pt sau khi dựng lại | Word: giãn dòng «Multiple» đặt phần giãn thêm **dưới** dòng chữ; «Exactly h» đặt baseline tại **0,8 × h** (đo thực nghiệm); khoảng cách trước đoạn bị bỏ ở đầu trang | Mô hình `ParaBlock.top/bottom` theo đúng quy luật trên; đoạn 1 dòng suy giãn dòng từ vị trí khối kế tiếp; đoạn tràn trang tính khoảng cách theo `end_page` |
| Giãn dòng «Exactly 18 pt» bị bắt nhầm về bội số 1,2 → lệch 0,08 pt/dòng, cộng dồn làm tràn trang | Ngưỡng làm tròn 2,5% quá rộng | `resolve_line_spacing`: chỉ nhận bội số chuẩn khi sai lệch ≤ 0,04 pt/dòng (đo trên toàn văn bản), ngược lại ghi «Exactly» |
| Đường kẻ dưới Quốc hiệu không được nhận | Word xuất viền bảng / đường kẻ dạng hình chữ nhật mảnh `re`, không phải nét `l`; nét dọc có hình bao rộng 0 nên `Rect.intersects` luôn sai | `admin_layout.extract_rules` nhận cả `re`/`qu` mảnh, nới hình bao nét dọc 0,5 pt |
| Bảng dữ liệu cao dần mỗi hàng ~0,5 pt | Word cộng độ dày nét viền vào chiều cao hàng `atLeast` | `trHeight` = khoảng cách 2 viền trên PDF − 0,5 pt; khoảng trống trước bảng chuyển thành `space_after` của đoạn trước |
| Chế độ `word_com` luôn lùi về `hybrid` | Script PowerShell đặt `param(...)` sau `$ErrorActionPreference` | `param` phải là câu lệnh đầu tiên; ghi script UTF-8 có BOM |
| Nút `QRadioButton` đang chọn không hiện chấm tròn | Kiểu `windows11` của Qt 6 + QSS của `theme.py` không vẽ indicator khi đã chọn (lỗi có sẵn) | **Đã sửa**: `theme.py` tự vẽ `QRadioButton::indicator` (chấm = `qradialgradient` màu nhấn/trắng) và `QCheckBox::indicator` (ô tô màu nhấn + SVG ✔) cho cả Sáng/Tối, kể cả `:hover`/`:disabled`. Bảng màu `Accent` vẫn đúng — đừng sửa palette |
| Python ghi tệp bằng `Path.write_text` trên Windows đổi xuống dòng sang CRLF | Chế độ văn bản dịch `\n` → `os.linesep`; kho dùng `eol=lf` (`.gitattributes`) | Ghi bằng `write_text(..., newline="\n")` hoặc công cụ Write/Edit |
| Trang PDF 3 trang khi sang Word bị tràn vài dòng sang trang thứ 4 | Word mặc định cộng dồn khoảng cách dòng lớn hơn PDF | Đặt `<w:snapToGrid w:val="0"/>`, `w:header="0" w:footer="0"` và nhân hệ số `line_spacing_factor = 0.93` trong `openxml_fixer.py` để giữ nguyên đúng 3 trang như PDF gốc |

---

## 6. Việc cần làm tiếp theo (Theo thứ tự ưu tiên cho Agent phiên sau)

1. **Kiểm thử engine `nd30` trên văn bản hành chính thật** (PDF ký số VGCA có số/ngày đóng dấu đè, PDF từ phần mềm quản lý văn bản, PDF in từ LibreOffice, văn bản nhiều phụ lục khổ ngang). Quy trình: `python -m qtpdfpro.cli convert <tệp> --mode nd30 --verify-layout`; mọi kết quả «Lệch nhỏ» phải truy nguyên bằng `compare_pdf_layouts` và bổ sung test. Văn bản chỉ dùng nội bộ, **không** đưa vào `samples/` nếu có thông tin thật.
2. **Hiện thực các công cụ đang «Coming Soon»** theo `docs/DE_XUAT_TINH_NANG.md` — mỗi công cụ xong thì đặt `ready=True` trong `qtpdfpro/ui/tool_catalog.py` và thêm nhánh xử lý trong `MainWindow.run_tool`. Ưu tiên: Xem 2 trang (v0.4), OCR tiếng Việt (v1.1). (Chuyển đổi hàng loạt đã xong.)
3. **Phát hành bản kế tiếp (v0.4.0)** khi xong «Xem 2 trang»: tăng `__version__`, thêm mục `## [0.4.0]` vào CHANGELOG (test `test_version.py` kiểm), chạy `build.bat`, nén `dist\QTPdfPro` thành `QTPdfPro-v0.4.0-win64.zip`, `git tag v0.4.0` + push, `gh release create` kèm tệp zip (bản trước: [v0.3.0](https://github.com/quangthoai1985/QTPdfPro/releases/tag/v0.3.0)).

---

## 7. Danh sách kiểm tra bắt buộc trước khi báo "Xong"

- [x] `python -m pytest -q tests` chạy qua 100% không có lỗi.
- [x] Nếu sửa giao diện (`qtpdfpro/ui/`): chạy thử cửa sổ với `QT_PDF_PRO_DATA` tạm và kiểm tra hiển thị tiếng Việt.
- [x] Nếu sửa engine chuyển đổi (`qtpdfpro/core/`): chạy `python -m qtpdfpro.cli convert samples/nd30/<tệp>.pdf -o <thư mục tạm>/x.docx --mode nd30 --verify-layout` cho cả 3 văn bản mẫu — kết quả phải là «Trùng khớp PDF gốc» (không ghi tệp DOCX vào `samples/`).
- [x] Cập nhật [CHANGELOG.md](CHANGELOG.md) và tệp `CLAUDE.md` này.
- [x] Thực hiện `git commit` và `git push` lên kho lưu trữ GitHub `quangthoai1985/QTPdfPro`.
