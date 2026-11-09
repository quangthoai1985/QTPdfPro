"""Kiểm thử điều hướng trang & mở tệp nhanh: nhấp ảnh thu nhỏ → khung đọc chuyển trang NGAY (không phải lăn
chuột), ảnh thu nhỏ kết xuất dần theo vùng nhìn, mở tệp không phân tích bố cục mọi trang."""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF
import pytest
from PySide6.QtWidgets import QApplication

from qtpdfpro.core.layout_analyzer import analyze_page_layout
from qtpdfpro.core.reader import PDFDocumentReader
from qtpdfpro.core.settings import AppSettings
from qtpdfpro.ui.main_window import MainWindow


def _make_pdf(path: Path, pages: int, table_page: int | None = None, widget_page: int | None = None) -> Path:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 90), f"Trang so {i + 1}", fontsize=28)
        if i == table_page:  # bảng 3×3 có đường kẻ
            xs, ys = [72, 200, 330, 460], [300, 330, 360, 390]
            for y in ys:
                page.draw_line((xs[0], y), (xs[-1], y), color=(0, 0, 0), width=1)
            for x in xs:
                page.draw_line((x, ys[0]), (x, ys[-1]), color=(0, 0, 0), width=1)
            for r in range(3):
                for c in range(3):
                    page.insert_text((xs[c] + 6, ys[r] + 20), f"o {r}{c}", fontsize=10)
        if i == widget_page:
            w = fitz.Widget()
            w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
            w.field_name = "ho_ten"
            w.rect = fitz.Rect(72, 500, 300, 520)
            page.add_widget(w)
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture()
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _open(app: QApplication, pdf: Path):
    win = MainWindow(settings=AppSettings.load())
    win.resize(1500, 900)
    win.show()
    app.processEvents()
    tab = win.open_pdf_path(pdf)
    assert tab is not None
    for _ in range(5):
        app.processEvents()
    return win, tab


def _page_top_in_viewport(tab, page: int) -> float:
    """Vị trí mép trên trang `page` trong vùng nhìn của khung đọc (theo vị trí THẬT của bề mặt vẽ)."""
    return tab.viewer._page_rects_px[page].top() + tab.viewer.widget().y()


def test_thumbnail_click_scrolls_viewer_immediately(app, tmp_path: Path) -> None:
    win, tab = _open(app, _make_pdf(tmp_path / "dai.pdf", 30))
    viewer = tab.viewer
    tab.sidebar_tabs.setVisible(True)
    tab.sidebar_tabs.setCurrentIndex(0)
    app.processEvents()

    # Chọn trang 12 trong danh sách ảnh thu nhỏ → trang chính hiện ngay, không cần lăn chuột
    tab.thumb_list.setCurrentRow(11)
    assert viewer.current_page == 11
    bar = viewer.verticalScrollBar()
    assert bar.value() > 0
    # Lỗi cũ: blockSignals làm thanh cuộn nhảy nhưng bề mặt vẽ đứng yên → nội dung không đổi
    assert viewer.widget().y() == -bar.value()
    assert 0 <= _page_top_in_viewport(tab, 11) <= viewer.viewport().height() * 0.2
    assert win.windowTitle() is not None and win.page_spin.value() == 12

    # Cuộn lệch xuống giữa trang 12 rồi nhấp lại đúng ảnh trang 12 → về lại đầu trang
    bar.setValue(bar.value() + 300)
    app.processEvents()
    assert viewer.current_page == 11
    tab._on_thumb_clicked(tab.thumb_list.item(11))
    assert 0 <= _page_top_in_viewport(tab, 11) <= viewer.viewport().height() * 0.2

    # Trang cuối (không cuộn được tới mép trên) vẫn là trang hiện tại
    tab.thumb_list.setCurrentRow(29)
    assert viewer.current_page == 29
    assert viewer.widget().y() == -bar.value()

    # Mục lục / nút trang dùng chung go_to_page
    viewer.go_to_page(4)
    assert viewer.widget().y() == -bar.value()
    assert tab.thumb_list.currentRow() == 4
    win.close()
    app.processEvents()


