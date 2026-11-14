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
