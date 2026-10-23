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

- [x] **Chuẩn thể thức Nghị định 30/2020/NĐ-CP (`v0.3.0`)**: chế độ `nd30` tái dựng văn bản hành chính giữ đúng bố cục PDF, đối chiếu thể thức 26 hạng mục, kiểm chứng bố cục bằng Microsoft Word.
- [x] **Trang chủ kiểu PdfCraft (`v0.3.0`)**: danh mục «Tất cả công cụ» + bảng lệnh `Ctrl+K`; mọi công cụ dưới đây đã hiển thị trên giao diện với nhãn **«Coming Soon»** (xem `qtpdfpro/ui/tool_catalog.py`, trường `milestone`).

| Công cụ «Coming Soon» | Mốc dự kiến |
|---|---|
| Xem 2 trang song song | v0.5 |
| Scan & OCR tiếng Việt | v1.2 |
| PDF sang Excel / ảnh / PowerPoint, Tạo PDF từ Word / ảnh, Điền biểu mẫu, Nén PDF | v1.2 |
| Ký số PDF, Xác thực chữ ký số, Đặt mật khẩu, Xoá thông tin nhạy cảm, So sánh 2 tệp PDF | v2.0 |

> Mốc mới của Nén PDF, Đặt mật khẩu, So sánh 2 tệp PDF… xem mục **«Lộ trình gần»** ngay dưới. Khi bắt tay làm công cụ nào thì sửa trường `milestone` (hoặc đặt `ready=True`) trong `qtpdfpro/ui/tool_catalog.py` cho khớp.

---

## Lộ trình gần (v0.5 – v0.8 → v1.1 → v2.0): Hoàn thiện trình đọc, công cụ văn phòng & vỏ ứng dụng

