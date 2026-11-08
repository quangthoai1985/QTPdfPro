# Đại tu giao diện QT PDF Pro (v1.3.0) — Kế hoạch thực hiện

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thay khung giao diện 6 tầng bằng khung 2 tầng (thanh trên + thanh chức năng 5 thẻ), một nguồn lệnh duy nhất, biểu tượng Lucide, Trang chủ gọn và hộp thoại «Có gì mới» sau khi cập nhật.

**Architecture:** Mọi lệnh khai báo một lần trong `ui/commands.py`; `MainWindow` tạo một `QAction` cho mỗi lệnh (`command_actions[key]`) và mọi nơi hiển thị (tầng 1 `TopBar`, tầng 2 `FunctionBar`, menu ☰, Ctrl+K, ô Trang chủ) chỉ tham chiếu khoá lệnh. Nút công cụ chú thích chuyển từ `EditToolbar` (nay chỉ còn hàng kiểu dáng) lên `FunctionBar`, điều khiển bộ điều khiển chú thích của tab đang mở. Lõi `core/` không đổi, trừ mô-đun dữ liệu mới `core/whats_new.py`.

**Tech Stack:** Python 3.14, PySide6 (Qt 6, `QtSvg`), pytest; biểu tượng Lucide (`lucide-static`, ISC).

**Spec:** `docs/superpowers/specs/2026-11-08-dai-tu-giao-dien-design.md` — đọc cùng kế hoạch này.

## Global Constraints

- Không import PySide6 trong `qtpdfpro/core/` (`core/whats_new.py` thuần Python).
- Chuỗi giao diện tiếng Việt có dấu chuẩn; chuỗi có `&` trên nút / `QAction` / tab phải viết `&&`.
- Phông Inter, QSS `font-weight` tối đa 600 (`ui/theme.py`); màu lấy từ token `_LIGHT_TOKENS` / `_DARK_TOKENS`, không mã màu rời trong widget.
- Không emoji làm biểu tượng ở tầng 1, tầng 2, thanh dọc, Trang chủ, ☰.
- Phím tắt giữ nguyên danh sách ở spec §5.2; thêm Alt+1…5; bỏ F3.
- Mỗi màn hình tối đa một nút màu nhấn (`objectName` = `primaryConvertBtn`).
- Bề rộng tối thiểu cửa sổ khi có tài liệu ≤ 1280 px.
- Test GUI không được mở hộp thoại modal thật (`monkeypatch` `exec`, `QFileDialog`, `QMessageBox`); dữ liệu người dùng qua `QT_PDF_PRO_DATA` (conftest đã đặt).
- Ghi tệp văn bản bằng LF (`write_text(..., newline="\n")` hoặc công cụ Edit/Write); `.bat` giữ ASCII + CRLF.
- Mỗi task kết thúc bằng `python -m pytest -q tests` qua 100%, **mã thoát 0**, rồi commit (tiếng Việt, dòng cuối `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`).
- Không tăng `__version__` trong kế hoạch này: CLAUDE.md §6.3 chỉ tăng khi phát hành (người dùng chưa yêu cầu). Ghi chú «Có gì mới» soạn sẵn cho 1.3.0.

## Review Focus

1. **Đổi tab tài liệu khi đang ở thẻ Chỉnh sửa / Điền & Ký**: tab mới được đưa vào đúng chế độ của thẻ; nút công cụ đang bật trên tầng 2 theo bộ điều khiển của tab mới, không điều khiển nhầm tab cũ → test ở Task 5.
2. **Có thay đổi chưa lưu rồi chuyển sang thẻ Đọc**: nút Lưu vẫn hiện ở thẻ Đọc; lưu xong thì nút biến mất → test ở Task 5.
3. **Thu nhỏ rồi phóng to cửa sổ nhiều lần**: công cụ dồn vào `⋯` vẫn chạy khi chọn từ menu, phóng to lại thì về đúng chỗ cũ, không mất / nhân đôi nút → test ở Task 4.
4. **Đóng tài liệu cuối cùng khi đang ở thẻ Chỉnh sửa**: về Trang chủ, tầng 2 ẩn, không còn chế độ chỉnh sửa treo; mở tệp mới → thẻ Đọc; Alt+1…5 khi không có tài liệu không làm gì → test ở Task 4.
5. **Chọn lệnh cần tài liệu từ Ctrl+K khi đang ở Trang chủ rồi huỷ hộp thoại mở tệp**: không lỗi, không đổi trạng thái → test ở Task 2.

---

## File Structure

| Tệp | Trách nhiệm | Task |
|---|---|---|
| `tools/fetch_lucide_icons.py` | Tải SVG Lucide (phiên bản ghim) cho danh sách tên → `qtpdfpro/ui/assets/icons/` | 1 |
| `qtpdfpro/ui/assets/icons/*.svg`, `LICENSE-lucide.txt` | Biểu tượng + giấy phép ISC | 1 |
| `qtpdfpro/ui/icons.py` | Dựng `QIcon` từ SVG tô màu theo giao diện, lưu đệm, gắn & tô lại khi đổi giao diện | 1 |
| `qtpdfpro/ui/commands.py` | Danh sách lệnh, bố cục thẻ, nhóm ▾, ô Trang chủ, tìm không dấu | 2 |
| `qtpdfpro/ui/command_palette.py` | Ctrl+K đọc `commands.search`, cột phím tắt | 2 |
| `qtpdfpro/ui/top_bar.py` | Tầng 1 + menu ☰ | 3 |
| `qtpdfpro/ui/function_bar.py` | Tầng 2: thẻ, vùng công cụ có `⋯`, cụm điều khiển xem | 4, 5 |
| `qtpdfpro/ui/main_window.py` | Ghép các thanh, `run_command`, dòng thông báo, cột phải gọn | 2–5 |
| `qtpdfpro/ui/annotation_tools.py` | `EditToolbar` chỉ còn hàng kiểu dáng + phím tắt chữ cái | 5 |
| `qtpdfpro/ui/home_page.py` | Trang chủ mới | 6 |
| `qtpdfpro/core/whats_new.py`, `qtpdfpro/ui/whats_new_dialog.py`, `qtpdfpro/ui/assets/whats_new.json` | «Có gì mới» | 7 |
| `qtpdfpro/core/settings.py`, `qtpdfpro/ui/app.py` | `last_seen_version`, cờ `existed`, thứ tự hộp thoại khởi động | 7 |
| `qtpdfpro/ui/theme.py` | QSS các thành phần mới, bỏ QSS cũ | 3–6, 8 |
| `qtpdfpro/ui/tool_catalog.py` | Xoá | 8 |
| `build.bat`, `QTPdfPro.spec` | `--add-data` biểu tượng + `whats_new.json` | 1, 7 |

---

### Task 1: Biểu tượng Lucide và `ui/icons.py`

