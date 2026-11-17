"""Kiểm thử tính năng Chỉnh sửa nâng cao (kiểu PdfCraft):
- Thu gọn bảng thumbnail mặc định khi mở tài liệu, đóng/mở bằng thanh dọc phải / F4.
- Thanh công cụ Chỉnh sửa bên trái (`EditSidebar`) chỉ hiện khi vào mục Chỉnh sửa.
- Thanh công cụ nổi nhanh (`FloatingHotbar`): chọn công cụ, kéo thả, tuỳ chỉnh ẩn/hiện nút.
- Xoay trang, lật ngang/dọc (Flip Horizontal/Vertical), cắt trang (Crop), chèn/nhân bản/xoá trang,
  chèn & xoay/lật ảnh, liên kết, đầu/chân trang, đánh số Bates, nền trang, đính kèm tệp,
  che thông tin (Redact), đóng dấu nước, làm sạch siêu dữ liệu — Hoàn tác/Làm lại và Lưu (`Ctrl+S`).
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QInputDialog, QMessageBox

from qtpdfpro.core import page_edit, page_stamp
from qtpdfpro.core.settings import AppSettings
from qtpdfpro.ui.main_window import MainWindow


@pytest.fixture(autouse=True)
def _fail_on_modal_alert(monkeypatch) -> None:
    def _unexpected(kind: str):
        def _handler(*args, **kwargs):
            raise AssertionError(f"Unexpected QMessageBox.{kind}: {args[1:3]}")
        return _handler

    monkeypatch.setattr(QMessageBox, "warning", _unexpected("warning"))
    monkeypatch.setattr(QMessageBox, "critical", _unexpected("critical"))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Discard)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _mouse(widget, kind: QEvent.Type, pos: QPointF, buttons, button=Qt.MouseButton.LeftButton) -> None:
    gpos = QPointF(widget.mapToGlobal(pos.toPoint()))
    QApplication.sendEvent(widget, QMouseEvent(kind, pos, gpos, button, buttons, Qt.KeyboardModifier.NoModifier))


def _drag(viewer, page: int, p0, p1, steps: int = 4) -> None:
    surface = viewer.widget()
    t = viewer.page_transform(page)
    a, b = t.map(QPointF(*p0)), t.map(QPointF(*p1))
    left = Qt.MouseButton.LeftButton
    _mouse(surface, QEvent.Type.MouseButtonPress, a, left)
    for i in range(1, steps + 1):
        q = QPointF(a.x() + (b.x() - a.x()) * i / steps, a.y() + (b.y() - a.y()) * i / steps)
        _mouse(surface, QEvent.Type.MouseMove, q, left, Qt.MouseButton.NoButton)
    _mouse(surface, QEvent.Type.MouseButtonRelease, b, Qt.MouseButton.NoButton)


def _make_asymmetric_pdf(path: Path) -> Path:
    """Tạo PDF 2 trang có 4 góc màu khác nhau và chữ bí mật để kiểm chứng lật/xoay/cắt/che/lưu."""
    doc = fitz.open()
    for pno in range(2):
        page = doc.new_page(width=400, height=600)
        # Góc trên-trái đỏ, trên-phải xanh lá, dưới-trái xanh dương
        page.draw_rect(fitz.Rect(20, 20, 100, 100), color=None, fill=(1, 0, 0))
        page.draw_rect(fitz.Rect(300, 20, 380, 100), color=None, fill=(0, 1, 0))
        page.draw_rect(fitz.Rect(20, 500, 100, 580), color=None, fill=(0, 0, 1))
        page.insert_text(fitz.Point(60, 260), f"TrangSo{pno + 1} SECRET_TOKEN", fontsize=14)
    doc.set_metadata({"title": "TaiLieuGoc", "author": "Tester"})
    doc.save(str(path))
    doc.close()
    return path


def _make_png_bytes() -> bytes:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 20), False)
    pix.clear_with(0)
    # Nửa trái đỏ, nửa phải xanh dương
    for y in range(20):
        for x in range(40):
            pix.set_pixel(x, y, (255, 0, 0) if x < 20 else (0, 0, 255))
    return pix.tobytes("png")


def _new_window(tmp_path: Path) -> MainWindow:
    settings = AppSettings()
    win = MainWindow(settings=settings)
    win.resize(1400, 900)
    win.show()
    return win


def _close_cleanly(win: MainWindow) -> None:
    for i in range(win.doc_tabs.count()):
        tab = win.doc_tabs.widget(i)
        if hasattr(tab, "reader") and hasattr(tab.reader, "_edit_session"):
            tab.reader._edit_session = None
    win.close()


def _sample_rgb(page: fitz.Page, x: int, y: int) -> tuple[int, int, int]:
    pix = page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
    r, g, b = pix.pixel(x, y)[:3]
    return int(r), int(g), int(b)


def test_thumbnails_collapsed_on_open_and_edit_sidebar_lifecycle(tmp_path: Path) -> None:
    app = _app()
    pdf = _make_asymmetric_pdf(tmp_path / "sample.pdf")
    win = _new_window(tmp_path)
    try:
        tab = win.open_pdf_path(pdf)
        assert tab is not None
        app.processEvents()

        # 1. Mở tài liệu: thumbnail bên phải thu gọn mặc định; EditSidebar bên trái đang ẩn; Hotbar đang hiện
        assert not tab.sidebar_tabs.isVisible()
        assert not tab.edit_sidebar.isVisible()
        assert tab.hotbar.isVisible()
        assert win.minimumSizeHint().width() <= 1280

        # 2. Mở / đóng thumbnail bằng thanh dọc phải và F4
        tab.rail_panel_buttons[0].click()
        app.processEvents()
        assert tab.sidebar_tabs.isVisible() and tab.sidebar_tabs.currentIndex() == 0
        assert tab.rail_panel_buttons[0].isChecked()

        win.run_command("toggle_sidebar")
        app.processEvents()
        assert not tab.sidebar_tabs.isVisible()

        # 3. Chọn tab «Chỉnh sửa» -> hiện thanh EditSidebar bên trái (cỡ 212 px)
        win.set_function_tab("edit")
        app.processEvents()
        assert tab.edit_sidebar.isVisible()
        assert tab.edit_sidebar.width() == 212
        assert win.minimumSizeHint().width() <= 1280

        # Chuyển sang «Điền & Ký» -> ẩn EditSidebar
        win.set_function_tab("fill")
        app.processEvents()
        assert not tab.edit_sidebar.isVisible()

        # Quay lại «Chỉnh sửa», bấm nút đóng ✕ -> ẩn EditSidebar
        win.set_function_tab("edit")
        app.processEvents()
        assert tab.edit_sidebar.isVisible()
        tab.edit_sidebar.btn_close.click()
        app.processEvents()
        assert not tab.edit_sidebar.isVisible()

        # Về «Đọc» -> ẩn EditSidebar
        win.set_function_tab("read")
        app.processEvents()
        assert not tab.edit_sidebar.isVisible()
    finally:
        _close_cleanly(win)


def test_hotbar_actions_drag_and_customize(tmp_path: Path) -> None:
    app = _app()
    pdf = _make_asymmetric_pdf(tmp_path / "hotbar.pdf")
    win = _new_window(tmp_path)
    try:
        tab = win.open_pdf_path(pdf)
        app.processEvents()
        hb = tab.hotbar
        assert hb.isVisible()

        # Kéo tay nắm Hotbar di chuyển vị trí
        start_pos = hb.pos()
        grip = hb.grip
        _mouse(grip, QEvent.Type.MouseButtonPress, QPointF(8, 8), Qt.MouseButton.LeftButton)
        _mouse(grip, QEvent.Type.MouseMove, QPointF(68, 48), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
        _mouse(grip, QEvent.Type.MouseButtonRelease, QPointF(68, 48), Qt.MouseButton.NoButton)
        assert hb.pos() != start_pos
        hb.reset_position(top_offset=20)
        assert hb.pos().x() == 12

        # Nhấp các nút công cụ trên Hotbar
        hb.tool_buttons["crop"].click()
        app.processEvents()
        assert tab.edit_mode and tab.toolset == "edit" and tab.annot_controller.tool == "crop"

        hb.tool_buttons["hand"].click()
        app.processEvents()
        assert tab.annot_controller.tool == "pan"

        hb.tool_buttons["fill_sign"].click()
        app.processEvents()
        assert tab.edit_mode and tab.toolset == "fill" and tab.annot_controller.tool == "fill_sign"

        # Tuỳ chỉnh ẩn bớt nút trên Hotbar và ẩn hoàn toàn thanh nổi
        hb._toggle_tool_visibility("stamp", False)
        assert "stamp" not in hb.visible_tools()
        assert hb.tool_buttons["stamp"].isHidden()
        hb._toggle_tool_visibility("stamp", True)
        assert "stamp" in hb.visible_tools()

        hb.hideRequested.emit()
        app.processEvents()
        assert not hb.isVisible()
    finally:
        _close_cleanly(win)


def test_page_rotate_flip_crop_insert_duplicate_delete_undo_save(tmp_path: Path) -> None:
    app = _app()
    pdf = _make_asymmetric_pdf(tmp_path / "pages.pdf")
    win = _new_window(tmp_path)
    try:
        tab = win.open_pdf_path(pdf)
        app.processEvents()
        win.set_function_tab("edit")
        app.processEvents()

        # 1. Xoay trang 1 sang phải 90° qua EditSidebar rồi lưu Ctrl+S
        tab._on_edit_sidebar_action("page_rotate_right")
        assert tab.reader.has_unsaved_changes
        win.action_save()
        with fitz.open(str(pdf)) as check:
            assert check[0].rotation == 90

        # Xoay trái lại 90° để góc về 0° cho bài kiểm tra toạ độ pixel lật trang
        tab._on_edit_sidebar_action("page_rotate_left")
        win.action_save()
        with fitz.open(str(pdf)) as check:
            assert check[0].rotation == 0

        # 2. Lật ngang (Flip Horizontal): góc trên-trái đỏ -> sang phải (340, 60), trên-phải xanh lá -> sang trái (60, 60)
        tab._on_edit_sidebar_action("flip_horizontal")
        r_left = _sample_rgb(tab.reader.doc[0], 60, 60)
        r_right = _sample_rgb(tab.reader.doc[0], 340, 60)
        assert r_left[1] > 200 and r_right[0] > 200  # trái xanh lá, phải đỏ

        # Hoàn tác -> trở lại đỏ bên trái, xanh lá bên phải
        assert tab.annot_controller.undo()
        assert _sample_rgb(tab.reader.doc[0], 60, 60)[0] > 200
        assert _sample_rgb(tab.reader.doc[0], 340, 60)[1] > 200
        # Làm lại lật ngang + lật dọc (Flip Vertical: góc đỏ ở (340, 60) -> xuống (340, 540))
        assert tab.annot_controller.redo()
        tab._on_edit_sidebar_action("flip_vertical")
        assert _sample_rgb(tab.reader.doc[0], 340, 540)[0] > 200

        # Lưu và mở lại file từ đĩa để xác nhận thay đổi lật trang được ghi bền vững
        win.action_save()
        with fitz.open(str(pdf)) as check:
            assert _sample_rgb(check[0], 340, 540)[0] > 200

        # 3. Cắt trang (Crop) bằng thao tác kéo chuột công cụ "crop"
        orig_w, orig_h = tab.reader.get_page_size(0)
        tab.enter_edit_mode("crop", "edit")
        app.processEvents()
        _drag(tab.viewer, 0, (40, 50), (280, 400))
        new_w, new_h = tab.reader.get_page_size(0)
        assert abs(new_w - 240.0) < 2.0 and abs(new_h - 350.0) < 2.0
        assert (new_w, new_h) != (orig_w, orig_h)
        win.action_save()
        with fitz.open(str(pdf)) as check:
            assert abs(check[0].rect.width - 240.0) < 2.0
            assert abs(check[0].rect.height - 350.0) < 2.0

        # 4. Chèn trang trắng, nhân bản trang, xoá trang, Hoàn tác & Lưu
        assert tab.reader.page_count == 2
        tab._on_edit_sidebar_action("page_insert_blank")
        assert tab.reader.page_count == 3 and tab.thumb_list.count() == 3
        tab._on_edit_sidebar_action("page_duplicate")
        assert tab.reader.page_count == 4 and tab.thumb_list.count() == 4
        tab._on_edit_sidebar_action("page_delete")
        assert tab.reader.page_count == 3 and tab.thumb_list.count() == 3
        # Hoàn tác xoá -> trở lại 4 trang
        assert tab.annot_controller.undo()
        assert tab.reader.page_count == 4
        win.action_save()
        with fitz.open(str(pdf)) as check:
            assert check.page_count == 4
    finally:
        _close_cleanly(win)


def test_image_link_redact_hf_bates_bg_attach_watermark_sanitize_save(tmp_path: Path, monkeypatch) -> None:
    app = _app()
    pdf = _make_asymmetric_pdf(tmp_path / "full_edit.pdf")
    attach_src = tmp_path / "note_dinh_kem.txt"
    attach_src.write_text("Noi dung tep dinh kem", encoding="utf-8")
    png_bytes = _make_png_bytes()

    win = _new_window(tmp_path)
    try:
        tab = win.open_pdf_path(pdf)
        app.processEvents()
        win.set_function_tab("edit")
        app.processEvents()

        # 1. Chèn ảnh, xoay phải, lật ngang/dọc ảnh đang chọn
        tab.annot_controller.set_pending_image(png_bytes, "logo.png")
        tab.enter_edit_mode("image", "edit")
        app.processEvents()
        assert tab.edit_toolbar.isVisible() and tab.edit_toolbar.image_box.isVisible()
        _drag(tab.viewer, 0, (120, 120), (220, 180))
        assert tab.annot_controller.is_image_selected()
        assert tab.annot_controller.transform_selected_image(rotate_delta=90)
        assert tab.annot_controller.transform_selected_image(flip_h=True)
        assert tab.annot_controller.transform_selected_image(flip_v=True)

        # 2. Chèn liên kết URL qua kéo chuột
        from qtpdfpro.ui import page_edit_dialogs

        monkeypatch.setattr(page_edit_dialogs.LinkInsertDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
        monkeypatch.setattr(
            page_edit_dialogs.LinkInsertDialog,
            "values",
            lambda self: {"uri": "https://example.org/docs", "target_page": None},
        )
        tab.enter_edit_mode("link", "edit")
        _drag(tab.viewer, 0, (50, 300), (200, 330))
        assert tab.annot_controller.undo()
        assert tab.annot_controller.redo()

        # 3. Đánh dấu & áp dụng che vĩnh viễn từ SECRET_TOKEN
        hits = tab.annot_controller.search_and_mark_redactions("SECRET_TOKEN", 0)
        assert hits >= 2
        applied = tab.annot_controller.apply_redactions(0)
        assert applied >= 1

        # 4. Đầu trang & Chân trang, Đánh số Bates, Nền trang, Đính kèm tệp, Dấu nước tại chỗ, Làm sạch siêu dữ liệu
        tab.annot_controller.session.run_doc_operation(
            "Thêm đầu trang & chân trang",
            0,
            lambda d: page_edit.apply_header_footer_in_doc(d, header_center="HeaderTest", footer_right="P{page}"),
        )
        tab.annot_controller.session.run_doc_operation(
            "Đánh số Bates",
            0,
            lambda d: page_edit.apply_bates_in_doc(d, prefix="BATES-", start=1, digits=6),
        )
        tab.annot_controller.session.run_doc_operation(
            "Đặt nền trang",
            0,
            lambda d: page_edit.apply_background_in_doc(d, color="#FEF3C7", opacity=0.4),
        )
        monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(attach_src), ""))
        tab._on_edit_sidebar_action("attach_file")

        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("DAU_NUOC_TEST", True))
        tab._on_edit_sidebar_action("watermark_inplace")

        tab._on_edit_sidebar_action("sanitize_doc")

        # Lưu Ctrl+S và mở lại bằng PyMuPDF để kiểm tra từng thành phần trên đĩa
        win.action_save()
        with fitz.open(str(pdf)) as saved:
            text_p0 = saved[0].get_text("text")
            assert "SECRET_TOKEN" not in text_p0
            assert "HeaderTest" in text_p0
            assert "BATES-000001" in text_p0
            assert "DAU_NUOC_TEST" in text_p0
            assert any(lk.get("uri") == "https://example.org/docs" for lk in saved[0].get_links())
            assert "note_dinh_kem.txt" in saved.embfile_names()
            assert not (saved.metadata or {}).get("author")
    finally:
        _close_cleanly(win)


def test_read_tab_rotation_saves_cleanly(tmp_path: Path) -> None:
    app = _app()
    pdf = _make_asymmetric_pdf(tmp_path / "read_rot.pdf")
    win = _new_window(tmp_path)
    try:
        tab = win.open_pdf_path(pdf)
        app.processEvents()
        win.run_command("rotate_left")
        assert tab.reader.get_page_rotation(0) == 270
        assert tab.reader.has_pending_view_rotations
        win.action_save()
        with fitz.open(str(pdf)) as check:
            assert check[0].rotation == 270
    finally:
        _close_cleanly(win)


def _drag_widget(viewer, a: QPointF, b: QPointF, steps: int = 4) -> None:
    surface = viewer.widget()
    left = Qt.MouseButton.LeftButton
    _mouse(surface, QEvent.Type.MouseButtonPress, a, left)
    for i in range(1, steps + 1):
        q = QPointF(a.x() + (b.x() - a.x()) * i / steps, a.y() + (b.y() - a.y()) * i / steps)
        _mouse(surface, QEvent.Type.MouseMove, q, left, Qt.MouseButton.NoButton)
    _mouse(surface, QEvent.Type.MouseButtonRelease, b, Qt.MouseButton.NoButton)


def test_page_size_blank_pdf_and_resize_modes(tmp_path: Path) -> None:
    # 1. Quy đổi khổ giấy & tạo PDF trắng
    w_a4, h_a4 = page_edit.resolve_page_size_pt("A4", orientation="portrait")
    assert abs(w_a4 - 210.0 * page_edit.MM) < 0.1
    assert abs(h_a4 - 297.0 * page_edit.MM) < 0.1
    w_a5_l, h_a5_l = page_edit.resolve_page_size_pt("A5", orientation="landscape")
    assert w_a5_l > h_a5_l and abs(w_a5_l - 210.0 * page_edit.MM) < 0.1
    with pytest.raises(page_edit.PageEditError):
        page_edit.resolve_page_size_pt("custom", width_mm=10.0, height_mm=100.0)

    blank_bytes = page_edit.create_blank_pdf_bytes("A4", orientation="portrait", page_count=2)
    with fitz.open("pdf", blank_bytes) as doc:
        assert doc.page_count == 2
        assert abs(doc[0].rect.width - w_a4) < 0.5
        idx = page_edit.insert_sized_blank_page(doc, 0, preset="A5", orientation="landscape", count=1)
        assert idx == 1 and doc.page_count == 3
        assert abs(doc[1].rect.width - w_a5_l) < 0.5

    # 2. Đổi khổ trang cho tài liệu có nội dung + chú thích + liên kết ở các chế độ fit / center / stretch
    pdf = _make_asymmetric_pdf(tmp_path / "resize_src.pdf")
    with fitz.open(str(pdf)) as d:
        d[0].insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(40, 40, 120, 60), "uri": "https://qtpdfpro.local"})
        r_annot = d[0].add_rect_annot(fitz.Rect(50, 150, 150, 210))
        r_annot.set_colors(stroke=(1, 0, 0))
        r_annot.update()

        changed = page_edit.resize_pages_in_doc(d, preset="A4", orientation="portrait", scale_mode="fit", pages_spec="1")
        assert changed == 1
        assert abs(d[0].rect.width - w_a4) < 0.5 and abs(d[0].rect.height - h_a4) < 0.5
        assert "SECRET_TOKEN" in d[0].get_text("text")
        assert any(lk.get("uri") == "https://qtpdfpro.local" for lk in d[0].get_links())
        assert any(a.type[1] == "Square" for a in d[0].annots())

        # Trang 2 đổi sang A5 ngang bằng chế độ center (chữ vẫn giữ và giấy lớn/nhỏ theo A5)
        changed2 = page_edit.resize_pages_in_doc(d, preset="A5", orientation="landscape", scale_mode="center", pages_spec="2")
        assert changed2 == 1
        assert abs(d[1].rect.width - w_a5_l) < 0.5 and abs(d[1].rect.height - h_a5_l) < 0.5

        # Chế độ stretch sang custom 150x220 mm
        page_edit.resize_pages_in_doc(
            d, preset="custom", orientation="portrait", width_mm=150.0, height_mm=220.0, scale_mode="stretch", pages_spec="1"
        )
        assert abs(d[0].rect.width - 150.0 * page_edit.MM) < 0.5
        assert abs(d[0].rect.height - 220.0 * page_edit.MM) < 0.5


def test_embed_pdf_pages_and_8_handle_resize_undo_save(tmp_path: Path, monkeypatch) -> None:
    app = _app()
    # Tạo tệp đích khổ nhỏ (400 x 500 pt) và tệp nguồn gồm 3 trang vector
    target_pdf = _make_asymmetric_pdf(tmp_path / "target.pdf")
    source_pdf = tmp_path / "multi_source.pdf"
    src_doc = fitz.open()
    for i in range(3):
        pg = src_doc.new_page(width=300, height=420)
        pg.draw_rect(fitz.Rect(15, 15, 285, 405), color=(0.1, 0.3, 0.8), width=2)
        pg.insert_text(fitz.Point(40, 120), f"TrangNguonSo{i + 1} VECTOR_OK", fontsize=16)
    src_doc.save(str(source_pdf))
    src_doc.close()

    from qtpdfpro.ui import page_edit_dialogs

    win = _new_window(tmp_path)
    try:
        tab = win.open_pdf_path(target_pdf)
        app.processEvents()
        win.set_function_tab("edit")
        app.processEvents()

        # Import trang 1-2 từ source_pdf lên trang 1, tự đổi trang 1 sang A4 dọc
        monkeypatch.setattr(page_edit_dialogs.EmbedPdfDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
        monkeypatch.setattr(
            page_edit_dialogs.EmbedPdfDialog,
            "values",
            lambda self: {
                "source_path": str(source_pdf),
                "page_count": 3,
                "pages_spec": "1-2",
                "layout_mode": "grid_2",
                "margin_mm": 10.0,
                "gap_mm": 5.0,
                "border": True,
                "ensure_a4": True,
            },
        )
        tab._on_edit_sidebar_action("embed_pdf_pages")
        app.processEvents()

        # Trang đích giờ phải đúng khổ A4 dọc
        w_cur, h_cur = tab.reader.get_page_size(0)
        assert abs(w_cur - 210.0 * page_edit.MM) < 1.0
        assert abs(h_cur - 297.0 * page_edit.MM) < 1.0

        # Có 2 đối tượng pdfpage trên trang 1, trang nguồn 2 đang được chọn sẵn
        embedded = [i for i in tab.annot_controller.session.list_annotations() if i.app_kind == "pdfpage"]
        assert len(embedded) == 2
        assert tab.annot_controller.tool == "select"
        assert tab.annot_controller.is_pdf_page_selected()
        sel_page, sel_xref = tab.annot_controller.selected
        assert sel_page == 0
        orig_rect = tab.annot_controller.session.annotation_rect(0, sel_xref)
        assert orig_rect is not None
        orig_aspect = orig_rect.height / orig_rect.width

        # Kéo tay nắm góc dưới-phải ("se") thu nhỏ đối tượng pdfpage (mặc định giữ tỷ lệ)
        t = tab.viewer.page_transform(0)
        wr = tab.viewer.page_rect_to_widget(0, orig_rect, t).adjusted(-3, -3, 3, 3)
        se_center = tab.annot_controller._widget_handle_rects(wr)["se"].center()
        _drag_widget(tab.viewer, se_center, QPointF(se_center.x() - 40.0, se_center.y() - 40.0))
        app.processEvents()

        shrunk_rect = tab.annot_controller.session.annotation_rect(0, sel_xref)
        assert shrunk_rect is not None
        assert shrunk_rect.width < orig_rect.width - 5.0
        assert abs((shrunk_rect.height / shrunk_rect.width) - orig_aspect) < 0.05

        # Kéo tay nắm cạnh phải ("e") mở rộng ngang (chỉ đổi chiều rộng)
        wr2 = tab.viewer.page_rect_to_widget(0, shrunk_rect, tab.viewer.page_transform(0)).adjusted(-3, -3, 3, 3)
        e_center = tab.annot_controller._widget_handle_rects(wr2)["e"].center()
        _drag_widget(tab.viewer, e_center, QPointF(e_center.x() + 30.0, e_center.y()))
        app.processEvents()
        widened_rect = tab.annot_controller.session.annotation_rect(0, sel_xref)
        assert widened_rect is not None and widened_rect.width > shrunk_rect.width + 5.0

        # Xoay 90° & Lật ngang trang PDF nhúng đang chọn
        assert tab.annot_controller.transform_selected_image(rotate_delta=90)
        assert tab.annot_controller.transform_selected_image(flip_h=True)

        # Kiểm tra Hoàn tác / Làm lại thao tác đổi kích thước & biến đổi
        assert tab.annot_controller.undo()
        assert tab.annot_controller.redo()

        # Kiểm tra kéo 8 tay nắm cho Khung chữ nhật (Square) và Hộp chữ (textbox)
        box_xref = tab.annot_controller.session.add_shape(
            0, "rect", fitz.Point(60, 500), fitz.Point(160, 560), tab.annot_controller.style("rect")
        )
        tab.annot_controller.select(0, box_xref)
        r_sq0 = tab.annot_controller.session.annotation_rect(0, box_xref)
        wr_sq = tab.viewer.page_rect_to_widget(0, r_sq0, tab.viewer.page_transform(0)).adjusted(-3, -3, 3, 3)
        se_sq = tab.annot_controller._widget_handle_rects(wr_sq)["se"].center()
        _drag_widget(tab.viewer, se_sq, QPointF(se_sq.x() + 35.0, se_sq.y() + 25.0))
        r_sq1 = tab.annot_controller.session.annotation_rect(0, box_xref)
        assert r_sq1.width > r_sq0.width + 10.0 and r_sq1.height > r_sq0.height + 10.0

        # Lưu Ctrl+S và mở lại kiểm tra dữ liệu pdf_z64 giữ nguyên cho phép kéo cỡ tiếp sau khi mở lại
        win.action_save()
        with fitz.open(str(target_pdf)) as check:
            assert abs(check[0].rect.width - 210.0 * page_edit.MM) < 1.0
            annots_pdf = [a for a in check[0].annots() if (check.xref_get_key(a.xref, "Name")[1] or "").endswith(page_edit.APP_PDF_PAGE_NAME)]
            assert len(annots_pdf) == 2
            # Thử resize sau khi mở lại từ đĩa (dùng pdf_z64 nhúng sẵn trong chú thích)
            resized = page_edit.resize_annotation_in_page(check[0], annots_pdf[0].xref, fitz.Rect(20, 20, 200, 280))
            assert abs(resized.width - 180.0) < 2.0
    finally:
        _close_cleanly(win)


def test_new_blank_pdf_action_and_cli_resize(tmp_path: Path, monkeypatch, capsys) -> None:
    app = _app()
    from qtpdfpro import cli
    from qtpdfpro.ui import page_edit_dialogs

    # 1. Tạo PDF trắng mới qua action_new_blank_pdf
    new_pdf = tmp_path / "tao_moi_a4.pdf"
    monkeypatch.setattr(page_edit_dialogs.InsertBlankPageDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(
        page_edit_dialogs.InsertBlankPageDialog,
        "values",
        lambda self: {
            "preset": "A4",
            "orientation": "portrait",
            "width_mm": 210.0,
            "height_mm": 297.0,
            "count": 2,
            "position": "after",
        },
    )
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(new_pdf), ""))
    win = _new_window(tmp_path)
    try:
        win.run_command("new_blank_pdf")
        app.processEvents()
        assert new_pdf.is_file()
        tab = win.active_tab()
        assert tab is not None and tab.reader.page_count == 2
        w, h = tab.reader.get_page_size(0)
        assert abs(w - 210.0 * page_edit.MM) < 1.0 and abs(h - 297.0 * page_edit.MM) < 1.0
    finally:
        _close_cleanly(win)

    # 2. Lệnh CLI resize --json
    src = _make_asymmetric_pdf(tmp_path / "cli_src.pdf")
    out = tmp_path / "cli_a4.pdf"
    rc = cli.main(["resize", str(src), "-o", str(out), "--size", "A4", "--mode", "fit", "--json"])
    assert rc == 0
    payload = capsys.readouterr().out
    assert '"pages_changed": 2' in payload
    with fitz.open(str(out)) as check:
        assert abs(check[0].rect.width - 210.0 * page_edit.MM) < 1.0
