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


def test_order_by_columns_reads_left_column_first() -> None:
    """Phần đầu văn bản hành chính 2 cột: chép ra hết cột cơ quan rồi mới tới Quốc hiệu, không xen từng hàng;
    phần thân một cột bên dưới giữ thứ tự trên → dưới."""
    R = fitz.Rect
    rects = [
        R(60, 40, 260, 54),    # 0 ỦY BAN NHÂN DÂN TỈNH AN   (trái, hàng 1)
        R(320, 40, 560, 54),   # 1 CỘNG HÒA XÃ HỘI…          (phải, hàng 1)
        R(130, 58, 190, 72),   # 2 GIANG                     (trái, hàng 2)
        R(380, 58, 500, 72),   # 3 VIỆT NAM                  (phải, hàng 2)
        R(70, 76, 250, 90),    # 4 SỞ GIÁO DỤC…              (trái, hàng 3)
        R(340, 76, 540, 90),   # 5 Độc lập - Tự do…          (phải, hàng 3)
        R(60, 130, 540, 144),  # 6 thân bài dòng 1 (cả bề ngang)
        R(60, 148, 300, 162),  # 7 thân bài dòng 2
    ]
    assert ts.order_by_columns(rects) == [0, 2, 4, 1, 3, 5, 6, 7]
    # Một cột có thụt đầu dòng: không bị tách thành hai cột
    body = [R(100, 10, 520, 24), R(72, 28, 520, 42), R(72, 46, 300, 60)]
    assert ts.order_by_columns(body) == [0, 1, 2]


_INSTALLED_BUNDLE = None
try:  # conftest đổi QT_PDF_PRO_DATA sang thư mục tạm khi chạy → tìm bộ mô hình thật lúc nạp module
    from qtpdfpro.core import ocr_models as _ocr_models

    _INSTALLED_BUNDLE = _ocr_models.find_bundle()
except Exception:
    pass