**Files:**
- Create: `tools/fetch_lucide_icons.py`, `qtpdfpro/ui/icons.py`, `qtpdfpro/ui/assets/icons/*.svg`, `qtpdfpro/ui/assets/icons/LICENSE-lucide.txt`
- Modify: `build.bat` (thêm `--add-data "qtpdfpro\ui\assets\icons;qtpdfpro\ui\assets\icons"` cạnh dòng phông Inter)
- Test: `tests/test_icons.py`

**Interfaces:**
- Produces:
  - `ICON_DIR: Path` (= `qtpdfpro/ui/assets/icons`), `ICON_NAMES: tuple[str, ...]` (mọi tên dự án dùng — danh sách spec §7, chốt theo tệp thật).
  - `icon_path(name: str) -> Path`
  - `icon(name: str, color: str | None = None, size: int = 18) -> QIcon` — `color=None` dùng màu hiện tại (`current_color()`); thiếu tệp → `QIcon()` + `logging.warning`.
  - `set_icon_color(color: str) -> None` — đổi màu hiện tại, xoá đệm, tô lại mọi nút đã `bind`.
  - `current_color() -> str`
  - `bind(button: QAbstractButton, name: str, size: int = 18) -> None` — đặt biểu tượng và ghi nhớ (weakref) để `set_icon_color` tô lại.

- [ ] **Step 1: Viết `tools/fetch_lucide_icons.py`**: `LUCIDE_VERSION = "0.460.0"`, `URL = "https://cdn.jsdelivr.net/npm/lucide-static@{v}/icons/{name}.svg"`, nhập `ICON_NAMES` từ `qtpdfpro.ui.icons`, tải từng tệp (chỉ https, kiểm nội dung bắt đầu bằng `<svg`), ghi LF; tải `LICENSE` của gói thành `LICENSE-lucide.txt` kèm dòng «lucide-static <phiên bản>». Tên không tồn tại → in tên và thoát mã 1 (sửa `ICON_NAMES` theo danh mục Lucide rồi chạy lại; vd `check-square` → `square-check`).
- [ ] **Step 2: Viết test**

```python
def test_every_icon_name_has_svg():
    for name in icons.ICON_NAMES:
        assert icons.icon_path(name).is_file(), name
    assert (icons.ICON_DIR / "LICENSE-lucide.txt").is_file()

def test_icon_renders_in_theme_color_and_rebinds(qapp):
    icons.set_icon_color("#E6E8EC")
    btn = QPushButton(); icons.bind(btn, "search")
    img = btn.icon().pixmap(18, 18).toImage()
    assert _has_pixel_near(img, QColor("#E6E8EC"))
    icons.set_icon_color("#0F172A")
    assert _has_pixel_near(btn.icon().pixmap(18, 18).toImage(), QColor("#0F172A"))

def test_missing_icon_returns_null_icon(caplog):
    assert icons.icon("khong-co-bieu-tuong-nay").isNull()
```
(`_has_pixel_near`: có điểm ảnh alpha > 128 với sai lệch RGB ≤ 40 — viết trong tệp test.)

- [ ] **Step 3: Chạy** `python -m pytest -q tests/test_icons.py` → FAIL (chưa có `qtpdfpro.ui.icons`).
- [ ] **Step 4: Viết `qtpdfpro/ui/icons.py`** (đọc SVG, thay `currentColor` bằng màu, `QSvgRenderer` vẽ lên `QPixmap` trong suốt ở cỡ × `devicePixelRatio` màn hình chính, đệm theo `(tên, màu, cỡ)`), rồi chạy `python tools/fetch_lucide_icons.py`.
- [ ] **Step 5: Chạy** `python -m pytest -q tests/test_icons.py` → PASS; `python -m pytest -q tests` → qua, mã thoát 0.
- [ ] **Step 6: Commit** `git add tools/fetch_lucide_icons.py qtpdfpro/ui/icons.py qtpdfpro/ui/assets/icons build.bat tests/test_icons.py` — «Thêm bộ biểu tượng Lucide và ui/icons.py tô màu theo giao diện».

---

### Task 2: Nguồn lệnh `ui/commands.py`, `QAction` dùng chung, Ctrl+K mới

**Files:**
- Create: `qtpdfpro/ui/commands.py`, `tests/test_commands.py`
- Modify: `qtpdfpro/ui/main_window.py` (`_build_actions_and_menus` → `_build_command_actions`; `run_command`; `run_tool` thành bí danh), `qtpdfpro/ui/command_palette.py`, `qtpdfpro/ui/theme.py` (gọi `icons.set_icon_color(tokens["text"])` trong `_apply_theme` của `MainWindow`)
- Test: `tests/test_commands.py`; sửa `tests/test_ui.py` chỗ dùng `tool_catalog` cho Ctrl+K

**Interfaces:**
- Consumes: `icons.ICON_NAMES` (Task 1).
- Produces (`qtpdfpro/ui/commands.py`):
  - `@dataclass(frozen=True) class Command` — đúng các trường spec §8.1, thêm `register_shortcut: bool = True` (False cho V / H và phím chữ cái công cụ chú thích — các phím này do tab / `EditToolbar` đăng ký theo ngữ cảnh) và `palette: bool = True` (False cho lệnh chỉ là thân nút tách, nếu cần).
  - `TABS: tuple[tuple[str, str], ...] = (("read", "Đọc"), ("convert", "Chuyển đổi"), ("edit", "Chỉnh sửa"), ("fill", "Điền && Ký"), ("security", "Bảo mật"))`
  - `COMMANDS: tuple[Command, ...]`, `BY_KEY: dict[str, Command]`, `get(key: str) -> Command`
  - `GROUPS: dict[str, tuple[str, ...]]` — `"word"`, `"mark"`, `"draw"`, `"fill_mark"`, `"pages"`, `"process"`, `"save"`.
  - `TAB_LAYOUT: dict[str, tuple[str, ...]]` — phần tử là khoá lệnh, `"group:<tên>"` (nút ▾ nhớ kiểu vừa dùng), `"split:<khoá>:<nhóm>"` (thân = lệnh cố định, mũi tên = nhóm), `"date_formats"` (nút Ngày ▾ đặc biệt), hoặc `"|"` (vạch ngăn).
  - `HOME_QUICK_TOOLS: tuple[str, ...] = ("ocr", "batch_convert", "combine", "organize", "compress", "fill_mode", "protect", "print")`
  - `search(query: str, has_document: bool = True) -> list[Command]` — so khớp không dấu trên `label + keywords + tab label`, bỏ `palette=False`; rỗng → mọi lệnh theo thứ tự `TABS` rồi `system`.
- Produces (`MainWindow`): `command_actions: dict[str, QAction]` (mỗi lệnh một `QAction`, biểu tượng qua `icons.icon`, phím tắt nếu `register_shortcut`, thêm vào cửa sổ bằng `self.addAction`), `run_command(key: str) -> None`, `run_tool = run_command` (bí danh tạm, xoá ở Task 8), `_command_handlers() -> dict[str, Callable[[], None]]`.

**Danh sách lệnh** (khoá → hàm hiện có trong `MainWindow`; nhãn tiếng Việt lấy từ spec §3 / §5):

