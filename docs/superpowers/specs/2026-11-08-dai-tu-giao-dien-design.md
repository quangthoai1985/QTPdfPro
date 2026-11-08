# Đặc tả: Đại tu giao diện QT PDF Pro (v1.3.0)

- **Ngày**: 2026-11-08
- **Trạng thái**: đã duyệt từng phần qua trao đổi; chờ người dùng duyệt bản viết này rồi mới lập kế hoạch thực hiện.
- **Phạm vi**: chỉ tầng giao diện (`qtpdfpro/ui/`) cùng một mô-đun dữ liệu mới không dùng Qt (`core/whats_new.py`). Không đổi logic xử lý PDF / chuyển đổi Word trong `qtpdfpro/core/`.
- **Skill dùng khi thiết kế**: `superpowers:brainstorming` (quy trình), `ui-ux-pro-max` (nguyên tắc UI/UX). Kho dữ liệu của `ui-ux-pro-max` không có mục khớp riêng cho ứng dụng desktop PySide6 (đã tìm lại một lần), nên thiết kế dựa trên các quy tắc chung của skill: `nav-hierarchy`, `avoid-mixed-patterns`, `primary-action`, `progressive-disclosure`, `overflow-menu`, `no-emoji-icons`, `icon-style-consistent`, `escape-routes`, «User Freedom — cho bỏ qua giới thiệu».

---

## 1. Mục tiêu & tiêu chí thành công

**Người dùng nói** (2026-11-08):
1. Đại tu giao diện cho bớt rối.
2. Bỏ mục «Tất cả công cụ», chỉ giữ chức năng chính cho từng thẻ chức năng.
3. Bỏ những mục trùng lặp giữa thanh công cụ và thanh menu.
4. Thêm phần giới thiệu Changelog khi người dùng vừa cập nhật lên bản mới.

**Đã chốt qua hỏi đáp**:

| Câu hỏi | Lựa chọn |
|---|---|
| Hàng menu chữ (Tệp · Xem · Công cụ · Chỉnh sửa PDF · Trợ giúp) | Gom vào **một nút ☰** |
| 10 công cụ «Soon» chưa làm | **Ẩn hẳn** (kể cả Ctrl+K); thẻ «Ký số & Bảo mật» → «Bảo mật» |
| Biểu tượng | Đổi emoji → **Lucide** (SVG nét, giấy phép ISC) |
| Nội dung «Có gì mới» | **Ghi chú riêng cho người dùng**, đóng kèm ứng dụng |
| Bố cục tổng thể | **Phương án A — gọn 2 tầng** |

**Tiêu chí thành công** (kiểm được):
- Khi xem tài liệu, phía trên trang PDF chỉ còn **2 tầng** cố định + 1 dòng thông báo mảnh tắt được (hiện nay: 6 tầng).
- Trên một màn hình, **mỗi lệnh chỉ có một nút** (phím tắt và Ctrl+K không tính) — có bài test tự động.
- Không còn thẻ / cột «Tất cả công cụ», không còn công cụ «Soon» ở bất kỳ đâu.
- Mỗi màn hình **tối đa một nút chính** (màu nhấn).
- Không còn emoji làm biểu tượng ở thanh trên, thanh chức năng, thanh dọc, Trang chủ.
- Mọi phím tắt hiện có vẫn chạy (trừ F3 bị bỏ cùng cột công cụ).
- Lần đầu mở sau khi cập nhật lên bản mới thấy hộp thoại «Có gì mới»; cài mới hoàn toàn thì không.

**Ngoài phạm vi**: logic PDF/DOCX, nội dung các hộp thoại công cụ (In, Nén, OCR, Chuyển đổi…) — chỉ đổi biểu tượng nếu có emoji ở nút mở chúng; xem 2 trang song song; phát hành bản mới (chỉ làm khi người dùng yêu cầu).

---

## 2. Khung giao diện khi đang xem tài liệu