def test_thumbnails_render_lazily_for_visible_rows(app, tmp_path: Path) -> None:
    win, tab = _open(app, _make_pdf(tmp_path / "nhieu_trang.pdf", 80))
    tab.sidebar_tabs.setVisible(True)
    tab.sidebar_tabs.setCurrentIndex(0)
    for _ in range(10):
        app.processEvents()

    assert tab.thumb_list.count() == 80  # đủ mục cho mọi trang (trước đây chỉ có ảnh cho 60 trang đầu)
    assert 0 in tab._thumb_done
    assert 79 not in tab._thumb_done  # chưa nhìn tới → chưa kết xuất
    # Ảnh thu nhỏ không chiếm bộ đệm LRU của khung đọc
    assert all(key[1] >= 150 for key in tab.reader._render_cache)

    tab.thumb_list.scrollToBottom()
    for _ in range(20):
        app.processEvents()
    assert 79 in tab._thumb_done
    assert len(tab._thumb_done) < 80
    win.close()
    app.processEvents()


def test_open_does_not_analyze_every_page(app, tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "bang.pdf", 6, table_page=4)
    win = MainWindow(settings=AppSettings.load())
    win.show()
    app.processEvents()
    tab = win.open_pdf_path(pdf)
    assert tab is not None
    # Mở tệp: chưa phân tích bố cục trang nào (trước đây find_tables cho MỌI trang ngay lúc mở)
    assert tab.reader._layout_cache == {}
    assert tab.notice_bar.isHidden()

    # Phân tích nền: dò bảng dần từng trang rồi hiện thanh thông báo
    tab.wait_for_document_analysis()
    assert tab._banner_tables == 1
    assert not tab.notice_bar.isHidden()
    assert "bảng biểu" in tab.notice_lbl.text() and tab.notice_link.objectName() == "linkBtn"

    # «Soi bố cục» chỉ phân tích khi ngăn đang hiện
    tab.sidebar_tabs.setVisible(True)
    tab.sidebar_tabs.setCurrentIndex(0)
    app.processEvents()
    tab.viewer.go_to_page(2)
    assert tab._inspector_page is None
    tab.sidebar_tabs.setCurrentIndex(3)
    for _ in range(3):
        app.processEvents()
    assert tab._inspector_page == 2
    assert "Trang 3/6" in tab.layout_info_lbl.text()
    win.close()
    app.processEvents()


def test_banner_counts_widgets_without_table_scan(app, tmp_path: Path) -> None:
    win, tab = _open(app, _make_pdf(tmp_path / "bieu_mau.pdf", 3, widget_page=1))
    tab.wait_for_document_analysis()
    assert tab._banner_sigs == 1
    assert "1 chữ ký số" in tab.notice_lbl.text()
    assert tab._table_scan_timer.isActive() is False
    win.close()
    app.processEvents()


def test_reader_fast_paths(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "doc.pdf", 4, table_page=2, widget_page=3)
    with PDFDocumentReader(pdf) as reader:
        assert reader.count_form_widgets() == 1
        assert reader.get_page_size(1) == (595.0, 842.0)
        assert 1 in reader._page_size_cache
        reader.rotate_page(1, 90)
        assert reader.get_page_size(1) == (842.0, 595.0)

        buf = reader.render_page(0, scale=0.1, cache=False)
        assert buf.width == round(595 * 0.1) or abs(buf.width - 59.5) <= 1
        assert reader._render_cache == {}
        reader.render_page(0, scale=1.0)
        assert len(reader._render_cache) == 1

        assert reader.quick_table_count(0) == 0  # không có nét vẽ → không dò bảng
        assert 0 not in reader._layout_cache
        assert reader.quick_table_count(2) == 1
        assert reader.get_page_layout(2).table_count == 1
        assert reader.page_has_text(0, min_chars=8) is True  # «Trang so 1» = 8 ký tự không trắng
        assert reader.page_has_text(0) is False  # < 20 ký tự → coi như không có lớp chữ
        assert reader.is_closed is False
    assert reader.is_closed is True


def test_analyze_page_layout_without_layout_model_finds_tables(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "t.pdf", 1, table_page=0)
    with fitz.open(pdf) as doc:
        fast = analyze_page_layout(doc[0], use_layout_model=False)
        assert fast.table_count == 1
        assert any(el.kind == "table" for el in fast.elements)
