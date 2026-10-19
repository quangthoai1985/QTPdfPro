# Thiết kế Kiến trúc Kỹ thuật của QT PDF Pro

Tài liệu này mô tả chi tiết kiến trúc mô-đun, luồng dữ liệu, cơ chế đọc/hiển thị PDF tốc độ cao và cơ chế chuyển đổi PDF sang DOCX chuẩn xác trong **QT PDF Pro**.

---

## 1. Nguyên tắc thiết kế cốt lõi

1. **Tách biệt hoàn toàn Engine (`qtpdfpro/core/`) và Giao diện (`qtpdfpro/ui/`)**:
   - Toàn bộ phần đọc PDF, phân tích bố cục, chuẩn hoá phông chữ, chuyển đổi DOCX và kiểm định chất lượng nằm trong `qtpdfpro/core/`, **không phụ thuộc vào `PySide6`**.
   - Giúp kiểm thử tự động (`pytest`) 100% logic qua dòng lệnh (`qtpdfpro/cli.py`) mà không cần mở cửa sổ đồ hoạ.
2. **Không làm đơ giao diện (Non-blocking UI)**:
   - Tác vụ chuyển đổi PDF sang DOCX chạy trên luồng nền (`QThread` / `ConversionWorker`), phát tín hiệu tiến trình theo từng trang (`progress(current, total, message)`) về luồng giao diện chính.
3. **Bảo toàn 100% thành phần tài liệu**:
   - Mọi thành phần trên trang PDF (khối văn bản, phông chữ, cỡ chữ, màu RGB, in đậm/nghiêng/gạch chân, bảng có viền, bảng ẩn viền 2 cột, hình ảnh nhúng, nét vẽ vector) đều được định danh và ánh xạ sang cấu trúc OpenXML tương ứng.

---

## 2. Sơ đồ kiến trúc tổng thể

```
┌────────────────────────────────────────────────────────────────────────────┐
│                        Giao diện Người dùng (PySide6)                      │
│  ui/main_window.py ──► Đa tab PDF, Thanh công cụ, Sidebar 4 ngăn           │
│  ui/pdf_canvas.py  ──► Khung xem PDF (Zoom, Cuộn, Tô sáng tìm kiếm/Bố cục)│
│  ui/convert_dialog.py ► Hộp thoại chuyển đổi + Báo cáo độ chính xác        │
└───────────────────┬────────────────────────────────────┬───────────────────┘
                    │ Gọi đồng bộ (render nhanh)          │ QThread (bất đồng bộ)
                    ▼                                    ▼
┌───────────────────────────────────────┐  ┌─────────────────────────────────┐
│         Engine Đọc & Phân tích        │  │    Engine Chuyển đổi PDF→DOCX   │
│  core/reader.py (PyMuPDF / fitz)      │  │  core/converter.py              │
│  core/layout_analyzer.py              │  │   ├─ Mode 1: Hybrid Structural  │
│   ├─ Render trang DPI cao (RGB)       │  │   ├─ Mode 2: Exact Frame 1:1    │
│   ├─ Mục lục (TOC), Metadata          │  │   └─ Mode 3: MS Word COM Bridge │
│   ├─ Tìm kiếm văn bản + BBox          │  │  core/font_resolver.py          │
│   └─ Phát hiện Khối chữ/Bảng/Ảnh/Hình │  │  core/openxml_fixer.py (lxml)   │
│                                       │  │  core/fidelity.py (Kiểm định)   │
└───────────────────────────────────────┘  └─────────────────────────────────┘
```

---

## 3. Thiết kế Trình đọc PDF (`core/reader.py` & `ui/pdf_canvas.py`)

1. **Kết xuất trang (Page Rendering)**:
   - Dùng `fitz.Page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)` chuyển thẳng sang bộ đệm RGB (`bytes`), nạp vào `QImage(data, w, h, stride, QImage.Format_RGB888)` → `QPixmap`.
   - Có bộ nhớ đệm trang theo mức thu phóng (`LRU Cache` tối đa 24 trang gần nhất) để cuộn lên/xuống mượt mà không cần render lại.
