"""Kiểm thử Đợt 2 của công cụ «Chọn chữ»: lớp chữ nhận dạng ngầm cho trang ảnh quét (`core/ocr_layer.py`,
`ui/ocr_layer_service.py`) — từ theo trang, lưu đệm theo SHA-256 tệp, dùng lại khi lưu PDF tìm kiếm được, chọn chữ
trên trang scan như PDF thường. Engine OCR giả tìm dòng theo dải mực (không cần bộ mô hình 88 MB)."""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QGuiApplication, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

from qtpdfpro import cli
from qtpdfpro.core import ocr as ocr_mod
from qtpdfpro.core import ocr_layer
from qtpdfpro.core import text_select as ts
from qtpdfpro.core.ocr import OcrLine
from qtpdfpro.core.settings import AppSettings
from qtpdfpro.ui.main_window import MainWindow
from ui_helpers import clipboard_text

LEFT = Qt.MouseButton.LeftButton
LINES = ["Cộng hòa xã hội chủ nghĩa", "Độc lập tự do hạnh phúc"]


def _font_kwargs() -> dict:
    font = Path(r"C:\Windows\Fonts\times.ttf")
    return {"fontname": "tnr", "fontfile": str(font)} if font.exists() else {"fontname": "helv"}


def _scanned_pdf(path: Path, pages: int = 2) -> Path:
    """PDF ảnh quét: mỗi trang hai dòng chữ kết xuất thành ảnh 150 dpi (không còn lớp chữ)."""
    out = fitz.open()
    for _ in range(pages):
        src = fitz.open()
        p = src.new_page(width=595, height=842)
        p.insert_text((72, 100), LINES[0], fontsize=18, **_font_kwargs())
        p.insert_text((72, 160), LINES[1], fontsize=18, **_font_kwargs())
        pix = p.get_pixmap(dpi=150)
        out.new_page(width=595, height=842).insert_image(fitz.Rect(0, 0, 595, 842), pixmap=pix)
        src.close()
    out.save(str(path))
    out.close()
    return path


class _BandEngine:
    """Engine giả: mỗi dải hàng có mực = một dòng; chữ lấy lần lượt từ `texts`. Đủ để kiểm phép đổi toạ độ."""

    def __init__(self, texts=LINES) -> None:
        self.texts = list(texts)
        self.calls = 0

    def ocr_image(self, rgb: np.ndarray, zoom: float, clean_ink: bool = True):
        self.calls += 1
        mask = rgb.mean(axis=2) < 128
        rows = np.where(mask.any(axis=1))[0]
        bands, start, prev = [], None, None
        for y in rows:
            if start is None:
                start = prev = y
            elif y > prev + 3:
                bands.append((start, prev))
                start = y
            prev = y
        if start is not None:
            bands.append((start, prev))
        out = []
        for (y0, y1), text in zip(bands, self.texts):
            cols = np.where(mask[y0:y1 + 1].any(axis=0))[0]
            out.append(OcrLine(text, (cols[0] / zoom, y0 / zoom, (cols[-1] + 1) / zoom, (y1 + 1) / zoom),
                               size=14.0, baseline=(y1 + 1) / zoom))
        return out


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


# ─── Lõi ───────────────────────────────────────────────────────────────────


def test_split_line_words_proportional_boxes() -> None:
    words = ocr_layer.split_line_words("Độc lập  tự do", fitz.Rect(0, 10, 140, 20))
    assert [w for _r, w in words] == ["Độc", "lập", "tự", "do"]
    assert words[0][0].x0 == 0 and words[-1][0].x1 == 140
    assert all(a[0].x1 <= b[0].x0 for a, b in zip(words, words[1:]))
    assert ocr_layer.split_line_words("   ", fitz.Rect(0, 0, 10, 10)) == []