| Thẻ | Khoá (phím tắt) → hàm |
|---|---|
| read | `rotate_left` → `viewer.rotate_current_page(-90)` · `rotate_right` → `(+90)` · `read_mode` (F11) → `action_read_mode` · `print` (Ctrl+P) → `action_print` · `doc_info` (Ctrl+I) → `action_show_doc_info` |
| convert | `convert_word` (Ctrl+Shift+W) → `action_convert_to_docx` (hộp thoại, chế độ auto — vì thân nút đã mở hộp thoại tuỳ chỉnh nên menu ▾ **không** có mục «Tuỳ chỉnh xuất…» như spec §3 ghi, tránh trùng) · `convert_word_nd30` / `convert_word_exact` / `convert_word_flow` → `action_convert_to_docx_mode("nd30" / "exact" / "hybrid")` · `ocr` (Ctrl+Shift+R) → `action_ocr` · `nd30_check` (Ctrl+Shift+N) → `action_nd30_check` · `verify_docx` → `action_verify_docx` · `layout_overlay` (F8, checkable) → `action_toggle_layout_overlay` · `batch_convert` (Ctrl+Shift+B) → `action_batch_convert` |
| edit | `annot.<khoá>` cho `select, highlight, underline, strikeout, squiggly, pen, marker, rect, ellipse, line, arrow, text, note, stamp, eraser` (phím chữ cái của `TOOL_DEFS`, `register_shortcut=False`) → `active_tab().enter_edit_mode(khoá, "edit")` · `undo` (Ctrl+Z) · `redo` (Ctrl+Y, Ctrl+Shift+Z) · `organize` (Ctrl+Shift+O) · `combine` (Ctrl+Shift+M) · `split` · `extract_pages` → `action_organize(...)` · `compress` / `watermark` / `page_numbers` → `action_pdf_tool(...)` · `save` (Ctrl+S) → `action_save` · `save_as` (Ctrl+Shift+S) → `action_save_as` · `export_flattened` → `action_export_flattened` |
| fill | `annot.fill_text, fill_check, fill_cross, fill_dot, fill_line, fill_date, fill_sign, fill_initials` → `enter_edit_mode(khoá, "fill")` · `signatures` → `action_signature_library` |
| security | `sig_inspect` → `_open_inspector(True)` · `protect` / `unlock` → `action_pdf_tool(...)` |
| system | `open` (Ctrl+O) · `close_tab` (Ctrl+F4) · `home` (Alt+Home) · `quit` (Ctrl+Q) · `zoom_in` (Ctrl++) · `zoom_out` (Ctrl+-) · `fit_width` (Ctrl+1) · `fit_page` (Ctrl+0) · `pointer_select` (V) · `pointer_hand` (H) · `toggle_sidebar` (F4) · `toggle_theme` (Ctrl+Shift+T) · `palette` (Ctrl+K) · `find` (Ctrl+F) · `extract_text` (Ctrl+T) · `edit_mode` (Ctrl+E) → `set_function_tab` (Task 4; trước đó gọi `toggle_edit_mode`) · `fill_mode` (Ctrl+Shift+F) → `action_fill_sign` · `check_update` · `whats_new` (Task 7, tạm không có trong `COMMANDS` cho tới Task 7) · `github` → `_open_link(...)` · `about` → `action_show_about` · `default_app` → `default_app.make_default` · `auto_check_updates` / `auto_download_updates` (checkable) → hành động hiện có của `UpdateController` |

`needs_document=True` cho mọi lệnh thẻ read/convert/edit/fill/security trừ `batch_convert`, `combine`, `ocr`, `nd30_check` (hỏi chọn tệp như hiện nay — giữ hành vi `run_tool` cho các khoá tương ứng).

- [ ] **Step 1: Viết test** trong `tests/test_commands.py`:

```python
def test_command_keys_and_shortcuts_unique():
    keys = [c.key for c in commands.COMMANDS]
    assert len(keys) == len(set(keys))
    sc = [c.shortcut for c in commands.COMMANDS if c.shortcut and c.register_shortcut]
    assert len(sc) == len(set(sc))
    assert "F3" not in sc

def test_layout_groups_and_icons_exist():
    for tab, items in commands.TAB_LAYOUT.items():
        assert tab in dict(commands.TABS)
        for item in items:  # khoá / group: / split: / date_formats / |
            for key in commands.expand_layout_item(item):
                assert key in commands.BY_KEY, (tab, item)
    for c in commands.COMMANDS:
        assert c.icon in icons.ICON_NAMES, c.key

def test_search_is_accent_insensitive_and_has_system_commands():
    assert commands.search("xuat word")[0].key == "convert_word"
    assert "close_tab" in [c.key for c in commands.search("dong tai lieu")]
    assert not [c for c in commands.COMMANDS if "soon" in c.keywords.lower()]

def test_every_registered_shortcut_has_window_action(qapp, tmp_path):
    win = MainWindow(settings=AppSettings.load())
    for c in commands.COMMANDS:
        act = win.command_actions[c.key]
        assert act in win.actions()
        if c.shortcut and c.register_shortcut:
            assert act.shortcut().toString() == QKeySequence(c.shortcut.split(",")[0]).toString()
    win.close()

def test_palette_command_needing_document_cancelled_on_home(qapp, monkeypatch):
    win = MainWindow(settings=AppSettings.load())
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([], ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    win.run_command("compress")
    assert win.active_tab() is None and win.stack.currentWidget() is win.home_page
    win.close()
```
(`commands.expand_layout_item(item: str) -> tuple[str, ...]` — trả các khoá lệnh mà một phần tử bố cục tham chiếu; `"|"` → `()`, `"date_formats"` → `("annot.fill_date",)`.)

- [ ] **Step 2: Chạy** `python -m pytest -q tests/test_commands.py` → FAIL (chưa có `qtpdfpro.ui.commands`).
- [ ] **Step 3: Viết `qtpdfpro/ui/commands.py`** theo bảng trên; tìm không dấu dùng lại hàm bỏ dấu đang có trong `tool_catalog.py` (chuyển sang `commands.py`, `tool_catalog` nhập lại từ đây cho tới Task 8).
- [ ] **Step 4: Sửa `MainWindow`**: `_build_command_actions()` thay `_build_actions_and_menus()` — tạo `command_actions` + giữ tạm `main_menu` (dựng từ `command_actions` theo 5 menu cũ để thanh top hiện tại vẫn chạy tới Task 3); giữ tên thuộc tính cũ mà code khác dùng (`act_save`, `act_undo`, `act_redo`, `act_edit_mode`, `act_fill_sign`, `act_toggle_overlay`, `act_ocr`, `pointer_actions`) làm bí danh trỏ vào `command_actions[...]`. `run_command(key)`: lệnh `needs_document` mà chưa có tab và không thuộc nhóm tự hỏi tệp → `action_open_pdf()` rồi chạy nếu đã có tab (như `run_tool`).
- [ ] **Step 5: Sửa `command_palette.py`**: liệt kê `commands.search(q, has_document)`, mỗi dòng «biểu tượng · tên · tên thẻ · phím tắt căn phải», lệnh cần tài liệu khi chưa có tài liệu có ghi chú mờ «cần mở tệp»; chọn → `window.run_command(key)`.
- [ ] **Step 6: Chạy** `python -m pytest -q tests/test_commands.py` → PASS; sửa các test cũ bị ảnh hưởng (`tests/test_ui.py` phần bảng lệnh) rồi `python -m pytest -q tests` → qua, mã thoát 0.
- [ ] **Step 7: Commit** — «Nguồn lệnh duy nhất ui/commands.py, QAction dùng chung, Ctrl+K liệt kê mọi lệnh kèm phím tắt».