```
┌────────────────────────────────────────────────────────────────────────────┐
│ ⌂  Mở │ quyet_dinh.pdf × │ ke_hoach.pdf ●×   [Có bản mới]  [Tìm lệnh… Ctrl+K] ☾ ☰ │  ← Tầng 1
├────────────────────────────────────────────────────────────────────────────┤
│ Đọc Chuyển đổi Chỉnh sửa Điền & Ký Bảo mật │ (công cụ của thẻ…)  ⋯ │ Aa/✋ ◀ 1/2 ▶ 100%▾ │  ← Tầng 2
├────────────────────────────────────────────────────────────────────────────┤
│ ⓘ Văn bản hành chính — Xuất Word chuẩn NĐ30 giữ đúng thể thức.  Xuất ngay  ✕ │  ← dòng thông báo (tắt được)
├────────────────────────────────────────────────────────────┬───────┬───────┤
│                                                            │ ngăn  │ Trang │
│                  TRANG PDF                                 │ phải  │ Mục lục│
│                                                            │       │ Tìm   │
│                                                            │       │ Chú thích│
└────────────────────────────────────────────────────────────┴───────┴───────┘
```

### 2.1 Tầng 1 — thanh trên cùng (luôn hiện)
Từ trái sang: `⌂ Trang chủ` (Alt+Home) · `Mở` (Ctrl+O) · **tab tài liệu** (chuyển lên cùng hàng; bỏ hàng tab riêng `tab_strip`; tab có ● khi chưa lưu, đóng được, kéo đổi chỗ được, quá dài thì rút gọn ở giữa) · nhãn «Có bản mới» (chỉ khi có — giữ hành vi `show_update_badge`) · khoảng trống · ô `Tìm lệnh… Ctrl+K` · nút biểu tượng **☀/☾** đổi giao diện (Ctrl+Shift+T; thay nút chữ «Giao diện Sáng») · nút **☰**.
- Bỏ khỏi tầng 1: 5 nút menu chữ, nút «GitHub» (chuyển vào ☰).
- Nhiều tab không vừa: thanh tab cuộn ngang bằng nút mũi tên mặc định của `QTabBar` (không đẩy các nút bên phải ra ngoài).

### 2.2 Tầng 2 — thanh chức năng (chỉ khi có tài liệu)
- **Trái**: 5 thẻ `Đọc · Chuyển đổi · Chỉnh sửa · Điền & Ký · Bảo mật` (chữ, không biểu tượng; thẻ đang chọn có gạch chân màu nhấn). Mở tài liệu → thẻ **Đọc**. Alt+1…5 chuyển thẻ. Không còn thẻ «Tất cả công cụ».
- **Giữa**: công cụ của thẻ đang chọn (mục 3). Không đủ chỗ → công cụ cuối gom vào nút `⋯` (menu thả xuống, giữ thứ tự).
- **Phải**: cụm điều khiển xem dùng chung mọi thẻ — nút bật/tắt `Chọn chữ ↔ Bàn tay` (V / H, giữ `settings.pointer_mode`) · `◀ [số trang] / N ▶` · ô thu phóng `100% ▾` (Vừa ngang, Vừa trang, 50…300%; Ctrl+± / Ctrl+1 / Ctrl+0).
- Thứ tự ưu tiên khi hẹp: thẻ và cụm điều khiển xem luôn hiện đủ; vùng công cụ co lại và dồn vào `⋯`.

### 2.3 Dòng thông báo thông minh
- Thay thanh `signature_banner` hiện nay bằng **một dòng mảnh** (cao ~32 px): biểu tượng `info` + câu ngắn + **một liên kết chữ** (vd «Xuất Word chuẩn NĐ30», «Lưu thành PDF tìm kiếm được») + nút ✕.
- Không còn nút xanh to trong thông báo. Bấm ✕ → không hiện lại cho tệp đó (ghi nhớ theo đường dẫn tệp trong phiên chạy; không cần lưu vĩnh viễn).
- Nội dung & điều kiện hiện giữ nguyên logic hiện có (`_analyze_document`: văn bản hành chính, chữ ký số/con dấu, bảng, tài liệu ảnh quét).

### 2.4 Cột phải
- Giữ **thanh biểu tượng dọc** `Trang · Mục lục · Tìm · Chú thích` là chỗ chuyển ngăn **duy nhất**; bấm lại biểu tượng đang chọn → ẩn ngăn (F4 cũng ẩn/hiện).
- Bỏ hàng tab chữ phía trên ngăn (`sidebar_tabs` dùng `tabBar().hide()`, vẫn là `QTabWidget`/`QStackedWidget` bên trong).
- Bỏ khỏi thanh dọc: Chọn / Tay, ▲ ▼ đổi trang, + − ↔ ↻ thu phóng / xoay (đã có ở tầng 2 hoặc thẻ Đọc).
- Ngăn «Soi bố cục» không còn biểu tượng ở thanh dọc: mở bằng công cụ «Soi bố cục» (thẻ Chuyển đổi) hoặc F8 — bật lớp phủ và hiện ngăn cùng lúc như hiện nay.

