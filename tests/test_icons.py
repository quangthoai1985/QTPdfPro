"""Bộ biểu tượng Lucide và ui/icons.py."""

from __future__ import annotations

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QPushButton

from qtpdfpro.ui import icons


def _has_pixel_near(img: QImage, color: QColor, tol: int = 40) -> bool:
    for y in range(img.height()):
        for x in range(img.width()):
            px = img.pixelColor(x, y)
            if (
                px.alpha() > 128
                and abs(px.red() - color.red()) <= tol
                and abs(px.green() - color.green()) <= tol
                and abs(px.blue() - color.blue()) <= tol
            ):
                return True
    return False


def test_every_icon_name_has_svg():
    for name in icons.ICON_NAMES:
        assert icons.icon_path(name).is_file(), name
    assert (icons.ICON_DIR / "LICENSE-lucide.txt").is_file()


def test_icon_renders_in_theme_color_and_rebinds(qapp):
    icons.set_icon_color("#E6E8EC")
    btn = QPushButton()
    icons.bind(btn, "search")
    img = btn.icon().pixmap(18, 18).toImage()
    assert _has_pixel_near(img, QColor("#E6E8EC"))
    icons.set_icon_color("#0F172A")
    assert _has_pixel_near(btn.icon().pixmap(18, 18).toImage(), QColor("#0F172A"))
    icons.set_icon_color("#E6E8EC")


def test_destroyed_button_does_not_break_recolor(qapp):
    btn = QPushButton()
    icons.bind(btn, "search")
    btn.deleteLater()
    del btn
    from PySide6.QtCore import QCoreApplication, QEvent

    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    icons.set_icon_color("#123456")
    icons.set_icon_color("#E6E8EC")


def test_missing_icon_returns_null_icon(qapp, caplog):
    assert icons.icon("khong-co-bieu-tuong-nay").isNull()