---

### Task 3: Tầng 1 `TopBar` và menu ☰

**Files:**
- Create: `qtpdfpro/ui/top_bar.py`, `tests/test_top_bar.py`
- Modify: `qtpdfpro/ui/main_window.py` (bỏ `_build_top_bar`, `_build_tab_strip`, `tab_strip`, `menu_buttons`, `main_menu` 5 menu cũ; dựng `self.top_bar = TopBar(...)`), `qtpdfpro/ui/theme.py` (QSS `#topBar`, `#docTabBar` trong tầng 1, `#iconBtn`), `qtpdfpro/ui/update_dialog.py` (hành động menu cập nhật lấy từ `command_actions`)
- Test: `tests/test_top_bar.py`; sửa `tests/test_ui.py` chỗ dùng `menu_buttons`, `tab_strip`, `btn_theme_toggle.text()`

**Interfaces:**
- Consumes: `command_actions` (Task 2), `icons.bind` (Task 1).
- Produces (`qtpdfpro/ui/top_bar.py`):
  - `class TopBar(QFrame)` — `__init__(self, actions: dict[str, QAction], recent_menu: QMenu, parent=None)`; thuộc tính `btn_home`, `btn_open`, `tab_bar: QTabBar` (objectName `docTabBar`, closable, movable, elide giữa, nút cuộn khi tràn), `btn_update_badge`, `search: QLineEdit` (placeholder «Tìm lệnh…  Ctrl+K»), `btn_theme`, `btn_menu`, `menu: QMenu`.
  - Tín hiệu: `paletteRequested(str)` (Enter / gõ trong ô tìm → mở Ctrl+K với chuỗi đã gõ).
  - `set_theme(theme: str) -> None` (biểu tượng `sun` khi đang Tối / `moon` khi đang Sáng, chú giải đổi theo), `show_update_badge(text: str, ready: bool) -> None`, `visible_command_keys() -> list[str]` (khoá lệnh của các nút đang hiện: `home`, `open`, `palette`, `toggle_theme`).
- `MainWindow` giữ bí danh để code cũ chạy: `doc_tab_bar = top_bar.tab_bar`, `btn_home`, `btn_update_badge`, `toolbar_search_input = top_bar.search`, `btn_theme_toggle = top_bar.btn_theme`, `show_update_badge()` uỷ quyền cho `top_bar`.

- [ ] **Step 1: Viết test** `tests/test_top_bar.py`:

```python
def test_hamburger_menu_contents_in_spec_order(qapp):
    win = MainWindow(settings=AppSettings.load())
    texts = [a.text().split("\t")[0] for a in win.top_bar.menu.actions() if not a.isSeparator()]
    assert texts == ["Mở tệp…", "Tệp mở gần đây", "Đóng tài liệu", "Lưu", "Lưu thành tệp mới…",
                     "Ẩn/hiện ngăn bên phải", "Cài đặt", "Kiểm tra cập nhật…",
                     "Mã nguồn & báo lỗi (GitHub)", "Giới thiệu QT PDF Pro", "Thoát"]
    assert not win.command_actions["close_tab"].isEnabled()  # chưa có tài liệu
    win.close()

def test_top_bar_has_no_text_menus_and_tabs_inline(qapp, sample_pdf):
    win, tab = open_window(sample_pdf)   # tiện ích chung: tests/ui_helpers.py
    assert not hasattr(win, "menu_buttons")
    assert win.top_bar.tab_bar.count() == 1 and win.top_bar.tab_bar.isVisible()
    assert win.command_actions["close_tab"].isEnabled()
    win.close()

def test_theme_button_is_icon_only_and_toggles(qapp):
    win = MainWindow(settings=AppSettings.load())
    assert win.top_bar.btn_theme.text() == ""
    before = win.settings.theme
    win.top_bar.btn_theme.click()
    assert win.settings.theme != before
    win.close()
```
(«Có gì mới trong bản này» chèn sau «Kiểm tra cập nhật…» ở Task 7 — Task 7 cập nhật test này. `tests/ui_helpers.py`: `open_window(pdf, settings=None, width=1400, height=900) -> (MainWindow, PDFDocumentTab)` gom từ các `_open` đang lặp trong nhiều tệp test.)

- [ ] **Step 2: Chạy** `python -m pytest -q tests/test_top_bar.py` → FAIL.
- [ ] **Step 3: Viết `TopBar`**; menu ☰ dựng từ `actions` đúng thứ tự spec §5.1 (mục «Cài đặt» là menu con chứa `auto_check_updates`, `auto_download_updates`, `default_app`); `MainWindow` bật/tắt `close_tab` / `save` / `save_as` theo việc có tài liệu (`_sync_toolbar_with_active_tab`).
- [ ] **Step 4: Chạy** test mới → PASS; sửa test cũ; `python -m pytest -q tests` → qua, mã thoát 0.
- [ ] **Step 5: Commit** — «Tầng 1 mới: tab tài liệu lên cùng hàng, nút ☰ thay 5 menu chữ, nút biểu tượng đổi giao diện».

---

### Task 4: Tầng 2 `FunctionBar`, bỏ thanh chế độ / thanh nhanh / cột công cụ trái, cột phải gọn, dòng thông báo mảnh

**Files:**
- Create: `qtpdfpro/ui/function_bar.py`, `tests/test_function_bar.py`
- Modify: `qtpdfpro/ui/main_window.py` (bỏ `_build_mode_bar`, `_build_tool_strip`, `_refresh_tool_strip`, `_run_strip_command`, `STRIP_TOOLS`, `set_tools_panel_visible`, `action_toggle_left_tools`, `PDFDocumentTab._build_left_tools_panel` / `tools_panel` / `set_tool_category` / `toolsPanelHideRequested` / `toolRequested`; `set_mode_category` → `set_function_tab`; `_build_right_rail` chỉ còn 4 nút ngăn; `sidebar_tabs.tabBar().hide()`; thay `signature_banner` bằng dòng thông báo), `qtpdfpro/ui/theme.py`
- Test: `tests/test_function_bar.py`; sửa `tests/test_ui.py`, `tests/test_ocr_ui.py`, `tests/test_pdf_tools_ui.py`, `tests/test_print_ui.py`, `tests/test_batch.py`, `tests/test_viewer_navigation.py`, `tests/test_text_select.py`, `tests/test_ui_fonts.py` (mọi chỗ dùng `STRIP_TOOLS`, `strip_buttons`, `tools_panel`, `mode_buttons`, `set_mode_category`, `pointer_btns`, `banner_convert_btn`, `btn_convert_docx`)

