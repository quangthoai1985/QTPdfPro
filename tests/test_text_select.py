"""Kiểm thử công cụ «Chọn chữ» (như Acrobat): lõi `core/text_select.py`, lệnh `cli text`, công cụ chuột trên khung
đọc (kéo chọn, khung, nhấp đúp, Ctrl+C, menu chuột phải), chuyển Chọn ↔ Bàn tay, giữ Space để kéo cuộn, và nhận
dạng vùng trên trang ảnh quét (engine OCR giả — không cần bộ mô hình 88 MB)."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
import pytest
from PySide6.QtCore import QEvent, QObject, QPointF, Qt, Signal
from PySide6.QtGui import QGuiApplication, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

from qtpdfpro import cli
from qtpdfpro.core import text_select as ts
from qtpdfpro.core.font_resolver import _TCVN3_TO_UNICODE
from qtpdfpro.core.ocr import OcrLine
from qtpdfpro.core.settings import AppSettings
from qtpdfpro.ui.main_window import MainWindow

LEFT = Qt.MouseButton.LeftButton


# ─── Tiện ích ──────────────────────────────────────────────────────────────


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _mouse(widget, kind, pos: QPointF, button=LEFT, buttons=LEFT, mods=Qt.KeyboardModifier.NoModifier) -> None:
    gpos = QPointF(widget.mapToGlobal(pos.toPoint()))
    QApplication.sendEvent(widget, QMouseEvent(kind, pos, gpos, button, buttons, mods))


def _drag(viewer, page: int, p0, p1, steps: int = 4, mods=Qt.KeyboardModifier.NoModifier) -> None:
    surface = viewer.widget()
    t = viewer.page_transform(page)
    a, b = t.map(QPointF(*p0)), t.map(QPointF(*p1))
    _mouse(surface, QEvent.Type.MouseButtonPress, a, mods=mods)
    for i in range(1, steps + 1):
        q = QPointF(a.x() + (b.x() - a.x()) * i / steps, a.y() + (b.y() - a.y()) * i / steps)
        _mouse(surface, QEvent.Type.MouseMove, q, LEFT, LEFT, mods)
    _mouse(surface, QEvent.Type.MouseButtonRelease, b, LEFT, Qt.MouseButton.NoButton, mods)


def _key(widget, key, mods=Qt.KeyboardModifier.NoModifier, release: bool = False) -> None:
    kind = QEvent.Type.KeyRelease if release else QEvent.Type.KeyPress
    QApplication.sendEvent(widget, QKeyEvent(kind, key, mods))


def _font_kwargs() -> dict:
    font = Path(r"C:\Windows\Fonts\times.ttf")
    return {"fontname": "tnr", "fontfile": str(font)} if font.exists() else {"fontname": "helv"}


def _text_pdf(path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    kw = _font_kwargs()
    page.insert_text((72, 100), "Cộng hoà xã hội chủ nghĩa Việt Nam", fontsize=14, **kw)
    page.insert_text((72, 130), "Độc lập - Tự do - Hạnh phúc", fontsize=14, **kw)
    page.insert_text((300, 400), "Ô bảng một", fontsize=11, **kw)
    page.insert_text((300, 420), "Ô bảng hai", fontsize=11, **kw)
    doc.new_page(width=595, height=842).insert_text((72, 100), "Trang hai", fontsize=14, **kw)
    doc.save(str(path))
    doc.close()
    return path


def _scanned_pdf(path: Path) -> Path:
    """PDF ảnh quét: trang chữ kết xuất thành ảnh rồi chèn vào trang mới (không còn lớp chữ)."""
    src = fitz.open()
    p = src.new_page(width=595, height=842)
    p.insert_text((72, 200), "Văn bản quét thử nghiệm", fontsize=20, **_font_kwargs())
    p.draw_rect(fitz.Rect(72, 300, 200, 330), color=None, fill=(0, 0, 0))  # khối mực để engine giả «đọc»
    pix = p.get_pixmap(dpi=150)
    doc = fitz.open()
    doc.new_page(width=595, height=842).insert_image(fitz.Rect(0, 0, 595, 842), pixmap=pix)
    doc.save(str(path))
    doc.close()
    src.close()
    return path


class _InkEngine:
    """Engine OCR giả: một «dòng» bao quanh vùng mực đậm của ảnh — đủ để kiểm phép đổi toạ độ ↔ trang."""

    def __init__(self, text: str = "Văn bản quét thử nghiệm") -> None:
        self.text = text
        self.calls = 0

    def ocr_image(self, rgb: np.ndarray, zoom: float, clean_ink: bool = True):
        self.calls += 1
        ys, xs = np.where(rgb.mean(axis=2) < 60)
        if ys.size == 0:
            return []
        box = (xs.min() / zoom, ys.min() / zoom, (xs.max() + 1) / zoom, (ys.max() + 1) / zoom)
        return [OcrLine(self.text, box), OcrLine("dòng thứ hai", (box[0], box[3] + 4, box[2], box[3] + 20))]


class _Models(QObject):
    """Thay `OcrModelController`: lần đầu «chưa cài» → phát `finished` khi test gọi `finish()`."""

    progress = Signal(int, int)
    finished = Signal(bool, str)

    def __init__(self, installed: bool) -> None:
        super().__init__()
        self.installed = installed
        self.started = 0
        self.done_bytes, self.total_bytes = 0, 100

    def ensure_started(self) -> bool:
        if not self.installed:
            self.started += 1
        return self.installed

    def finish(self) -> None:
        self.installed = True
        self.progress.emit(100, 100)
        self.finished.emit(True, "")


def _open(app, pdf: Path, settings: AppSettings | None = None):
    win = MainWindow(settings=settings or AppSettings.load())
    win.resize(1400, 900)
    win.show()
    app.processEvents()
    tab = win.open_pdf_path(pdf)
    assert tab is not None
    tab.viewer.set_zoom_mode("percent", 100)
    tab.viewer.go_to_page(0)
    for _ in range(3):
        app.processEvents()
    return win, tab


# ─── Lõi ───────────────────────────────────────────────────────────────────


def test_select_range_area_word_line(tmp_path: Path) -> None:
    with fitz.open(_text_pdf(tmp_path / "a.pdf")) as doc:
        words = ts.page_words(doc[0])
        assert words[0][4] == "Cộng"
        assert ts.near_text(words, (80, 96)) and not ts.near_text(words, (500, 700))
        rng = ts.select_range(words, (73, 96), (110, 126))
        assert ts.selection_text(rng) == "Cộng hoà xã hội chủ nghĩa Việt Nam\nĐộc lập"
        assert len(ts.selection_rects(rng)) == 2
        area = ts.select_area(words, fitz.Rect(290, 380, 420, 425))
        assert ts.selection_text(area) == "Ô bảng một\nÔ bảng hai"
        assert [w[4] for w in ts.select_word(words, (80, 96))] == ["Cộng"]
        assert ts.selection_text(ts.select_line(words, (80, 126))) == "Độc lập - Tự do - Hạnh phúc"
        assert ts.select_word(words, (500, 700)) == []


def test_lines_to_text_joins_wrapped_lines_into_paragraphs() -> None:
    L = ts.TextLine
    lines = [
        L(fitz.Rect(100, 100, 520, 114), "Căn cứ Luật Tổ chức chính quyền địa phương ngày 19 tháng"),  # thụt đầu dòng
        L(fitz.Rect(72, 118, 520, 132), "02 năm 2025;"),
        L(fitz.Rect(100, 136, 520, 150), "Căn cứ Nghị định số 30/2020/NĐ-CP ngày 05 tháng 3 năm 2020"),
        L(fitz.Rect(72, 154, 300, 168), "của Chính phủ về công tác văn thư;"),  # dòng ngắn → hết đoạn
        L(fitz.Rect(72, 172, 520, 186), "Điều 1. Ban hành kèm theo Quyết định này Quy chế ứng dụng công nghệ"),
        L(fitz.Rect(72, 190, 520, 204), "số trong quản lý văn bản."),
        L(fitz.Rect(72, 208, 520, 222), "- Gạch đầu dòng là một đoạn riêng"),
    ]
    assert ts.lines_to_text(lines).count("\n") == 6
    joined = ts.lines_to_text(lines, join_lines=True)
    assert joined.split("\n") == [
        "Căn cứ Luật Tổ chức chính quyền địa phương ngày 19 tháng 02 năm 2025;",
        "Căn cứ Nghị định số 30/2020/NĐ-CP ngày 05 tháng 3 năm 2020 của Chính phủ về công tác văn thư;",
        "Điều 1. Ban hành kèm theo Quyết định này Quy chế ứng dụng công nghệ số trong quản lý văn bản.",
        "- Gạch đầu dòng là một đoạn riêng",
    ]


def test_tcvn3_font_words_copied_as_unicode() -> None:
    """PDF cũ gõ bằng phông `.VnTime` (bảng mã TCVN3): chép ra phải là Unicode, không phải «Céng hoµ x· héi»."""
    inverse = {u: t for t, u in _TCVN3_TO_UNICODE.items()}
    legacy = "".join(inverse.get(ch, ch) for ch in "Cộng hoà xã hội")
    assert legacy == "Céng hoµ x· héi"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), legacy, fontsize=14, fontname="helv")  # phông đơn, mã WinAnsi như PDF TCVN3 thật
    for font in page.get_fonts():
        doc.xref_set_key(font[0], "BaseFont", "/.VnTime")
    page = doc.reload_page(page)
    assert [w[4] for w in ts.page_words(page)] == ["Cộng", "hoà", "xã", "hội"]


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("view", [0, 90])
def test_render_region_maps_pixels_back_to_page(rotation: int, view: int) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    target = fitz.Rect(120, 300, 220, 330)
    page.draw_rect(target, color=None, fill=(0, 0, 0))
    page.set_rotation(rotation)
    region = ts.render_region(page, fitz.Rect(100, 280, 300, 360), dpi=144, view_rotation=view)
    assert min(region.rgb.shape[:2]) >= ts.REGION_MIN_SIDE_PX  # đệm cho bộ dò dòng
    res = ts.recognize_region(_InkEngine(), region)
    assert res.text() == "Văn bản quét thử nghiệm\ndòng thứ hai"
    back = res.page_rects[0]
    assert all(abs(a - b) < 0.6 for a, b in zip(back, target))
    png = ts.region_png(region)
    assert fitz.Pixmap(png).width == region.size[0]


def test_is_scanned_page(tmp_path: Path) -> None:
    with fitz.open(_scanned_pdf(tmp_path / "s.pdf")) as doc:
        assert ts.is_scanned_page(doc[0]) is True
    with fitz.open(_text_pdf(tmp_path / "t.pdf")) as doc:
        assert ts.is_scanned_page(doc[0]) is False


def test_cli_text_rect_and_join(tmp_path: Path) -> None:
    pdf = _text_pdf(tmp_path / "c.pdf")
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert cli.main(["text", str(pdf), "--rect", "60,80,560,140", "--json"]) == 0
    data = json.loads(buf.getvalue())
    assert data["mode"] == "text"
    assert data["text"] == "Cộng hoà xã hội chủ nghĩa Việt Nam\nĐộc lập - Tự do - Hạnh phúc"
    assert len(data["lines"]) == 2
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert cli.main(["text", str(pdf), "--page", "2"]) == 0
    assert buf.getvalue().strip() == "Trang hai"


# ─── Giao diện ─────────────────────────────────────────────────────────────


def test_select_mode_drag_copy_double_click_and_context_menu(tmp_path: Path) -> None:
    app = _app()
    win, tab = _open(app, _text_pdf(tmp_path / "ui.pdf"))
    viewer, tool = tab.viewer, tab.text_select
    assert tab.pointer_mode == "select" and viewer.interaction is tool
    assert tab.pointer_btns["select"].isChecked()

    # Kéo từ chữ «Cộng» tới giữa dòng 2 → chọn theo thứ tự đọc
    _drag(viewer, 0, (73, 96), (110, 126))
    assert tool.selection_page == 0
    assert tool.selected_text() == "Cộng hoà xã hội chủ nghĩa Việt Nam\nĐộc lập"
    _key(viewer.widget(), Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert QGuiApplication.clipboard().text() == "Cộng hoà xã hội chủ nghĩa Việt Nam\nĐộc lập"
    _key(viewer.widget(), Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    assert QGuiApplication.clipboard().text() == "Cộng hoà xã hội chủ nghĩa Việt Nam Độc lập"

    # Kéo từ chỗ trống → khung chữ nhật chỉ lấy hai ô
    _drag(viewer, 0, (290, 380), (420, 425))
    assert tool.selected_text() == "Ô bảng một\nÔ bảng hai"

    # Nhấp đúp = một từ; Esc bỏ chọn
    surface = viewer.widget()
    pos = viewer.page_transform(0).map(QPointF(80, 96))
    _mouse(surface, QEvent.Type.MouseButtonPress, pos)
    _mouse(surface, QEvent.Type.MouseButtonRelease, pos, LEFT, Qt.MouseButton.NoButton)
    _mouse(surface, QEvent.Type.MouseButtonDblClick, pos)
    _mouse(surface, QEvent.Type.MouseButtonRelease, pos, LEFT, Qt.MouseButton.NoButton)
    assert tool.selected_text() == "Cộng"
    _key(surface, Qt.Key.Key_Escape)
    assert not tool.has_selection

    # Ctrl+A → cả trang; menu chuột phải → Tô sáng vùng chọn thành chú thích
    _key(surface, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert "Ô bảng hai" in tool.selected_text()
    _drag(viewer, 0, (73, 126), (200, 126))
    menu = tool.build_context_menu(0)
    actions = {a.text().split("\t")[0]: a for a in menu.actions() if a.text()}
    assert actions["📋 Sao chép"].isEnabled()
    assert actions["🖼 Sao chép ảnh vùng chọn"].isEnabled()
    actions["🖍 Tô sáng vùng chọn"].trigger()
    app.processEvents()
    annots = tab.annot_controller.session.list_annotations()
    assert [a.subtype for a in annots] == ["Highlight"] and annots[0].content.startswith("Độc lập")
    assert not tool.has_selection
    tab.annot_controller.session.undo()
    win.close()
    app.processEvents()


def test_switch_hand_mode_persists_and_space_pans(tmp_path: Path) -> None:
    app = _app()
    pdf = _text_pdf(tmp_path / "hand.pdf")
    win, tab = _open(app, pdf)
    viewer = tab.viewer
    tab.pointer_btns["hand"].click()
    assert win.settings.pointer_mode == "hand" and AppSettings.load().pointer_mode == "hand"
    assert viewer.interaction is None and tab.pointer_btns["hand"].isChecked()
    assert win.pointer_actions["hand"].isChecked()

    # Chế độ chỉnh sửa dùng V/H cho công cụ khác → phím chọn chế độ con trỏ tắt; thoát thì về Bàn tay
    tab.enter_edit_mode()
    assert tab.edit_mode and not tab.pointer_btns["select"].isEnabled()
    assert not any(sc.isEnabled() for sc in tab._pointer_shortcuts)
    tab.exit_edit_mode()
    assert viewer.interaction is None and all(sc.isEnabled() for sc in tab._pointer_shortcuts)

    win.set_pointer_mode("select")
    assert viewer.interaction is tab.text_select
    # Giữ Space + kéo → cuộn trang, không chọn chữ
    viewer.set_zoom_mode("percent", 200)
    app.processEvents()
    bar = viewer.verticalScrollBar()
    bar.setValue(200)
    surface = viewer.widget()
    surface.setFocus()
    _key(surface, Qt.Key.Key_Space)
    assert viewer._space_pan
    before = bar.value()
    _drag(viewer, 0, (100, 300), (100, 200), steps=3)
    assert bar.value() > before
    assert not tab.text_select.has_selection
    _key(surface, Qt.Key.Key_Space, release=True)
    assert not viewer._space_pan
    win.close()
    app.processEvents()

    # Mở lại: nhớ chế độ đã chọn
    settings = AppSettings.load()
    settings.pointer_mode = "hand"
    win2, tab2 = _open(app, pdf, settings)
    assert tab2.pointer_mode == "hand" and tab2.viewer.interaction is None
    win2.close()
    app.processEvents()


def test_scanned_page_drag_recognizes_region(tmp_path: Path) -> None:
    app = _app()
    win, tab = _open(app, _scanned_pdf(tmp_path / "scan.pdf"))
    tool = tab.text_select
    engine = _InkEngine()
    tool.engine_factory = lambda: engine
    models = _Models(installed=False)
    tool.models_provider = lambda: models
    assert tool.is_scanned(0)

    # Lần đầu: chưa có mô hình → chờ tải, xong tự nhận dạng
    _drag(tab.viewer, 0, (60, 290), (215, 340))
    assert models.started == 1 and tool.ocr_busy and engine.calls == 0
    assert tool.popup is not None and tool.popup.isVisible()
    models.finish()
    tool.wait_ocr()
    assert engine.calls == 1
    res = tool.ocr_result
    assert res is not None and res.text() == "Văn bản quét thử nghiệm\ndòng thứ hai"
    assert all(abs(a - b) < 2.5 for a, b in zip(res.page_rects[0], (72, 300, 200, 330)))
    assert QGuiApplication.clipboard().text() == "Văn bản quét thử nghiệm\ndòng thứ hai"
    assert tool.popup.text_edit.toPlainText() == "Văn bản quét thử nghiệm\ndòng thứ hai"

    # Bật «Nối dòng thành đoạn» trong bong bóng; người dùng sửa chữ rồi Ctrl+C → lấy chữ đã sửa
    tool.popup.chk_join.setChecked(True)
    assert tool.popup.text_edit.toPlainText() == "Văn bản quét thử nghiệm dòng thứ hai"
    tool.popup.text_edit.setPlainText("Văn bản đã sửa")
    _key(tab.viewer.widget(), Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert QGuiApplication.clipboard().text() == "Văn bản đã sửa"

    # Lần sau: mô hình đã có → nhận dạng ngay; khung trống → báo không thấy chữ
    _drag(tab.viewer, 0, (400, 600), (500, 700))
    tool.wait_ocr()
    assert tool.ocr_result is None
    assert "Không thấy chữ" in tool.popup.title_lbl.text()
    menu = tool.build_context_menu(0)
    assert any(a.text().startswith("🔤 Nhận dạng chữ cả trang") for a in menu.actions())
    win.close()
    app.processEvents()