### 2.5 Bỏ hẳn
Cột «Tất cả công cụ» bên trái (`tools_panel`, `ToolCatalogPanel` trong khung tài liệu), F3, «◧ Bảng công cụ», thanh công cụ nhanh riêng hàng (`tool_strip`, `STRIP_TOOLS`), thẻ «all», hàng menu chữ (`menu_buttons`), nút «ℹ» và «Xuất Word» ở thanh chế độ cũ (chuyển vào thẻ), nút «📐 Soi bố cục» ở thanh chế độ cũ.

### 2.6 Nút chính
Mỗi màn hình tối đa một nút màu nhấn: thẻ Chuyển đổi → `Xuất Word`; thẻ Chỉnh sửa / Điền & Ký → `Lưu` **chỉ khi có thay đổi chưa lưu**; Trang chủ → «Chuyển sang Word chuẩn NĐ30»; hộp thoại «Có gì mới» → «Bắt đầu dùng».

---

## 3. Công cụ của từng thẻ

Nguyên tắc: một lệnh chỉ có một nút trên màn hình. Lệnh đã có ở thanh dọc phải hoặc cụm điều khiển xem không lặp lại trong thẻ.

| Thẻ | Công cụ (trái → phải) | Kiểu nút |
|---|---|---|
| **Đọc** | Xoay trái · Xoay phải · Đọc tập trung (F11) · In (Ctrl+P) · Thuộc tính (Ctrl+I) | biểu tượng + chữ |
| **Chuyển đổi** | **[Xuất Word ▾]** · OCR tiếng Việt · Kiểm tra thể thức NĐ30 · Kiểm chứng DOCX · Soi bố cục (F8, nút bật/tắt) · Hàng loạt | biểu tượng + chữ |
| **Chỉnh sửa** | Chọn/di chuyển · Đánh dấu chữ ▾ · Vẽ ▾ · Hộp chữ · Ghi chú · Dấu đóng · Tẩy · ↶ ↷ │ Trang ▾ · Xử lý ▾ │ **[Lưu ▾]** | công cụ vẽ: chỉ biểu tượng + chú giải; Trang/Xử lý/Lưu: biểu tượng + chữ |
| **Điền & Ký** | Gõ chữ · Dấu ✓ ▾ · Ngày ▾ · Chữ ký · Chữ ký nháy · Thư viện chữ ký · Tẩy · ↶ ↷ │ **[Lưu ▾]** | như trên |
| **Bảo mật** | Soi chữ ký số & con dấu · Đặt mật khẩu · Gỡ mật khẩu | biểu tượng + chữ |

**Nút có ▾**
- `Xuất Word ▾`: bấm thân nút = chuyển đổi chế độ `auto` (văn bản hành chính → NĐ30, như nút «Xuất Word» hiện nay, Ctrl+Shift+W); mũi tên: Chuẩn NĐ30 · Giữ vị trí 1:1 · Dòng chảy · Tuỳ chỉnh xuất…
- `Đánh dấu chữ ▾`: tô sáng / gạch chân / gạch ngang / gạch sóng. `Vẽ ▾`: bút / bút dạ quang / khung / elip / đường / mũi tên. Cả hai **nhớ kiểu vừa dùng**: thân nút mang biểu tượng của kiểu đó và bấm thẳng là dùng lại.
- `Trang ▾`: Sắp xếp & cắt ghép (Ctrl+Shift+O) · Ghép tệp (Ctrl+Shift+M) · Tách tệp · Trích trang.
- `Xử lý ▾`: Nén · Đóng dấu nước · Đánh số trang.
- `Dấu ✓ ▾`: ✓ ✕ ● ─ (nhớ dấu vừa dùng). `Ngày ▾`: chọn mẫu ngày (`fill_sign.DATE_FORMATS`, có mẫu NĐ30) rồi đặt ngày.
- `Lưu ▾`: thân nút = Lưu (Ctrl+S); mũi tên: Lưu thành tệp mới… (Ctrl+Shift+S) · Xuất bản làm phẳng chú thích…