**Interfaces:**
- Consumes: `commands.TABS`, `TAB_LAYOUT`, `GROUPS`, `expand_layout_item`, `command_actions`, `icons`.
- Produces (`qtpdfpro/ui/function_bar.py`):
  - `class FunctionBar(QFrame)` — `__init__(self, actions: dict[str, QAction], parent=None)`.
  - Tín hiệu: `tabRequested(str)`.
  - `tab_buttons: dict[str, QPushButton]`, `tool_buttons: dict[str, QToolButton]` (khoá = phần tử bố cục), `overflow_button: QToolButton` (biểu tượng `ellipsis`), `page_spin`, `total_page_lbl`, `btn_prev_page`, `btn_next_page`, `zoom_combo`, `btn_pointer_select`, `btn_pointer_hand` (nút biểu tượng gắn `command_actions["pointer_select" / "pointer_hand"]`).
  - `set_tab(key: str) -> None` (dựng lại vùng công cụ từ `TAB_LAYOUT[key]`: `QToolButton.setDefaultAction(actions[k])`; `group:` → `MenuButtonPopup` nhớ lệnh vừa dùng; `split:` → thân cố định + menu nhóm), `current_tab() -> str`, `set_save_visible(visible: bool) -> None` (thẻ không phải edit/fill: hiện / ẩn nút `split:save:save` ở cuối vùng công cụ), `visible_command_keys() -> list[str]` (gồm cả mục đang nằm trong `⋯`), `relayout_overflow() -> None` (gọi trong `resizeEvent`).
  - Kiểu nút: thẻ read/convert/security `ToolButtonTextBesideIcon`; công cụ chú thích `ToolButtonIconOnly` (chú giải = tên + phím tắt).
- Produces (`MainWindow`): `function_bar`, `set_function_tab(key: str) -> None` (đổi thẻ; edit → `tab.enter_edit_mode(None, "edit")`, fill → `enter_fill_mode()`, khác → `exit_edit_mode()`), bí danh `page_spin`, `zoom_combo`… trỏ vào `function_bar`. Phím `Alt+1…5` (`QShortcut` trên cửa sổ) → `set_function_tab` khi có tài liệu. Mở tài liệu / đóng tài liệu cuối → `set_function_tab("read")`.
- Dòng thông báo (`PDFDocumentTab`): `notice_bar: QFrame` (objectName `noticeBar`, cao tối đa 34 px) gồm `notice_icon`, `notice_lbl`, `notice_link: QPushButton` (objectName `linkBtn`), `notice_close`; `show_notice(text: str, link_text: str, command_key: str) -> None`; `notice_dismissed: bool` — bấm ✕ đặt `True` và không hiện lại cho tab đó. `_analyze_document` gọi `show_notice` thay vì bật `signature_banner` (lệnh liên kết: văn bản hành chính → `convert_word_nd30`; chữ ký / bảng → `convert_word_exact`; ảnh quét → `saveSearchableRequested`).

- [ ] **Step 1: Viết test** `tests/test_function_bar.py`:

```python
TAB_TOOLS = {
    "read": ["rotate_left", "rotate_right", "read_mode", "print", "doc_info"],
    "convert": ["split:convert_word:word", "ocr", "nd30_check", "verify_docx", "layout_overlay", "batch_convert"],
    "security": ["sig_inspect", "protect", "unlock"],
}

def test_tabs_and_tools_match_spec(qapp, sample_pdf):
    win, tab = open_window(sample_pdf)
    assert list(win.function_bar.tab_buttons) == ["read", "convert", "edit", "fill", "security"]
    assert win.function_bar.current_tab() == "read"
    for key, tools in TAB_TOOLS.items():
        win.set_function_tab(key)
        assert list(win.function_bar.tool_buttons) == tools
    assert not hasattr(tab, "tools_panel") and not hasattr(win, "tool_strip")
    win.close()

def test_right_rail_only_panel_switchers(qapp, sample_pdf):
    win, tab = open_window(sample_pdf)
    assert [b.toolTip().split(" (")[0] for b in tab.rail_panel_buttons] == ["Trang", "Mục lục", "Tìm kiếm", "Chú thích"]
    assert tab.sidebar_tabs.tabBar().isHidden()
    win.close()

def test_notice_line_dismiss_and_single_primary(qapp, admin_pdf):
    win, tab = open_window(admin_pdf); tab.wait_for_document_analysis()
    assert tab.notice_bar.isVisible() and tab.notice_link.objectName() == "linkBtn"
    tab.notice_close.click(); tab._analyze_document()
    assert not tab.notice_bar.isVisible()
    win.set_function_tab("convert")
    primaries = [w for w in win.findChildren(QAbstractButton) if w.isVisible() and w.objectName() == "primaryConvertBtn"]
    assert len(primaries) == 1
    win.close()

def test_overflow_roundtrip_keeps_actions(qapp, sample_pdf):            # Review Focus 3
    win, tab = open_window(sample_pdf, width=1280); win.set_function_tab("convert")
    for w in (900, 1280, 900, 1600, 1280):
        win.resize(w, 800); qapp.processEvents()
        keys = win.function_bar.visible_command_keys()
        assert sorted(keys) == sorted(set(keys))                         # không nhân đôi
        assert set(TAB_TOOLS["convert"]) <= set(win.function_bar.tool_buttons) | set(win.function_bar.overflow_keys())
    win.resize(900, 800); qapp.processEvents()
    hidden = win.function_bar.overflow_keys()
    assert hidden
    for k in hidden:                                                     # mục trong ⋯ vẫn là QAction dùng được
        act = win.command_actions[commands.expand_layout_item(k)[0]]
        assert act.isEnabled() and act in win.function_bar.overflow_button.menu().actions()
    win.close()

def test_min_width_and_close_last_doc_in_edit(qapp, sample_pdf):        # Review Focus 4
    win, tab = open_window(sample_pdf)
    assert win.minimumSizeHint().width() <= 1280
    win.set_function_tab("edit"); assert tab.edit_mode
    win.close_tab_at(0)
    assert win.stack.currentWidget() is win.home_page and not win.function_bar.isVisible()
    QTest.keyClick(win, Qt.Key.Key_3, Qt.KeyboardModifier.AltModifier)   # không có tài liệu → bỏ qua
    win2tab = win.open_pdf_path(sample_pdf)
    assert win.function_bar.current_tab() == "read" and not win2tab.edit_mode
    win.close()
```
(`overflow_keys() -> list[str]`: phần tử bố cục đang nằm trong `⋯`. `rail_panel_buttons: list[QPushButton]` trên `PDFDocumentTab`. Fixture `admin_pdf` = `samples/nd30/quyet_dinh_mau.pdf`, `sample_pdf` = PDF 2 trang tạo trong `tests/ui_helpers.py`.)