2. **Lớp phủ trực quan (Visual Overlays)**:
   - **Tô sáng kết quả tìm kiếm**: Khi người dùng gõ từ khoá, `reader.search(query)` trả về danh sách `(page_index, fitz.Rect, snippet)`. `pdf_canvas.py` vẽ khung màu vàng bán trong suốt (`rgba(255, 215, 0, 110)`) và viền cam quanh từ khoá đang chọn.
   - **Soi bố cục trước khi chuyển đổi (Layout Inspector Overlay)**: Khi bật chế độ *"Hiển thị khung bố cục"*, khung xem PDF vẽ trực tiếp các vùng nhận diện được lên trang:
     - Khối văn bản (`Text Block`): Viền xanh dương (`#2563EB`)
     - Bảng biểu (`Table / Grid`): Viền xanh lá (`#16A34A`)
     - Hình ảnh (`Image`): Viền cam (`#EA580C`)
     - Đồ hoạ Vector (`Vector Drawing`): Viền tím (`#9333EA`)
   - Nhờ đó người dùng kiểm tra ngay trên màn hình xem ứng dụng đã nhận diện đúng bảng biểu, đoạn văn hay chưa trước khi bấm chuyển sang Word.

---

## 4. Thiết kế Engine Chuyển đổi PDF sang DOCX (`core/converter.py`)

### 4.1. Bộ Chuẩn hoá Phông chữ & Tiếng Việt (`core/font_resolver.py`)
- **Gỡ tiền tố Subset**: Biểu thức chính quy `^[A-Z]{6}\+` loại bỏ tiền tố nhúng của PDF (ví dụ: `BCDEFG+TimesNewRomanPS-BoldMT` → `TimesNewRomanPS-BoldMT`).
- **Bảng ánh xạ Phông chữ Chuẩn (`FONT_ALIAS_MAP`)**:
  - `TimesNewRoman*`, `Times-Roman*`, `Tinos*`, `.VnTime*`, `VNI-Times*` → `Times New Roman`
  - `Arial*`, `Helvetica*`, `LiberationSans*`, `.VnArial*`, `VNI-Helve*` → `Arial`
  - `Courier*`, `Consolas*` → `Courier New`
  - `Calibri*` → `Calibri`; `Tahoma*` → `Tahoma`; `Cambria*` → `Cambria`; `SegoeUI*` → `Segoe UI`
- **Chuẩn hoá Tiếng Việt**:
  - Tự động chuyển chuỗi Unicode tổ hợp rời (`NFD`) sang Unicode dựng sẵn (`NFC`) bằng `unicodedata.normalize("NFC", text)` kèm sửa các ký tự dấu rời đặc thù khi trích xuất từ PDF.
  - Hỗ trợ phát hiện và chuyển mã tự động văn bản dùng phông cũ (`.Vn*` TCVN3 hoặc `VNI-*`) sang Unicode chuẩn nếu người dùng bật tuỳ chọn chuyển mã.

### 4.2. Bộ Hậu xử lý Chuẩn xác OpenXML (`core/openxml_fixer.py`)
Sau khi tệp `.docx` sơ bộ được tạo ra, `openxml_fixer.py` mở gói ZIP của `.docx`, phân tích cú pháp `word/document.xml` và `word/styles.xml` bằng `lxml.etree` để thực hiện 6 bước tinh chỉnh:
1. **Đồng bộ 4 thuộc tính phông chữ (`w:rFonts`)**:
   - Mọi thẻ `<w:rFonts>` đều được chuẩn hoá tên phông và gán đủ `w:ascii`, `w:hAnsi`, `w:cs`, `w:eastAsia`. Điều này khắc phục triệt để lỗi các ký tự tiếng Việt có dấu (`ă, â, đ, ê, ô, ơ, ư`) bị nhảy sang phông chữ khác trong Word.