**Hành vi**
- Chọn thẻ **Chỉnh sửa** → vào chế độ chỉnh sửa (bộ công cụ `edit`); **Điền & Ký** → bộ `fill`; chọn thẻ khác → thoát chế độ chỉnh sửa và về chế độ con trỏ đã chọn (Chọn chữ / Bàn tay). Ctrl+E → thẻ Chỉnh sửa (đang ở đó thì về Đọc); Ctrl+Shift+F → thẻ Điền & Ký.
- Phím tắt chữ cái của công cụ vẽ (hiện có trong `EditToolbar`) chỉ bật khi ở thẻ Chỉnh sửa / Điền & Ký như hiện nay.
- **Hàng kiểu dáng** (màu, độ đậm, bắt dòng chấm, mẫu chữ ký…) hiện thành hàng mảnh ngay dưới tầng 2 **chỉ khi** công cụ đang chọn có tuỳ chọn kiểu dáng; công cụ Chọn/di chuyển, Tẩy thì ẩn.
- `Lưu ▾` luôn hiện ở thẻ Chỉnh sửa / Điền & Ký; ở thẻ Đọc / Chuyển đổi / Bảo mật chỉ hiện (cuối vùng công cụ) khi tài liệu có thay đổi chưa lưu (vd tô sáng từ chuột phải của công cụ Chọn chữ).
- Công cụ cần tài liệu đang có thay đổi (Nén, Dấu nước…) giữ hành vi hỏi lưu trước như `action_pdf_tool` hiện nay.

**Bỏ khỏi thanh công cụ** (vẫn có qua Ctrl+K / phím tắt): Trích xuất văn bản (Ctrl+T), Tìm kiếm (Ctrl+F → mở ngăn Tìm), Mục lục, Vừa ngang / Vừa trang.

---

## 4. Trang chủ (khi chưa mở tài liệu)

- Chỉ có tầng 1. Bỏ cột «Tất cả công cụ» bên trái. Nội dung căn giữa, rộng tối đa ~1100 px.
- Thứ tự:
  1. **Lời chào + chip phiên bản** (`v1.3.0`; bấm → mở «Có gì mới»).
  2. **Bắt đầu**: thẻ «Mở tệp PDF» (kéo thả / bấm, Ctrl+O) + thẻ «Văn bản hành chính NĐ30» với «Chuyển sang Word chuẩn NĐ30» (nút chính) và «Kiểm tra thể thức». Hẹp thì xếp chồng (giữ `_relayout_start`).
  3. **Gần đây**: tối đa 6 tệp — biểu tượng, tên tệp, thư mục, thời điểm mở; chưa có tệp → một dòng hướng dẫn.
  4. **Công cụ nhanh**: 8 ô nhỏ, 4 cột (hẹp thì 2): OCR tiếng Việt · Chuyển đổi hàng loạt · Ghép tệp PDF · Sắp xếp & cắt ghép trang · Nén PDF · Điền & Ký · Đặt mật khẩu · In. Bấm → công cụ cần tệp thì hỏi chọn tệp (giữ hành vi `run_tool` hiện nay). Thay cho «Công cụ đề xuất».
  5. **Chân trang**: một dòng mờ về quyền riêng tư; bỏ liên kết GitHub / Bản phát hành (đã ở ☰).

---

## 5. Nút ☰ và phím tắt

### 5.1 Nội dung ☰
```
Mở tệp…                      Ctrl+O
Tệp mở gần đây             ▸
Đóng tài liệu                Ctrl+F4        (tắt khi không có tài liệu)
──────────────
Lưu                          Ctrl+S         (tắt khi không có tài liệu)
Lưu thành tệp mới…           Ctrl+Shift+S   (tắt khi không có tài liệu)
──────────────
Ẩn/hiện ngăn bên phải        F4
Cài đặt                    ▸  ☐ Tự kiểm tra cập nhật mỗi khi mở
                              ☐ Tự tải bản mới & cài khi thoát
                              Đặt làm trình xem PDF mặc định…
──────────────
Kiểm tra cập nhật…
Có gì mới trong bản này
Mã nguồn & báo lỗi (GitHub)
Giới thiệu QT PDF Pro
──────────────
Thoát
```
☰ chứa lệnh hệ thống / ít dùng — không lặp công cụ của các thẻ. «Lưu» ở ☰ là ngoại lệ có chủ đích (luôn tìm được dù đang ở thẻ không hiện nút Lưu); bài test chống trùng chỉ xét các nút **đang hiện**, nên menu ☰ đóng không tính.