- [ ] **Step 2: Chạy** `python -m pytest -q tests/test_function_bar.py` → FAIL.
- [ ] **Step 3: Viết `FunctionBar`** (bố cục: thẻ | vùng công cụ co giãn | cụm điều khiển xem; tràn: ẩn nút từ cuối, đưa vào menu `⋯` theo đúng thứ tự, `QAction` dùng chung nên trạng thái bật / tắt đồng bộ).
- [ ] **Step 4: Sửa `MainWindow` / `PDFDocumentTab`** theo danh sách bỏ ở mục Files; tầng 2 chỉ hiện khi có tài liệu (`_show_home` / `_show_documents`).
- [ ] **Step 5: Chạy** test mới → PASS; sửa các test cũ trong danh sách; `python -m pytest -q tests` → qua, mã thoát 0.
- [ ] **Step 6: Chạy cửa sổ thật** (`QT_PDF_PRO_DATA` tạm), chụp `win.grab()` ở 1366 × 768 cho từng thẻ, xem ảnh: không chữ bị cắt, tiếng Việt đủ dấu.
- [ ] **Step 7: Commit** — «Tầng 2: thanh chức năng 5 thẻ thay thanh chế độ, thanh công cụ nhanh và cột công cụ trái; cột phải và thanh thông báo gọn».

---

### Task 5: Công cụ chú thích lên tầng 2, `EditToolbar` chỉ còn hàng kiểu dáng, test chống trùng

**Files:**
- Modify: `qtpdfpro/ui/annotation_tools.py` (`EditToolbar`), `qtpdfpro/ui/main_window.py`, `qtpdfpro/ui/function_bar.py`, `qtpdfpro/ui/theme.py`
- Test: `tests/test_no_duplicates.py` (mới), sửa `tests/test_edit_ui.py`, `tests/test_fill_sign_ui.py` (chỗ dùng `edit_toolbar.tool_buttons`, `btn_save`, `btn_exit`, `btn_organize`)

**Interfaces:**
- Consumes: `FunctionBar.set_tab`, `GROUPS["mark"/"draw"/"fill_mark"]`, `command_actions["annot.*"]`.
- Produces:
  - `EditToolbar` (giữ tên lớp và các ô kiểu dáng `color_box`, `width_box`, `opacity_box`, `font_box`, `fill_chk`, `stamp_box`, `snap_chk`, `sig_combo`, `hint_lbl`, `set_shortcuts_enabled`): **bỏ** hàng 1 (`tool_buttons`, `btn_undo`, `btn_redo`, `btn_organize`, `btn_save`, `btn_exit`, tiêu đề), bỏ `date_box` (mẫu ngày chuyển lên nút «Ngày ▾») và `btn_manage_sig` (đã có lệnh `signatures`). `sync_from_controller()` tự `setVisible(False)` khi công cụ hiện tại là `pan`, `select`, `eraser` hoặc không có ô kiểu dáng nào hiện.
  - `FunctionBar.set_checked_tool(key: str | None) -> None` — đánh dấu nút công cụ (kể cả thân nút nhóm: đổi biểu tượng thân nút thành công cụ đó).
  - `MainWindow._connect_active_controller(tab)` — nối `tab.annot_controller.toolChanged` → `function_bar.set_checked_tool`; ngắt kết nối tab trước khi đổi tab (`_on_header_tab_changed`). Đổi tab khi đang ở thẻ edit / fill → tab mới `enter_edit_mode` / `enter_fill_mode`.
  - `MainWindow._sync_save_button()` — `function_bar.set_save_visible(tab.reader.has_unsaved_changes)` ở thẻ không phải edit/fill; nút `save` mang `primaryConvertBtn` chỉ khi `tab.reader.has_unsaved_changes`.
  - Nút «Ngày ▾»: menu liệt kê `fs.DATE_FORMATS` (nhãn `fs.format_date(key)`), chọn → `controller.date_format = key` rồi `enter_edit_mode("fill_date", "fill")`; thân nút = công cụ `fill_date` với mẫu đang chọn.

- [ ] **Step 1: Viết test** `tests/test_no_duplicates.py`:

```python
def _visible_keys(win, tab):
    keys = win.top_bar.visible_command_keys() + win.function_bar.visible_command_keys()
    keys += [b.property("command_key") for b in tab.rail_panel_buttons]
    return [k for k in keys if k]

@pytest.mark.parametrize("modified", [False, True])
def test_each_command_appears_once_per_screen(qapp, sample_pdf, modified):
    win, tab = open_window(sample_pdf)
    if modified:
        tab.annot_controller.session.add_markup(0, "highlight", [fitz.Rect(72, 90, 200, 105)],
                                                tab.annot_controller.style("highlight").copy())
        tab._on_annotations_changed(0)
    for key, _label in commands.TABS:
        win.set_function_tab(key); qapp.processEvents()
        flat = [commands.expand_layout_item(k) for k in _visible_keys(win, tab)]
        flat = [x for group in flat for x in group]
        assert len(flat) == len(set(flat)), (key, sorted(flat))
    win.close()

def test_edit_tab_tools_drive_active_tab_controller(qapp, sample_pdf, tmp_path):   # Review Focus 1
    win, tab1 = open_window(sample_pdf)
    tab2 = win.open_pdf_path(copy_pdf(sample_pdf, tmp_path / "b.pdf"))
    win.set_function_tab("edit")
    win.command_actions["annot.rect"].trigger()
    assert tab2.annot_controller.tool == "rect" and tab2.edit_mode
    win.top_bar.tab_bar.setCurrentIndex(0)
    assert tab1.edit_mode and win.function_bar.current_tab() == "edit"
    win.command_actions["annot.pen"].trigger()
    assert tab1.annot_controller.tool == "pen" and tab2.annot_controller.tool == "rect"
    win.close()

def test_save_visible_in_read_tab_only_when_modified(qapp, sample_pdf, monkeypatch):  # Review Focus 2
    win, tab = open_window(sample_pdf)
    win.set_function_tab("read")
    assert "split:save:save" not in win.function_bar.visible_command_keys()
    tab.text_select.highlightRequested.emit(0, [fitz.Rect(72, 90, 200, 105)])
    assert "split:save:save" in win.function_bar.visible_command_keys()
    win.command_actions["save"].trigger()
    assert not tab.reader.has_unsaved_changes and "split:save:save" not in win.function_bar.visible_command_keys()
    win.close()

def test_style_row_only_for_tools_with_style(qapp, sample_pdf):
    win, tab = open_window(sample_pdf); win.set_function_tab("edit")
    win.command_actions["annot.select"].trigger(); assert not tab.edit_toolbar.isVisible()
    win.command_actions["annot.highlight"].trigger(); assert tab.edit_toolbar.color_box.isVisible()
    win.close()
```
(`copy_pdf` trong `tests/ui_helpers.py`. Nút thanh dọc mang `setProperty("command_key", ...)`: `panel_pages`, `panel_toc`, `find`, `panel_annotations` — thêm 3 lệnh `panel_pages` / `panel_toc` / `panel_annotations` (thẻ `system`, không phím tắt) vào `COMMANDS` ở task này.)

