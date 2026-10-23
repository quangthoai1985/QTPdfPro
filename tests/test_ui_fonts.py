"""Phông giao diện Inter (giống PdfCraft): tệp đi kèm đủ chữ tiếng Việt, nạp vào Qt, QSS và cửa sổ dùng Inter."""

from __future__ import annotations

import unicodedata

import pymupdf
import pytest
from PySide6.QtCore import QEvent
from PySide6.QtGui import QFont, QFontDatabase, QFontInfo
from PySide6.QtWidgets import QApplication, QLabel

from qtpdfpro.core.settings import AppSettings
from qtpdfpro.ui import theme
from qtpdfpro.ui.home_page import CatalogRow
from qtpdfpro.ui.main_window import MainWindow
from qtpdfpro.ui.tool_catalog import TOOLS


def _vietnamese_letters() -> set[str]:
    letters = set("đĐ")
    for base in "aăâeêioôơuưyAĂÂEÊIOÔƠUƯY":
        letters.add(base)
        for mark in "̣̀́̃̉":  # huyền, sắc, ngã, hỏi, nặng
            letters.add(unicodedata.normalize("NFC", base + mark))
    return letters


@pytest.fixture()
def ui_fonts():
    """Nạp Inter cho một bài rồi gỡ ra, để các bài GUI khác vẫn chạy với phông như trước."""
    app = QApplication.instance() or QApplication([])
    original = QFont(app.font())
    loaded = theme.install_ui_fonts(app)
    yield app, loaded
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    app.setFont(original)
    for font_id in theme._ui_font_ids:
        QFontDatabase.removeApplicationFont(font_id)
    theme._ui_font_ids.clear()


def test_inter_font_files_cover_vietnamese() -> None:
    letters = _vietnamese_letters()
    assert len(letters) == 146
    for name in theme.UI_FONT_FILES:
        path = theme.FONT_DIR / name
        assert path.is_file(), name
        font = pymupdf.Font(fontfile=str(path))
        missing = sorted(ch for ch in letters | set("«»–—…“”") if not font.has_glyph(ord(ch)))
        assert missing == [], (name, missing)
    # Giấy phép SIL OFL phải đi kèm tệp phông (build.bat chép cả thư mục vào bản đóng gói)
    assert "SIL Open Font License" in (theme.FONT_DIR / "OFL-Inter.txt").read_text(encoding="utf-8")


def test_install_ui_fonts_sets_inter_without_hinting(ui_fonts) -> None:
    app, loaded = ui_fonts
    assert loaded is True
    assert {"Regular", "Medium", "SemiBold", "Bold"} <= set(QFontDatabase.styles(theme.UI_FONT_FAMILY))
    font = app.font()
    assert font.families()[:2] == [theme.UI_FONT_FAMILY, "Segoe UI"]
    assert font.hintingPreference() == QFont.HintingPreference.PreferNoHinting
    # Gọi lại không nạp trùng tệp phông
    theme.install_ui_fonts(app)
    assert len(theme._ui_font_ids) == len(theme.UI_FONT_FILES)


def test_stylesheets_use_inter_and_semibold() -> None:
    for name in ("light", "dark"):
        qss = theme.get_stylesheet(name)
        assert 'font-family: "Inter", "Segoe UI"' in qss
        # PdfCraft không dùng chữ Bold ở khung giao diện: tiêu đề, nhãn tối đa SemiBold
        assert "font-weight: 700" not in qss


def test_main_window_renders_with_inter(ui_fonts, sample_vietnamese_pdf) -> None:
    app, _ = ui_fonts
    win = MainWindow(settings=AppSettings.load())
    win.show()
    app.processEvents()

    title = win.findChild(QLabel, "homeTitle")
    info = QFontInfo(title.font())
    assert info.family() == theme.UI_FONT_FAMILY
    assert info.weight() == 600
    # QSS chỉ đặt họ / cỡ / độ đậm — lựa chọn «không nắn nét» vẫn kế thừa từ phông ứng dụng
    assert title.font().hintingPreference() == QFont.HintingPreference.PreferNoHinting

    # Inter rộng hơn Segoe UI một chút: cửa sổ đang xem tài liệu vẫn vừa màn hình 1400 px
    assert win.open_pdf_path(sample_vietnamese_pdf) is not None
    app.processEvents()
    assert win.minimumSizeHint().width() <= 1400
    win.close()
    win.deleteLater()


def test_catalog_row_elides_long_name_keeps_soon_badge(ui_fonts) -> None:
    app, _ = ui_fonts
    tool = max((t for t in TOOLS if not t.ready), key=lambda t: len(t.name))
    row = CatalogRow(tool)
    row.resize(200, row.sizeHint().height())
    row.show()
    app.processEvents()

    badge = row.findChild(QLabel, "soonBadgeSmall")
    name = row.findChild(QLabel, "catalogRowNameSoon")
    assert badge.isVisible() and badge.geometry().right() < row.width()
    assert name.text() == tool.name  # chỉ rút gọn khi vẽ
    assert row.minimumSizeHint().width() < 200
    row.close()
    row.deleteLater()