### 5.2 Phím tắt
- Giữ nguyên: Ctrl+O, Ctrl+S, Ctrl+Shift+S, Ctrl+P, Ctrl+I, Ctrl+F4, Ctrl+F, Ctrl+T, Ctrl+K, Ctrl+Z, Ctrl+Y, Ctrl++, Ctrl+-, Ctrl+1, Ctrl+0, V, H, F4, F8, F11, Ctrl+Shift+W, Ctrl+Shift+B, Ctrl+Shift+R, Ctrl+Shift+N, Ctrl+Shift+O, Ctrl+Shift+M, Ctrl+Shift+T, Alt+Home, Ctrl+E, Ctrl+Shift+F.
- Thêm: **Alt+1…5** chuyển 5 thẻ (Ctrl+1/0 đã dùng cho thu phóng).
- Bỏ: F3.
- Mọi phím tắt đăng ký trên cửa sổ chính (`QAction` thêm bằng `addAction` / `QShortcut`), **không** phụ thuộc menu nào đang hiện.

### 5.3 Ctrl+K
- Liệt kê **mọi lệnh dùng được**: công cụ của 5 thẻ + lệnh hệ thống (Đóng tài liệu, Phóng to, Thu nhỏ, Đổi giao diện, Có gì mới, Kiểm tra cập nhật…). Lệnh cần tài liệu vẫn chọn được khi chưa mở tài liệu, kèm ghi chú mờ «cần mở tệp»; chọn → hỏi mở tệp rồi chạy (như `run_tool`).
- Mỗi dòng: biểu tượng · tên · nhóm (tên thẻ) · **phím tắt** căn phải. Tìm không dấu (giữ `tools_for` → chuyển sang `commands.search`).
- Ô `Tìm lệnh…` ở tầng 1 dùng cùng nguồn (bỏ `QCompleter` riêng theo `TOOLS`).

---

## 6. Hộp thoại «Có gì mới»

### 6.1 Dữ liệu
`qtpdfpro/ui/assets/whats_new.json` (UTF-8, đóng gói cùng ứng dụng như phông / biểu tượng):
```json
{
  "versions": [
    {
      "version": "1.3.0",
      "date": "2026-11-20",
      "headline": "Giao diện gọn hơn",
      "items": [
        {"icon": "layout-panel-top", "title": "Giao diện gọn hơn",
         "text": "Mỗi thẻ chỉ còn công cụ chính, trang PDF rộng hơn; mọi lệnh tìm bằng Ctrl+K.", "shortcut": "Ctrl+K"},
        {"icon": "text-cursor", "title": "Chọn chữ liền nhiều trang",
         "text": "Kéo từ trang này sang trang khác để chép cả đoạn.", "shortcut": "V"}
      ]
    }
  ]
}
```
- (Ví dụ minh hoạ — ngày thật ghi khi phát hành.) `version` theo SemVer, mới nhất trước; 3–6 `items`/phiên bản; `icon` là tên biểu tượng Lucide có trong `ui/assets/icons/`; `shortcut` tuỳ chọn.
- Bản 1.3.0 gom luôn các điểm của v1.2.2 chưa phát hành (Chọn chữ / Bàn tay, chọn chữ trên bản scan, chọn liền nhiều trang, mở tệp nhanh) + giao diện mới.

### 6.2 Lõi `core/whats_new.py` (không Qt)
- `load_notes(path=None) -> list[VersionNotes]` (đọc, kiểm cấu trúc; tệp hỏng → danh sách rỗng, không làm hỏng khởi động).
- `notes_to_show(current, last_seen, settings_existed) -> list[VersionNotes]`:
  - `last_seen` rỗng và `settings_existed=False` (cài mới) → `[]`.
  - `last_seen` rỗng và `settings_existed=True` (cập nhật từ bản chưa có trường này) → chỉ mục của `current`.
  - `last_seen < current` → các mục có `last_seen < version ≤ current`, mới nhất trước.
  - `last_seen ≥ current` → `[]`.
- So sánh phiên bản dùng lại bộ SemVer của `core/update_check` (không viết lại).