def test_recognize_page_words_and_display_lines(tmp_path: Path) -> None:
    # (phép đổi toạ độ cho trang /Rotate + xoay xem đã kiểm ở test_text_select::test_render_region_maps_pixels_back_to_page)
    with fitz.open(_scanned_pdf(tmp_path / "s.pdf", 1)) as doc:
        page = doc[0]
        region = ocr_layer.prepare_page_image(page)
        res = ocr_layer.recognize_page(_BandEngine(), region)
        assert [w[4] for w in res.words][:3] == ["Cộng", "hòa", "xã"]
        assert ts.selection_text(res.words) == "\n".join(LINES)
        # Từ đầu tiên nằm đúng chỗ chữ «Cộng» trên trang chưa xoay (chữ chèn ở (72, 100) trước khi xoay)
        first = fitz.Rect(res.words[0][:4])
        assert abs(first.x0 - 72) < 3 and abs(first.y1 - 100) < 6
        # Dòng theo hệ trang hiển thị như OcrEngine.ocr_page (bỏ lề đệm): khớp toạ độ từ khi trang không xoay
        assert len(res.lines) == 2
        disp = fitz.Rect(res.lines[0].bbox) * page.derotation_matrix
        assert abs(disp.x0 - first.x0) < 1 and abs(disp.y0 - first.y0) < 1