- [ ] **Step 2: Chạy** `python -m pytest -q tests/test_no_duplicates.py` → FAIL.
- [ ] **Step 3: Sửa `EditToolbar`, `FunctionBar`, `MainWindow`** theo Interfaces.
- [ ] **Step 4: Chạy** test mới → PASS; sửa `tests/test_edit_ui.py`, `tests/test_fill_sign_ui.py`; `python -m pytest -q tests` → qua, mã thoát 0.
- [ ] **Step 5: Chạy cửa sổ thật**: thẻ Chỉnh sửa (chọn tô sáng → hàng kiểu dáng hiện; chọn Chọn → ẩn), thẻ Điền & Ký (Ngày ▾ đặt ngày mẫu NĐ30); chụp ảnh 1366 px Sáng + Tối.
- [ ] **Step 6: Commit** — «Công cụ chú thích lên thanh chức năng, nhóm ▾ nhớ kiểu vừa dùng; hàng kiểu dáng chỉ hiện khi cần; test mỗi lệnh một nút».

---

### Task 6: Trang chủ mới

**Files:**
- Modify: `qtpdfpro/ui/home_page.py` (bỏ `ToolCatalogPanel`, `CatalogRow`, `ToolCard`, `_ElidedLabel` nếu không còn dùng, `catalog`, «Công cụ đề xuất», liên kết chân trang), `qtpdfpro/ui/main_window.py` (bỏ `home_page.catalog`, nối tín hiệu mới), `qtpdfpro/ui/theme.py`
- Test: `tests/test_home_page.py` (mới), sửa `tests/test_ui.py` phần Trang chủ

**Interfaces:**
- Consumes: `commands.HOME_QUICK_TOOLS`, `commands.get`, `icons.bind`.
- Produces (`HomePage`): tín hiệu `commandRequested(str)` (thay `toolActivated`), `openRequested()`, `recentActivated(str)`, `filesDropped(list)`, `versionClicked()`; thuộc tính `version_chip: QPushButton`, `open_card`, `nd30_card` (nút `btn_nd30_convert` → `convert_word_nd30`, objectName `primaryConvertBtn`; `btn_nd30_check` → `nd30_check`), `recent_box`, `quick_tiles: dict[str, QPushButton]`, `privacy_lbl`; `set_recent_files(paths: list[str], has_open_docs: bool = False) -> None` giữ nguyên chữ ký. Nội dung rộng tối đa 1100 px, căn giữa; ô công cụ 4 cột (bề rộng < 760 px → 2 cột).

- [ ] **Step 1: Viết test** `tests/test_home_page.py`:

```python
def test_home_sections_and_quick_tools(qapp):
    win = MainWindow(settings=AppSettings.load())
    home = win.home_page
    assert list(home.quick_tiles) == list(commands.HOME_QUICK_TOOLS)
    assert not hasattr(home, "catalog")
    assert home.version_chip.text() == f"v{__version__}"
    primaries = [b for b in home.findChildren(QPushButton) if b.objectName() == "primaryConvertBtn"]
    assert primaries == [home.btn_nd30_convert]
    assert not win.function_bar.isVisible()
    win.close()

def test_quick_tile_runs_command(qapp, monkeypatch):
    win = MainWindow(settings=AppSettings.load())
    seen = []; monkeypatch.setattr(win, "run_command", seen.append)
    win.home_page.quick_tiles["batch_convert"].click()
    assert seen == ["batch_convert"]
    win.close()
```
- [ ] **Step 2: Chạy** → FAIL. **Step 3: Viết lại `HomePage`** theo spec §4. **Step 4: Chạy** test mới → PASS; `python -m pytest -q tests` → qua, mã thoát 0.
- [ ] **Step 5: Chụp** Trang chủ ở 1366 và 1920 px, Sáng + Tối; xem ảnh.
- [ ] **Step 6: Commit** — «Trang chủ mới: Bắt đầu, Gần đây, 8 ô công cụ nhanh; bỏ cột Tất cả công cụ».

---

### Task 7: Hộp thoại «Có gì mới»

**Files:**
- Create: `qtpdfpro/core/whats_new.py`, `qtpdfpro/ui/whats_new_dialog.py`, `qtpdfpro/ui/assets/whats_new.json`, `tests/test_whats_new.py`
- Modify: `qtpdfpro/core/settings.py` (`last_seen_version: str = ""`; `load()` đặt thuộc tính thường `existed: bool` — không phải trường dataclass, không ghi ra tệp), `qtpdfpro/ui/app.py`, `qtpdfpro/ui/main_window.py` (`self.whats_new = WhatsNewController(self, self.settings)`; lệnh `whats_new` vào `COMMANDS` + ☰ sau «Kiểm tra cập nhật…»; `home_page.versionClicked` → `whats_new.show_current()`), `qtpdfpro/ui/commands.py`, `build.bat` (`--add-data` `whats_new.json`), `tests/test_top_bar.py` (thêm mục ☰), `tests/test_version.py`

**Interfaces:**
- Produces (`core/whats_new.py`):
  - `NOTES_FILE: Path` = `Path(__file__).resolve().parents[1] / "ui" / "assets" / "whats_new.json"`
  - `@dataclass(frozen=True) class NoteItem: icon: str; title: str; text: str; shortcut: str = ""`
  - `@dataclass(frozen=True) class VersionNotes: version: str; date: str; headline: str; items: tuple[NoteItem, ...]`
  - `load_notes(path: Path | None = None) -> list[VersionNotes]` — mới nhất trước; tệp thiếu / hỏng / sai cấu trúc → `[]`.
  - `notes_for(version: str, notes: list[VersionNotes]) -> VersionNotes | None`
  - `notes_to_show(current: str, last_seen: str, settings_existed: bool, notes: list[VersionNotes]) -> list[VersionNotes]` — đúng 4 luật spec §6.2; so phiên bản bằng `update_check.parse_version`.
- Produces (`ui/whats_new_dialog.py`):
  - `class WhatsNewDialog(QDialog)` — `__init__(self, notes: list[VersionNotes], parent=None)`; `btn_start` (mặc định, `primaryConvertBtn`), `btn_github` (mở `https://github.com/{__github_repo__}/releases/tag/v{notes[0].version}`), các bản cũ trong khung thu gọn (`QToolButton` mũi tên + nội dung ẩn).
  - `class WhatsNewController` — `__init__(self, window, settings)`; `on_startup() -> bool` (tính `notes_to_show`; cài mới → ghi `last_seen_version`, trả `False`; có ghi chú → hẹn `QTimer.singleShot(700, self._show_due)`, trả `True`), `_show_due()` (mở hộp thoại rồi ghi `last_seen_version = __version__` + `settings.save()`), `show_current()` (ghi chú của `__version__`, không có thì bản mới nhất), `dialog_factory` (thuộc tính, test thay).