### 6.3 Khi nào hiện
- `settings.last_seen_version: str = ""` (trường mới trong `AppSettings`). `AppSettings.load()` cho biết tệp `settings.json` đã tồn tại trước đó hay chưa (cờ `existed`).
- `ui/app.py` gọi `win.whats_new.on_startup()` sau khi cửa sổ hiện, **trước** `win.default_app.on_startup()`; nếu đã hiện «Có gì mới» trong lần mở này thì hộp thoại trình xem mặc định để lần mở sau (không chồng hai hộp thoại). Như bộ cập nhật, **không** gọi trong `MainWindow.__init__` (test không bật hộp thoại).
- Sau khi hiện (hoặc khi quyết định không hiện vì cài mới) → ghi `last_seen_version = __version__`.

### 6.4 Giao diện `ui/whats_new_dialog.py`
- Tiêu đề: «Có gì mới trong QT PDF Pro {version}» + ngày.
- Danh sách thẻ: biểu tượng Lucide · tiêu đề (SemiBold) · một câu · chip phím tắt (nếu có).
- Nhảy nhiều bản: bản mới nhất mở sẵn, bản cũ hơn trong các mục thu gọn «Bản 1.2.x».
- Nút: «Xem đầy đủ trên GitHub» (mở trang Release của phiên bản) · **«Bắt đầu dùng»** (mặc định; Enter / Esc / ✕ đều đóng).
- Mở lại được từ ☰ › «Có gì mới trong bản này» và chip phiên bản ở Trang chủ (luôn hiện mục của phiên bản đang chạy).

---

## 7. Biểu tượng (Lucide)

- Chép SVG gốc của Lucide (giấy phép ISC — ghi `qtpdfpro/ui/assets/icons/LICENSE-lucide.txt`) vào `qtpdfpro/ui/assets/icons/<tên>.svg`; chỉ chép các biểu tượng dùng tới (~45). Nguồn: gói `lucide-static` (npm, phiên bản ghim, ghi trong LICENSE) — tải một lần lúc phát triển, **không** tải lúc chạy.
- `ui/icons.py`: `icon(name, color=None, size=18) -> QIcon` — đọc SVG, thay `currentColor` bằng màu chữ của giao diện hiện tại (theo token trong `theme.py`), dựng bằng `QSvgRenderer`, lưu đệm theo (tên, màu, cỡ); `refresh_icons()` gọi khi đổi Sáng/Tối để các nút đã gắn biểu tượng cập nhật (nút đăng ký bằng `icons.bind(button, name)`).
- Thiếu tệp SVG → trả `QIcon()` rỗng + ghi cảnh báo (không làm hỏng giao diện); bài test bắt mọi tên đang dùng phải có tệp.
- Bản đóng gói: thêm thư mục `icons` vào `build.bat` / `QTPdfPro.spec` (`--add-data`) như phông Inter.
- Dự kiến (tên Lucide): `house`, `folder-open`, `menu`, `sun`, `moon`, `search`, `text-cursor`, `hand`, `chevron-left`, `chevron-right`, `rotate-ccw`, `rotate-cw`, `book-open`, `printer`, `info`, `file-text`, `scan-text`, `badge-check`, `microscope`, `scan-eye`, `files`, `mouse-pointer-2`, `highlighter`, `pen-line`, `type`, `message-square`, `stamp`, `eraser`, `undo-2`, `redo-2`, `layers`, `combine`, `scissors`, `file-output`, `file-archive`, `droplet`, `list-ordered`, `save`, `pen-tool`, `signature`, `check-square`, `calendar`, `shield-check`, `lock`, `lock-open`, `layout-panel-top`, `list`, `panel-right`, `x`, `ellipsis`. Tên chính xác chốt khi thực hiện theo danh mục Lucide; không dùng biểu tượng thương hiệu (GitHub dùng `code-xml`).

---

## 8. Tổ chức mã