def test_cache_roundtrip_bundle_version_and_prune(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with fitz.open(_scanned_pdf(tmp_path / "s.pdf", 1)) as doc:
        res = ocr_layer.recognize_page(_BandEngine(), ocr_layer.prepare_page_image(doc[0]))
    cache = ocr_layer.OcrLayerCache(tmp_path / "cache")
    key = ocr_layer.file_sha256(tmp_path / "s.pdf")
    cache.save(key, {0: res})
    back = cache.load(key)[0]
    assert back.words[0][4] == "Cộng" and back.lines[0].text == LINES[0] and back.lines[0].size == 14.0
    assert ts.selection_text(back.words) == ts.selection_text(res.words)
    monkeypatch.setattr(ocr_layer, "_bundle_version", lambda: 99)  # bộ mô hình mới → bỏ lưu đệm cũ
    assert cache.load(key) == {}
    monkeypatch.undo()
    for i in range(5):
        cache.save(f"k{i}", {0: res})
    cache.prune(max_files=3)
    assert len(list((tmp_path / "cache").glob("*.json"))) == 3


def test_cached_engine_reused_by_ocr_pdf(tmp_path: Path) -> None:
    """Lưu PDF tìm kiếm được: trang đã có lớp chữ không nhận dạng lại; trang chưa có mới gọi bộ máy thật."""
    src = _scanned_pdf(tmp_path / "s.pdf", 2)
    with fitz.open(src) as doc:
        page0 = ocr_layer.recognize_page(_BandEngine(["Trang một dòng một", "Trang một dòng hai"]),
                                         ocr_layer.prepare_page_image(doc[0]))

    class _Real:
        calls = 0

        def ocr_page(self, page, dpi=0, clean_ink=True, keep_ink_images=False):
            _Real.calls += 1
            return ocr_mod.OcrPage(page.number, page.rect.width, page.rect.height,
                                   [OcrLine("Trang hai mới nhận dạng", (72, 80, 400, 104), size=14.0)])

    engine = ocr_layer.CachedOcrEngine({0: page0}, factory=_Real)
    res = ocr_mod.ocr_pdf(src, tmp_path / "out.pdf", engine=engine)
    assert res.pages_ocr == 2 and engine.reused == [0] and _Real.calls == 1
    with fitz.open(tmp_path / "out.pdf") as out:
        assert "Trang một dòng một" in out[0].get_text()
        assert "Trang hai mới nhận dạng" in out[1].get_text()


def test_cli_text_layer_uses_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = _scanned_pdf(tmp_path / "s.pdf", 1)
    engine = _BandEngine()
    monkeypatch.setattr(ocr_mod.OcrEngine, "load", classmethod(lambda cls, threads=0: engine))
    for _ in range(2):
        buf = io.StringIO()
        with redirect_stdout(buf):
            assert cli.main(["text", str(pdf), "--layer"]) == 0
        assert buf.getvalue().strip() == "\n".join(LINES)
    assert engine.calls == 1  # lần hai lấy từ lưu đệm
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert cli.main(["text", str(pdf), "--layer", "--rect", "60,130,560,170"]) == 0
    assert buf.getvalue().strip() == LINES[1]


# ─── Giao diện ─────────────────────────────────────────────────────────────


def _mouse(widget, kind, pos: QPointF, buttons=LEFT) -> None:
    QApplication.sendEvent(widget, QMouseEvent(kind, pos, QPointF(widget.mapToGlobal(pos.toPoint())), LEFT, buttons,
                                               Qt.KeyboardModifier.NoModifier))


def _drag(viewer, page: int, p0, p1, steps: int = 4) -> None:
    surface, t = viewer.widget(), viewer.page_transform(page)
    a, b = t.map(QPointF(*p0)), t.map(QPointF(*p1))
    _mouse(surface, QEvent.Type.MouseButtonPress, a)
    for i in range(1, steps + 1):
        _mouse(surface, QEvent.Type.MouseMove, QPointF(a.x() + (b.x() - a.x()) * i / steps,
                                                        a.y() + (b.y() - a.y()) * i / steps))
    _mouse(surface, QEvent.Type.MouseButtonRelease, b, Qt.MouseButton.NoButton)


def _open(app, pdf: Path, engine, models_ready: bool = True):
    win = MainWindow(settings=AppSettings.load())
    win.resize(1400, 900)
    win.show()
    app.processEvents()
    tab = win.open_pdf_path(pdf)
    tab.ocr_layer.engine_factory = lambda: engine
    tab.ocr_layer.models_ready = lambda: models_ready
    tab.viewer.set_zoom_mode("percent", 100)
    tab.viewer.go_to_page(0)
    tab.wait_for_document_analysis()  # → _analyze_document → xin nhận dạng ngầm trang đang xem
    return win, tab


def test_scanned_page_background_layer_makes_text_selectable(tmp_path: Path) -> None:
    app = _app()
    pdf = _scanned_pdf(tmp_path / "scan.pdf", 3)
    engine = _BandEngine()
    win, tab = _open(app, pdf, engine)
    tool, layer = tab.text_select, tab.ocr_layer

    # Tài liệu ảnh quét: dòng thông báo có liên kết «Lưu thành PDF tìm kiếm được»
    assert tab.is_scanned_document and not tab.notice_bar.isHidden()
    assert tab.notice_link.text() == "Lưu thành PDF tìm kiếm được"
    assert not layer.idle  # đã xin nhận dạng ngầm (đang băm tệp tra lưu đệm / đang nhận dạng)
    for _ in range(200):  # chờ tới lúc đang nhận dạng trang 0 → vẽ nhãn «Đang nhận dạng chữ…» không lỗi
        if layer.busy_page == 0 or layer.has_layer(0):
            break
        app.processEvents()
    tab.viewer.widget().grab()
    layer.wait_idle()
    assert layer.has_layer(0) and layer.has_layer(1) and not layer.has_layer(2)  # trang đang xem + trang kế
    assert engine.calls == 2 and not tool.needs_ocr(0)

    # Chọn chữ trên trang scan như PDF thường: kéo theo dòng, nhấp đúp, Ctrl+A
    first = fitz.Rect(layer.words(0)[0][:4])
    _drag(tab.viewer, 0, (first.x0 + 2, (first.y0 + first.y1) / 2), (first.x0 + 120, (first.y0 + first.y1) / 2))
    assert tool.selected_text().startswith("Cộng hòa")
    surface = tab.viewer.widget()
    QApplication.sendEvent(surface, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier))
    assert tool.selected_text() == "\n".join(LINES)
    QApplication.sendEvent(surface, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier))
    assert clipboard_text("\n".join(LINES)) == "\n".join(LINES)

    # Sang trang 3 → nhận dạng ngầm trang đó
    tab.viewer.go_to_page(2)
    layer.wait_idle()
    assert layer.has_layer(2) and engine.calls == 3

    # «Lưu thành PDF tìm kiếm được» dùng lại lớp chữ đã có
    captured = {}
    win.action_ocr = lambda engine_factory=None: captured.setdefault("factory", engine_factory)
    win.ocr_models.is_installed = lambda: True
    tab.notice_link.click()
    cached = captured["factory"]()
    assert isinstance(cached, ocr_layer.CachedOcrEngine) and sorted(cached.pages) == [0, 1, 2]
    menu = tool.build_context_menu(0)
    assert any(a.text().startswith("💾 Lưu thành PDF tìm kiếm được") for a in menu.actions())
    win.close()
    app.processEvents()

    # Mở lại tệp: lớp chữ lấy từ lưu đệm, không nhận dạng lại
    engine2 = _BandEngine()
    win2, tab2 = _open(app, pdf, engine2)
    tab2.ocr_layer.wait_idle()
    assert tab2.ocr_layer.has_layer(0) and tab2.ocr_layer.has_layer(1) and engine2.calls == 0
    win2.close()
    app.processEvents()


