# Lịch sử thay đổi (Changelog)

Định dạng theo [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/); phiên bản theo [SemVer](https://semver.org/lang/vi/).
**Quy tắc bắt buộc cho mọi Agent**: Sau mỗi phiên làm việc, phải cập nhật mục mới **ở trên cùng** của tệp này (ngày giờ, việc đã làm, kết quả test, lỗi gặp phải, việc còn dở), cập nhật [CLAUDE.md](CLAUDE.md), rồi `git commit` và `git push` lên GitHub.

---

## [Chưa phát hành]

### 2026-10-20 — Lộ trình v0.5 → v2.0 sau khi khảo sát cit-pdf (chỉ tài liệu)
- Khảo sát [cit-pdf](https://github.com/Cuongyd196/cit-pdf) (bản desktop Electron của BentoPDF, AGPL-3.0): chuyển PDF → Word của ta vượt xa (họ dùng PyMuPDF/pdf2docx mặc định, không có tuỳ chọn); giữ nguyên công nghệ Python + PySide6 + PyMuPDF native (nhanh, nhẹ hơn Electron + WASM). Chỉ học ý tưởng, không chép mã AGPL.
- `docs/DE_XUAT_TINH_NANG.md`: thêm mục **«Lộ trình gần»** — bảng mốc v0.5 / v0.6 / v0.7 / v0.8 / v1.1 / v2.0 và 14 mục có mã: nhóm **A** công cụ văn phòng (A1 In PDF — hiện chưa có chức năng in, A2 Nén, A3 Dấu nước / Đánh số trang / Đầu – chân trang / Bates, A4 Mật khẩu – metadata – làm sạch, A5 Chèn ảnh chữ ký / con dấu), nhóm **B** (B1 áp công cụ ngay trên tab có Hoàn tác, B2 So sánh 2 PDF, B3 OCR → DOCX NĐ30, B4 ký số USB token & xác thực đầy đủ), **vỏ ứng dụng** (V1 một cửa sổ duy nhất, V2 thông báo «Đã lưu», V3 bộ cài + «Mở bằng», V4 kiểm tra cập nhật, V5 tải mô-đun khi cần). Ghi rõ **không làm** nhóm tiện ích scan (người dùng đã có app scan riêng). Giai đoạn 2/4 trỏ tới B3/B4; «Chuyển đổi hàng loạt» đánh dấu đã xong (v0.3.0); «Đặt mật khẩu» dời lên v0.6.
- `CLAUDE.md`: liên kết lộ trình ở đầu tệp; mục 6 xếp việc theo mã mục.
- Không đổi mã nguồn; **62/62** `pytest`.

### Việc còn dở / Ưu tiên kế tiếp cho Agent phiên sau
1. **Kiểm thử engine NĐ30 trên văn bản thật** (PDF ký số VGCA, PDF xuất từ phần mềm quản lý văn bản, PDF in từ LibreOffice): chạy `python -m qtpdfpro.cli convert <tệp> --mode nd30 --verify-layout` (hoặc `cli batch <thư mục> --verify-layout`) và xử lý các trường hợp «Lệch nhỏ».
2. **v0.5** theo «Lộ trình gần» (`docs/DE_XUAT_TINH_NANG.md`): **Xem 2 trang song song**, **A1** In PDF, **V1** một cửa sổ duy nhất, **V2** thông báo «Đã lưu»; sau đó v0.6 (A2–A5), v0.7 (B1, B2), v0.8 (V3–V5), **OCR Tiếng Việt** (B3, v1.1).
   - «Chỉnh sửa PDF» mở rộng: đổi cỡ hộp chữ/hình bằng tay nắm, sửa kiểu dáng chú thích đã có, che thông tin (redaction), dấu đóng có ảnh chữ ký.
3. Tuỳ chọn: chuyển hàng loạt song song bằng nhiều tiến trình (`ProcessPoolExecutor`, cần `multiprocessing.freeze_support()` cho bản PyInstaller).

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