### 8.1 Nguồn lệnh duy nhất — `ui/commands.py` (mới)
```python
@dataclass(frozen=True)
class Command:
    key: str               # "convert_word", "ocr", "rotate_left", "save", …
    label: str             # tên hiện trên nút / Ctrl+K
    icon: str              # tên biểu tượng Lucide
    tab: str               # "read" | "convert" | "edit" | "fill" | "security" | "system"
    shortcut: str = ""     # "Ctrl+Shift+W"
    group: str = ""        # nhóm ▾ trong thẻ ("mark", "draw", "pages", "process", "save", "word")
    needs_document: bool = False
    summary: str = ""      # một dòng mô tả (Trang chủ, chú giải)
    keywords: str = ""     # tìm không dấu
    checkable: bool = False
```
- `COMMANDS: list[Command]`, `TAB_LAYOUT: dict[str, list[str | tuple]]` (thứ tự nút / nhóm của từng thẻ), `HOME_QUICK_TOOLS: list[str]`, `search(query) -> list[Command]`.
- Hàm xử lý nằm ở `MainWindow` (`run_command(key)` — thay `run_tool`; giữ tên `run_tool` làm bí danh cho code/test cũ trong giai đoạn chuyển). `QAction` của từng lệnh tạo **một lần** từ `COMMANDS` (`self.command_actions[key]`), dùng chung cho nút thanh chức năng, ☰, phím tắt.
- `ui/tool_catalog.py` bị thay thế: phần dữ liệu chuyển vào `commands.py`, bỏ mọi mục `ready=False`. Lộ trình các công cụ chưa làm chỉ còn ở `docs/DE_XUAT_TINH_NANG.md`.

### 8.2 Tệp mới / sửa / bỏ
| Tệp | Thay đổi |
|---|---|
| `ui/commands.py` | mới — mục 8.1 |
| `ui/icons.py`, `ui/assets/icons/*.svg`, `LICENSE-lucide.txt` | mới — mục 7 |
| `ui/top_bar.py` | mới — tầng 1 (`TopBar`: nút Trang chủ, Mở, `QTabBar` tài liệu, nhãn bản mới, ô tìm lệnh, nút giao diện, nút ☰ + menu) — tách từ `main_window._build_top_bar` / `_build_tab_strip` |
| `ui/function_bar.py` | mới — tầng 2 (`FunctionBar`: thẻ, vùng công cụ dựng từ `TAB_LAYOUT` có `⋯` tràn, cụm điều khiển xem; tín hiệu `tabChanged(str)`) — thay `_build_mode_bar`, `tool_strip`, `_refresh_tool_strip` |
| `ui/annotation_tools.py` | `EditToolbar` gọn: nút nhóm ▾ nhớ kiểu (`ToolGroupButton`), hàng kiểu dáng tách thành widget riêng hiện theo công cụ; công cụ vẽ dùng biểu tượng Lucide; nhúng vào vùng công cụ của tầng 2 thay vì thanh riêng trong `PDFDocumentTab` |
| `ui/main_window.py` | dùng `TopBar`, `FunctionBar`, `commands`; bỏ `tools_panel`, `tool_strip`, `STRIP_TOOLS`, `menu_buttons`, `mode_buttons["all"]`, `set_tools_panel_visible`, `doc_controls`/`btn_convert_docx`/`btn_mode_inspect` cũ, nút đổi trang/thu phóng ở `right_rail`; `set_mode_category` → `set_function_tab`; dòng thông báo mảnh thay `signature_banner` |
| `ui/home_page.py` | Trang chủ mục 4; bỏ `ToolCatalogPanel`, `CatalogRow`, `_ElidedLabel` nếu không còn dùng |
| `ui/command_palette.py` | đọc `commands.search`, thêm cột phím tắt, lệnh hệ thống |
| `ui/theme.py` | QSS cho tầng 1/2, dòng thông báo, nút nhóm ▾, ô công cụ nhanh, hộp thoại «Có gì mới»; bỏ QSS không còn dùng; token màu biểu tượng |
| `core/whats_new.py`, `ui/whats_new_dialog.py`, `ui/assets/whats_new.json` | mới — mục 6 |
| `core/settings.py` | thêm `last_seen_version`; `load()` báo `existed`; `show_tools_panel` giữ để đọc tệp cũ, không dùng |
| `ui/app.py` | gọi `whats_new.on_startup()` trước `default_app.on_startup()` |
| `build.bat` (+ `QTPdfPro.spec` khi nội dung đổi) | `--add-data` thư mục `icons`, `whats_new.json` |
| `ui/tool_catalog.py` | xoá (sau khi mọi chỗ dùng đã chuyển sang `commands.py`) |

