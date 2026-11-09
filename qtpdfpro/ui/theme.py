"""Giao diện Sáng / Tối (Fluent & PdfCraft-inspired QSS) cho QT PDF Pro."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from qtpdfpro.core.settings import get_data_dir

# Phông giao diện giống PdfCraft: Inter 4.1 (SIL OFL 1.1 — assets/fonts/OFL-Inter.txt), đủ 146 chữ cái
# tiếng Việt. Ký hiệu / emoji Inter không có (✕ ⌂ ✂ 📂…) thì Qt tự lấy từ Segoe UI Symbol / Emoji.
UI_FONT_FAMILY = "Inter"
UI_FONT_FALLBACKS = ("Segoe UI", "Arial")
FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
# PdfCraft chỉ dùng Regular / Medium / SemiBold; Bold cho chữ đậm trong hộp thoại (<b>, setBold)
UI_FONT_FILES = ("Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf", "Inter-Bold.ttf")
_ui_font_ids: list[int] = []


def load_ui_fonts() -> bool:
    """Nạp các tệp Inter đi kèm vào Qt (một lần); True khi Qt đã có họ phông `UI_FONT_FAMILY`."""
    if not _ui_font_ids:
        for name in UI_FONT_FILES:
            font_id = QFontDatabase.addApplicationFont(str(FONT_DIR / name))
            if font_id != -1:
                _ui_font_ids.append(font_id)
    return UI_FONT_FAMILY in QFontDatabase.families()


def install_ui_fonts(app: QApplication) -> bool:
    """Nạp Inter và đặt làm phông mặc định của ứng dụng (cả hộp thoại không cha, chú giải công cụ).

    Không nắn nét (hinting) như PdfCraft: nắn dọc / nắn đầy đủ của DirectWrite ép Inter 13 px vào lưới
    điểm ảnh làm mất dấu hỏi trên chữ có mũ («Kiểm» → «Kiếm», «Ổn» → «Ôn») và chữ Medium dính nhau.
    QSS chỉ đặt họ / cỡ / độ đậm nên mọi widget vẫn kế thừa lựa chọn này từ phông ứng dụng.
    Thiếu tệp phông thì vẫn đặt danh sách họ phông — Qt lùi về Segoe UI như trước.
    """
    loaded = load_ui_fonts()
    font = app.font()
    font.setFamilies([UI_FONT_FAMILY, *UI_FONT_FALLBACKS])
    if loaded:
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)
    return loaded


def get_stylesheet(theme: str = "dark") -> str:
    """Trả về chuỗi QSS theo chủ đề `'dark'` hoặc `'light'`."""
    if theme == "light":
        return _LIGHT_QSS + _shell_qss(_LIGHT_TOKENS)
    return _DARK_QSS + _shell_qss(_DARK_TOKENS)


def theme_tokens(theme: str = "dark") -> dict[str, str]:
    """Bảng màu `@token` của chủ đề (`'light'` / `'dark'`) — vd `theme_tokens(t)["text"]` = màu biểu tượng."""
    return dict(_LIGHT_TOKENS if theme == "light" else _DARK_TOKENS)


# Bảng màu cho khung PdfCraft (dải tiêu đề, thanh chế độ, Trang chủ, danh mục công cụ)
_LIGHT_TOKENS = {
    "strip": "#E9EBEF", "bar": "#FFFFFF", "page": "#F3F4F6", "card": "#FFFFFF", "card_hover": "#F8FAFF",
    "border": "#E2E5EA", "border_strong": "#CBD2DC", "text": "#0F172A", "muted": "#64748B", "faint": "#94A3B8",
    "accent": "#2563EB", "accent_soft": "#E8F0FE", "accent_text": "#1D4ED8", "hover": "#EEF1F5",
    "hero1": "#EEF4FF", "hero2": "#FFFFFF", "tab_sel": "#FFFFFF",
    "toast_bg": "#0F172A", "toast_text": "#FFFFFF", "on_accent": "#FFFFFF", "indicator_bg": "#FFFFFF",
}
_DARK_TOKENS = {
    "strip": "#0E1015", "bar": "#16181D", "page": "#111318", "card": "#1A1D24", "card_hover": "#1F2430",
    "border": "#2A2F3A", "border_strong": "#3A4150", "text": "#E6E8EC", "muted": "#9CA3AF", "faint": "#6B7280",
    "accent": "#3B82F6", "accent_soft": "#1E2A44", "accent_text": "#93C5FD", "hover": "#232833",
    "hero1": "#16233D", "hero2": "#1A1D24", "tab_sel": "#16181D",
    "toast_bg": "#F8FAFC", "toast_text": "#0F172A", "on_accent": "#FFFFFF", "indicator_bg": "#121419",
}

_SHELL_TEMPLATE = """
QWidget#appRoot, QWidget#homeContent, QScrollArea#homeScroll { background-color: @page; }
QFrame#topBar { background-color: @strip; border: none; }
QPushButton#topBtn {
    background-color: transparent; color: @text; border: 1px solid transparent; border-radius: 6px;
    padding: 5px 12px; font-weight: 600;
}
QPushButton#topBtn:hover { background-color: @hover; border-color: @border; }
QPushButton#topBtn:checked { background-color: @accent_soft; color: @accent_text; border-color: @accent; }
QToolButton#iconBtn {
    background-color: transparent; border: 1px solid transparent; border-radius: 6px; padding: 5px;
}
QToolButton#iconBtn:hover, QToolButton#iconBtn:pressed, QToolButton#iconBtn:open {
    background-color: @hover; border-color: @border;
}
QToolButton#iconBtn::menu-indicator { image: none; width: 0px; }
QPushButton#updateBadgeBtn {
    background-color: @accent; color: @on_accent; border: none; border-radius: 13px;
    padding: 4px 12px; font-weight: 600;
}
QPushButton#updateBadgeBtn:hover { background-color: @accent_text; }
QPushButton#updateBadgeBtn[ready="true"] { background-color: #16A34A; }
QPushButton#updateBadgeBtn[ready="true"]:hover { background-color: #15803D; }
QTabBar#docTabBar { background: transparent; }
QTabBar#docTabBar::tab {
    background-color: transparent; color: @muted; border: none; border-top-left-radius: 8px;
    border-top-right-radius: 8px; padding: 6px 12px; margin-right: 2px; min-width: 110px; max-width: 240px;
}
QTabBar#docTabBar::tab:hover { background-color: @hover; color: @text; }
QTabBar#docTabBar::tab:selected { background-color: @tab_sel; color: @text; font-weight: 600; }
QPushButton#ghostIconBtn {
    background-color: transparent; color: @text; border: 1px solid transparent; border-radius: 6px;
    padding: 5px 10px; font-weight: 500;
}
QPushButton#ghostIconBtn { padding: 4px 8px; min-width: 18px; }
QPushButton#ghostIconBtn:hover { background-color: @hover; border-color: @border; }
QPushButton#pillBtn {
    background-color: @card; color: @text; border: 1px solid @border_strong; border-radius: 15px;
    padding: 5px 14px; font-weight: 500;
}
QPushButton#pillBtn:hover { border-color: @accent; background-color: @card_hover; }
QFrame#functionBar { background-color: @bar; border-bottom: 1px solid @border; }
QPushButton#fnTabBtn {
    background-color: transparent; color: @muted; border: none; border-bottom: 2px solid transparent;
    border-radius: 0px; padding: 7px 8px 5px 8px; font-weight: 600;
}
QPushButton#fnTabBtn:hover { color: @text; background-color: transparent; }
QPushButton#fnTabBtn:checked { color: @text; border-bottom: 2px solid @accent; }
QToolButton#fnToolBtn, QToolButton#fnIconBtn {
    background-color: transparent; color: @text; border: 1px solid transparent; border-radius: 6px;
    padding: 4px 5px; font-weight: 500;
}
QToolButton#fnIconBtn { padding: 4px; }
QToolButton#fnToolBtn:hover, QToolButton#fnIconBtn:hover, QToolButton#fnToolBtn:open {
    background-color: @hover; border-color: @border;
}
QToolButton#fnToolBtn:checked, QToolButton#fnIconBtn:checked {
    background-color: @accent_soft; color: @accent_text; border-color: @accent;
}
QToolButton#fnToolBtn:disabled, QToolButton#fnIconBtn:disabled { color: @faint; }
QToolButton#fnToolBtn[popupMode="1"], QToolButton#primaryConvertBtn[popupMode="1"] { padding-right: 16px; }
QToolButton#fnToolBtn::menu-button { border: none; border-left: 1px solid @border; width: 14px; }
QToolButton#primaryConvertBtn::menu-button { border: none; border-left: 1px solid @on_accent; width: 14px; }
QFrame#functionBar QToolButton#primaryConvertBtn { padding: 4px 8px; padding-right: 16px; }
QToolButton#fnToolBtn::menu-indicator { image: none; width: 0px; }
QFrame#fnSep { color: @border_strong; margin: 6px 4px; }
QSpinBox#pageSpin { padding: 3px 2px; }
QSpinBox#pageSpin::up-button, QSpinBox#pageSpin::down-button { width: 0px; border: none; }  /* nút ▲▼ ẩn qua QSS: NoButtons + QSS làm ô nhập rộng 1 px */
QSpinBox#pageSpin::up-arrow, QSpinBox#pageSpin::down-arrow { image: none; width: 0px; }
QLabel#pageTotalLbl { color: @muted; padding: 0px 2px; }
QFrame#noticeBar { background-color: @accent_soft; border: none; border-bottom: 1px solid @border; }
QFrame#noticeBar QLabel { color: @text; background: transparent; }
QPushButton#linkBtn {
    background-color: transparent; color: @accent_text; border: none; padding: 2px 6px; font-weight: 600;
    text-decoration: underline;
}
QPushButton#linkBtn:hover { color: @accent; background-color: transparent; }
QToolButton#noticeClose { background-color: transparent; border: none; border-radius: 4px; padding: 3px; }
QToolButton#noticeClose:hover { background-color: @hover; }
QFrame#rightRail { background-color: @bar; border: none; border-left: 1px solid @border; }
QPushButton#railPanelBtn {
    background-color: transparent; border: 1px solid transparent; border-radius: 8px; padding: 0px;
}
QPushButton#railPanelBtn:hover { background-color: @hover; border-color: @border; }
QPushButton#railPanelBtn:checked { background-color: @accent_soft; border-color: @accent; }
QLineEdit#commandSearch {
    background-color: @card; border: 1px solid @border_strong; border-radius: 16px; padding: 6px 14px; color: @text;
}
QLineEdit#commandSearch:focus { border-color: @accent; }
QLabel#homeTitle { font-size: 28px; font-weight: 600; color: @text; }
QLabel#homeSubtitle { font-size: 14px; color: @muted; }
QFrame#homeHero {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 @hero1, stop:1 @hero2);
    border: 1px solid @border; border-radius: 14px;
}
QLabel#heroTitle { font-size: 16px; font-weight: 600; color: @text; }
QLabel#heroDesc { font-size: 13px; color: @muted; }
QFrame#ocrPopup { background-color: @card; border: 1px solid @border_strong; border-radius: 10px; }
QFrame#ocrPopup QLabel { color: @text; background: transparent; }
QLabel#sectionTitle { font-size: 17px; font-weight: 600; color: @text; }
QWidget#homeColumn { background: transparent; }
QDialog#whatsNewDialog QLabel { background: transparent; }
QLabel#whatsNewTitle { font-size: 20px; font-weight: 600; color: @text; }
QLabel#whatsNewSub { font-size: 13px; color: @muted; }
QScrollArea#whatsNewScroll, QWidget#whatsNewBody { background: transparent; }
QFrame#whatsNewItem { background-color: @card; border: 1px solid @border; border-radius: 10px; }
QLabel#whatsNewIcon { background-color: @accent_soft; border-radius: 8px; }
QLabel#whatsNewItemTitle { font-size: 14px; font-weight: 600; color: @text; }
QLabel#whatsNewItemText { font-size: 13px; color: @muted; }
QLabel#whatsNewKey { font-size: 11px; font-weight: 600; color: @muted; background-color: @page; border: 1px solid @border_strong; border-radius: 5px; padding: 1px 6px; }
QToolButton#whatsNewToggle { border: none; background: transparent; color: @muted; font-size: 13px; font-weight: 600; padding: 4px 2px; }
QToolButton#whatsNewToggle:hover { color: @text; }
QLabel#whatsNewOlderHead { font-size: 13px; font-weight: 600; color: @muted; padding-top: 4px; }
QLabel#homeHint { font-size: 12px; color: @muted; }
QPushButton#quickTile {
    background-color: @card; border: 1px solid @border; border-radius: 10px; color: @text;
    font-size: 13px; font-weight: 600; text-align: left; padding: 10px 14px;
}
QPushButton#quickTile:hover { border-color: @accent; background-color: @card_hover; }
QToolButton#homeIcon { background: transparent; border: none; }
QFrame#openFileCard { background-color: @page; border: 1px dashed @border_strong; border-radius: 12px; }
QFrame#openFileCard:hover { border-color: @accent; background-color: @accent_soft; }
QLabel#openFileTitle { font-size: 16px; font-weight: 600; color: @text; }
QPushButton#versionChip {
    font-size: 12px; font-weight: 600; color: @accent_text; background-color: @accent_soft;
    border: 1px solid transparent; border-radius: 9px; padding: 2px 10px; margin-bottom: 4px;
}
QPushButton#versionChip:hover { border-color: @accent; }
QFrame#recentBox { background-color: transparent; border: none; }
QFrame#recentRow { background-color: transparent; border: 1px solid transparent; border-radius: 10px; }
QFrame#recentRow:hover { background-color: @card; border-color: @border; }
QLabel#recentName { font-size: 14px; font-weight: 600; color: @text; }
QLabel#recentPath { font-size: 11px; color: @faint; }
QLabel#recentMeta { font-size: 12px; color: @muted; }
QLabel#privacyText { font-size: 12px; color: @muted; }
QLabel#mutedLabel { color: @muted; }
QLabel#dialogHeadline { font-size: 14px; color: @text; }
QLabel#toast {
    background-color: @toast_bg; color: @toast_text; border-radius: 10px; padding: 10px 16px; font-weight: 600;
}
QDialog#commandPalette { background-color: @card; border: 1px solid @border_strong; border-radius: 12px; }
QLineEdit#paletteInput { font-size: 15px; padding: 9px 12px; border-radius: 9px; }
QListWidget#paletteList { border: none; font-size: 13px; background-color: @card; }
QListWidget#paletteList::item { padding: 7px 8px; border-radius: 6px; }
QListWidget#paletteList::item:selected { background-color: @accent_soft; color: @text; }
QTableWidget { background-color: @card; gridline-color: @border; border: 1px solid @border; }
QFrame#editToolbar { background-color: @bar; border: none; border-bottom: 1px solid @border; }  /* hàng kiểu dáng */
QFrame#editToolbar QLabel { color: @text; }
QWidget#editToolbarBox { background-color: transparent; }
QFrame#editToolbar QLabel#mutedLabel { color: @muted; }
QPushButton#annotToolBtn {
    background-color: transparent; color: @text; border: 1px solid transparent; border-radius: 6px;
    padding: 3px 6px; min-width: 20px; font-size: 14px;
}
QPushButton#annotToolBtn:hover { background-color: @hover; border-color: @border; }
QPushButton#annotToolBtn:checked { background-color: @accent_soft; color: @accent_text; border-color: @accent; }
QPushButton#annotToolBtn:disabled { color: @faint; }
QListWidget#pageGrid { background-color: @page; border: 1px solid @border; border-radius: 10px; padding: 6px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0px; }
QScrollBar::handle:vertical { background: @border_strong; border-radius: 4px; min-height: 30px; margin: 2px; }
QScrollBar::handle:horizontal { background: @border_strong; border-radius: 4px; min-width: 30px; margin: 2px; }
QScrollBar::handle:hover { background: @faint; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0px; height: 0px; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QHeaderView::section {
    background-color: @page; color: @muted; border: none; border-bottom: 1px solid @border;
    padding: 6px; font-weight: 600;
}
QRadioButton, QCheckBox { spacing: 8px; }
QRadioButton::indicator, QCheckBox::indicator {
    width: 14px; height: 14px; border: 1px solid @faint; background-color: @indicator_bg;
}
QRadioButton::indicator { border-radius: 8px; }
QCheckBox::indicator { border-radius: 4px; }
QRadioButton::indicator:hover, QCheckBox::indicator:hover { border-color: @accent; background-color: @accent_soft; }
QRadioButton::indicator:checked {
    border-color: @accent;
    background-color: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
        stop:0 @on_accent, stop:0.42 @on_accent, stop:0.5 @accent, stop:1 @accent);
}
QRadioButton::indicator:checked:hover {
    background-color: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
        stop:0 @on_accent, stop:0.5 @on_accent, stop:0.58 @accent, stop:1 @accent);
}
QCheckBox::indicator:checked, QCheckBox::indicator:indeterminate {
    border-color: @accent; background-color: @accent; image: @check_icon;
}
QCheckBox::indicator:indeterminate { image: none; }
QRadioButton::indicator:disabled, QCheckBox::indicator:disabled { border-color: @border; background-color: @hover; }
QRadioButton::indicator:checked:disabled {
    border-color: @border_strong;
    background-color: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
        stop:0 @on_accent, stop:0.42 @on_accent, stop:0.5 @border_strong, stop:1 @border_strong);
}
QCheckBox::indicator:checked:disabled { border-color: @border_strong; background-color: @border_strong; }
QRadioButton:disabled, QCheckBox:disabled { color: @faint; }
"""


_CHECK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 14 14">'
    '<path d="M3 7.3 L5.8 10 L11 4.2" fill="none" stroke="{color}" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
)


def _check_icon(color: str) -> str:
    """Giá trị `image:` cho dấu ✔ của QCheckBox — tệp SVG ghi vào thư mục dữ liệu ứng dụng.

    QSS không nhận ảnh nhúng nên phải trỏ tới tệp; không ghi được thì trả `none`
    (ô đang chọn vẫn tô màu nhấn nên vẫn phân biệt được).
    """
    try:
        path = get_data_dir() / "theme" / f"check_{color.lstrip('#').lower()}.svg"
        svg = _CHECK_SVG.format(color=color)
        if not path.exists() or path.read_text(encoding="utf-8") != svg:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(svg, encoding="utf-8", newline="\n")
        return f'url("{path.as_posix()}")'
    except OSError:
        return "none"


def _shell_qss(tokens: dict) -> str:
    """Điền bảng màu vào mẫu QSS (thay `@ten_mau`, khoá dài thay trước để không đè khoá ngắn)."""
    out = _SHELL_TEMPLATE
    for key in sorted(tokens, key=len, reverse=True):
        out = out.replace("@" + key, tokens[key])
    # Đường dẫn tệp thay sau cùng để không bị thay nhầm khoá màu nằm trong đường dẫn
    return out.replace("@check_icon", _check_icon(tokens["on_accent"]))


_DARK_QSS = """
QMainWindow, QDialog, QWidget {
    background-color: #16181D;
    color: #E6E8EC;
    font-family: "Inter", "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}
QLabel, QCheckBox {
    background-color: transparent;
    color: #E6E8EC;
}
QMenuBar {
    background-color: #1C1F26;
    color: #E6E8EC;
    border-bottom: 1px solid #2A2E39;
    padding: 2px 6px;
}
QMenuBar::item:selected {
    background-color: #2D3340;
    border-radius: 4px;
}
QMenu {
    background-color: #20242D;
    color: #E6E8EC;
    border: 1px solid #343946;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #2563EB;
    color: #FFFFFF;
}
QToolBar {
    background-color: #1C1F26;
    border-bottom: 1px solid #2A2E39;
    spacing: 6px;
    padding: 6px 10px;
}
QPushButton, QToolButton {
    background-color: #252934;
    color: #E6E8EC;
    border: 1px solid #353B49;
    border-radius: 6px;
    padding: 5px 11px;
    font-weight: 500;
}
QPushButton:hover, QToolButton:hover {
    background-color: #2F3543;
    border-color: #4B5568;
}
QPushButton:pressed, QToolButton:pressed {
    background-color: #2563EB;
    border-color: #3B82F6;
    color: #FFFFFF;
}
QPushButton#primaryConvertBtn, QToolButton#primaryConvertBtn {
    background-color: #16A34A;
    color: #FFFFFF;
    border: 1px solid #22C55E;
    font-weight: 600;
    padding: 6px 14px;
}
QPushButton#primaryConvertBtn:hover, QToolButton#primaryConvertBtn:hover {
    background-color: #15803D;
}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {
    background-color: #121419;
    color: #F3F4F6;
    border: 1px solid #323744;
    border-radius: 6px;
    padding: 5px 8px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-color: #3B82F6;
}
QTabWidget::pane {
    border: 1px solid #2A2E39;
    background-color: #181A20;
}
QTabBar::tab {
    background-color: #1C1F26;
    color: #9CA3AF;
    border: 1px solid #2A2E39;
    border-bottom: none;
    padding: 7px 14px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    background-color: #262B36;
    color: #FFFFFF;
    font-weight: 600;
    border-bottom: 2px solid #3B82F6;
}
QListWidget, QTreeWidget {
    background-color: #14161B;
    color: #E6E8EC;
    border: 1px solid #2A2E39;
    border-radius: 5px;
    outline: none;
}
QListWidget::item:selected, QTreeWidget::item:selected {
    background-color: #2563EB;
    color: #FFFFFF;
}
QGroupBox {
    border: 1px solid #2E3442;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 10px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #60A5FA;
}
QProgressBar {
    background-color: #14161B;
    border: 1px solid #343946;
    border-radius: 5px;
    text-align: center;
    color: #FFFFFF;
    height: 20px;
}
QProgressBar::chunk {
    background-color: #16A34A;
    border-radius: 4px;
}
QStatusBar {
    background-color: #1C1F26;
    color: #9CA3AF;
    border-top: 1px solid #2A2E39;
}
"""


_LIGHT_QSS = """
QMainWindow, QDialog, QWidget {
    background-color: #F1F5F9;
    color: #0F172A;
    font-family: "Inter", "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}
QLabel, QCheckBox {
    background-color: transparent;
    color: #0F172A;
}
QMenuBar {
    background-color: #FFFFFF;
    color: #0F172A;
    border-bottom: 1px solid #E2E8F0;
    padding: 2px 6px;
}
QMenuBar::item:selected {
    background-color: #E2E8F0;
    border-radius: 4px;
}
QMenu {
    background-color: #FFFFFF;
    color: #0F172A;
    border: 1px solid #CBD5E1;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #2563EB;
    color: #FFFFFF;
}
QToolBar {
    background-color: #FFFFFF;
    border-bottom: 1px solid #E2E8F0;
    spacing: 6px;
    padding: 6px 10px;
}
QPushButton, QToolButton {
    background-color: #FFFFFF;
    color: #1E293B;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 5px 11px;
    font-weight: 500;
}
QPushButton:hover, QToolButton:hover {
    background-color: #F1F5F9;
    border-color: #94A3B8;
}
QPushButton:pressed, QToolButton:pressed {
    background-color: #2563EB;
    color: #FFFFFF;
}
QPushButton#primaryConvertBtn, QToolButton#primaryConvertBtn {
    background-color: #16A34A;
    color: #FFFFFF;
    border: 1px solid #15803D;
    font-weight: 600;
    padding: 6px 14px;
}
QPushButton#primaryConvertBtn:hover, QToolButton#primaryConvertBtn:hover {
    background-color: #15803D;
}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {
    background-color: #FFFFFF;
    color: #0F172A;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 5px 8px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-color: #2563EB;
}
QTabWidget::pane {
    border: 1px solid #E2E8F0;
    background-color: #F8FAFC;
}
QTabBar::tab {
    background-color: #F1F5F9;
    color: #475569;
    border: 1px solid #CBD5E1;
    border-bottom: none;
    padding: 7px 14px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    background-color: #FFFFFF;
    color: #0F172A;
    font-weight: 600;
    border-bottom: 2px solid #2563EB;
}
QListWidget, QTreeWidget {
    background-color: #FFFFFF;
    color: #1E293B;
    border: 1px solid #E2E8F0;
    border-radius: 5px;
    outline: none;
}
QListWidget::item:selected, QTreeWidget::item:selected {
    background-color: #2563EB;
    color: #FFFFFF;
}
QGroupBox {
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 10px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #1D4ED8;
}
QProgressBar {
    background-color: #E2E8F0;
    border: 1px solid #CBD5E1;
    border-radius: 5px;
    text-align: center;
    color: #0F172A;
    height: 20px;
}
QProgressBar::chunk {
    background-color: #16A34A;
    border-radius: 4px;
}
QStatusBar {
    background-color: #FFFFFF;
    color: #475569;
    border-top: 1px solid #E2E8F0;
}
"""