def test_no_background_ocr_without_models_or_in_hand_mode(tmp_path: Path) -> None:
    app = _app()
    pdf = _scanned_pdf(tmp_path / "scan.pdf", 2)
    engine = _BandEngine()
    win, tab = _open(app, pdf, engine, models_ready=False)  # chưa cài bộ mô hình → không tự tải / nhận dạng
    tab.ocr_layer.wait_idle()
    assert engine.calls == 0 and not tab.ocr_layer.has_layer(0) and tab.text_select.needs_ocr(0)
    tab.ocr_layer.models_ready = lambda: True
    win.set_pointer_mode("hand")
    tab.viewer.go_to_page(1)
    tab.ocr_layer.wait_idle()
    assert engine.calls == 0  # Bàn tay: không nhận dạng
    win.set_pointer_mode("select")  # bật lại Chọn chữ → nhận dạng trang đang xem
    tab.ocr_layer.wait_idle()
    assert tab.ocr_layer.has_layer(1) and engine.calls >= 1
    win.close()
    app.processEvents()


# ─── Hoàn thiện: khung từ theo khe mực, dùng lại lớp chữ của trang đang xoay xem ──────────────


def test_split_line_words_snaps_to_ink_gaps() -> None:
    # Ba «từ» mực rộng 10 / 60 / 20 cột, cách nhau 8 cột; chia theo số ký tự sẽ lệch rất xa
    ink = np.zeros(120, dtype=bool)
    ink[2:12] = ink[20:80] = ink[88:108] = True
    words = ocr_layer.split_line_words("ab cdefgh ij", fitz.Rect(0, 0, 120, 20), ink)
    boxes = [(round(r.x0), round(r.x1)) for r, _w in words]
    assert [w for _r, w in words] == ["ab", "cdefgh", "ij"]
    assert boxes == [(2, 12), (20, 80), (88, 108)]
    # Khe giữa các chữ cái trong một từ (hẹp) không bị coi là ranh giới từ
    ink2 = np.ones(100, dtype=bool)
    ink2[30:32] = False  # khe 2 cột giữa hai chữ cái
    ink2[48:58] = False  # khe 10 cột = dấu cách
    words2 = ocr_layer.split_line_words("xin chào", fitz.Rect(0, 0, 100, 20), ink2)
    assert [(round(r.x0), round(r.x1)) for r, _w in words2] == [(0, 48), (58, 100)]
    # Không tìm thấy khe gần ranh giới ước lượng → giữ khung theo tỷ lệ ký tự
    flat = np.ones(100, dtype=bool)
    assert [(round(r.x0), round(r.x1)) for r, _ in ocr_layer.split_line_words("ab cd", fitz.Rect(0, 0, 100, 20), flat)] \
        == [(0, 40), (60, 100)]