- `ui/app.py`: `shown = win.whats_new.on_startup()`; `if not shown: win.default_app.on_startup()`.
- Nội dung `whats_new.json` bản `1.3.0` (5 mục, biểu tượng có trong `icons.ICON_NAMES`): Giao diện gọn hơn (`layout-panel-top`, Ctrl+K) · Chọn chữ liền nhiều trang (`text-cursor`, V) · Chọn chữ trên bản scan (`scan-text`) · Lưu thành PDF tìm kiếm được (`save`) · Mở tệp nhanh hơn, nhấp ảnh thu nhỏ chuyển trang ngay (`files`). Lời văn ngắn, không thuật ngữ kỹ thuật.

- [ ] **Step 1: Viết test** `tests/test_whats_new.py`:

```python
N = [wn.VersionNotes("1.4.0", "", "", ()), wn.VersionNotes("1.3.0", "", "", ()), wn.VersionNotes("1.2.1", "", "", ())]

def test_notes_to_show_rules():
    assert wn.notes_to_show("1.3.0", "", False, N) == []                       # cài mới
    assert [n.version for n in wn.notes_to_show("1.3.0", "", True, N)] == ["1.3.0"]  # cập nhật từ bản cũ
    assert wn.notes_to_show("1.3.0", "1.3.0", True, N) == []
    assert [n.version for n in wn.notes_to_show("1.4.0", "1.2.1", True, N)] == ["1.4.0", "1.3.0"]

def test_broken_file_gives_empty(tmp_path):
    p = tmp_path / "w.json"; p.write_text("{hỏng", encoding="utf-8")
    assert wn.load_notes(p) == []

def test_bundled_notes_valid():
    notes = wn.load_notes()
    assert notes and 3 <= len(notes[0].items) <= 6
    assert all(i.icon in icons.ICON_NAMES for n in notes for i in n.items)

def test_startup_shows_once_then_records(qapp, monkeypatch):
    s = AppSettings.load(); s.existed = True; s.last_seen_version = "1.2.1"
    win = MainWindow(settings=s)
    shown = []; win.whats_new.dialog_factory = lambda notes, parent: FakeDialog(shown, notes)
    monkeypatch.setattr(wn, "load_notes", lambda path=None: [wn.VersionNotes(__version__, "", "", ())])
    if __version__ != "1.2.1":
        assert win.whats_new.on_startup() is True
        win.whats_new._show_due()
        assert shown and AppSettings.load().last_seen_version == __version__
    win.close()

def test_fresh_install_records_without_dialog(qapp):
    s = AppSettings.load(); s.existed = False
    win = MainWindow(settings=s)
    assert win.whats_new.on_startup() is False and s.last_seen_version == __version__
    win.close()
```
(`FakeDialog(shown, notes)`: có `exec()` ghi `shown.append(notes)` và trả `1`.) Thêm vào `tests/test_version.py`:

```python
def test_whats_new_ready_for_current_or_next_version():
    notes = wn.load_notes()
    newest = parse_version(notes[0].version)
    assert wn.notes_for(__version__, notes) is not None or newest > parse_version(__version__)
```
- [ ] **Step 2: Chạy** `python -m pytest -q tests/test_whats_new.py tests/test_version.py` → FAIL.
- [ ] **Step 3: Viết** `core/whats_new.py`, `whats_new.json`, `ui/whats_new_dialog.py`; sửa `settings.py`, `app.py`, `main_window.py`, `commands.py`, `build.bat`, `tests/test_top_bar.py`.
- [ ] **Step 4: Chạy** → PASS; `python -m pytest -q tests` → qua, mã thoát 0.
- [ ] **Step 5: Chạy thử**: thư mục dữ liệu tạm có `settings.json` với `"last_seen_version": "1.2.1"` → mở ứng dụng (`python -m qtpdfpro`) thấy hộp thoại; mở lại → không thấy; ☰ › «Có gì mới trong bản này» mở lại được. Chụp hộp thoại Sáng + Tối.
- [ ] **Step 6: Commit** — «Hộp thoại «Có gì mới» sau khi cập nhật: ghi chú riêng cho người dùng, hiện một lần, mở lại từ ☰».

---

### Task 8: Dọn dẹp, đóng gói, tài liệu

**Files:**
- Delete: `qtpdfpro/ui/tool_catalog.py` (sau khi `grep -rn "tool_catalog" qtpdfpro tests` trống)
- Modify: `qtpdfpro/ui/main_window.py` (xoá bí danh `run_tool` và bí danh tạm không còn ai dùng; `PDFDocumentTab` docstring), `qtpdfpro/ui/theme.py` (xoá QSS của `#modeBar`, `#toolStrip`, `#toolsPanel`, `#catalogRow`, `#toolCard`, `#signatureBanner`, nhãn «Soon»), `QTPdfPro.spec` (sinh lại bằng `build.bat`, chỉ commit khi nội dung đổi), `CHANGELOG.md`, `CLAUDE.md` (mục 1, 4, 5, 6, 7), `docs/DE_XUAT_TINH_NANG.md` (ghi công cụ chưa làm không còn hiện trong ứng dụng)
- Test: toàn bộ `tests/`

**Interfaces:**
- Consumes: mọi task trước.

- [ ] **Step 1: Xoá `tool_catalog.py` và bí danh**; `grep -rn "run_tool\|tool_catalog\|STRIP_TOOLS\|show_tools_panel\|Coming Soon" qtpdfpro tests` chỉ còn `settings.show_tools_panel` (giữ để đọc tệp cũ).
- [ ] **Step 2: Dọn QSS** không còn bộ chọn nào dùng (`grep` từng `objectName` trong `qtpdfpro/ui`).
- [ ] **Step 3: Chạy** `python -m pytest -q tests` → qua, mã thoát 0.
- [ ] **Step 4: Đóng gói thử** `cmd.exe /c ".\build.bat"` rồi kiểm `dist\QTPdfPro\_internal\qtpdfpro\ui\assets\icons\search.svg` và `...\assets\whats_new.json` tồn tại; chạy `dist\QTPdfPro\QTPdfPro.exe --skip-default-prompt` với `QT_PDF_PRO_DATA` tạm, chụp màn hình (nếu Smart App Control chặn thì ghi lại và kiểm bằng nội dung thư mục).
- [ ] **Step 5: Ảnh chụp kiểm cuối** (spec §9 thủ công): Trang chủ, 5 thẻ, thẻ Chỉnh sửa có hàng kiểu dáng, «Có gì mới» — 1366 × 768 và 1920 × 1080, Sáng và Tối; đối chiếu tiêu chí thành công spec §1 (đếm tầng, một nút chính, không emoji).
- [ ] **Step 6: Cập nhật** `CHANGELOG.md` (mục mới trên cùng trong «Chưa phát hành»), `CLAUDE.md` (bảng tệp: thêm `commands.py`, `icons.py`, `top_bar.py`, `function_bar.py`, `whats_new*`, bỏ `tool_catalog.py`; mục 5 thêm bài học gặp phải; mục 6 bước phát hành nhắc viết `whats_new.json`), `docs/DE_XUAT_TINH_NANG.md`.
- [ ] **Step 7: Commit & push** — «Hoàn tất đại tu giao diện: xoá tool_catalog, dọn QSS, đóng gói biểu tượng, cập nhật tài liệu» → `git push`.
