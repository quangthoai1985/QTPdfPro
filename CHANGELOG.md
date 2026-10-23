# Lịch sử thay đổi (Changelog)

Định dạng theo [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/); phiên bản theo [SemVer](https://semver.org/lang/vi/).
**Quy tắc bắt buộc cho mọi Agent**: Sau mỗi phiên làm việc, phải cập nhật mục mới **ở trên cùng** của tệp này (ngày giờ, việc đã làm, kết quả test, lỗi gặp phải, việc còn dở), cập nhật [CLAUDE.md](CLAUDE.md), rồi `git commit` và `git push` lên GitHub.

---

## [Chưa phát hành]

### Việc còn dở / Ưu tiên kế tiếp cho Agent phiên sau
1. **Kiểm thử engine NĐ30 trên văn bản thật** (PDF ký số VGCA, PDF xuất từ phần mềm quản lý văn bản, PDF in từ LibreOffice): chạy `python -m qtpdfpro.cli convert <tệp> --mode nd30 --verify-layout` (hoặc `cli batch <thư mục> --verify-layout`) và xử lý các trường hợp «Lệch nhỏ».
2. **v1.1+** (các mục v0.6–v0.8 còn lại) theo «Lộ trình gần» (`docs/DE_XUAT_TINH_NANG.md`): **Xem 2 trang song song**, **V1** một cửa sổ duy nhất, **V2** thông báo «Đã lưu», phần còn lại của **A3** (đầu – chân trang, Bates, dấu nước ảnh), **A4** (metadata, làm sạch `scrub`), **A5** chèn ảnh chữ ký / con dấu; sau đó v0.7 (B1, B2), v0.8 (V3, V5), **OCR Tiếng Việt** (B3 phát hành ở v1.2.0 — còn thử thêm bản scan mờ / nghiêng / có bảng, dựng bảng Word từ trang scan, trang cài đặt quản lý mô-đun của V5). Còn in thử 1 trang ra giấy trên máy in thật khi người dùng đồng ý.
   - «Chỉnh sửa PDF» mở rộng: đổi cỡ hộp chữ/hình bằng tay nắm, sửa kiểu dáng chú thích đã có, che thông tin (redaction), dấu đóng có ảnh chữ ký.
3. Tuỳ chọn: chuyển hàng loạt song song bằng nhiều tiến trình (`ProcessPoolExecutor`, cần `multiprocessing.freeze_support()` cho bản PyInstaller).

---

## [1.2.0] — 2026-10-23 (OCR tiếng Việt cho PDF ảnh quét & phông giao diện Inter)

### 2026-10-23 — Phát hành v1.2.0 trên GitHub
- Đăng bộ mô hình OCR [ocr-models-v1](https://github.com/quangthoai1985/QTPdfPro/releases/tag/ocr-models-v1) (**pre-release**, `QTPdfPro_OCR_vi_v1.zip` 91 937 523 byte, SHA-256 `a9f6ea0f…a71b7` khớp mã ghim); `releases/latest` vẫn trỏ bản ứng dụng. Đã tải thật bằng `ocr --install` vào thư mục dữ liệu tạm (mạng máy phát triển ~140 KB/s → ~11 phút) và nhận dạng thử trang 1 Thông tư 47 (34 dòng).
- `__version__` 1.2.0; `python tools/build_release.py`: `QTPdfPro_Setup.exe` 95,5 MB (v1.1.0: 86,8 MB — thêm onnxruntime + phông Inter), `QTPdfPro_Update.zip` = `QTPdfPro-v1.2.0-win64.zip` 137,8 MB (gốc `QTPdfPro/`, có `onnxruntime.dll`, `assets/fonts/Inter-*.ttf`).
- Máy phát triển có bản cài thật (khoá gỡ cài `…_is1` tồn tại) → theo CLAUDE.md **không** chạy thử bộ cài; chạy `dist\QTPdfPro\QTPdfPro.exe --skip-default-prompt` với dữ liệu tạm: cửa sổ «QT PDF Pro v1.2.0» mở bình thường, phông Inter đã nạp, thẻ «OCR tiếng Việt» có ở Trang chủ / «Tất cả công cụ». OCR trong môi trường đóng gói đã chạy thử riêng (PyInstaller cùng cấu hình). 182/184 `pytest`.
- Phát hành cùng phiên «Font PDFCraft tương tự» (phần phông Inter, commit 8435e59) — phiên OCR dựng và đăng bản phát hành.

### 2026-10-23 — Phông giao diện Inter giống PdfCraft
- PdfCraft (`storytold/pdfcraft`, egui) dùng **Inter** Regular / Medium / SemiBold cho giao diện. Nhúng **Inter 4.1** chính thức (`rsms/inter`, tệp trùng kích thước với bản PdfCraft dùng) vào `qtpdfpro/ui/assets/fonts/` — Regular, Medium, SemiBold, Bold (~1,6 MB) + `OFL-Inter.txt` (SIL OFL 1.1, ghi vào `THIRD_PARTY_NOTICES.md`). Đủ **146/146 chữ cái tiếng Việt** ở cả 4 độ đậm; ký hiệu / emoji Inter không có (✕ ⌂ ✂ 📂…) Qt tự lấy từ Segoe UI Symbol / Emoji.
- `theme.py`: `load_ui_fonts` / `install_ui_fonts(app)` (gọi trong `ui/app.py` trước khi dựng cửa sổ) nạp phông một lần và đặt phông ứng dụng `["Inter", "Segoe UI", "Arial"]` **không nắn nét** (`PreferNoHinting`, giống cách egui vẽ); QSS Sáng/Tối `font-family: "Inter", "Segoe UI", …`, độ đậm tối đa **600** như PdfCraft (tiêu đề, nhãn «Soon», tiêu đề bảng — trước là 700). Thiếu tệp phông thì lùi về Segoe UI như trước.
- `home_page.py`: tên công cụ ở cột «Tất cả công cụ» tự rút gọn «…» (`_ElidedLabel`) — Inter rộng hơn Segoe UI ~5% làm nhãn «Soon» bị đẩy khỏi cột («Soo»); trước đây tên dài («PDF sang Word dạng dòng chả») cũng đã bị cắt cụt. `pdf_canvas.py`: nhãn khung soi bố cục dùng phông giao diện thay cho «Segoe UI» viết cứng.
- `build.bat` + `QTPdfPro.spec`: `--add-data` thư mục `fonts` (đã dựng thử `build.bat` vào thư mục tạm: phông nằm ở `_internal/qtpdfpro/ui/assets/fonts/`, spec sinh lại trùng nội dung).
- Lỗi gặp khi làm: nắn nét **dọc** hoặc **đầy đủ** (mặc định của DirectWrite) ép Inter 13 px vào lưới điểm ảnh làm **mất dấu hỏi trên chữ có mũ** («Kiểm» → «Kiếm», «thể» → «thế», «Ổn» → «Ôn») và chữ Medium dính nhau → `PreferNoHinting`. Chiều rộng tối thiểu cửa sổ khi xem tài liệu 1184 → 1208 px (vẫn ≤ 1400).
- **182/184** `pytest` (thêm `test_ui_fonts.py` 5 bài: đủ chữ Việt trong tệp phông, nạp vào Qt không trùng, QSS, cửa sổ dùng Inter SemiBold + không nắn nét, tên dài rút gọn giữ nhãn «Soon»). Đã chụp Trang chủ + khung tài liệu Sáng/Tối, phóng to kiểm dấu tiếng Việt.

### 2026-10-23 — OCR tiếng Việt cho PDF ảnh quét (mục B3) + tải bộ mô hình ngầm lần đầu (V5, mô-đun OCR)
- **Lõi `core/ocr.py`** (không PySide6, chỉ ONNX Runtime + OpenCV + numpy): PP-OCRv6 det small tìm dòng (tiền xử lý / hậu xử lý DB viết lại theo RapidOCR, nới khung chữ nhật chính xác không cần pyclipper) → VietOCR vgg_seq2seq đọc chữ (giải mã tham lam numpy, cắt dòng > 14:1 tại khoảng trắng). Thêm so với bản thử: xoá nét đỏ / xanh trước khi đọc, tách hai cột cùng hàng (`column_spans`), khôi phục gạch «-» đầu dòng, sửa chữ hoa lạc («BGDĐT NGÀY» → «ngày»), chân chữ theo hình chiếu mực, đậm / nghiêng ước lượng từ nét chữ, cỡ chữ gom theo trung vị cả tài liệu, dpi tự chọn theo ảnh quét (200–300). Trang đã có ≥ 100 ký tự chữ thật thì bỏ qua; chữ chèn sau khi scan (số / ngày) được đọc từ trang kết xuất.
- **Đầu ra**: `ocr_pdf` — PDF tìm kiếm được (ảnh giữ nguyên, lớp chữ ẩn Times New Roman nhúng tập con, dấu cách chép ra U+0020, đúng chỗ cả trên trang `/Rotate` 90/180/270); `ocr_to_text`; `ocr_to_docx` — dựng trang chữ thật + ảnh con dấu / chữ ký rồi chuyển bằng `convert_pdf_to_docx` (văn bản hành chính tự đi đường NĐ30).
- **Kết quả trên Thông tư 47/2026/TT-BGDĐT scan thật** (3 trang, 986 từ): lỗi ký tự theo dòng 0,25%, lỗi từ 2,2%, 4 lỗi dấu, ~5,5 giây/trang trên i7-7700; DOCX đúng 3 trang như bản gốc, phần đầu 2 cột, «Căn cứ…» nghiêng, tiêu đề / «Điều» đậm, con dấu + chữ ký neo đúng chỗ (dựng lại bằng Word).
- **Bộ mô hình `core/ocr_models.py`**: `QTPdfPro_OCR_vi_v1.zip` (91 937 523 byte: PP-OCRv6 det 10 MB + VietOCR ONNX 84 + 5 MB) **không nằm trong bộ cài**; tải từ GitHub Release `ocr-models-v1` (URL / kích thước / SHA-256 ghim trong mã, chỉ https + host GitHub qua `update_check._open`), giải nén chặn zip-slip, kiểm từng tệp theo `manifest.json`, cài vào `%LOCALAPPDATA%\QTPdfPro\modules\ocr-vi-1\`. Dựng bằng `tools/export_ocr_models.py` (môi trường riêng có PyTorch; tự kiểm ONNX khớp PyTorch).
- **Giao diện `ui/ocr_dialog.py`**: «OCR tiếng Việt» (`Ctrl+Shift+R`, menu Tệp, chế độ Chuyển đổi, Trang chủ, công cụ `ocr` `ready=True`). Lần đầu bấm là **tự tải ngầm** bộ mô hình (`OcrModelController` thuộc cửa sổ chính — đóng hộp thoại vẫn tải tiếp, xong báo thông báo nổi; thoát ứng dụng thì huỷ và đợi luồng). Hộp thoại: tệp nguồn (đếm trang ảnh quét), PDF / Word / văn bản, trang, bỏ trang có chữ, bỏ nét màu; bấm «Nhận dạng» khi đang tải thì chạy ngay khi tải xong; «Dừng» giữa các trang.
- **CLI** `ocr in.pdf [-o|--docx|--txt] [--pages] [--dpi] [--all-pages] [--no-clean] [--json]`, `ocr --status|--install|--remove`.
- `page_stamp.shrink_font_tables` tách thành hàm dùng chung; `onnxruntime>=1.20.0` vào `requirements.txt` + `THIRD_PARTY_NOTICES.md` (kèm giấy phép mô hình). Bản PyInstaller đóng được onnxruntime (đã chạy OCR trong bản đóng gói thử): thư mục cài +38 MB (305 → 343 MB), gói cập nhật +18,6 MB, bộ cài ước +8 MB (LZMA).
- Lỗi gặp khi làm: kéo giãn chữ bằng `Matrix(sx, 1)` làm cỡ chữ đọc lại tăng √sx → dùng `Matrix(sx, 1/sx)`; chèn từng từ làm MuPDF dính từ → chèn cả dòng; trang xoay 90/270 phải kéo theo trục dọc; chân chữ theo 78% khung lệch ở dòng ngắn → đo theo hình chiếu mực; `tests/test_ui.py` dùng «ocr» làm ví dụ Coming Soon (mở hộp thoại thật, treo test) → đổi sang «pdf_to_excel».
- **177/179** `pytest` (thêm `test_ocr.py` 26 bài — bài mô hình thật chạy khi máy có mô hình, `test_ocr_ui.py` 6 bài). 3 văn bản mẫu NĐ30 vẫn «Trùng khớp PDF gốc». Đã chụp hộp thoại OCR giao diện Sáng / Tối.
- **Chưa làm**: đăng GitHub Release `ocr-models-v1` (pre-release) — trước khi đăng, nút tải báo lỗi 404; thử thêm bản scan mờ / nghiêng / có bảng / fax; bảng biểu trên trang scan chưa dựng thành bảng Word.

### 2026-10-23 — Thử nghiệm OCR tiếng Việt trên bản scan thật, chốt phương án cho B3 (chỉ sửa tài liệu)
- So **6 nhóm công nghệ, gần 30 cấu hình** trên «Thông tư 47/2026/TT-BGDĐT» bản scan thật (3 trang, JPEG màu 200 dpi, có con dấu đỏ + chữ ký xanh; 986 từ). Bản chuẩn chép tay, mọi chỗ lệch soi lại trên ảnh; máy i7-7700, không GPU. Mã thử nghiệm để ở thư mục tạm, **không** đưa vào kho.
- **Chốt**: PP-OCRv6 det small (ONNX) tìm dòng + VietOCR `vgg_seq2seq` (xuất ONNX, khớp PyTorch 144/144 đoạn) đọc chữ, cắt dòng dài, lọc nét đỏ / xanh, giữ lớp chữ sẵn có → lỗi ký tự 0,75%, lỗi từ 3,3%, 3 lỗi dấu, 99/103 số hiệu, **5,1 giây/trang**; chỉ cần thêm `onnxruntime` + ~100 MB mô hình (tải qua V5).
- Loại: bộ đọc chữ PP-OCRv5/v6 (từ điển thiếu 88/146 chữ cái tiếng Việt), Tesseract làm chính (sai dấu gấp 6 lần; qua PyMuPDF còn dính từ — lỗi từ 29%), VLM PaddleOCR-VL-1.6 / SenOCR-Vi trên CPU (30–216 giây mỗi dòng, đọc «BGDĐT» → «BGDDT»), OCR của Windows (thiếu gói tiếng Việt).
- Phát hiện: văn bản scan có số hiệu / ngày do phần mềm cấp số **chèn dạng chữ thật sau khi scan** — OCR riêng ảnh gốc sẽ mất số hiệu.
- Cập nhật `docs/DE_XUAT_TINH_NANG.md` (B3, V5, Giai đoạn 2 — bảng số liệu và dây chuyền chi tiết; mốc OCR v1.1 → v1.2), `CLAUDE.md` mục 5 (6 rào cản mới) và mục 6.

---

## [1.1.0] — 2026-10-23 (Điền & Ký: gõ chữ vào dòng chấm, dấu ✓ ✕, ngày tháng, chữ ký hình ảnh)

### 2026-10-23 — «Điền & Ký» giai đoạn 1: gõ chữ bắt dòng chấm, dấu ✓ ✕ ● ─, ngày tháng, thư viện chữ ký
- **Lõi `core/fill_sign.py`** (không PySide6): `find_leaders` tìm dòng chấm «……» / «.....» / gạch dưới «____» trong chữ (rawdict, chỉ dòng nằm ngang khi xem) và đường kẻ ngang mảnh không phải gạch chân chữ in sẵn; `snap_text_target` đặt chân chữ lên dòng (nâng ~0,14 cỡ chữ để dấu dưới không lẫn chấm), cỡ chữ theo chữ in quanh đó, nhấp ở ¼ đầu dòng thì bắt đầu đầu dòng; `add_fill_text` (FreeText `/IT /FreeTextTypeWriter`, hình hiển thị dựng bằng `page_stamp._TextStamps` → phông Windows nhúng tập con, `ToUnicode` gọn — chép chữ ra đúng dấu cách), `rebuild_fill_text`; `add_mark` ✓ ✕ ● ─ vẽ vector, tự căn giữa ô vuông (☐ hoặc khung 5–24 pt); `format_date` (`dmy`, `nd30`, `nd30_cap`, `dmy_dash`, `dmy_dot`); `Signature` (vẽ / gõ tên / ảnh, chữ ký nháy), `add_signature` (nhấp = cỡ mặc định 150 pt, chữ ký nháy 60 pt, giới hạn cao; kéo khung = vừa khung giữ tỷ lệ), `render_signature_png`; `clean_signature_photo` (OpenCV: đóng hình thái học trên **kênh tối nhất** để ước lượng giấy, độ đậm, ngưỡng kép + bỏ đốm, xoá mặt bàn tối, **giữ màu mực từng điểm**, cắt sát, điểm trong suốt không mang màu → PNG nhỏ), `prepare_signature_image`; `SignatureLibrary` (`<dữ liệu>/signatures/<id>.qtsig`, **mã hoá DPAPI** `CryptProtectData` + entropy riêng, tệp hỏng bị bỏ qua); `apply_fill_operations` (JSON).
- `annotations.py`: `APP_KIND_LABELS` (Chữ điền / Ngày tháng / Dấu điền / Chữ ký / Chữ ký nháy trong ngăn «Chú thích»). `EditSession`: `leaders`/`boxes` (đệm theo trang), `fill_target`, `add_fill_text`, `add_fill_mark`, `add_signature`, sửa nội dung chữ điền.
- **Giao diện**: chế độ **«Điền & Ký»** trên thanh chế độ (`CATEGORIES`, nhóm công cụ «ĐIỀN & KÝ»: Điền & Ký, Thư viện chữ ký, Điền biểu mẫu PDF — Coming Soon), `Ctrl+Shift+F`, menu Chỉnh sửa PDF, thẻ ở cột trái, `STRIP_TOOLS["fill"]`. `EditToolbar(toolset="fill")` dùng chung `AnnotationController`: Aa Gõ chữ, ✓, ✕, ●, ─, 📅 Ngày, ✍ Chữ ký, ✍ₙ Chữ ký nháy, chọn, tẩy; ô «Bắt dòng chấm / ô vuông», mẫu ngày, ô chọn chữ ký có ảnh xem trước + «Thư viện chữ ký…». Rê chuột thấy khung xem trước (vạch chân chữ). Nhấp ký khi chưa có chữ ký → hộp thoại tạo chữ ký rồi đặt luôn vào chỗ vừa nhấp. `ui/signature_dialog.py`: `SignatureCreateDialog` (thẻ Vẽ — `SignaturePad`, Gõ tên — báo khi phông thiếu chữ Việt, Ảnh có sẵn — tách nền trắng, Ảnh chụp trên giấy — thanh «độ nhạy mực», «giữ màu mực»), `SignatureManagerDialog`; ghi chú «chữ ký hình ảnh không thay thế chữ ký số».
- **CLI**: `fill` (`--text/--check/--cross/--dot/--line TRANG:X,Y[:CHỮ]`, `--date --date-format`, `--sign/--initials` + `--signature-id|--signature-image|--signature-text`, `--no-snap`, `--ops`, `--leaders`, `--flatten`, `--json`), `signature list|add|delete|clean`.
- Lỗi gặp khi làm: đóng hình thái học **từng kênh màu** coi con dấu đỏ là «giấy» ở kênh đỏ → vệt xanh quanh dấu; làm mờ ước lượng giấy tràn qua mép bóng tay thành «mực» → dùng kênh tối nhất, không làm mờ, nới vùng mặt bàn. Phông viết tay của Windows (Segoe Script/Print, Ink Free, Gabriola) **thiếu chữ tiếng Việt** → chữ ký gõ tên lùi về Times New Roman nghiêng (báo trên hộp thoại). Đọc `doc[0].load_annot(x).rect` (trang tạm bị thu hồi) gây lỗi bộ nhớ — giữ biến trang.
- **146/147** `pytest` (thêm `test_fill_sign.py` 11 bài, `test_fill_sign_ui.py` 3 bài — chuột thật trên khung đọc). Đã chụp giao diện chế độ Điền & Ký, các thẻ của hộp thoại tạo chữ ký, thư viện chữ ký.

---

## [1.0.2] — 2026-10-23 (Thanh top ngang, Trang chủ sắp lại, báo bản mới ngay khi mở)

### 2026-10-23 — Thanh top ngang, Trang chủ sắp lại, kiểm tra bản mới ngay khi mở
- **Thanh top một hàng** (`MainWindow._build_top_bar`): `⌂ Trang chủ` · `📂 Mở` · các menu **Tệp · Xem · Công cụ · Chỉnh sửa PDF · Trợ giúp** thành nút thả xuống nằm ngang (`menu_buttons`, mỗi submenu của `main_menu`; bỏ nút «☰ Menu» và «？», đổi tên menu «Công cụ && Chuyển đổi» → «Công cụ») · nhãn nhắc bản mới · ô tìm công cụ Ctrl+K (chuyển từ thanh chế độ lên) · GitHub · Sáng/Tối. Hàng tab tài liệu (`tab_strip`) tách riêng và **chỉ hiện khi có tài liệu mở**; thanh chế độ gọn lại (chiều rộng tối thiểu cửa sổ giảm). QSS mới: `topBar`, `menuBarBtn`, `openTopBtn`, `homeTabBtn` (chữ «Trang chủ»), `updateBadgeBtn`.
- **Trang chủ** (`ui/home_page.py`): lời chào gọn + nhãn phiên bản; «Bắt đầu» = thẻ **Mở tệp PDF** (kéo thả) cạnh thẻ **NĐ30** (xếp chồng khi hẹp); **Gần đây** đưa lên ngay dưới (6 tệp); **Công cụ đề xuất** xuống dưới (bỏ thẻ «Mở tệp» khỏi lưới); chân trang gom quyền riêng tư + GitHub + Bản phát hành (bỏ 2 nút này khỏi thẻ NĐ30).
- **Kiểm tra bản mới ngay khi mở**: `STARTUP_CHECK_DELAY_MS` 4000 → 600 ms; `UpdateController.start_auto_check` **bỏ giới hạn 1 lần/ngày** (hỏi GitHub mỗi lần mở, luồng nền; `core.update_check.should_auto_check` vẫn còn nhưng UI không dùng). Có bản mới là **báo ngay** (`announce`): thông báo nổi + nhãn «🎉 Có bản mới vX — Cập nhật» ở thanh top, *rồi mới* tải ngầm (trước đây chỉ báo sau khi tải xong); trong lúc tải: «Đã có bản vX — đang tải ngầm…», xong đổi sang «Khởi động lại để cập nhật» (nhãn xanh lá). Bản đã «Bỏ qua» vẫn không báo.
- **«ℹ» và «📄 Xuất Word»** chuyển vào `doc_controls` nên chỉ hiện khi đang xem tài liệu (ẩn ở Trang chủ).
- **Test**: sửa `test_update_ui.py` (không còn «cùng ngày → không hỏi lại»), thêm `test_startup_check_announces_new_version_immediately`; `test_ui.py` kiểm nút Mở, 5 menu ngang, `tab_strip` ẩn/hiện. Đã chụp thử cửa sổ Sáng/Tối (Trang chủ, khung tài liệu) — tiếng Việt hiển thị đúng.

---

## [1.0.1] — 2026-10-21 (Khung xem tài liệu gọn hơn: thanh công cụ nhanh thay cột trái)

### 2026-10-21 — Phát hành v1.0.1 trên GitHub
- `__version__` = `1.0.1`. Đóng gói bằng `python tools/build_release.py` (PyInstaller 6.22.3, Python 3.14; Inno Setup 6.7.3 chưa có trên máy nên script tự cài bằng `winget --scope user`; ISCC không cảnh báo; `QTPdfPro.spec` không đổi): `QTPdfPro_Setup.exe` **86,8 MB** (SHA-256 `27b5400c489e0d0f6f14238dea983fc4a7ab5827bb8462236f8bc39bdecba1fd`), `QTPdfPro_Update.zip` = `QTPdfPro-v1.0.1-win64.zip` **123,3 MB** (SHA-256 `7e627164190b2db66988fa31d70909551cd8c9720c8cabc58334e377777b78d3`, 321 mục, thư mục gốc `QTPdfPro/` có `QTPdfPro.exe` + `_internal/`).
- Chạy thử `dist\QTPdfPro\QTPdfPro.exe --skip-default-prompt <PDF mẫu>` với dữ liệu tạm: cửa sổ «QT PDF Pro v1.0.1 — …». **Không** cài thử / gỡ im lặng bộ cài lần này: máy đang có bản QT PDF Pro cài thật (cùng `AppId`), gỡ bản thử sẽ xoá khoá gỡ cài đặt & liên kết `.pdf` của bản thật — muốn thử bộ cài thì dùng máy ảo / tài khoản Windows khác.
- Người dùng v1.0.0 nhận bản này qua trình tải cập nhật ngầm (`QTPdfPro_Update.zip`); v0.5.0 qua `QTPdfPro-v1.0.1-win64.zip`.

### 2026-10-21 — Gọn khung xem tài liệu: ẩn cột công cụ trái, thêm thanh công cụ nhanh trên cùng
- **Cột «Tất cả công cụ» bên trái mặc định ẩn** khi xem tài liệu (khung đọc rộng thêm ~255 px). Bật lại bằng **F3**, nút **«◧ Bảng công cụ»** hoặc ☰ Menu › Xem; tắt bằng ✕ trên cột. Lựa chọn áp cho mọi tab và **được ghi nhớ** (`settings.show_tools_panel`, mặc định `False`). Đổi chế độ trên thanh chế độ **không còn tự bật** cột trái; chế độ đọc tập trung (F11) khôi phục theo lựa chọn đã nhớ.
- **Thanh công cụ nhanh** (`MainWindow.tool_strip`, tầng 3 dưới thanh chế độ, chỉ hiện khi xem tài liệu, ẩn ở Trang chủ và F11): nút đổi theo chế độ đang chọn — `STRIP_TOOLS` trong `ui/main_window.py`: *Tất cả công cụ* (Word NĐ30, Kiểm tra NĐ30, Chỉnh sửa, Sắp xếp trang, Nén, Dấu nước, Số trang, Mật khẩu, In), *Đọc* (Tìm kiếm, Trích văn bản, Mục lục, Xoay trái/phải, Đọc tập trung, Thuộc tính, In), *Chuyển đổi* (Word NĐ30 / 1:1 / dòng chảy, Tuỳ chỉnh xuất…, Kiểm tra NĐ30, Kiểm chứng DOCX, Hàng loạt), *Chỉnh sửa* (Sắp xếp trang, Ghép, Tách, Trích trang, Nén, Dấu nước, Số trang — công cụ chú thích vẫn ở thanh chỉnh sửa), *Ký số & Bảo mật* (Soi chữ ký số, Đặt / Gỡ mật khẩu, Ký số và Xác thực chữ ký hiện mờ «Coming Soon»). Nút gọi `run_tool(khoá)` (hoặc lệnh riêng `:rotate_left`, `:convert_dialog`), chú thích khi trỏ chuột lấy từ danh mục. Dùng `FlowLayout` nên tự xuống dòng, **không tăng** chiều rộng tối thiểu cửa sổ (vẫn 1376 px). QSS `toolStrip` / `stripToolBtn` / `stripToolSoonBtn` cho cả Sáng/Tối.
- Đã chụp thử cửa sổ (dữ liệu tạm) ở các chế độ Tất cả / Chuyển đổi / Chỉnh sửa, Sáng/Tối, bật/tắt cột trái: tiếng Việt hiển thị đúng. Lỗi gặp khi làm: đổi chế độ thì nút cũ còn đè nút mới (`deleteLater` chỉ xoá khi về vòng lặp sự kiện) → ẩn nút cũ ngay trước khi xoá.
- **131/132** `pytest` (1 bài in qua trình điều khiển bỏ qua mặc định). Thêm `test_tool_strip_replaces_left_panel_and_remembers_choice`; sửa `test_ui.py`/`test_edit_ui.py` theo hành vi mới (cột trái ẩn → kiểm lọc thẻ bằng `isHidden`).

---

## [1.0.0] — 2026-10-21 (Bộ cài Windows, trình xem PDF mặc định & tự cập nhật ngầm)

### 2026-10-21 — Bộ cài Inno Setup, đăng ký trình mở .pdf, tải cập nhật ngầm, phát hành v1.0.0
- **Bộ cài `installer.iss`** (Inno Setup 6.7.3, cài bằng `winget install JRSoftware.InnoSetup --scope user`) → `dist\QTPdfPro_Setup.exe`: **cài theo người dùng, không UAC** (`PrivilegesRequired=lowest`) vào `%LOCALAPPDATA%\Programs\QT PDF Pro`; lối tắt Start Menu (+ màn hình nền tuỳ chọn); giao diện tiếng Việt (`installer/Vietnamese.isl` tự viết, gộp với `compiler:Default.isl`); cài đè xoá `_internal` cũ; `AppMutex=QTPdfPro.AppMutex` (ứng dụng giữ mutex này trong `ui/app.py`) + `CloseApplications`; `/SILENT`, `/VERYSILENT /SUPPRESSMSGBOXES`. Gỡ cài đặt xoá thư mục cài, `.old`, bộ đệm `%LOCALAPPDATA%\QT PDF Pro`, mọi khoá registry; hỏi trước khi xoá thiết lập `%LOCALAPPDATA%\QTPdfPro` (gỡ im lặng thì giữ).
- **Đăng ký trình mở `.pdf`** (HKCU, `core/file_assoc.py` là nguồn chuẩn, test đối chiếu với `[Registry]` của `installer.iss`): ProgID `HKCU\Software\Classes\QTPdfPro.PDF` (lệnh mở `"…\QTPdfPro.exe" "%1"`, biểu tượng), `.pdf\OpenWithProgids`, `Applications\QTPdfPro.exe\SupportedTypes`, `Software\QTPdfPro\Capabilities\FileAssociations` + `RegisteredApplications`, `App Paths`. Windows 10/11 **không cho ứng dụng tự đặt mình làm mặc định** (`UserChoice` có mã băm, Windows 11 có driver UCPD bảo vệ `.pdf`) — nên cuối bộ cài tự mở `ms-settings:defaultapps?registeredAppUser=QTPdfPro` (trang của chính QT PDF Pro, bấm «Đặt mặc định» một lần; bỏ qua nếu đã là mặc định hoặc cài im lặng). Ứng dụng: ☰ Menu › Trợ giúp › «Đặt QT PDF Pro làm trình xem PDF mặc định...» (`ui/default_app.py`; bản giải nén tay tự đăng ký `.exe` đang chạy), lần đầu chạy bản cài hỏi một lần (`default_app_prompted`; bộ cài mở ứng dụng kèm `--skip-default-prompt` để không hỏi trùng). CLI `assoc [--status|--register --exe …|--open-settings] [--json]`.
- **Tải cập nhật ngầm** (`core/updater.py` — `auto_install_blocker`, `download_and_prepare`, `PreparedUpdate`): tự kiểm tra thấy bản mới (không «Bỏ qua») và bản đang chạy là `.exe` cài ở thư mục ghi được → `BackgroundUpdateWorker` tải `QTPdfPro_Update.zip` (kiểm SHA-256) về **`%LOCALAPPDATA%\QT PDF Pro\updates\`**, giải nén, sinh script; thông báo «✅ Bản vX.Y.Z đã tải xong — Khởi động lại để cập nhật». Không bấm thì bản mới **được cài khi thoát** (không mở lại). Lỗi tải → lùi về thông báo «Cập nhật» thủ công. Tắt được ở ☰ Menu › Trợ giúp › «Tự tải bản mới ở chế độ nền & cài khi thoát» (`auto_download_updates`).
- **`core/update_check.py`**: tệp cập nhật chính tên **`QTPdfPro_Update.zip`** (`UPDATE_ASSET_NAME`), vẫn nhận tên cũ `QTPdfPro-v<x.y.z>-win64.zip`; `updates_dir()` = `%LOCALAPPDATA%\QT PDF Pro\updates` (ngoài thư mục cài `Programs`; `QT_PDF_PRO_DATA` khi test); script `apply_update.ps1` chép lại `unins000.exe/.dat` của bộ cài sang thư mục mới và ghi `DisplayVersion` vào `HKCU\…\Uninstall\{A23779E2-FE6A-4983-9D0C-82D2465C4D8B}_is1` (`INNO_APP_ID`, trùng `AppId`); dọn `QTPdfPro_Update.zip` cũ lúc khởi động.
- **`tools/build_release.py`**: tự cài PyInstaller (pip) / Inno Setup (winget → choco) nếu thiếu, chạy `build.bat`, `iscc /DAppVersion=<__version__>`, nén `dist\QTPdfPro` → `QTPdfPro_Update.zip` (thư mục gốc `QTPdfPro/`) + bản sao tên cũ `QTPdfPro-v1.0.0-win64.zip` cho người dùng v0.5.0 (bản đó chỉ nhận tên cũ), in SHA-256.
- **Đóng gói** (PyInstaller 6.22.3, Python 3.14, Inno Setup 6.7.3 — ISCC không cảnh báo): `QTPdfPro_Setup.exe` **88,8 MB** (SHA-256 `a346164353645ea3fc327137dca28f0ee6f7e88196794d4f9ed92a1213c978b1`), `QTPdfPro_Update.zip` = `QTPdfPro-v1.0.0-win64.zip` **122,8 MB** (SHA-256 `cd3c66f904d7eba0d1c2301e2ff4c280ac14be6b2f97ae14809568641cda15df`). `QTPdfPro.spec` sinh lại không đổi nội dung.
- **Chạy thử đầu-cuối trên máy** (thư mục tạm, dữ liệu tạm): `QTPdfPro_Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /DIR=…\Cài thử\QT PDF Pro` → mã 0, có `unins000.exe/.dat`, lối tắt Start Menu, «Apps & features» hiện `QT PDF Pro 1.0.0`, `cli assoc --json` báo đã đăng ký (mặc định vẫn là `MSEdgePDF` — đúng: Windows bắt người dùng tự chọn); mở `.exe` kèm PDF mẫu bằng đúng lệnh đã đăng ký → cửa sổ «QT PDF Pro v1.0.0 — …». Hoán đổi cập nhật thật trên bản cài (giả làm 1.0.1, `QTPdfPro_Update.zip`): giải nén 3,3 giây, script mã 0, giữ `unins*`, tạo `.old`, `DisplayVersion` → `1.0.1`. Gỡ im lặng → thư mục cài, `.old`, ProgID, Capabilities, RegisteredApplications, OpenWithProgids, App Paths, khoá gỡ cài, lối tắt đều đã xoá. Chưa bấm thử giao diện bộ cài có cửa sổ (chỉ chạy im lặng).
- `__version__` = `1.0.0`. **130/131** `pytest` (1 bài in qua trình điều khiển bỏ qua mặc định). Kiểm thử mới: `tests/test_installer.py` (registry dưới khoá tạm `HKCU\Software\QTPdfProTest-…` rồi xoá, đối chiếu `installer.iss` ↔ `file_assoc`, BOM, zip cập nhật), thêm vào `test_update_check.py` (tên tệp mới, giữ `unins*` khi chạy script thật, thư mục tải mặc định) và `test_update_ui.py` (tải ngầm → khởi động lại / cài khi thoát, lỗi tải, tắt tự tải, trình xem mặc định).

---

## [0.5.0] — 2026-10-20 (In tài liệu, công cụ văn phòng & tự cập nhật)

### 2026-10-20 — Phát hành bản Release v0.5.0 trên GitHub
- Gộp vào `main` hai nhánh làm song song: «In tài liệu» (`claude/recursing-borg-149273`, A1) và «Công cụ văn phòng» (`claude/hungry-hermann-d58117`, A2 + A3/A4 một phần); xung đột chỉ ở các dòng thêm cạnh nhau (`cli.py`, `main_window.py`, `settings.py`, CHANGELOG, CLAUDE.md) — giữ cả hai bên.
- `__version__` = `0.5.0`. Danh mục: 41 công cụ — 30 dùng được; «Xem 2 trang song song» dời mốc sang **v0.6**, «So sánh 2 tệp PDF» sang **v0.7** (theo lộ trình).
- **Bản đầu tiên có trình tự cập nhật** (V4): người dùng v0.4.0 phải tải tay bản này một lần; từ v0.5.0 trở đi bấm «Cập nhật» là xong. Tệp phát hành giữ đúng mẫu `QTPdfPro-v0.5.0-win64.zip` (thư mục gốc `QTPdfPro/`).
- Đóng gói: PyInstaller 6.22.3, Python 3.14.0, PySide6 6.11.2, PyMuPDF 1.28.2 — thư mục 303,5 MB / 321 tệp, nén còn **127,1 MB** (`QTPdfPro-v0.5.0-win64.zip`, SHA-256 `544e79d6701b5f055211be654ee6b7227506b287af91dcf64e7ed272d0658deb`); `QTPdfPro.spec` sinh lại không đổi. Tệp zip tạo bằng `zipfile` (đường dẫn `/`, thư mục gốc `QTPdfPro/`) và đã giải nén thử bằng chính `update_check.extract_update` → tìm thấy `QTPdfPro/QTPdfPro.exe`.
- Chạy thử `dist\QTPdfPro\QTPdfPro.exe` (dữ liệu tạm): tiêu đề «QT PDF Pro v0.5.0 — …», mở `samples/nd30/cong_van_mau.pdf`; `Qt6PrintSupport.dll` + `QtPrintSupport.pyd` có trong gói (Qt 6 không còn plugin `printsupport` riêng). Chưa in thử ra giấy từ bản .exe.
- **121/121** `pytest` (1 bài in qua trình điều khiển Windows bỏ qua mặc định).

### 2026-10-20 — Tự phát hiện bản mới & cập nhật một chạm từ GitHub Release (mục V4)
- **`core/update_check.py`** (không PySide6, chỉ `urllib`): đọc `releases/latest` của kho trong `__github_repo__`, so thẻ với `__version__` theo SemVer (bỏ qua bản nháp, pre-release và thẻ `-rc`/`-beta`), chọn tệp **`QTPdfPro-v<x.y.z>-win64.zip`**, trả ghi chú phát hành. Tải về `<thư mục dữ liệu>/updates/` qua tệp `.part`: có tiến trình, huỷ được, kiểm kích thước + **SHA-256** (trường `digest` của asset). Chỉ nhận **https + host GitHub** (`api.github.com`, `github.com`, `objects.githubusercontent.com`, `release-assets.githubusercontent.com`), kiểm từng bước chuyển hướng và URL cuối; timeout + User-Agent `QTPdfPro/<phiên bản>`. Biến `QT_PDF_PRO_UPDATE_API` (chỉ để kiểm thử) đổi địa chỉ API và cho phép `127.0.0.1`/`localhost`.
- **Cài bản mới** (bản đóng gói onedir): giải nén vào `updates/staging` (chặn đường dẫn thoát ra ngoài), sinh `apply_update.ps1` (UTF-8 có BOM, `param` đầu tiên). Script đợi ứng dụng thoát, đổi thư mục cài thành `.old` (khôi phục nếu lỗi), chuyển bản mới vào (khác ổ đĩa thì chép), mở lại ứng dụng; lần khởi động sau báo «Đã cập nhật lên …» và xoá `.old`, thư mục tạm, tệp zip cũ. Thư mục cài không ghi được (Program Files) → chỉ tải về, mở thư mục chứa tệp và hướng dẫn chép tay. Chạy từ mã nguồn → chỉ báo và mở trang phát hành.
- **Giao diện** (`ui/update_dialog.py`, `MainWindow` chỉ thêm 5 dòng): tự kiểm tra 4 giây sau khi mở, tối đa 1 lần/ngày, chạy nền `QThread`; thông báo nổi góc dưới phải «🎉 Đã có bản vX.Y.Z — Cập nhật»; hộp thoại ghi chú phát hành (Markdown), dung lượng, «Tải về & cập nhật» / «Để sau» / «Bỏ qua bản này», thanh tiến trình, Huỷ, rồi «Khởi động lại & cập nhật» / «Cài khi thoát ứng dụng». Khởi động lại đi qua `closeEvent` nên vẫn hỏi lưu tab chưa lưu (bấm Huỷ thì để cài khi thoát). ☰ Menu › Trợ giúp: «Kiểm tra cập nhật...» (báo «Bạn đang dùng bản mới nhất») và «Tự kiểm tra cập nhật khi khởi động». Cài đặt mới: `auto_check_updates`, `last_update_check`, `skipped_update_version`.
- **CLI**: `update --check [--json]`, `update --download [-o thư_mục] [--json]`.
- **Kiểm thử**: `tests/test_update_check.py` (18 bài: SemVer, bỏ pre-release, chọn asset, đúng/sai SHA-256, sai host / chuyển hướng lạ, huỷ giữa chừng, HTTP server cục bộ qua đúng `urllib`, nhịp 1 lần/ngày, zip-slip, nội dung + mã hoá script, **chạy script thật trên thư mục giả** đổi `.old`, dọn dẹp, CLI) và `tests/test_update_ui.py` (7 bài, giả lập hộp thoại modal). **87/87** `pytest`; không bài nào gọi mạng thật.
- **Chạy thử đầu-cuối trên bản `build.bat`** (thư mục tạm): bản 0.4.0 cài ở `E:\…\Ứng dụng\QTPdfPro` (có dấu và khoảng trắng, khác ổ với dữ liệu trên C:), server cục bộ phát tệp zip 166 MB của bản build 0.4.1 qua chuyển hướng 302 → tự báo bản mới, tải + kiểm SHA-256, giải nén, khởi động lại → script thay 319/319 tệp trong ~2 giây → mở lại tiêu đề «QT PDF Pro v0.4.1», thông báo «Đã cập nhật lên QT PDF Pro v0.4.1.», `.old` đã xoá. Kiểm tra thật với API GitHub: đang ở v0.4.0 → «Bạn đang dùng bản mới nhất»; tệp v0.4.0 được chuyển hướng tới `release-assets.githubusercontent.com` (được chấp nhận).
- **Việc còn dở**: khi phát hành phải giữ đúng tên tệp `QTPdfPro-v<x.y.z>-win64.zip` (thư mục gốc `QTPdfPro/` trong zip) thì trình cập nhật mới nhận ra. Bản v0.4.0 chưa có trình cập nhật — người dùng phải tải tay bản kế tiếp một lần.
### 2026-10-20 — Chức năng «In tài liệu» (Ctrl+P) — mục A1 của lộ trình v0.5
Trước đây ứng dụng chưa có chức năng in. Học ý tưởng hộp thoại in của cit-pdf (không chép mã — AGPL-3.0).

#### Thêm mới — Engine (`qtpdfpro/core/printing.py`, không phụ thuộc PySide6)
- **Khoảng trang** `parse_print_range`: cú pháp của `cli extract` (`1-3,5`, `end`, `le`/`chan`) cộng khoảng mở `8-` (từ trang 8 tới hết) và `-3`; giữ thứ tự nhập, bỏ trùng; chịu gạch ngang dài «–» khi dán từ Word. `resolve_print_pages` cho «Tất cả / Trang hiện tại / Tuỳ chọn»; `apply_subset` lọc trang lẻ / chẵn (theo số trang) và in ngược thứ tự — dùng để **in 2 mặt thủ công** trên máy in không có in 2 mặt tự động.
- **Kế hoạch in** `plan_print` / `plan_document` → `PrintPlan` gồm các `PrintSheet` (trang, góc xoay thêm, khung đặt ảnh trên tờ, tỷ lệ, cờ mất mép): khổ A4 / A5 / A3 / Letter / Legal; hướng giấy «Tự động theo trang» (theo đa số trang được in) / Dọc / Ngang; **tự xoay** trang khác hướng giấy (trang ngang trên giấy dọc xoay ngược chiều kim đồng hồ — đầu trang về mép gáy; trang dọc trên giấy ngang xoay thuận chiều); tỷ lệ «Vừa khổ giấy» (căn giữa vùng in được, tránh lề phần cứng của máy in) / «Cỡ thật (100%)» (căn giữa tờ giấy, báo mất mép) / «Chỉ thu nhỏ trang quá khổ». `job_sheets` nhân bản (trọn bộ hoặc 1-1, 2-2…) và chèn tờ trắng giữa các bộ khi in 2 mặt để bộ sau bắt đầu ở mặt trước.
- **Kết xuất** `render_sheet` / `render_sheet_pixmap`: PyMuPDF dựng ảnh đúng cỡ khung ở DPI máy in (`clamp_print_dpi` giới hạn 300–600 dpi; trang quá khổ như A0 tự hạ DPI để một ảnh ≤ 48 triệu điểm ảnh), **đen trắng = pixmap xám 1 kênh** (dữ liệu gửi máy in nhỏ hơn 3 lần), in kèm chú thích / con dấu / chữ ký (`annots=True`, tắt được).
- `PrintOptions` (chuẩn hoá giá trị lạ, `to_settings`/`from_settings` — nhớ máy in, khổ giấy, hướng, tỷ lệ, 2 mặt, màu, chất lượng; **không** nhớ số bản và khoảng trang); `printing_allowed` (tôn trọng cờ cấm in của PDF mã hoá); `snapshot_pdf_bytes` (bản chụp tài liệu kèm chú thích chưa lưu cho luồng in); `print_to_pdf` dựng «bản in» thành PDF chỉ bằng PyMuPDF.
- `settings.py`: trường mới `print_settings`.

#### Thêm mới — Giao diện
- **`ui/print_job.py`**: gửi lệnh in bằng `QPrinter` độ phân giải cao — `setFullPage(True)` (gốc toạ độ = góc tờ giấy), khổ / hướng / màu / 2 mặt, đọc lề phần cứng của máy in; để trình điều khiển tự in nhiều bản khi hỗ trợ (`supportsMultipleCopies`), ngược lại nhân bản trong lệnh in; dừng giữa chừng gọi `printer.abort()` và xoá tệp dở. Máy in ảo «Microsoft Print to PDF» / «XPS Document Writer» được hỏi nơi lưu trước (tránh hộp thoại của trình điều khiển bật lên trong luồng nền).
- **Hộp thoại «In tài liệu»** (`ui/print_dialog.py`): chọn máy in (mặc định của Windows, kèm mục «💾 Lưu bản in thành tệp PDF…»), hiện khả năng máy in (in 2 mặt tự động, máy in màu / đen trắng — mục không hỗ trợ bị làm mờ kèm gợi ý in 2 mặt thủ công), số bản + «In trọn từng bộ», trang in (Tất cả / Trang hiện tại / Tuỳ chọn + báo lỗi khoảng trang ngay khi gõ), lọc trang lẻ / chẵn, in ngược, khổ giấy, hướng, tỷ lệ, tự xoay, in 2 mặt, màu / đen trắng, chất lượng (theo máy in tối đa 600 dpi / nhanh 300 dpi), in kèm chú thích. **Xem trước từng tờ** đúng như sẽ in (tờ giấy, viền vùng in được, ảnh trang đặt theo kế hoạch, đen trắng), ◀ ▶ / PgUp PgDn, dòng tóm tắt. In trong `QThread` (luồng in mở bản chụp tài liệu riêng — PyMuPDF không dùng chung tài liệu giữa các luồng) có thanh tiến trình và nút «Dừng in»; nhớ thiết lập lần trước trong `settings.json`.
- `MainWindow`: menu «Tệp → In…» **Ctrl+P**, thẻ «🖨 In tài liệu» ở cột «Tất cả công cụ» của tab, công cụ «In tài liệu» (`print`, nhóm Đọc) trong danh mục / Ctrl+K; báo «🖨 Đã gửi n tờ tới …» / «💾 Đã lưu bản in …».
- CLI `print`: `--to-pdf` (dựng bản in ra PDF, không cần máy in), `--printer TÊN|mac-dinh`, `--plan` (xem hướng / tỷ lệ / xoay từng tờ), `--list-printers`; `--paper --orientation --scale --no-auto-rotate --grayscale --duplex --copies --no-collate --subset --reverse --no-annots --dpi --json`. Bắt buộc chọn đích — không bao giờ tự in ra máy in mặc định.

#### Kiểm thử
- `tests/test_printing.py` (12 bài): khoảng trang, tự xoay & hướng giấy, tỷ lệ & lề máy in, nhân bản / tờ trắng khi in 2 mặt, chuẩn hoá & nhớ thiết lập, DPI, ảnh xám / xoay / chú thích, `print_to_pdf`, cờ cấm in, `cli print`.
- `tests/test_print_ui.py` (5 bài): in bằng `QPrinter` `PdfFormat` ra tệp tạm (số trang, hướng, ảnh `DeviceGray`, dừng giữa chừng), hộp thoại in (khoảng trang sai, in «2-» ra PDF, nhớ thiết lập), điều hướng xem trước, Ctrl+P / thẻ công cụ / `run_tool("print")` (giả lập `exec`, không mở hộp thoại modal). Bài in qua trình điều khiển Windows («Microsoft Print to PDF» ghi ra tệp) chỉ chạy khi đặt `QTPDFPRO_NATIVE_PRINT_TEST=1`.
- Đã chạy tay: in qua trình điều khiển «Microsoft Print to PDF» trong `QThread` (3 tờ × 2 bản do trình điều khiển nhân → 6 trang, chú thích & trang xoay đúng); chụp hộp thoại Sáng / Tối kiểm tra tiếng Việt. **Chưa in thử ra giấy** trên máy in thật (cần người dùng đồng ý).
- **78/78** `pytest` đạt (+1 bài in qua trình điều khiển bỏ qua mặc định).

#### Rào cản kỹ thuật đã gặp (ghi vào CLAUDE.md mục 5)
- In qua hàng đợi in của Windows khi bật «Để Windows quản lý máy in mặc định» (`LegacyDefaultPrinterMode = 0`) làm Windows **đổi máy in mặc định** sang máy in vừa dùng — lần chạy thử với «Microsoft Print to PDF» đã đổi máy in mặc định của máy dev → bài test in qua trình điều khiển chuyển sang tuỳ chọn bật bằng biến môi trường.
- Bộ in Windows của Qt (`QAlphaPaintEngine`) ghi lại lệnh vẽ cả trang rồi phát lại khi `newPage()`/`end()`, còn `QImage` dựng từ bộ đệm PyMuPDF chỉ trỏ vào bộ nhớ → giữ ảnh của trang đang vẽ tới sau khi sang trang.
- `QPageLayout.minimumMargins()` trả cùng một bộ lề cho cả hướng dọc và ngang → dùng lề lớn nhất cho cả 4 cạnh.
- `QPrinter.setPrinterName` mất 0,2–1 giây (lần đầu với «Microsoft Print to PDF» ~1 giây) → hộp thoại lưu đệm lề theo máy in & khổ giấy và chỉ đọc sau khi đã hiện.
### 2026-10-20 — Công cụ văn phòng: Nén PDF, Đóng dấu nước, Đánh số trang, Đặt / Gỡ mật khẩu (A2, A3 một phần, A4 một phần)
Chỉ dùng PyMuPDF 1.28 có sẵn (không Ghostscript, không thêm thư viện). Học ý tưởng từ cit-pdf, **không chép mã** (AGPL).

#### Thêm mới — Engine (`qtpdfpro/core/`, không phụ thuộc PySide6)
- **`pdf_io.py`** — hàm dùng chung: `open_pdf` (đăng nhập mật khẩu; tệp hạn chế quyền sửa chỉ xử lý khi có **mật khẩu chủ**), `resolve_output` (mặc định `<tên><hậu tố>.pdf`, **từ chối ghi đè tệp nguồn** kể cả khác hoa/thường), `check_signature` (tệp có chữ ký số → `SignedDocumentError` trừ khi `allow_signed`), `write_pdf_bytes` (qua tệp tạm), `ToolResult` (`to_dict()` cho `--json`), `format_size` («1,25 MB»).
- **`compress.py`** — `compress_pdf`: `rewrite_images` theo 3 mức **Nhẹ** (> 250 → 200 dpi, JPEG 85) / **Vừa** (> 180 → 150 dpi, JPEG 75) / **Mạnh** (> 120 → 96 dpi, JPEG 60), `subset_fonts()`, `tobytes(garbage=4, deflate, clean, use_objstms=1)`; báo dung lượng trước/sau; **không ghi** khi kết quả không nhỏ hơn; tệp có mật khẩu giữ nguyên mật khẩu. PDF có ảnh 1200×1600 px (~260 dpi): 5,14 MB → 903 KB (Nhẹ) / 463 KB (Vừa) / 32,7 KB (Mạnh).
- **`page_stamp.py`** — **dấu nước chữ** (`watermark_pdf`/`apply_watermark`: tiếng Việt nhiều dòng, cỡ, độ mờ, góc bất kỳ, màu, giữa trang hoặc **lát gạch so le**, khoảng trang, đặt trên/dưới nội dung) và **đánh số trang** (`number_pages`/`apply_page_numbers`: 6 vị trí, mẫu `{n}` / `Trang {n}` / `{n} / {total}`…, bắt đầu từ số bất kỳ, bỏ trang đầu vẫn tính số, lề mm, Times New Roman / Arial; mẫu **«Chuẩn NĐ30»** = giữa lề trên, Times New Roman 13, không hiện số trang 1). Chữ vẽ trên tài liệu tạm bằng phông Windows (`insert_text` + `fontfile`, mọi nhãn dùng chung 1 phông) → `subset_fonts()` → thu gọn `/W` và `ToUnicode` về đúng ký tự đã dùng → `show_pdf_page` lên từng trang (toạ độ trang hiển thị × `derotation_matrix`, góc + `/Rotate`) — **đúng chiều trên trang xoay 90/180/270°**, chữ tìm kiếm / chép được, không lỗi «Ỷ» → «Ý».
- **`pdf_security.py`** — `protect_pdf` (**AES-256**, mật khẩu mở + mật khẩu chủ, quyền in / sao chép / sửa / chú thích; hạn chế quyền bắt buộc có mật khẩu chủ khác mật khẩu mở), `unlock_pdf` (gỡ khi biết mật khẩu; tệp hạn chế quyền cần mật khẩu chủ), `security_info`.
- `page_ops.save_pdf(doc, path, **save_options)` nhận thêm tham số `Document.save` (vd giữ mã hoá); `reader.password`.

#### Thêm mới — Dòng lệnh
- `compress`, `watermark`, `number` (`--preset nd30`), `protect`, `unlock` — đều có `--json`, `--password` (tệp nguồn có mật khẩu), `--force` (tệp có chữ ký số); lỗi → mã thoát 1.

#### Thêm mới — Giao diện
- **`ui/pdf_tools_dialog.py`**: khung `PdfToolDialog` (tệp nguồn = tệp của tab đang đọc hoặc chọn tệp, hỏi mật khẩu; nơi lưu mặc định cạnh tệp gốc; chạy `QThread`; **hỏi trước khi xử lý tệp có chữ ký số**; tệp hạn chế quyền → hỏi mật khẩu chủ rồi chạy lại) và 5 hộp thoại `CompressDialog`, `WatermarkDialog` (mẫu nhanh BẢN SAO / MẬT / DỰ THẢO…, **xem trước** trang), `PageNumberDialog` (nút «Dùng mẫu Chuẩn NĐ30», xem trước đúng số của trang), `ProtectDialog` (nhập lại mật khẩu, hiện mật khẩu, 4 quyền), `UnlockDialog` (tình trạng bảo vệ của tệp).
- `tool_catalog.py`: `compress`, `protect` → dùng được; thêm `watermark`, `page_numbers`, `unlock` (40 công cụ — 29 dùng được). `MainWindow.run_tool` → `action_pdf_tool` (tab có chú thích chưa lưu → hỏi «Lưu rồi tiếp tục / Dùng bản đã lưu»; xong → **hỏi mở tệp kết quả thành tab mới**, kèm mật khẩu). Cột trái của tab: mục «CÔNG CỤ VĂN PHÒNG» và «BẢO MẬT» (tín hiệu `PDFDocumentTab.toolRequested`); menu «Chỉnh sửa PDF» thêm 5 mục.

#### Lỗi gặp phải & cách xử lý
- **MuPDF 1.28: đọc `doc.needs_pass` sau `doc.authenticate()` làm hỏng khoá giải mã** → lần lưu sau ghi luồng nội dung rác («aes padding out of range», trang trắng). `pdf_io` chỉ đọc `needs_pass` một lần trước khi đăng nhập; sau đó dùng `is_encrypted` / `metadata["encryption"]`.
- `ToUnicode` MuPDF sinh cho Arial/Times ánh xạ glyph dấu cách → U+00A0 (chép ra «BẢN\xa0SAO»), và ghi `/W` + `ToUnicode` cho **cả phông** (~25 KB mỗi lần). Tự viết lại 2 bảng theo các ký tự đã dùng: đánh số 10 trang chỉ thêm ~21 KB/tệp (phông Times nhúng tập con), dấu nước ~17 KB, thay vì ~45 KB.
- `insert_htmlbox` trên nhiều trang của cùng tài liệu tạm nhúng **mỗi trang một bản phông** → dùng `insert_text` + `fontfile` (một phông chung) cho nhãn số trang / dấu nước.
- `QDoubleSpinBox` chưa có kiểu trong QSS giao diện Tối → ô lề dùng `QSpinBox` (mm nguyên).

#### Kiểm thử
- `tests/test_pdf_tools.py` (10 bài: nén nhỏ hơn với ảnh lớn, không ghi khi không nhỏ hơn, từ chối tệp ký số / ghi đè nguồn, dấu nước tiếng Việt + trang chọn + trang xoay + lát gạch, số trang mẫu/bắt đầu/bỏ trang đầu/vị trí mm/trang xoay, mẫu NĐ30, đặt/gỡ mật khẩu & quyền, công cụ trên tệp có mật khẩu giữ mã hoá, CLI) và `tests/test_pdf_tools_ui.py` (8 bài: danh mục, nén → mở tab kết quả, xem trước, mẫu NĐ30, hỏi chữ ký số, đặt/gỡ mật khẩu, hỏi mật khẩu chủ trên tab hạn chế quyền). **80/80** `pytest`.
- Chạy thử GUI với `QT_PDF_PRO_DATA` tạm: chụp 5 hộp thoại ở giao diện Sáng/Tối và cột công cụ — chữ tiếng Việt hiển thị đúng.

### 2026-10-20 — Lộ trình v0.5 → v2.0 sau khi khảo sát cit-pdf (chỉ tài liệu)
- Khảo sát [cit-pdf](https://github.com/Cuongyd196/cit-pdf) (bản desktop Electron của BentoPDF, AGPL-3.0): chuyển PDF → Word của ta vượt xa (họ dùng PyMuPDF/pdf2docx mặc định, không có tuỳ chọn); giữ nguyên công nghệ Python + PySide6 + PyMuPDF native (nhanh, nhẹ hơn Electron + WASM). Chỉ học ý tưởng, không chép mã AGPL.
- `docs/DE_XUAT_TINH_NANG.md`: thêm mục **«Lộ trình gần»** — bảng mốc v0.5 / v0.6 / v0.7 / v0.8 / v1.1 / v2.0 và 14 mục có mã: nhóm **A** công cụ văn phòng (A1 In PDF — hiện chưa có chức năng in, A2 Nén, A3 Dấu nước / Đánh số trang / Đầu – chân trang / Bates, A4 Mật khẩu – metadata – làm sạch, A5 Chèn ảnh chữ ký / con dấu), nhóm **B** (B1 áp công cụ ngay trên tab có Hoàn tác, B2 So sánh 2 PDF, B3 OCR → DOCX NĐ30, B4 ký số USB token & xác thực đầy đủ), **vỏ ứng dụng** (V1 một cửa sổ duy nhất, V2 thông báo «Đã lưu», V3 bộ cài + «Mở bằng», V4 kiểm tra cập nhật, V5 tải mô-đun khi cần). Ghi rõ **không làm** nhóm tiện ích scan (người dùng đã có app scan riêng). Giai đoạn 2/4 trỏ tới B3/B4; «Chuyển đổi hàng loạt» đánh dấu đã xong (v0.3.0); «Đặt mật khẩu» dời lên v0.6.
- `CLAUDE.md`: liên kết lộ trình ở đầu tệp; mục 6 xếp việc theo mã mục.
- Không đổi mã nguồn; **62/62** `pytest`.

---

## [0.4.0] — 2026-10-20 (Chỉnh sửa PDF: tô màu, đánh dấu, chú thích & sắp xếp / cắt ghép trang)

### 2026-10-20 — Phát hành bản Release v0.4.0 trên GitHub
- Gói chức năng «Chỉnh sửa PDF» (mục dưới) thành bản **v0.4.0** — bản có tính năng mới nên tăng số phụ theo SemVer; «Xem 2 trang song song» (trước dự kiến v0.4) dời sang **v0.5**.
- `__version__` = `0.4.0`; đóng gói bằng `build.bat` → `QTPdfPro-v0.4.0-win64.zip`; tag `v0.4.0`; GitHub Release: https://github.com/quangthoai1985/QTPdfPro/releases/tag/v0.4.0.
- Đóng gói: PyInstaller 6.22.3, Python 3.14.0, PySide6 6.11.2, PyMuPDF 1.28.2 — thư mục 303 MB / 319 tệp, nén còn 123,6 MB. `QTPdfPro.spec` sinh lại không đổi.
- Chạy thử `dist\QTPdfPro\QTPdfPro.exe` (dữ liệu tạm): tiêu đề «QT PDF Pro v0.4.0»; mở `samples/nd30/cong_van_mau.pdf` → đóng dấu «ĐÃ DUYỆT», tô sáng một dòng bằng chuột, `Ctrl+S` → tệp lưu có chú thích, hình hiển thị dùng phông TrueType nhúng (`/FontFile2`) — `insert_htmlbox`/`Story`/`subset_fonts` chạy được trong bản đóng gói (nhúng tập con dùng hàm của MuPDF, không cần `fontTools`).
- **Sửa trước khi phát hành — thanh công cụ chỉnh sửa ép cửa sổ rộng tràn màn hình**: khi bật chế độ chỉnh sửa trên cửa sổ ~1376 px, hàng nút (16 công cụ + Hoàn tác/Lưu…) và dòng gợi ý dài làm chiều rộng tối thiểu của cửa sổ vượt màn hình. Thêm `FlowLayout` (`ui/annotation_tools.py`) — nút công cụ và nhóm kiểu dáng tự xuống dòng; dòng gợi ý `QSizePolicy.Ignored` (thiếu chỗ thì ẩn, xem ở tooltip); các khung chứa nền trong suốt (`QWidget#editToolbarBox`). Chiều rộng tối thiểu của thanh công cụ còn ~370 px; `test_edit_ui` kiểm tra thêm (< 500 px, cửa sổ ≤ 1400 px).
- **62/62** `pytest`.

### 2026-10-20 — Chức năng «Chỉnh sửa PDF»: tô màu, đánh dấu, chú thích & sắp xếp / cắt ghép trang

#### Thêm mới — Engine (`qtpdfpro/core/`, không phụ thuộc PySide6)
- **`page_ops.py`** — tổ chức trang: mô hình `PageRef` (trang nguồn + góc xoay thêm; `page_index=None` = trang trắng), `assemble_pdf` (gom các trang liên tiếp cùng nguồn vào 1 lệnh `insert_pdf`, giữ chú thích / liên kết / trường biểu mẫu, **giữ mục lục** của trang còn lại — trỏ tới lần xuất hiện đầu tiên, sửa cấp mục lục; khi ghép nhiều tệp thêm 1 mục cấp 1 cho mỗi tệp), `merge_pdfs` (nhận `a.pdf:1-3`, chịu ổ đĩa `C:\`), `split_pdf` (mỗi N trang / theo khoảng / cắt sau các trang), `extract_pages`, `organize_pdf` theo chuỗi thứ tự (`'3,1-2r90,blank,end,le,chan'`), `save_pdf` ghi qua tệp tạm rồi đổi tên; từ chối ghi đè tệp nguồn đang mở.
- **`annotations.py`** — chú thích: tô sáng / gạch chân / gạch ngang / gạch sóng (chọn chữ theo **thứ tự đọc** từ điểm đầu tới điểm cuối như bôi đen trong Word, hoặc theo vùng), vẽ tay, bút dạ quang (Multiply, trong suốt), khung / elip / đường / mũi tên, ghi chú dán, **hộp chữ** và **dấu đóng** (9 mẫu: ĐÃ DUYỆT, BẢN SAO, MẬT, KHẨN, HỎA TỐC, ĐÃ XEM, ĐÃ KÝ, KHÔNG DUYỆT, BẢN NHÁP — kèm dòng ngày tuỳ chọn); liệt kê (`list_annotations`, kèm chữ dưới vùng tô sáng), chọn theo điểm (nét vẽ/đường xét khoảng cách tới nét), dời chú thích (`translate_annotation`), xoá mềm, làm phẳng (`bake`), `mark_text` (đánh dấu mọi chỗ có cụm từ), `apply_operations` (danh sách thao tác JSON, toạ độ trang đang hiển thị).
- **`edit_session.py`** — `EditSession`: thêm / xoá / di chuyển / sửa nội dung kèm **Hoàn tác – Làm lại** (tối đa 200 bước), trạng thái «chưa lưu» theo mốc lưu.
- **`reader.py`**: `edit_session()`, `has_unsaved_changes`, `save()` (vào chính tệp: **ghi bổ sung incremental**, giữ bản ký số trước đó; tệp không ghi bổ sung được thì ghi đè an toàn qua tệp tạm rồi mở lại; tệp khác: ghi toàn bộ rồi tab chuyển sang tệp mới), `export_flattened()`, `invalidate_pages()`, `page_view_matrix()` / `view_to_page()` (toạ độ trang chưa xoay ↔ điểm ảnh, tính cả `/Rotate` lẫn xoay xem).

#### Thêm mới — Giao diện
- **Chế độ chỉnh sửa trên khung đọc** (`ui/annotation_tools.py`): bật bằng `Ctrl+E`, chế độ «Chỉnh sửa» trên thanh trên cùng, thẻ «CHỈNH SỬA PDF» ở cột trái hoặc công cụ trong danh mục. Thanh công cụ 2 tầng: 16 công cụ (Cuộn, Chọn, Tô sáng, Gạch chân, Gạch ngang, Gạch sóng, Bút, Bút dạ quang, Khung, Elip, Đường, Mũi tên, Hộp chữ, Ghi chú, Dấu, Tẩy — phím tắt V/H/U/K/G/P/M/R/O/L/A/T/N/D/X khi con trỏ ở khung đọc) + Hoàn tác/Làm lại + «🧩 Trang» + «💾 Lưu»; tầng 2 đổi theo công cụ: 9 màu nhanh + màu tuỳ chọn (mỗi công cụ nhớ màu riêng), độ dày nét, độ đậm, phông Arial/Times/Courier + cỡ + đậm, «Tô nền», mẫu dấu + «Kèm ngày», dòng gợi ý cách dùng. Xem trước khi kéo (vùng chọn chữ, nét đang vẽ, hình, mũi tên); Shift bắt hình vuông/tròn/góc 45°; Alt chọn chữ theo vùng; trang ảnh quét tô sáng theo vùng; công cụ Chọn kéo để di chuyển, Delete để xoá, nhấp đúp để sửa nội dung; tự cuộn khi kéo sát mép.
- **Ngăn «Chú thích»** (tab thứ 5 bên phải + nút trên thanh dọc): danh sách theo trang (màu, loại, nội dung/chữ được tô, tác giả, thời gian), nhấp để đi tới & chọn, sửa nội dung, xoá.
- **«Sắp xếp & cắt ghép trang»** (`ui/organizer_dialog.py`, `Ctrl+Shift+O`; «Ghép tệp PDF» `Ctrl+Shift+M`, «Tách tệp PDF», «Trích trang»): lưới ảnh trang kéo thả (vẽ bằng delegate: số thứ tự, tệp nguồn có chấm màu, góc xoay, «Phần k», điểm cắt ✂), chọn nhiều, xoay, nhân bản, xoá, chèn trang trắng, đảo thứ tự, di chuyển (Ctrl+←/→, «Di chuyển tới vị trí…»), thêm tệp PDF (có hỏi mật khẩu), đặt điểm cắt → «Xuất các phần…», «Chia tệp…» (mỗi N trang / khoảng trang / điểm cắt / mỗi trang một tệp), trích trang chọn, hoàn tác/làm lại, menu chuột phải, thanh cỡ ảnh. Làm việc trên tài liệu đang mở (gồm cả chú thích chưa lưu); lưu đè lên tệp đang mở thì tab được đóng, ghi tệp, mở lại đúng trang.
- `MainWindow`: menu «Chỉnh sửa PDF», `Ctrl+S` Lưu / `Ctrl+Shift+S` Lưu thành (cảnh báo văn bản có chữ ký số) / Xuất bản làm phẳng, `Ctrl+Z` / `Ctrl+Y`; dấu **●** trên tab có thay đổi chưa lưu; hỏi «Lưu / Không lưu / Huỷ» khi đóng tab hoặc thoát ứng dụng. Danh mục: 8 công cụ nhóm «Chỉnh sửa» chuyển sang dùng được (thêm «Tô sáng & đánh dấu chữ», «Vẽ & hình khối»); «Chỉnh sửa PDF» vào «Công cụ đề xuất».
- Cài đặt mới `annot_author` (tên người chú thích; trống = tên đăng nhập Windows).
- CLI: `merge`, `split`, `organize`, `extract`, `annotate` (`--highlight/--underline/--strikeout` cụm từ, `--stamp … --stamp-date`, `--ops` JSON, `--flatten`, `--author`), `annots`.

#### Đã sửa
- Tô sáng kết quả tìm kiếm và khung «Soi bố cục» lệch chỗ trên trang có `/Rotate` hoặc đang xoay xem — nay đổi toạ độ qua `page_transform` (cùng phép biến đổi với chú thích).

#### Rào cản kỹ thuật đã gặp (ghi vào CLAUDE.md mục 5)
- Hộp chữ (FreeText) do MuPDF tự vẽ dùng Helvetica dựng sẵn → «Ỷ» thành «Ý»; chế độ rich-text thì thụt lề ~40 pt, lẫn phông, bỏ qua màu viền. → Tự dựng hình hiển thị bằng `insert_htmlbox` + phông Windows (nhúng tập con) trên trang tạm, chép nội dung + tài nguyên thành Form XObject (`_graft_form_xobject`) làm `/AP /N`; xoay bằng `/Matrix` theo `/Rotate`.
- Gọi `set_info` / `set_rect` sau khi gắn hình hiển thị riêng làm MuPDF coi chú thích «cần vẽ lại» và tự sinh lại bằng Helvetica → ghi `/Rect`, `/T`, `/M`, `/Contents`, `/CA` trực tiếp qua `xref_set_key`. Dấu đóng đặt `/Name /QTDauDong` để MuPDF không vẽ lại thành «APPROVED».
- Bật journal của MuPDF (undo/redo gốc) thì PyMuPDF 1.28 chặn `show_pdf_page`/`new_page`… (`ENSURE_OPERATION` → «Can't undo/redo during an operation») → tự viết lịch sử hoàn tác (xoá mềm bằng cờ Hidden, dịch ngược, khôi phục khoá).
- `set_rect` không dùng được cho Ink/Line và làm khung chữ nhật phình 1 pt mỗi lần `update()` → di chuyển bằng cách dịch mọi khoá hình học (`Rect`, `QuadPoints`, `InkList`, `L`, `Vertices`, `CL`) trong không gian PDF.
- `QImage(pix.samples, …)`: `pix.samples` tạo bytes mới mỗi lần gọi, bị giải phóng trước khi `.copy()` → ảnh rác; phải giữ biến tạm. Vẽ viền ảnh bằng `drawRect` khi chổi tô còn màu nền thẻ sẽ phủ kín ảnh → đặt `NoBrush`.
- Giữ `Page` còn sống khi dùng `Annot` (duyệt `doc[0].annots()` trên trang tạm rồi đọc `annot.rect` có thể gây segfault).

#### Kiểm thử
- **62/62** `pytest` (thêm `test_page_ops.py` 8 bài, `test_annotations.py` 8 bài, `test_edit_ui.py` 5 bài — thao tác chuột thật qua `PDFScrollViewer`: tô sáng, vẽ, đóng dấu, kéo di chuyển, hộp chữ, ghi chú, tẩy, hoàn tác, lưu; hộp thoại sắp xếp: xoay/nhân bản/xoá/trang trắng/di chuyển/kéo thả (`moveRow`)/ghép tệp/điểm cắt/lưu/tách/ghi đè tệp đang mở). `test_ui.py`: kiểm tra «Coming Soon» chuyển sang công cụ OCR.
- Kiểm chứng NĐ30 (MS Word) 3 văn bản mẫu sau khi sửa `core/`: cả 3 «Trùng khớp PDF gốc» (công văn 26/26 dòng, lệch ≤ 0,48 pt; quyết định 51/51, ≤ 0,72 pt; kế hoạch 78/78, ≤ 0,84 pt).
- Chạy thử GUI với `QT_PDF_PRO_DATA` tạm (Sáng/Tối): thanh chỉnh sửa, ngăn Chú thích, hộp thoại sắp xếp hiển thị đúng tiếng Việt; **kéo thả thật bằng chuột** trong lưới trang đổi đúng thứ tự (nhấp/rê nhẹ không đổi), Ctrl+Z hoàn tác. Dấu đóng/hộp chữ đứng thẳng và đúng tâm trên trang xoay 0/90/180/270°.

---

## [0.3.1] — 2026-10-20 (Icon ứng dụng mới)

### 2026-10-20 — Phát hành bản Release v0.3.1 trên GitHub
- Bản vá sau v0.3.0: chỉ thêm icon ứng dụng (cửa sổ, thanh tác vụ, tệp `QTPdfPro.exe`); engine chuyển đổi không đổi.
- `__version__` = `0.3.1`; đóng gói bằng `build.bat` → `QTPdfPro-v0.3.1-win64.zip`; tag `v0.3.1`; GitHub Release: https://github.com/quangthoai1985/QTPdfPro/releases/tag/v0.3.1.

### 2026-10-20 — Icon ứng dụng mới

#### Thêm mới
- **Icon QT PDF Pro**: nền vuông bo góc xanh dương (màu nhấn của app), trang tài liệu gấp góc có nhãn đỏ «PDF» và huy hiệu xanh lá mũi tên chuyển đổi. Nguồn SVG: `qtpdfpro/ui/assets/app_icon.svg` (cỡ lớn) và `app_icon_small.svg` (bản giản lược cho 16–32 px để không nhoè); `tools/make_app_icon.py` dựng bằng Qt ra `app_icon.ico` 10 cỡ (16, 20, 24, 32, 40, 48, 64, 96, 128, 256 px, ảnh PNG trong .ico) và `app_icon_256.png` (dùng trong README).
- `qtpdfpro/ui/app.py`: `app_icon()` + `app.setWindowIcon(...)` → icon ở thanh tiêu đề mọi cửa sổ/hộp thoại và thanh tác vụ. Khi chạy bằng `python -m qtpdfpro`, đặt `SetCurrentProcessExplicitAppUserModelID("quangthoai1985.QTPdfPro")` để thanh tác vụ không gộp vào nhóm «Python» (hiện icon của app); bản .exe không đặt (Windows lấy icon nhúng, và để không tách khỏi lối tắt đã ghim).
- `build.bat`: `--icon qtpdfpro\ui\assets\app_icon.ico` (nhúng icon vào `QTPdfPro.exe`) và `--add-data` chép `app_icon.ico` vào `_internal\qtpdfpro\ui\assets\` cho icon cửa sổ; `QTPdfPro.spec` sinh lại tương ứng.

#### Đã sửa
- Ứng dụng không có icon: thanh tiêu đề và thanh tác vụ hiện biểu tượng cửa sổ mặc định của Windows (chưa từng gọi `setWindowIcon`, `build.bat` chưa có `--icon`).

#### Kiểm thử
- **41/41** `pytest` (thêm `test_app_icon_has_all_sizes`: tệp .ico tồn tại, `QIcon` đọc đủ các cỡ 16/24/32/48/256).
- Chạy `python -m qtpdfpro` và `dist\QTPdfPro\QTPdfPro.exe` (dữ liệu tạm): icon mới hiện ở thanh tiêu đề và thanh tác vụ; icon nhúng trong .exe đọc lại được.

---

## [0.3.0] — 2026-10-20 (Engine chuẩn thể thức NĐ30, Chuyển đổi hàng loạt, Trang chủ kiểu PdfCraft & Phát hành Release)

### 2026-10-20 — Phát hành bản Release v0.3.0 trên GitHub
- Gộp các thay đổi «Chuyển đổi hàng loạt» và «Sửa theme» (trước ghi ở [Chưa phát hành]) vào bản **v0.3.0** (bản v0.3.0 chưa từng phát hành; «Xem 2 trang» chưa xong nên chưa lên v0.4.0).
- Đóng gói bằng `build.bat` (PyInstaller, `--onedir --windowed`) → `QTPdfPro-v0.3.0-win64.zip`; tag `v0.3.0`; GitHub Release: https://github.com/quangthoai1985/QTPdfPro/releases/tag/v0.3.0.
- README: thêm mục «Chuyển đổi hàng loạt», «Tải bản chạy ngay», lệnh `cli batch`.
- Kiểm thử: **40/40** `pytest`; chạy thử `dist\QTPdfPro\QTPdfPro.exe` (PyInstaller 6.22.3, Python 3.14, PySide6 6.11.2) với `QT_PDF_PRO_DATA` tạm — mở `samples/nd30/cong_van_mau.pdf`, tiếng Việt hiển thị đúng, tiêu đề «QT PDF Pro v0.3.0», ghi được `theme/check_ffffff.svg` (bản đóng gói có sẵn plugin `qsvg`/`qsvgicon`).
- Tệp phát hành: thư mục 304 MB / 318 tệp, nén còn 128,7 MB. `build.bat` sinh lại `QTPdfPro.spec` (chỉ khác CRLF) → khôi phục bằng `git checkout -- QTPdfPro.spec`, không commit.

### 2026-10-20 — Sửa theme: nút chọn (radio) và ô đánh dấu (checkbox) hiện rõ trạng thái

#### Đã sửa
- **`QRadioButton` đang chọn không hiện chấm** ở cả giao diện Sáng lẫn Tối (kiểu `windows11` của Qt 6 + QSS của ứng dụng không vẽ trạng thái đã chọn — bảng màu `Accent` vẫn đúng, lỗi nằm ở phần vẽ). Thấy rõ nhất ở nhóm «Phạm vi trang» của hộp thoại chuyển 1 tệp: mục «Tất cả các trang» đang chọn mà không có vòng/chấm nào.
- `qtpdfpro/ui/theme.py` (`_SHELL_TEMPLATE`, theo bảng màu Sáng/Tối) tự vẽ toàn bộ `QRadioButton::indicator` và `QCheckBox::indicator`:
  - Chưa chọn: vòng tròn / ô vuông bo góc viền `faint`, nền `indicator_bg`; di chuột: viền màu nhấn + nền `accent_soft`.
  - Radio đang chọn: hình tròn màu nhấn (`accent`) có chấm trắng giữa (gradient tròn), chấm to hơn khi di chuột — giống Windows 11.
  - Checkbox đang chọn: ô tô màu nhấn + dấu ✔ trắng (trước đây chỉ có dấu ✔, không có khung ô).
  - Trạng thái vô hiệu (`:disabled`, cả đã chọn) chuyển sang màu xám; chữ của radio/checkbox vô hiệu dùng màu `faint`.
- Dấu ✔ là tệp SVG nhỏ do `theme._check_icon()` ghi vào `<thư mục dữ liệu>/theme/check_ffffff.svg` (QSS không nhận ảnh nhúng; cách này không phải sửa `build.bat`/PyInstaller). Không ghi được tệp thì dùng `image: none` — ô đang chọn vẫn tô màu nhấn nên vẫn phân biệt được.

#### Kiểm thử
- **40/40** bài test `pytest` vượt qua (thêm `test_theme_styles_radio_and_checkbox_indicators`: QSS cả 2 theme có kiểu indicator, không còn khoá màu `@…` chưa thay, tệp SVG dấu ✔ được ghi đúng thư mục dữ liệu tạm).
- Đã chụp hộp thoại «Chuyển PDF sang Word» thật ở giao diện Tối và Sáng (kiểu `windows11`): radio «Tất cả các trang» hiện chấm, các checkbox có khung + dấu ✔; trạng thái vô hiệu hiển thị xám.

### 2026-10-20 — Chuyển đổi hàng loạt PDF sang Word

#### Thêm mới
- **Engine chuyển đổi hàng loạt** `qtpdfpro/core/batch.py` (không phụ thuộc PySide6):
  - `convert_batch(pdf_paths, out_dir, options, progress_cb, should_cancel)` chuyển lần lượt từng tệp bằng `convert_pdf_to_docx`; mặc định `default_batch_options()` = chế độ `auto` (văn bản hành chính tự dùng engine `nd30`, chính sách `faithful`), **không** kiểm chứng bằng MS Word (bật `verify_layout` nếu cần — chậm ~7 giây/tệp).
  - Kết quả `BatchReport` gồm danh sách `BatchItemResult` từng tệp: trạng thái (Hoàn tất / Thất bại / Đã huỷ), chế độ thực thi, số trang, điểm chuẩn xác (fidelity), điểm thể thức NĐ30 (nếu là văn bản hành chính), kết luận kiểm chứng Word, lỗi, ghi chú; kèm số tệp đạt/lỗi và điểm trung bình.
  - Một tệp lỗi (hỏng, có mật khẩu, không tìm thấy, DOCX đang mở trong Word…) chỉ đánh dấu tệp đó thất bại, không dừng cả lượt; `should_cancel` dừng trước tệp kế tiếp.
  - `collect_pdf_paths` gom tệp từ đường dẫn tệp/thư mục (bỏ trùng không phân biệt hoa/thường, tuỳ chọn duyệt thư mục con); `plan_output_paths` đặt tên DOCX không ghi đè lẫn nhau khi hai PDF trùng tên (`_2`, `_3`…); `write_batch_report` lưu báo cáo `.csv` (UTF-8 có BOM, mở đúng tiếng Việt trong Excel) hoặc `.json`.
- **Lệnh CLI** `python -m qtpdfpro.cli batch <thư mục | a.pdf b.pdf …> [-o <thư mục ra>] [--mode auto] [--nd30-policy faithful] [--verify-layout] [-r] [--report bao_cao.csv] [--json]`: in từng tệp khi xong và dòng tổng kết; mã thoát 1 nếu có tệp thất bại hoặc không tìm thấy PDF.
- **Hộp thoại «Chuyển đổi hàng loạt»** `qtpdfpro/ui/batch_dialog.py` (`BatchConvertDialog`): kéo thả nhiều PDF hoặc cả thư mục, nút thêm tệp/thư mục, bỏ tệp chọn; lưu vào thư mục chọn (ghi nhớ trong `settings.batch_output_dir`) hoặc cạnh từng tệp gốc; hỏi trước khi ghi đè DOCX đã có; chạy nền bằng `QThread` với thanh tiến trình và bảng điểm từng tệp (trạng thái, chế độ, số trang, chuẩn xác, thể thức NĐ30, kiểm chứng Word, tệp Word/lỗi — tô màu theo điểm); nút «Dừng» (sau tệp hiện tại), «📂 Mở thư mục kết quả», «Lưu báo cáo (.csv)…»; nhấp đúp một dòng để mở tệp Word.
- Công cụ `batch_convert` chuyển từ «Coming Soon» sang **dùng được** trên Trang chủ / bảng lệnh Ctrl+K; thêm mục menu «Tệp → Chuyển đổi hàng loạt PDF sang Word…» (**Ctrl+Shift+B**).

#### Thay đổi
- `convert_pdf_to_docx` báo lỗi tiếng Việt «Không mở được tệp PDF (tệp hỏng hoặc không đúng định dạng PDF)» thay cho thông báo tiếng Anh của PyMuPDF.
- Danh sách chế độ engine / chính sách NĐ30 tách thành `MODE_CHOICES`, `POLICY_CHOICES` trong `convert_dialog.py`, dùng chung cho hộp thoại chuyển 1 tệp và hàng loạt.

#### Kiểm thử
- **39/39** bài test `pytest` vượt qua (thêm `tests/test_batch.py` 10 bài: gom tệp/đặt tên, chuyển 3 văn bản mẫu `samples/nd30` + `sample_vietnamese_pdf` + tệp hỏng, huỷ giữa chừng, báo cáo CSV/JSON, CLI `--json` & mã thoát, hộp thoại kéo thả → chuyển → bảng điểm, `MainWindow.run_tool("batch_convert")`).
- `cli batch samples/nd30 --mode nd30 --verify-layout`: cả 3 văn bản mẫu «Trùng khớp PDF gốc» (chuẩn xác 99,9–100%, thể thức NĐ30 96,2–100%).
- Đã chụp hộp thoại thật ở giao diện Sáng và Tối (tiếng Việt hiển thị đúng).

#### Ghi chú kỹ thuật
- Sự kiện tiến trình mang **bản sao** `BatchItemResult` tại thời điểm phát — trước đó tham chiếu chung khiến nơi nhận (luồng giao diện xử lý tín hiệu muộn) thấy trạng thái đã bị luồng nền ghi đè.
- Chạy tuần tự trong một luồng: bộ vá `pdf2docx` dùng biến toàn cục theo trang nên không an toàn khi song song trong cùng tiến trình.
- Kiểu `windows11` của Qt + QSS hiện tại **không vẽ chấm của `QRadioButton` đang chọn** (lỗi có sẵn, thấy ở «Phạm vi trang» của hộp thoại chuyển 1 tệp) → hộp thoại hàng loạt dùng `QComboBox` cho nơi lưu.

### 2026-10-20 — Engine chuẩn thể thức NĐ30 giữ đúng bố cục PDF & Trang chủ kiểu PdfCraft

#### Thêm mới
- **Chế độ chuyển đổi `nd30` — tái dựng văn bản hành chính đúng thể thức Nghị định 30/2020/NĐ-CP** (`qtpdfpro/core/admin_layout.py`, `nd30_standard.py`, `nd30_engine.py`):
  - **Đo trên PDF rồi ước lượng về giá trị gốc người soạn đã đặt**: lề 4 phía (vd 29,98 mm → 30 mm), cỡ chữ, khoảng cách dòng (bội số chuẩn của Word 1,0/1,15/1,5… hoặc «Exactly 18 pt»), khoảng cách đoạn, thụt đầu dòng (1 cm / 1,27 cm). Lề dưới được ước lượng theo khoảng [cận dưới, cận trên] từ các trang đầy.
  - **Phần đầu văn bản** (Tên cơ quan | Quốc hiệu – Tiêu ngữ; Số, ký hiệu | Địa danh, ngày tháng) và **khối ký** (Nơi nhận | Quyền hạn, chức vụ, họ tên) dựng bằng **bảng 2 cột không viền**; từng dòng được căn tâm đúng toạ độ PDF bằng thụt lề đoạn trong ô.
  - **Đường kẻ giữ nguyên PDF**: dựng bằng viền dưới của đoạn văn với đúng toạ độ x và độ dài như PDF (chỉnh sửa được trong Word, không dùng ảnh). Nhận diện cả đường kẻ dạng hình chữ nhật mảnh `re` mà Microsoft Word xuất ra.
  - Số trang là trường `PAGE` ở đầu trang, không hiển thị trang 1; bảng dữ liệu có viền (gộp ô, chiều cao hàng, lề ô đo từ PDF); con dấu / chữ ký số giữ ảnh PNG trong suốt neo theo đoạn văn.
  - **Hai chính sách**: `faithful` (mặc định — giữ đúng bố cục PDF, chỉ làm tròn về giá trị chuẩn khi sai số đo nhỏ) và `nd30` (ép chuẩn hoá lề/cỡ chữ/giãn dòng/cách đoạn ≥ 6 pt theo NĐ30, có thể đổi dàn trang).
  - Chế độ `auto` tự chọn `nd30` khi trang đầu có khối Quốc hiệu – Tiêu ngữ 2 cột.
- **Đối chiếu thể thức NĐ30** (`check_nd30_compliance`): 26 hạng mục (khổ giấy, 4 lề, phông, cỡ chữ, căn lề, giãn dòng, cách đoạn, thụt đầu dòng, Quốc hiệu, Tiêu ngữ & gạch nối có cách chữ, đường kẻ dưới Tiêu ngữ/tên cơ quan, số ký hiệu, ngày tháng có số 0, tên loại, trích yếu, Nơi nhận, «Lưu: VT», chức vụ, họ tên, đánh số trang) với kết quả Đạt / Cần xem lại / Chưa đạt và điểm %.
- **Kiểm chứng bố cục bằng Microsoft Word** (`qtpdfpro/core/layout_verify.py`): xuất DOCX trở lại PDF bằng chính Word rồi so từng dòng với PDF gốc (số trang, dòng khớp, dòng bị đẩy trang, độ lệch dọc/ngang theo pt).
- **CLI**: lệnh mới `nd30 <pdf>` (báo cáo đối chiếu + thông số Word ước lượng), cờ `convert --mode nd30 --nd30-policy faithful|nd30 --verify-layout`, `verify --render`.
- **Trang chủ thiết kế lại theo [storytold/pdfcraft](https://github.com/storytold/pdfcraft)** (`qtpdfpro/ui/home_page.py`, `tool_catalog.py`, `command_palette.py`, `nd30_dialog.py`):
  - Header 2 tầng: dải tiêu đề (⌂ Trang chủ, tab tài liệu, «＋ Mở», GitHub, Trợ giúp, Sáng/Tối) và thanh chế độ («☰ Menu», Tất cả công cụ · Đọc · Chuyển đổi · Chỉnh sửa · Ký số & Bảo mật, ô tìm công cụ, «Xuất Word»).
  - Cột trái «Tất cả công cụ» (35 công cụ chia nhóm — 14 dùng được, 21 «Coming Soon», tìm không dấu, lọc theo chế độ); lời chào; thẻ nổi bật văn bản hành chính NĐ30; lưới «Công cụ đề xuất» + thẻ «Mở tệp» (kéo thả); «Gần đây» kèm số trang & dung lượng; ghi chú quyền riêng tư.
  - Công cụ chưa phát triển hiển thị nhãn **«Coming Soon»** kèm mốc dự kiến (Sắp xếp/Ghép/Tách trang, OCR, Chuyển hàng loạt, PDF sang Excel/ảnh/PowerPoint, Ký số, Đặt mật khẩu…); bấm vào chỉ hiện thông báo nhỏ.
  - Bảng lệnh **Ctrl+K** tìm mọi công cụ/lệnh và tìm chữ trong tài liệu đang mở; hộp thoại **Kiểm tra thể thức NĐ30** (Ctrl+Shift+N) và **Kiểm chứng DOCX với PDF**; chế độ đọc tập trung (F11).
  - Khung tài liệu: thêm thẻ «Xuất Word chuẩn NĐ30», «Kiểm tra thể thức NĐ30», lọc thẻ theo chế độ; thanh thông báo nhận diện văn bản hành chính.
- **Dữ liệu mẫu** `samples/nd30/` (Quyết định, Kế hoạch có bảng & con dấu, Công văn — nội dung hư cấu, tạo theo chuẩn NĐ30 rồi xuất PDF bằng Microsoft Word).

#### Sửa lỗi
- Nút «Xuất Word — Giữ vị trí 1:1» không chọn sẵn chế độ `exact` trong hộp thoại (ghi vào thuộc tính `last_convert_mode` không ai đọc) → hộp thoại nhận `initial_mode`.
- Chế độ `word_com` luôn thất bại âm thầm rồi lùi về `hybrid`: script PowerShell đặt `param(...)` sau câu lệnh khác (PowerShell bắt buộc `param` đứng đầu).
- Ký tự `&` trong tiêu đề nhóm/hộp chọn của hộp thoại chuyển đổi và nút «Mở tệp PDF để đọc & soi bố cục» bị Qt biến thành phím tắt (mất chữ).

#### Kiểm thử
- **29/29** bài test `pytest` vượt qua (thêm `tests/test_nd30.py` 11 bài và 2 bài giao diện Trang chủ / hộp thoại).
- Kiểm chứng bằng Microsoft Word trên 3 văn bản mẫu (dựng DOCX → Word xuất PDF → so từng dòng): **Quyết định 51/51 dòng, Công văn 26/26 dòng, Kế hoạch 78/78 dòng khớp; đúng số trang; lệch dọc tối đa 0,84 pt, lệch ngang tối đa 0,42 pt** (≈ 0,3 mm).

#### Ghi chú kỹ thuật (đã gặp & xử lý)
- Mẫu DOCX mặc định của `python-docx` dùng `compatibilityMode=14` (Word 2010) → ngắt dòng / căn đều khác văn bản Word hiện đại; engine NĐ30 đặt `15`.
- Word đặt baseline tại **0,8 × chiều cao dòng** khi giãn dòng «Exactly», còn với «Multiple» thì phần giãn thêm nằm **dưới** dòng chữ; Word bỏ khoảng cách trước đoạn ở đầu trang.
- Bội số giãn dòng chỉ được làm tròn khi sai lệch ≤ 0,04 pt/dòng (đo trên toàn văn bản), tránh cộng dồn lệch làm tràn trang.

---

## [0.2.0] — 2026-10-19 (Hoàn thiện Chuyển đổi Văn bản Hành chính Việt Nam 100% & Giao diện PdfCraft Sáng/Tối & Phát hành Release)

### Thêm mới
- **Đóng gói bản phát hành Windows độc lập & Xuất bản GitHub Release**:
  - Biên dịch hoàn chỉnh thành tệp thực thi độc lập `QTPdfPro.exe` bằng PyInstaller ([`build.bat`](file:///c:/Users/quang/OneDrive/Desktop/App/QTPdfPro/build.bat), [`QTPdfPro.spec`](file:///c:/Users/quang/OneDrive/Desktop/App/QTPdfPro/QTPdfPro.spec)).
  - Đóng gói tệp nén `QTPdfPro-v0.2.0-win64.zip` (125.6 MB) chứa đầy đủ runtime, DLLs và tài liệu đi kèm (người dùng giải nén là chạy được ngay, không cần cài đặt Python).
  - Xuất bản bản phát hành chính thức đầu tiên lên GitHub Releases: [Release v0.2.0](https://github.com/quangthoai1985/QTPdfPro/releases/tag/v0.2.0) kèm tệp đính kèm `QTPdfPro-v0.2.0-win64.zip`.
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