### 8.3 Ràng buộc giữ nguyên
- `core/` không import PySide6 (`whats_new.py` thuần Python).
- Chuỗi giao diện tiếng Việt có dấu; `&` trên nút/QAction nhân đôi `&&`.
- Phông Inter, độ đậm tối đa 600 (`theme.py`).
- Không thêm nút cố định nào làm tăng bề rộng tối thiểu cửa sổ; tầng 2 phải dùng được ở 1366 px (mục tiêu: bề rộng tối thiểu cửa sổ khi có tài liệu ≤ 1280 px — hiện ~1376 px).

---

## 9. Kiểm thử

**Tự động (`pytest`)**
1. `commands`: khoá duy nhất; phím tắt không trùng (kể cả với phím tắt của `EditToolbar` khi ở thẻ chỉnh sửa); mọi `icon` có tệp SVG; mọi khoá trong `TAB_LAYOUT` / `HOME_QUICK_TOOLS` tồn tại; không còn lệnh «Soon».
2. **Chống trùng**: mở tài liệu, lần lượt chọn từng thẻ (và trạng thái có / không có thay đổi chưa lưu); gom khoá lệnh của mọi nút **đang hiện** ở tầng 1, tầng 2 (kể cả mục trong `⋯` nếu đang mở), thanh dọc phải → mỗi khoá xuất hiện đúng một lần.
3. Thẻ: Chỉnh sửa / Điền & Ký vào đúng chế độ, thẻ khác thoát; Ctrl+E / Ctrl+Shift+F / Alt+1…5; mở tài liệu → thẻ Đọc.
4. Phím tắt: mọi phím trong mục 5.2 có `QAction`/`QShortcut` đăng ký trên cửa sổ và gọi đúng lệnh (giả lập phím, `monkeypatch` hộp thoại modal).
5. Ctrl+K: chỉ lệnh dùng được, có lệnh hệ thống, hiện phím tắt, tìm không dấu.
6. Tầng 2 ở bề rộng 1280 px: không tràn, công cụ dư nằm trong `⋯`.
7. `whats_new`: 4 tình huống của `notes_to_show`; tệp JSON hỏng → `[]`; `test_version.py` báo lỗi nếu `whats_new.json` thiếu mục `__version__`; `on_startup` ghi `last_seen_version`, không chồng với hộp thoại trình xem mặc định.
8. `icons`: dựng được mọi biểu tượng ở cả Sáng/Tối; đổi giao diện → màu biểu tượng đổi.
9. Cập nhật / bỏ các bài test cũ dựa trên `STRIP_TOOLS`, `tools_panel`, «Coming Soon», `mode_buttons["all"]`, `menu_buttons` (`tests/test_ui.py`, `tests/test_ocr_ui.py`, `tests/test_text_select.py`, …).

**Thủ công (bắt buộc trước khi báo xong)**
- Chạy cửa sổ thật với `QT_PDF_PRO_DATA` tạm; chụp `win.grab()` ở 1366 × 768 và 1920 × 1080, Sáng và Tối: Trang chủ, mỗi thẻ khi có tài liệu, thẻ Chỉnh sửa có hàng kiểu dáng, hộp thoại «Có gì mới»; kiểm tiếng Việt đủ dấu, không chữ bị cắt.
- `python -m pytest -q tests` qua 100%, mã thoát 0.

---

## 10. Thực hiện theo bước (chi tiết ở kế hoạch)

Mỗi bước để ứng dụng chạy được, test xanh rồi commit:
1. Biểu tượng Lucide + `ui/icons.py`.
2. `ui/commands.py` (thay `tool_catalog`, bỏ «Soon») + Ctrl+K mới.
3. Tầng 1 (`TopBar`, ☰, tab tài liệu lên cùng hàng).
4. Tầng 2 (`FunctionBar`), bỏ thanh chế độ cũ / thanh nhanh / cột công cụ trái; dọn thanh dọc phải; dòng thông báo mảnh.
5. Thanh chỉnh sửa / điền & ký gọn (nhóm ▾, hàng kiểu dáng theo công cụ).
6. Trang chủ mới.
7. «Có gì mới» (lõi + hộp thoại + JSON + khởi động).
8. Dọn QSS, đóng gói (`build.bat`), test chống trùng, ảnh chụp thủ công, CHANGELOG / CLAUDE.md, tăng `__version__` → 1.3.0 (phát hành chỉ khi người dùng yêu cầu).