def test_recognize_page_word_boxes_follow_real_word_gaps(tmp_path: Path) -> None:
    text = "Ủy ban nhân dân tỉnh An Giang quyết định"
    src = fitz.open()
    p = src.new_page(width=595, height=842)
    p.insert_text((72, 100), text, fontsize=16, **_font_kwargs())
    truth = [fitz.Rect(w[:4]) for w in p.get_text("words")]
    pix = p.get_pixmap(dpi=200)
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, pixmap=pix)
    res = ocr_layer.recognize_page(_BandEngine([text]), ocr_layer.prepare_page_image(page))
    assert [w[4] for w in res.words] == text.split()
    for w, t in zip(res.words, truth):
        assert abs(w[0] - t.x0) < 1.5 and abs(w[2] - t.x1) < 1.5, (w[4], w[:4], tuple(t))
    doc.close()
    src.close()


def test_view_matrix_matches_page_with_extra_rotate() -> None:
    for base in (0, 90, 180, 270):
        for extra in (0, 90, 180, 270):
            doc = fitz.open()
            doc.new_page(width=300, height=500)
            doc.new_page(width=300, height=500)
            doc[0].set_rotation(base)
            doc[1].set_rotation((base + extra) % 360)
            got, want = ocr_mod.view_matrix(doc[0], extra), doc[1].rotation_matrix
            assert all(abs(a - b) < 1e-6 for a, b in zip(got, want)), (base, extra)
            doc.close()


@pytest.mark.parametrize("base,extra", [(0, 90), (0, 270), (90, 180), (270, 180)])
def test_rotated_view_layer_reused_for_searchable_pdf(tmp_path: Path, base: int, extra: int) -> None:
    """Trang quét nằm ngang người dùng xoay xem cho đúng chiều: lớp chữ nhận dạng khi xem được dùng lại khi lưu PDF
    tìm kiếm được, đặt đúng chỗ dòng chữ trên trang (trước đây trang xoay xem phải nhận dạng lại)."""
    # Dải mực nằm dọc trên trang chưa xoay (dòng chữ chạy dọc trang — bản scan bị quay ngang)
    ink_rect = fitz.Rect(120, 200, 150, 560)
    src = fitz.open()
    p = src.new_page(width=595, height=842)
    p.draw_rect(ink_rect, color=None, fill=(0, 0, 0))
    pix = p.get_pixmap(dpi=100)
    path = tmp_path / f"rot_{base}_{extra}.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, pixmap=pix)
    page.set_rotation(base)
    doc.save(str(path))
    doc.close()
    src.close()
    with fitz.open(str(path)) as doc:
        page = doc[0]
        res = ocr_layer.recognize_page(_BandEngine(["Dòng chữ quay ngang"]),
                                       ocr_layer.prepare_page_image(page, view_rotation=extra), extra)
        assert res.view_rotation == extra and len(res.lines) == 1
        word_box = fitz.Rect(res.words[0][:4])
        for w in res.words[1:]:
            word_box |= fitz.Rect(w[:4])
        assert word_box.intersects(ink_rect)
    cached = ocr_layer.CachedOcrEngine({0: res}, factory=lambda: pytest.fail("không được nhận dạng lại"))
    out = tmp_path / f"rot_{base}_{extra}_ocr.pdf"
    ocr_mod.ocr_pdf(path, out, engine=cached)
    assert cached.reused == [0]
    with fitz.open(str(out)) as doc:
        words = doc[0].get_text("words")
        assert " ".join(w[4] for w in words) == "Dòng chữ quay ngang"
        box = fitz.Rect(words[0][:4])
        for w in words[1:]:
            box |= fitz.Rect(w[:4])
        # Chữ ẩn chạy dọc trang chưa xoay, phủ suốt chiều dài dải mực (bề ngang theo cỡ chữ, không theo dải mực)
        assert abs(box.y0 - ink_rect.y0) < 3 and abs(box.y1 - ink_rect.y1) < 3, (tuple(box), tuple(ink_rect))
        assert ink_rect.x0 <= (box.x0 + box.x1) / 2 <= ink_rect.x1
        assert box.height > box.width * 3