2. **Chuẩn hoá Unicode NFC trên toàn bộ thẻ `<w:t>`**:
   - Quét mọi nút văn bản `<w:t>`, gộp dấu tổ hợp rời và đặt `xml:space="preserve"` khi có khoảng trắng đầu/cuối.
3. **Tắt bắt dính lưới trang (`w:snapToGrid`)**:
   - Chèn `<w:snapToGrid w:val="0"/>` vào cấu hình đoạn văn (`w:pPr`) và cấu hình lưới trang (`w:docGrid`), ngăn Microsoft Word tự động đẩy giãn khoảng cách dòng làm tràn trang.
4. **Tinh chỉnh khoảng cách dòng (`w:spacing`) & chống gãy dòng sớm**:
   - Kiểm tra các đoạn có `w:lineRule="exact"` hoặc `atLeast`: nếu chiều cao dòng quá sát gây cắt dấu mũ tiếng Việt (như chữ `Ấ`, `Ể`, `Ự`), tự động nới nhẹ hoặc chuyển sang hệ số chuẩn để không mất dấu mà vẫn giữ nguyên tổng chiều cao đoạn.
   - Giảm nhẹ `w:spacing` (khoảng cách giữa các chữ cái `-1` đến `-2` twips = `-0.05pt` đến `-0.1pt`) ở các dòng dài sát mép cột để ngăn hiện tượng từ cuối cùng của dòng bị rớt xuống dòng mới.
5. **Chuẩn hoá Bảng biểu (`w:tbl`)**:
   - Đặt `<w:tblLayout w:type="fixed"/>` để khoá cứng độ rộng các cột theo đúng toạ độ PDF.
   - Tinh chỉnh khoảng đệm ô `<w:tcMar>` (`left`/`right` giảm từ `108 dxa` xuống `36 dxa` ≈ `1.8pt`, `top`/`bottom` = `20 dxa`) để chữ trong các cột hẹp không bị ép xuống dòng.
6. **Khoá kích thước trang & lề phân đoạn (`w:sectPr`)**:
   - Đảm bảo `<w:pgSz>` và `<w:pgMar>` khớp với kích thước trang PDF gốc, đặt `header="0"` và `footer="0"` để vùng nội dung sát mép trên/dưới không bị đẩy sang trang kế tiếp.

### 4.3. Engine Giữ nguyên Vị trí Tuyệt đối 1:1 (`core/exact_layout_engine.py`)
Khi người dùng chọn chế độ **`Exact Visual Layout (1:1)`**:
- Với mỗi trang PDF:
  1. Tạo một bản sao trang PDF trong bộ nhớ, xoá các lệnh vẽ chữ (`redaction` chỉ xoá text, giữ nguyên đường kẻ bảng, khung biểu mẫu, hình ảnh, con dấu, hình nền) rồi kết xuất thành ảnh nền PNG sắc nét (150–200 DPI).
  2. Chèn ảnh nền đó vào trang Word dưới dạng hình nổi phía sau văn bản (`<wp:anchor behindDoc="1" ...>`), phủ khít trang từ toạ độ `(0, 0)`.
  3. Trích xuất toàn bộ các dòng/khối văn bản từ `page.get_text("rawdict")` cùng toạ độ `bbox = (x0, y0, x1, y1)`, phông chữ, cỡ chữ, màu sắc, kiểu đậm/nghiêng.
  4. Tạo các đoạn văn có `<w:framePr w:x="..." w:y="..." w:w="..." w:h="..." w:hAnchor="page" w:vAnchor="page" w:wrap="notBeside"/>` đặt đúng vào toạ độ `(x0, y0)` (quy đổi `1 pt = 20 twips`).
- Nhờ cơ chế này, **mọi biểu mẫu, hoá đơn, văn bằng, tài liệu phức tạp khi mở trong Word đều giống bản PDF 100% không sai lệch dù chỉ 1 milimet**, và toàn bộ chữ vẫn chỉnh sửa được ngay.