@pytest.mark.skipif(_INSTALLED_BUNDLE is None, reason="chưa cài bộ mô hình OCR (ocr --install)")
def test_real_models_recognize_scanned_region(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Chạy mô hình thật: bản scan 200 dpi của hai cột + một đoạn → đọc đúng chữ, đúng thứ tự cột."""
    from qtpdfpro.core import ocr_models
    from qtpdfpro.core.ocr import OcrEngine

    monkeypatch.setenv(ocr_models.MODELS_ENV, str(_INSTALLED_BUNDLE.root))
    src = fitz.open()
    p = src.new_page(width=595, height=842)
    kw = _font_kwargs()
    p.insert_text((70, 80), "ỦY BAN NHÂN DÂN", fontsize=13, **kw)
    p.insert_text((70, 98), "XÃ VĨNH TẾ", fontsize=13, **kw)
    p.insert_text((330, 80), "CỘNG HÒA XÃ HỘI CHỦ NGHĨA", fontsize=13, **kw)
    p.insert_text((350, 98), "Độc lập - Tự do - Hạnh phúc", fontsize=13, **kw)
    p.insert_text((72, 200), "Căn cứ Luật Tổ chức chính quyền địa phương ngày 19 tháng 02 năm 2025;", fontsize=13, **kw)
    pix = p.get_pixmap(dpi=200)
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, pixmap=pix)
    assert ts.is_scanned_page(page)
    engine = OcrEngine.load()
    head = ts.recognize_region(engine, ts.render_region(page, fitz.Rect(50, 60, 560, 110)))
    assert head.text().split("\n") == ["ỦY BAN NHÂN DÂN", "XÃ VĨNH TẾ", "CỘNG HÒA XÃ HỘI CHỦ NGHĨA",
                                       "Độc lập - Tự do - Hạnh phúc"]
    body = ts.recognize_region(engine, ts.render_region(page, fitz.Rect(60, 180, 560, 210)))
    assert body.text() == "Căn cứ Luật Tổ chức chính quyền địa phương ngày 19 tháng 02 năm 2025;"
    assert body.page_rects[0].intersects(fitz.Rect(72, 186, 540, 204))


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
    assert win.function_bar.btn_pointer_select.isChecked()

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
    win.function_bar.btn_pointer_hand.click()  # nút «Bàn tay» ở cụm điều khiển xem của tầng 2
    assert win.settings.pointer_mode == "hand" and AppSettings.load().pointer_mode == "hand"
    assert viewer.interaction is None and win.function_bar.btn_pointer_hand.isChecked()
    assert not win.function_bar.btn_pointer_select.isChecked()
    assert win.pointer_actions["hand"].isChecked()

    # Chế độ chỉnh sửa dùng V/H cho công cụ khác → phím chọn chế độ con trỏ tắt; thoát thì về Bàn tay
    tab.enter_edit_mode()
    assert tab.edit_mode
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


# ─── Hoàn thiện: chọn liền nhiều trang, bong bóng không che chữ, danh mục công cụ ─────────────


def _multi_pdf(path: Path) -> Path:
    doc = fitz.open()
    kw = _font_kwargs()
    for lines in (["Trang một dòng đầu", "trang một dòng cuối"],
                  ["Trang hai dòng đầu", "trang hai dòng cuối"],
                  ["Trang ba dòng đầu", "trang ba dòng cuối"]):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), lines[0], fontsize=14, **kw)
        page.insert_text((72, 760), lines[1], fontsize=14, **kw)
    doc.save(str(path))
    doc.close()
    return path


def test_select_pages_range_and_join_page_texts(tmp_path: Path) -> None:
    with fitz.open(_multi_pdf(tmp_path / "m.pdf")) as doc:
        words = {i: ts.page_words(doc[i]) for i in range(3)}
        words_of = lambda i: words.get(i, [])  # noqa: E731
        sel = ts.select_pages_range(words_of, 0, (140, 755), 2, (110, 96))  # «dòng cuối» trang 1 → «Trang ba»
        assert sorted(sel) == [0, 1, 2]
        assert ts.selection_text(sel[0]) == "dòng cuối"
        assert ts.selection_text(sel[1]) == "Trang hai dòng đầu\ntrang hai dòng cuối"
        assert ts.selection_text(sel[2]) == "Trang ba"
        # Kéo ngược (từ trang sau lên trang trước) cho cùng kết quả; trang không có chữ bị bỏ qua
        assert ts.select_pages_range(words_of, 2, (110, 96), 0, (140, 755)) == sel
        words[1] = []
        assert sorted(ts.select_pages_range(words_of, 0, (140, 755), 2, (110, 96))) == [0, 2]
    assert ts.join_page_texts(["Căn cứ Luật tổ chức", "chính quyền địa phương;"]) == \
        "Căn cứ Luật tổ chức\nchính quyền địa phương;"
    assert ts.join_page_texts(["Căn cứ Luật tổ chức", "chính quyền địa phương;"], True) == \
        "Căn cứ Luật tổ chức chính quyền địa phương;"
    assert ts.join_page_texts(["Hết điều 1.", "điều 2"], True) == "Hết điều 1.\nđiều 2"
    assert ts.join_page_texts(["", "  ", "Một"], True) == "Một"


def test_drag_and_shift_click_select_across_pages(tmp_path: Path) -> None:
    app = _app()
    win, tab = _open(app, _multi_pdf(tmp_path / "ui_multi.pdf"))
    viewer, tool = tab.viewer, tab.text_select
    surface = viewer.widget()
    # Kéo từ «dòng cuối» trang 1 sang «Trang hai» trang 2 (bước giữa rơi vào khe giữa hai trang)
    a = viewer.page_transform(0).map(QPointF(140, 755))
    b = viewer.page_transform(1).map(QPointF(110, 96))
    _mouse(surface, QEvent.Type.MouseButtonPress, a)
    gap_y = (viewer.page_transform(0).map(QPointF(0, 842)).y() + viewer.page_transform(1).map(QPointF(0, 0)).y()) / 2
    _mouse(surface, QEvent.Type.MouseMove, QPointF(a.x(), gap_y), LEFT, LEFT)
    assert tool.selection_pages == [0]  # trong khe giữa hai trang: tới hết trang 1
    assert tool.selected_text() == "dòng cuối"
    _mouse(surface, QEvent.Type.MouseMove, b, LEFT, LEFT)
    _mouse(surface, QEvent.Type.MouseButtonRelease, b, LEFT, Qt.MouseButton.NoButton)
    assert tool.selection_pages == [0, 1]
    assert tool.selected_text() == "dòng cuối\nTrang hai"
    _key(surface, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert QGuiApplication.clipboard().text() == "dòng cuối\nTrang hai"

    # Shift+nhấp trên trang 3 → mở rộng từ điểm đầu (trang 1) sang trang 3
    c = viewer.page_transform(2).map(QPointF(112, 96))
    _mouse(surface, QEvent.Type.MouseButtonPress, c, mods=Qt.KeyboardModifier.ShiftModifier)
    _mouse(surface, QEvent.Type.MouseButtonRelease, c, LEFT, Qt.MouseButton.NoButton, Qt.KeyboardModifier.ShiftModifier)
    assert tool.selection_pages == [0, 1, 2]
    assert tool.selected_text().split("\n") == ["dòng cuối", "Trang hai dòng đầu", "trang hai dòng cuối", "Trang ba"]
    assert len(tool.selection_rects(1)) == 2 and tool.selection_rects(5) == []

    # Menu chuột phải: ảnh vùng chọn chỉ cho một trang; tô sáng → chú thích trên cả ba trang
    menu = tool.build_context_menu(2)
    actions = {a.text().split("\t")[0]: a for a in menu.actions() if a.text()}
    assert not actions["🖼 Sao chép ảnh vùng chọn"].isEnabled()
    actions["🖍 Tô sáng vùng chọn"].trigger()
    app.processEvents()
    pages = sorted({a.page_index for a in tab.annot_controller.session.list_annotations()})
    assert pages == [0, 1, 2]
    win.close_tab_at(0, force=True)  # tô sáng chưa lưu: đóng thẳng, không bật hộp thoại «Lưu thay đổi?» thật
    win.close()
    app.processEvents()


def test_viewer_page_near_covers_gaps_and_outside(tmp_path: Path) -> None:
    app = _app()
    win, tab = _open(app, _multi_pdf(tmp_path / "near.pdf"))
    viewer = tab.viewer
    r0, r1 = viewer._page_rects_px[0], viewer._page_rects_px[1]
    assert viewer.page_near(QPointF(r0.center().x(), r0.top() - 5)) == 0
    assert viewer.page_near(QPointF(r0.center().x(), (r0.bottom() + r1.top()) / 2)) == 0
    assert viewer.page_near(QPointF(r1.center().x(), r1.top() + 3)) == 1
    assert viewer.page_near(QPointF(5, viewer._page_rects_px[-1].bottom() + 50)) == 2
    win.close()
    app.processEvents()


def test_place_beside_avoids_covering_selection() -> None:
    from PySide6.QtCore import QRect

    from qtpdfpro.ui.text_select_tool import place_beside

    def box(pt, w=400, h=200):
        return QRect(pt.x(), pt.y(), w, h)

    area_w, area_h = 1200, 800
    sel = QRect(100, 100, 300, 60)  # còn chỗ phía dưới → đặt dưới
    assert place_beside(sel, 400, 200, area_w, area_h).y() == sel.bottom() + 8
    sel = QRect(100, 550, 300, 60)  # sát đáy → sang phải (không lên trên che đoạn vừa đọc)
    pos = place_beside(sel, 400, 200, area_w, area_h)
    assert pos.x() > sel.right() and not box(pos).intersects(sel)
    sel = QRect(20, 550, 1100, 60)  # rộng cả trang, sát đáy → phía trên
    pos = place_beside(sel, 400, 200, area_w, area_h)
    assert pos.y() + 200 <= sel.top() and not box(pos).intersects(sel)
    sel = QRect(0, 0, 1200, 800)  # che kín → vẫn nằm trong khung
    pos = place_beside(sel, 400, 200, area_w, area_h)
    assert QRect(0, 0, area_w, area_h).contains(box(pos))


def test_ocr_popup_drag_keeps_user_position(tmp_path: Path) -> None:
    app = _app()
    win, tab = _open(app, _scanned_pdf(tmp_path / "scan_popup.pdf"))
    tool = tab.text_select
    engine = _InkEngine()
    tool.engine_factory = lambda: engine
    models = _Models(installed=True)
    tool.models_provider = lambda: models
    _drag(tab.viewer, 0, (60, 290), (215, 340))
    tool.wait_ocr()
    popup = tool.popup
    assert popup is not None and popup.isVisible() and tool.ocr_result is not None
    # Bong bóng không đè lên vùng vừa nhận dạng
    vp_sel = tab.viewer.page_rect_to_widget(0, tool.bounding_rect()).translated(QPointF(tab.viewer.widget().pos()))
    assert not popup.geometry().intersects(vp_sel.toAlignedRect())
    # Kéo tiêu đề bong bóng → giữ nguyên chỗ người dùng đặt kể cả khi cuộn trang
    start = QPointF(popup.title_lbl.geometry().center())
    _mouse(popup, QEvent.Type.MouseButtonPress, start)
    _mouse(popup, QEvent.Type.MouseMove, start + QPointF(-60, 40), LEFT, LEFT)
    _mouse(popup, QEvent.Type.MouseButtonRelease, start + QPointF(-60, 40), LEFT, Qt.MouseButton.NoButton)
    assert popup.user_moved
    moved_to = popup.pos()
    tab.viewer.verticalScrollBar().setValue(tab.viewer.verticalScrollBar().value() + 30)
    app.processEvents()
    assert popup.pos() == moved_to
    # Vùng mới → bong bóng lại tự đặt cạnh vùng chọn
    _drag(tab.viewer, 0, (60, 290), (215, 340))
    tool.wait_ocr()
    assert not popup.user_moved
    win.close()
    app.processEvents()


def test_select_text_and_hand_tools_in_catalog(tmp_path: Path) -> None:
    from qtpdfpro.ui.tool_catalog import get_tool, tools_for

    assert get_tool("select_text").ready and get_tool("hand_tool").ready
    assert "select_text" in [t.key for t in tools_for("all", "chon chu")]
    assert "hand_tool" in [t.key for t in tools_for("all", "ban tay")]
    app = _app()
    win, tab = _open(app, _text_pdf(tmp_path / "cat.pdf"))
    assert {"pointer_select", "pointer_hand"} <= set(win.function_bar.visible_command_keys())
    win.run_tool("hand_tool")
    assert tab.pointer_mode == "hand" and tab.viewer.interaction is None
    tab.enter_edit_mode()
    win.run_tool("select_text")  # thoát chế độ chỉnh sửa, về Chọn chữ
    assert not tab.edit_mode and tab.pointer_mode == "select" and tab.viewer.interaction is tab.text_select
    win.close()
    app.processEvents()