> **Nguồn**: khảo sát [cit-pdf](https://github.com/Cuongyd196/cit-pdf) ngày 2026-10-20 (bản desktop Electron của BentoPDF, AGPL-3.0, hơn 50 công cụ). Kết luận chính:
> - **Chuyển PDF → Word của QT PDF Pro vượt xa** (cit-pdf dùng PyMuPDF/pdf2docx mặc định, không có tuỳ chọn); **giữ nguyên công nghệ** Python + PySide6 + PyMuPDF native — nhanh và nhẹ hơn Electron + WASM (PyMuPDF chạy trong Pyodide, Ghostscript, LibreOffice, Tesseract.js).
> - **Chỉ học ý tưởng, KHÔNG chép mã cit-pdf**: mã AGPL chép vào sẽ buộc cả dự án theo AGPL (dự án đang là MIT).
> - **Không làm nhóm tiện ích scan** (gộp mặt trước/mặt sau, xoá trang trắng, nắn thẳng trang, cắt lề, N-up, tập sách) — người dùng đã có ứng dụng scan riêng.
>
> Mỗi mục có mã (**A1**, **B2**, **V3**…) để giao việc từng phần. Làm xong mục nào: đánh dấu `[x]`, ghi phiên bản, cập nhật `tool_catalog.py`, `CHANGELOG.md`, `CLAUDE.md`.

### Thứ tự làm & mốc phiên bản

| Phiên bản | Nội dung | Mã mục |
|---|---|---|
| **v0.5.0** — *đã phát hành 2026-10-20* | In PDF · Nén · Dấu nước chữ + Đánh số trang (mẫu «Chuẩn NĐ30») · Đặt / gỡ mật khẩu · Tự cập nhật từ GitHub Release | A1, A2, A3 (một phần), A4 (một phần), V4 |
| **v0.6.0** — Đọc & hoàn thiện công cụ văn phòng | Xem 2 trang song song · Một cửa sổ duy nhất · Thông báo «Đã lưu» · Đầu – chân trang / Bates / dấu nước ảnh · Metadata & làm sạch · Chèn ảnh chữ ký / con dấu | V1, V2, A3 (còn lại), A4 (còn lại), A5 |
| **v0.7.0** — Studio & So sánh | Áp công cụ ngay trên tab đang đọc có Hoàn tác · So sánh 2 PDF | B1, B2 |
| **v0.8.0** — Phát hành chuyên nghiệp | ~~Bộ cài + Portable + «Mở bằng QT PDF Pro»~~ (xong ở v1.0.0) · Tải mô-đun khi cần (kiểm tra cập nhật V4 đã có từ v0.5.0) | ~~V3~~, V5 |
| **v1.1.0** — *đã phát hành 2026-10-23* | «Điền & Ký» giai đoạn 1 (gõ chữ bắt dòng chấm, ✓ ✕, ngày, chữ ký hình ảnh) | A5, A6 (giai đoạn 1) |
| **v1.2.0** — OCR | OCR tiếng Việt → PDF tìm kiếm được & DOCX chuẩn NĐ30 (*đã làm 2026-10-23, chưa phát hành*) | B3, V5 (mô-đun OCR) |
| **v2.0.0** — Ký số | Ký số bằng USB token qua kho chứng thư Windows · Xác thực chữ ký đầy đủ | B4 |

Mọi mục đều theo quy tắc của `CLAUDE.md`: phần xử lý viết trong `qtpdfpro/core/` (không import PySide6), có lệnh CLI (hỗ trợ `--json`) và bài test; ghi tệp qua tệp tạm, từ chối ghi đè tệp nguồn đang mở như `page_ops.save_pdf`; chuỗi giao diện tiếng Việt có dấu.

### Nhóm A — Công cụ văn phòng (chỉ cần PyMuPDF 1.28 có sẵn, không thêm thư viện)

- [x] **A1. In PDF (`Ctrl+P`)** — *v0.5* — **xong 2026-10-20** (chưa phát hành): `core/printing.py`, `ui/print_job.py`, `ui/print_dialog.py`, `cli print`. Chưa chạy thử in ra giấy (cần người dùng đồng ý).
  - Lõi `core/printing.py`: phân tích khoảng trang (`1-3,5,8-`, trang hiện tại), lập kế hoạch in (tự xoay theo trang ngang/dọc, «Vừa khổ giấy» / «Cỡ thật»), kết xuất trang bằng PyMuPDF ở DPI máy in (giới hạn 300–600 dpi, `annots=True`), tuỳ chọn đen trắng (pixmap xám).
  - Giao diện: hộp thoại in tiếng Việt — chọn máy in (mặc định của Windows), số bản, khoảng trang, khổ A4/A5/A3/Letter, hướng giấy, in 2 mặt, màu/đen trắng, **xem trước từng trang**; nhớ thiết lập lần trước trong `settings.json`; in trong `QThread` có tiến trình.
  - Xong khi: test in ra PDF bằng `QPrinter` (`OutputFormat.PdfFormat`) đúng số trang & hướng; chạy thử in thật một trang.
- [x] **A2. Nén PDF** — *v0.6* — **xong 2026-10-20** (`core/compress.py`, `cli compress`, hộp thoại «Nén PDF»; chưa phát hành).
  - `doc.rewrite_images(dpi_threshold, dpi_target, quality)` theo 3 mức Nhẹ / Vừa / Mạnh, `subset_fonts()`, `save(garbage=4, deflate=True, clean=True, use_objstms=1)`.
  - Báo dung lượng trước/sau; không ghi nếu kết quả không nhỏ hơn. **Cảnh báo trước** khi tệp có chữ ký số (ghi lại toàn bộ tệp làm chữ ký mất hiệu lực).
- [ ] **A3. Đóng dấu nước, Đánh số trang, Đầu – chân trang, Đánh số Bates** — *v0.6*. **Đã xong 2026-10-20**: dấu nước chữ & đánh số trang (`core/page_stamp.py`, `cli watermark` / `cli number --preset nd30`). **Còn**: đầu – chân trang, Bates, dấu nước bằng ảnh (dùng lại `_TextStamps` / `show_pdf_page`).
  - Dấu nước chữ: nội dung tiếng Việt, cỡ, độ mờ, góc xoay, màu, giữa trang hoặc lát gạch, khoảng trang. Dùng phông Windows nhúng tập con như cách `annotations.py` dựng hộp chữ (tránh lỗi «Ỷ» → «Ý» của Helvetica dựng sẵn). Dấu nước bằng ảnh làm sau.
  - Đánh số trang: 6 vị trí đầu/chân trang, mẫu «1», «Trang 1», «1 / 10», bắt đầu từ số bất kỳ, bỏ trang đầu, lề theo mm, đúng cả trang có `/Rotate`. Có mẫu sẵn **«Chuẩn NĐ30»**: giữa lề trên, Times New Roman 13–14, không đánh số trang đầu.
  - Đầu – chân trang (chữ trái/giữa/phải, có `{trang}`, `{tong}`, `{ngay}`, `{tep}`); đánh số Bates (tiền tố + số 6 chữ số) cho hồ sơ.
  - Cảnh báo chữ ký số như A2.
- [ ] **A4. Mật khẩu & quyền, Metadata, Làm sạch PDF** — *v0.6* (công cụ `protect` trước đây dự kiến v2.0). **Đã xong 2026-10-20**: đặt / gỡ mật khẩu AES-256 & quyền (`core/pdf_security.py`, `cli protect` / `cli unlock`). **Còn**: metadata, làm sạch.
  - Đặt mật khẩu AES-256 (mật khẩu mở + mật khẩu chủ, quyền in / sao chép / sửa / chú thích); gỡ mật khẩu khi biết mật khẩu.
  - Xem/sửa metadata (tiêu đề, tác giả, chủ đề, từ khoá), xoá metadata.
  - Làm sạch bằng `doc.scrub()`: gỡ JavaScript, tệp đính kèm, XMP, chú thích ẩn, thông tin nhạy cảm còn sót.
- [x] **A5. Chèn ảnh chữ ký / con dấu + thư viện ảnh đã lưu** — **xong 2026-10-23** trong «Điền & Ký» giai đoạn 1 (`core/fill_sign.py`, `ui/signature_dialog.py`, `cli fill` / `cli signature`; phát hành ở v1.1.0): chữ ký vẽ / gõ tên / ảnh / ảnh chụp tách nền giữ màu mực, thư viện mã hoá DPAPI, đặt bằng nhấp hoặc kéo khung. Con dấu dùng chung đường «ảnh».
  - Công cụ «Ảnh» trong chế độ chỉnh sửa: chèn PNG/JPG, kéo đặt vị trí, đổi cỡ giữ tỷ lệ; tạo thành chú thích có `/AP` chứa ảnh (giống dấu đóng hiện có) để di chuyển, hoàn tác được; làm phẳng khi xuất.
  - Thư viện ảnh lưu ở `<thư mục dữ liệu>/signatures/`; nút **«Tách nền trắng»** bằng OpenCV (đã có trong `requirements.txt`) biến nền giấy của con dấu/chữ ký scan thành trong suốt, giữ màu đỏ/xanh.
  - Ghi rõ trên giao diện: đây là **chữ ký hình ảnh**, không phải chữ ký số (xem B4).

- [ ] **A6. «Điền & Ký» (Fill & Sign)** — giai đoạn 1 **xong 2026-10-23**, phát hành ở **v1.1.0**: chế độ «Điền & Ký» (`Ctrl+Shift+F`), gõ chữ tự bắt dòng chấm «……» / gạch dưới / đường kẻ, dấu ✓ ✕ ● ─ tự vào ô vuông, ngày tháng (mẫu NĐ30), chữ ký & chữ ký nháy (gồm A5). Học ý tưởng từ PdfCraft (`ui-egui/src/fill_sign.rs`, `engine/src/signature_scan.rs`, Apache-2.0 — không chép mã), cải tiến: bắt dòng chấm khi điền, giữ màu mực từng điểm (PdfCraft tô một màu trung bình), mã hoá thư viện bằng DPAPI.
  - **Giai đoạn 2**: điền biểu mẫu PDF có ô nhập thật (AcroForm: `page.widgets()`, ô chữ / ô chọn / danh sách) — phải tự dựng `/AP` bằng phông Windows như hộp chữ (hình MuPDF tự sinh dùng Helvetica, sai dấu tiếng Việt); tự dò ô cần điền trên đơn in sẵn để tạo ô nhập.
  - **Giai đoạn 3**: ký số (B4) dùng chữ ký trong thư viện làm hình hiển thị.
  - Có thể thêm: phông viết tay có đủ chữ tiếng Việt (phông viết tay của Windows thiếu «ễ», «ư»… nên gõ tên đang lùi về Times New Roman nghiêng), gõ chữ trực tiếp trên trang thay cho hộp nhập.

### Nhóm B — Giá trị cao, công sức vừa

- [ ] **B1. Áp công cụ ngay trên tab đang đọc (kiểu «Studio») có Hoàn tác** — *v0.7*, cần A2, A3.
  - Ngăn bên phải của tab đang đọc: Xoay, Xoá trang, Chèn PDF khác, Trích trang, Đóng dấu nước, Đánh số trang, Làm phẳng, Nén — áp thẳng lên tài liệu, giữ nguyên trang & mức thu phóng.
  - Một lịch sử chung cho cả chú thích lẫn thao tác trang: Hoàn tác/Làm lại (thao tác trang lưu ảnh chụp `doc.tobytes()`, tối đa ~20 bước, cũ hơn thì gộp vào bản gốc), danh sách các bước, «Khôi phục bản gốc». `EditSession` phải `rebind` khi số trang đổi.
  - Lưu một lần bằng `Ctrl+S` / Lưu thành sẵn có; dấu ● trên tab đã có.
- [ ] **B2. So sánh 2 tệp PDF** — *v0.7* (công cụ `compare` trước đây dự kiến v2.0).
  - Ghép cặp trang theo độ giống nội dung (chịu được trang chèn thêm/bị xoá), so chữ theo từ bằng `difflib` (dùng lại cách `layout_verify.compare_pdf_layouts`), tô **xanh** phần thêm, **đỏ** phần bị xoá trên 2 khung đọc cạnh nhau cuộn đồng bộ.
  - So hình cho trang có ảnh/con dấu: hiệu điểm ảnh bằng `numpy` trên trang đã kết xuất, có ngưỡng.
  - Xuất báo cáo (PDF có chú thích đánh dấu + JSON); lệnh `cli compare a.pdf b.pdf --json`. Dùng để so các bản dự thảo văn bản.
- [x] **B3. OCR tiếng Việt → PDF tìm kiếm được & DOCX chuẩn NĐ30** — *v1.2* — **xong 2026-10-23 (chưa phát hành)**: `core/ocr.py`, `core/ocr_models.py`, `ui/ocr_dialog.py`, `cli ocr`, `tools/export_ocr_models.py`. Phương án chốt bằng thử nghiệm cùng ngày (số liệu, phương án bị loại: Giai đoạn 2).
  - Phạm vi: **PDF ảnh nhận được** (văn bản scan do nơi khác gửi), không làm khâu scan.
  - **Dây chuyền chỉ dùng ONNX Runtime** (không PyTorch, không Paddle; OpenCV + numpy đã có sẵn trong `requirements.txt`): **PP-OCRv6 det small** tìm dòng chữ → cắt dòng dài → **VietOCR `vgg_seq2seq`** (xuất ONNX) đọc chữ. Đo trên bản scan thật: lỗi ký tự 0,75%, lỗi từ 3,3%, 3 lỗi dấu / 986 từ, **5,1 giây/trang** trên CPU i7-7700.
  - **Giữ lớp chữ sẵn có** của trang (số, ngày do phần mềm cấp số chèn sau khi scan — không có trong ảnh) và chỉ OCR phần ảnh, ghép theo toạ độ.
  - Lọc nét đỏ (con dấu) / xanh (chữ ký) trước khi tìm dòng; giữ ảnh con dấu, chữ ký để neo lại vào DOCX.
  - Đầu ra: PDF có lớp chữ ẩn (tìm kiếm, sao chép) và `TextLine` có toạ độ cho `admin_layout` → `nd30_engine`.
  - **Điểm khác biệt**: đưa kết quả OCR vào engine `nd30` → văn bản hành chính scan thành DOCX đúng thể thức (cit-pdf và các ứng dụng khác không có).
  - **Kết quả bản cài đặt** (Thông tư 47, 3 trang 200 dpi): lỗi ký tự theo dòng **0,25%**, lỗi từ **2,2%**, 4 lỗi dấu / 986 từ, ~5,5 giây/trang; DOCX đúng 3 trang, phần đầu 2 cột, đậm / nghiêng, con dấu + chữ ký neo đúng chỗ (Word dựng lại). Thêm so với thử nghiệm: tách 2 cột cùng hàng, khôi phục gạch đầu dòng «-», sửa chữ hoa lạc («BGDĐT NGÀY» → «ngày»), đo chân chữ theo hình chiếu mực, tự chọn dpi theo ảnh quét.
  - Giao diện: «OCR tiếng Việt» (`Ctrl+Shift+R`, menu Tệp, chế độ Chuyển đổi, Trang chủ) — lần đầu bấm là **tự tải ngầm bộ mô hình** (không hỏi, không chặn giao diện), bấm «Nhận dạng» khi đang tải thì chạy ngay khi tải xong. CLI `ocr in.pdf [-o|--docx|--txt]`, `ocr --status|--install|--remove`.
  - Còn lại: **đăng GitHub Release `ocr-models-v1`** (pre-release, tệp `QTPdfPro_OCR_vi_v1.zip` 91 937 523 byte, SHA-256 ghim trong `ocr_models.BUNDLE_ASSET`) — chưa đăng thì nút tải báo lỗi 404; thử thêm bản scan mờ / nghiêng / có bảng / fax; bảng biểu trên trang scan chưa dựng thành bảng Word.
- [ ] **B4. Ký số bằng USB token & Xác thực chữ ký đầy đủ** — *v2.0* (chi tiết ở Giai đoạn 4).
  - cit-pdf chỉ ký bằng tệp PFX/P12 và xác thực không kiểm thu hồi — trong khi ở Việt Nam đa số dùng **USB token** (VGCA, Viettel-CA, VNPT-CA). Ký qua kho chứng thư Windows (driver token đăng ký chứng thư vào đó) hoặc PKCS#11; chuẩn PAdES (B-LT/LTA) bằng `pyHanko`, dấu thời gian TSA, hình hiển thị dùng ảnh con dấu từ A5.
  - Xác thực: `/ByteRange` phủ toàn tệp, phát hiện **«tài liệu đã bị sửa sau khi ký»** (bản ghi bổ sung sau chữ ký), chuỗi chứng thư tới gốc tin cậy (Root CA quốc gia, gốc của Ban Cơ yếu Chính phủ cho VGCA), kiểm OCSP/CRL. Nối với «Soi chữ ký số & con dấu» sẵn có.

### Vỏ ứng dụng

- [ ] **V1. Một cửa sổ duy nhất + mở tệp từ Explorer vào tab mới** — *v0.5*.
  - Hiện mở 2 tệp PDF từ Explorer sẽ chạy 2 tiến trình. Dùng `QLocalServer`/`QLocalSocket` (tên kênh theo người dùng): tiến trình thứ hai gửi danh sách đường dẫn rồi thoát; cửa sổ đang chạy mở thành tab mới và tự đưa lên trước (lưu ý giới hạn `SetForegroundWindow` của Windows).
  - Nhận nhiều tệp ở dòng lệnh (`python -m qtpdfpro a.pdf b.pdf`).
- [ ] **V2. Thông báo «Đã lưu» sau khi ghi tệp** — *v0.5*: thông báo nhỏ ở góc thay cho hộp thoại, kèm nút **Xem kết quả** (mở PDF vừa ghi thành tab mới; DOCX thì mở bằng Word) và **Mở thư mục**; dùng cho Lưu thành, chuyển đổi, ghép/tách, các công cụ nhóm A.
- [x] **V3. Bộ cài + bản Portable + «Mở bằng QT PDF Pro»** — *xong sớm ở v1.0.0 (2026-10-21)*.
  - `installer.iss` (Inno Setup 6) theo từng người dùng, không UAC, `%LOCALAPPDATA%\Programs\QT PDF Pro`: lối tắt Start Menu, gỡ cài đặt sạch, ProgID `QTPdfPro.PDF` + Capabilities + RegisteredApplications (`core/file_assoc.py`). Windows không cho tự đặt mặc định → cuối bộ cài mở `ms-settings:defaultapps?registeredAppUser=QTPdfPro`; ứng dụng hỏi một lần + mục menu. Bản Portable = `QTPdfPro_Update.zip`.
  - Đóng gói: `python tools/build_release.py` (Python, nên không vướng quy tắc `.bat`).
- [x] **V4. Kiểm tra cập nhật & cập nhật một chạm** — *xong sớm 2026-10-20 (dự kiến v0.8, phát hành cùng bản kế tiếp)*.
  - `core/update_check.py` (chỉ `urllib`, không thêm thư viện): đọc `https://api.github.com/repos/quangthoai1985/QTPdfPro/releases/latest`, so thẻ với `__version__` theo SemVer, bỏ qua bản nháp / pre-release; chọn tệp `QTPdfPro-v<x.y.z>-win64.zip` (**giữ đúng mẫu tên này khi phát hành**); chỉ nhận https + host GitHub (`api.github.com`, `github.com`, `objects.githubusercontent.com`, `release-assets.githubusercontent.com`, kiểm cả từng bước chuyển hướng), có timeout và User-Agent; tải vào `<thư mục dữ liệu>/updates/` có tiến trình, huỷ được, kiểm kích thước + SHA-256 (trường `digest`).
  - Tự kiểm tra mỗi lần mở ứng dụng (từ v1.0.2; chạy nền `QThread`, tắt được: menu Trợ giúp hoặc ô trong hộp thoại), thông báo nổi «Đã có bản vX.Y.Z — Cập nhật»; «Kiểm tra cập nhật...» kiểm tra bằng tay. Hộp thoại: ghi chú phát hành, dung lượng, «Tải về & cập nhật» / «Để sau» / «Bỏ qua bản này», thanh tiến trình, Huỷ.
  - **Chỉ tải và cài khi người dùng bấm.** Bản đóng gói: giải nén vào thư mục tạm, script PowerShell đợi ứng dụng thoát (sau khi `closeEvent` hỏi lưu các tab), đổi thư mục cài thành `.old` (khôi phục nếu lỗi), đưa bản mới vào, mở lại ứng dụng; lần mở sau xoá `.old`. Thư mục cài không ghi được (Program Files) → tải về, mở thư mục chứa tệp và hướng dẫn chép tay. Chạy từ mã nguồn → chỉ báo và mở trang phát hành.
  - CLI `update --check [--json]`, `update --download [-o thư_mục]`. Test bằng phản hồi giả lập + HTTP server cục bộ (`QT_PDF_PRO_UPDATE_API`), không gọi mạng thật.
- [ ] **V5. Tải mô-đun nặng khi cần dùng lần đầu** — *v0.8*, tiền đề cho B3. **Một phần xong 2026-10-23** cho mô-đun OCR.
  - **Đã làm** (`core/ocr_models.py`): bộ mô hình OCR tiếng Việt `QTPdfPro_OCR_vi_v1.zip` (~88 MB: `PP-OCRv6_det_small.onnx` 10 MB + VietOCR `vgg_seq2seq` ONNX 84 + 5 MB) tải từ GitHub Release `ocr-models-v1`, URL / kích thước / SHA-256 ghim trong mã, chỉ https + host GitHub (dùng lại `update_check._open`), giải nén có chặn zip-slip, kiểm từng tệp theo `manifest.json`, cài vào `%LOCALAPPDATA%\QTPdfPro\modules\ocr-vi-1\` (theo `QT_PDF_PRO_DATA` khi test); dùng được khi không có mạng sau đó. Người dùng yêu cầu **tải ngầm khi bấm lần đầu, không hỏi**. `onnxruntime` (MIT, ~14 MB nén) **đóng trong bộ cài** — chạy thư viện C++ từ wheel tải về trong bản PyInstaller dễ vỡ.
  - Còn lại: trang cài đặt xem trạng thái / tải lại / xoá từng mô-đun (hiện có CLI `ocr --status|--install|--remove`); mô-đun kế tiếp nếu cần (ví dụ `tessdata_best/script/Vietnamese.traineddata` 12 MB làm dự phòng).

---

## Giai đoạn 2 (v1.2.0): OCR Tiếng Việt cho PDF Scan & Công thức Toán học

1. **Tích hợp OCR thông minh cho PDF ảnh quét (Scanned PDF)** — kế hoạch cụ thể ở mục **B3** (cần **V5**):
   - Tự động phát hiện trang PDF không có lớp văn bản (chỉ có ảnh scan).
   - **Thử nghiệm chọn công nghệ (2026-10-23)**: bản scan thật «Thông tư 47/2026/TT-BGDĐT» (3 trang, ảnh JPEG màu 200 dpi từ HP Scan, có con dấu đỏ + chữ ký xanh, 986 từ / 4.472 ký tự). Bản chuẩn chép tay, mọi chỗ lệch đều soi lại trên ảnh. Máy đo: i7-7700 4 nhân, 32 GB RAM, card AMD (không CUDA). «Ký tự» = lỗi ký tự so từng dòng chuẩn với đoạn khớp nhất (không phụ thuộc thứ tự đọc); «Số hiệu» = từ có chữ số hoặc «BGDĐT» đọc đúng.

     | Phương án | Ký tự | Từ | Lỗi dấu | Số hiệu | Giây/trang |
     |---|---|---|---|---|---|
     | **PP-OCRv6 det small + VietOCR seq2seq, cả hai ONNX; cắt dòng dài; lọc con dấu** | 0,75% | 3,3% | 3 | 99/103 | **5,1** |
     | PP-OCRv6 det medium (chạy bằng Paddle) + VietOCR, cắt dòng dài | 0,48% | 2,9% | 5 | 100/103 | chậm (Paddle 3.3 trên CPU này phải tắt oneDNN) |
     | PP-OCRv6 det medium (ONNX) + VietOCR, cắt dòng dài | 0,68% | 3,9% | 3 | 98/103 | 28 |
     | VietOCR `vgg_transformer` (thay seq2seq) | 0,68% | 4,0% | 12 | 98/103 | 34 |
     | Tesseract 5 `tessdata_best/script/Vietnamese` 300 dpi + tự chèn dấu cách + lọc con dấu | 0,55% | 5,1% | 18 | 98/103 | 6,5 |
     | Tesseract qua `get_textpage_ocr` nguyên bản (kế hoạch cũ của B3) | 3,6% | 29% | — | 80/103 | 8 |
     | PP-OCRv5 latin, PP-OCRv6 small/medium nguyên bộ (`lang="vi"`) | 12,6–13,1% | 49–51% | — | — | 20–134 |
     | VLM PaddleOCR-VL-1.6 / SenOCR-Vi (Transformers 5.20, CPU) — chỉ đọc 5 dòng khó | | | | sai «BGDĐT» | 30–216 **mỗi dòng** |

   - **Dây chuyền đã chọn** (chi tiết để viết `core/ocr.py`):
     1. Kết xuất trang **gồm cả lớp chữ sẵn có**: văn bản scan được phần mềm cấp số chèn số hiệu / ngày dưới dạng chữ thật (`TimesNewRomanPSMT`) **sau khi scan** — ảnh nhúng không có các chữ này. Giữ nguyên span chữ thật, chỉ dùng kết quả OCR ở chỗ không có chữ thật.
     2. Lọc nét màu: `R − max(G, B) > 50` (đỏ) hoặc `B − max(R, G) > 35 và B > 80` (xanh), nới 1 px, **không** xoá điểm tối trung tính (độ sáng < 110, chênh kênh < 40 — chữ in nằm dưới con dấu). Đừng lọc theo độ bão hoà HSV + nới rộng: nhiễu màu JPEG quanh chữ đen sẽ bị xoá, chữ mòn.
     3. Tìm dòng: `PP-OCRv6_det_small.onnx` (RapidOCR 3.10, Apache-2.0; `limit_side_len 736`, `limit_type min`); hậu xử lý DB tự viết bằng OpenCV (đã có), không cần kèm gói `rapidocr`. Bản tiny gần ngang (4,8 s/trang), medium chậm gấp 4 mà hơn không đáng kể.
     4. Cắt dòng tỷ lệ > 14:1 tại cột ít mực nhất gần điểm chia: VietOCR huấn luyện với ảnh cao 32 px, rộng tối đa 512 px (16:1). **Nới `image_max_width` lên 2048 làm hỏng kết quả** (0,75% → 13–23%); cắt dòng thì 0,75% → 0,48%.
     5. Đọc chữ: VietOCR `vgg_seq2seq` (mã Apache-2.0; trọng số tải từ `vocr.vn` — kiểm điều khoản trước khi phát hành kèm) xuất thành 2 đồ thị ONNX: bộ mã hoá ảnh (CNN + GRU, 84 MB) và **một bước** giải mã (GRU + attention, 5 MB); giải mã tham lam bằng numpy (token 1 = bắt đầu, 2 = kết thúc, tối đa 128). Khớp PyTorch **144/144 đoạn**, nhanh gấp ~3. Khi xuất phải viết lại `Vgg.forward` với chỉ số chiều không âm (`transpose(2, 3).flatten(2).permute(2, 0, 1)`) — ONNX Runtime từ chối `Transpose` có `perm` âm; dựng mô hình với `cnn.pretrained = False` (không thì tải trọng số ImageNet 549 MB vô ích).
     6. Gom khung thành dòng theo chồng lấn dọc → `TextLine` (cỡ chữ từ chiều cao khung) cho `admin_layout`; PDF tìm kiếm được: chữ ẩn (`render_mode=3`) đặt theo khung từng dòng.
     7. Hậu xử lý: VietOCR **bỏ gạch đầu dòng «-»** ở dòng ngắn (13 lỗi ở «Nơi nhận») và nhầm hoa/thường ở chữ cỡ nhỏ («về» → «VỀ») — khôi phục «-» theo khung, kiểm âm tiết tiếng Việt hợp lệ để đánh dấu chỗ nghi sai, chuẩn hoá NFC.
   - **Không dùng**:
     - **Bộ đọc chữ PP-OCRv5 latin / PP-OCRv6** dù PaddleOCR 3.7 khai báo `vi`: từ điển ký tự thiếu **88/146 chữ cái tiếng Việt** (mọi chữ có dấu nặng, hỏi, dấu chồng: ạ ả ấ ầ ộ ố ủ ở ự…) → rơi chữ («Bộ» → «B», «của» → «ca»). Phần **tìm dòng** của PP-OCRv6 vẫn tốt nhất.
     - **VLM trên CPU** (PaddleOCR-VL-1.6, SenOCR-Vi ~1 tỷ tham số, Apache-2.0): đọc đúng phần lớn dòng khó nhưng mỗi token tốn bằng một lượt chạy đầy đủ (~3,8 s — bộ nhớ đệm KV không hiệu lực với `paddleocr_vl` trong Transformers 5.20; riêng bước đọc ảnh đã ~4 s/dòng); cả hai đọc «BGDĐT» → «BGDDT», PaddleOCR-VL còn bịa «Cổng TTĐT Bộ GDĐT» → «TTỄT BỘ GDỘT». Chỉ xét lại khi có GPU, và luôn đối chiếu số hiệu với kết quả VietOCR.
     - **Tesseract làm chính**: sai dấu gấp 6 lần VietOCR («bổ» → «bồ», «mầm» → «mằm»), đọc con dấu / chữ ký thành ký tự rác nếu không lọc màu. Chỉ giữ làm dự phòng khi chưa tải mô-đun OCR — khi đó **bắt buộc** tự dựng lại dấu cách (xem `CLAUDE.md` mục 5).
     - OCR của Windows (`Windows.Media.Ocr`): cần cài gói nhận dạng tiếng Việt (quyền quản trị). Surya: mã GPL-3, trọng số hạn chế thương mại. Dịch vụ đám mây (Gemini…): chính xác cao nhưng văn bản hành chính không nên gửi ra ngoài — chỉ làm tuỳ chọn có hỏi.
2. **Nhận diện Công thức Toán học (OMML)**:
   - Chuyển các ký hiệu toán học/phân số/căn thức trong PDF sang định dạng phương trình gốc của Word (`Office MathML - <m:oMath>`) thay vì ảnh tĩnh.
3. [x] **Chuyển đổi hàng loạt (Batch Conversion)** — *đã làm sớm ở `v0.3.0`* (`core/batch.py`, `cli batch`, hộp thoại «Chuyển đổi hàng loạt»):
   - Cho phép kéo-thả hàng chục tệp PDF để chuyển đổi sang DOCX với báo cáo tổng hợp.

---

## Giai đoạn 3 (v1.2.0): Công cụ Biên tập & Tổ chức Trang PDF

> **Đã làm sớm, phát hành ở `v0.4.0`**: mục 1 (ghép, tách, xoay, xoá, sắp xếp trang kéo-thả, chèn trang trắng, trích trang, điểm cắt ✂) và mục 2 (tô sáng, gạch chân, gạch ngang, gạch sóng, bút, bút dạ quang, khung/elip/đường/mũi tên, hộp chữ tiếng Việt, ghi chú dán, dấu đóng «ĐÃ DUYỆT»/«BẢN SAO»/«MẬT»…, hoàn tác, lưu ghi bổ sung giữ chữ ký số) — xem `core/page_ops.py`, `core/annotations.py`, `core/edit_session.py`, `ui/organizer_dialog.py`, `ui/annotation_tools.py`. Còn lại: sửa trực tiếp chữ có sẵn trong PDF, che thông tin (redaction), điền biểu mẫu.

1. **Ghép, Tách, Xoay, Xoá, Sắp xếp lại trang PDF** bằng giao diện kéo-thả trực quan trên lưới trang thu nhỏ.
2. **Chú thích & Đánh dấu (Annotations)**:
   - Tô sáng văn bản (Highlight), gạch chân, thêm ghi chú (Sticky Note), vẽ khung, đóng dấu (Stamp "ĐÃ DUYỆT", "BẢN SAO") và lưu trực tiếp vào PDF.
3. **Chuyển đổi đa chiều**:
   - Xuất PDF sang Excel (`.xlsx` chuyên cho bảng biểu tài chính), PowerPoint (`.pptx`), hoặc ảnh chất lượng cao (`.png`/`.tiff`).

---

## Giai đoạn 4 (v2.0.0): Chữ ký số (USB Token / VGCA) & Bảo mật PDF

1. **Ký số PDF chuẩn PAdES**: Hỗ trợ hiển thị và kiểm tra chữ ký số Việt Nam (VGCA, Viettel-CA, VNPT-CA) — kế hoạch cụ thể ở mục **B4** (ký bằng USB token, xác thực đầy đủ).
2. **Đặt mật khẩu bảo vệ / Gỡ mật khẩu PDF** (khi biết mật khẩu; dời lên `v0.6`, mục **A4**) và xoá thông tin nhạy cảm (`Redaction`).
