"""Kiểm thử giao diện «Chỉnh sửa PDF»: chế độ chú thích trên khung đọc (thao tác chuột thật qua `PDFScrollViewer`)
và hộp thoại «Sắp xếp & cắt ghép trang»."""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF
import pytest
from PySide6.QtCore import QEvent, QModelIndex, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog

from qtpdfpro.core.settings import AppSettings
from qtpdfpro.ui import annotation_tools
from qtpdfpro.ui.main_window import MainWindow
from qtpdfpro.ui.organizer_dialog import PageOrganizerDialog


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _mouse(widget, kind: QEvent.Type, pos: QPointF, buttons, button=Qt.MouseButton.LeftButton,
           mods=Qt.KeyboardModifier.NoModifier) -> None:
    gpos = QPointF(widget.mapToGlobal(pos.toPoint()))
    QApplication.sendEvent(widget, QMouseEvent(kind, pos, gpos, button, buttons, mods))


def _drag(viewer, page: int, p0, p1, steps: int = 4) -> None:
    """Kéo chuột trái trên trang `page` từ `p0` tới `p1` (toạ độ trang chưa xoay)."""
    surface = viewer.widget()
    t = viewer.page_transform(page)
    a, b = t.map(QPointF(*p0)), t.map(QPointF(*p1))
    left = Qt.MouseButton.LeftButton
    _mouse(surface, QEvent.Type.MouseButtonPress, a, left)
    for i in range(1, steps + 1):
        q = QPointF(a.x() + (b.x() - a.x()) * i / steps, a.y() + (b.y() - a.y()) * i / steps)
        _mouse(surface, QEvent.Type.MouseMove, q, left, Qt.MouseButton.NoButton)
    _mouse(surface, QEvent.Type.MouseButtonRelease, b, Qt.MouseButton.NoButton)


def _click(viewer, page: int, p) -> None:
    _drag(viewer, page, p, p, steps=1)


def test_edit_mode_annotate_with_mouse_undo_save(sample_vietnamese_pdf: Path, monkeypatch) -> None:
    app = _app()
    win = MainWindow(settings=AppSettings.load())
    win.resize(1400, 900)
    win.show()
    tab = win.open_pdf_path(sample_vietnamese_pdf)
    app.processEvents()
    viewer = tab.viewer

    win.run_tool("edit_pdf")
    app.processEvents()
    assert tab.edit_mode is True and tab.edit_toolbar.isVisible()
    assert tab.annot_controller.tool == "highlight"

    # Tô sáng: kéo qua cụm "Độc lập - Tự do" ở dòng tiêu ngữ
    page = tab.reader.doc[0]
    hit = page.search_for("Độc lập")[0]
    _drag(viewer, 0, (hit.x0 + 1, (hit.y0 + hit.y1) / 2), (hit.x1 + 30, (hit.y0 + hit.y1) / 2))
    app.processEvents()
    ses = tab.annot_controller.session
    kinds = [i.subtype for i in ses.list_annotations()]
    assert kinds == ["Highlight"]
    assert ses.list_annotations()[0].content.startswith("Độc lập")
    assert win.doc_tab_bar.tabText(win.doc_tabs.indexOf(tab)).startswith("● ")

    # Hoàn tác / Làm lại bằng phím tắt của cửa sổ
    win.act_undo.trigger()
    assert ses.list_annotations() == []
    win.act_redo.trigger()
    assert len(ses.list_annotations()) == 1

    # Bút vẽ tay
    tab.annot_controller.set_tool("pen")
    _drag(viewer, 0, (300, 500), (420, 560), steps=6)
    # Dấu đóng rồi kéo đi bằng công cụ Chọn
    tab.annot_controller.set_tool("stamp")
    _click(viewer, 0, (420, 650))
    stamp = [i for i in ses.list_annotations() if i.subtype == "Stamp"][0]
    tab.annot_controller.set_tool("select")
    before = ses.annotation_rect(0, stamp.xref)
    _drag(viewer, 0, (420, 650), (440, 690))
    after = ses.annotation_rect(0, stamp.xref)
    assert after.x0 == pytest.approx(before.x0 + 20, abs=1.5)
    assert after.y0 == pytest.approx(before.y0 + 40, abs=1.5)

    # Hộp chữ & ghi chú (hộp nhập liệu được giả lập)
    monkeypatch.setattr(annotation_tools.QInputDialog, "getMultiLineText",
                        staticmethod(lambda *a, **k: ("Nội dung chú thích tiếng Việt", True)))
    tab.annot_controller.set_tool("text")
    _drag(viewer, 0, (60, 700), (260, 712))
    tab.annot_controller.set_tool("note")
    _click(viewer, 0, (540, 120))
    kinds = [i.subtype for i in ses.list_annotations()]
    assert kinds == ["Highlight", "Ink", "Stamp", "FreeText", "Text"]

    # Tẩy nét vẽ
    tab.annot_controller.set_tool("eraser")
    _click(viewer, 0, (300, 500))
    assert "Ink" not in [i.subtype for i in ses.list_annotations()]

    # Ngăn «Chú thích» liệt kê đúng số chú thích
    tab.show_annotation_panel()
    app.processEvents()
    assert tab.annot_panel.list.count() == 4

    # Lưu (ghi bổ sung) → tiêu đề tab hết dấu ●, tệp có chú thích
    win.action_save()
    app.processEvents()
    assert tab.reader.has_unsaved_changes is False
    assert win.doc_tab_bar.tabText(win.doc_tabs.indexOf(tab)).startswith("📄 ")
    tab.exit_edit_mode()
    assert viewer.interaction is None
    win.close_tab_at(0)
    app.processEvents()
    with fitz.open(str(sample_vietnamese_pdf)) as doc:
        assert [a.type[1] for a in doc[0].annots()] == ["Highlight", "Stamp", "FreeText", "Text"]
    win.close()


def test_close_tab_asks_when_unsaved(sample_vietnamese_pdf: Path) -> None:
    app = _app()
    win = MainWindow(settings=AppSettings.load())
    win.show()
    tab = win.open_pdf_path(sample_vietnamese_pdf)
    tab.enter_edit_mode("stamp")
    app.processEvents()
    _click(tab.viewer, 0, (300, 300))
    assert tab.reader.has_unsaved_changes
    asked = []
    win._confirm_close_tab = lambda t: asked.append(t) or False  # người dùng bấm «Huỷ»
    win.close_tab_at(0)
    assert asked and win.doc_tabs.count() == 1
    win.close_tab_at(0, force=True)
    assert win.doc_tabs.count() == 0
    app.processEvents()
    win.close()


def test_mode_bar_edit_category_toggles_edit_mode(sample_vietnamese_pdf: Path) -> None:
    app = _app()
    win = MainWindow(settings=AppSettings.load())
    win.show()
    tab = win.open_pdf_path(sample_vietnamese_pdf)
    win.set_mode_category("edit")
    app.processEvents()
    assert tab.edit_mode and tab.tool_btn_organize.isVisible() and not tab.tool_btn_rot_left.isVisible()
    win.set_mode_category("read")
    app.processEvents()
    assert not tab.edit_mode
    win.set_mode_category("all")
    win.close_tab_at(0, force=True)
    win.close()


def _make_pdf(path: Path, n: int, label: str) -> Path:
    doc = fitz.open()
    for i in range(n):
        doc.new_page().insert_text((72, 72), f"{label} trang {i + 1}", fontsize=16)
    doc.save(str(path))
    doc.close()
    return path


def _texts(path: Path) -> list[str]:
    with fitz.open(str(path)) as doc:
        return [p.get_text().strip() for p in doc]


def test_page_organizer_dialog_operations(tmp_path: Path, monkeypatch) -> None:
    app = _app()
    a = _make_pdf(tmp_path / "A.pdf", 4, "A")
    b = _make_pdf(tmp_path / "B.pdf", 2, "B")
    doc_a = fitz.open(str(a))
    dlg = PageOrganizerDialog(sources=[(str(a), doc_a, "A.pdf")], theme="light")
    dlg.show()
    app.processEvents()
    assert dlg.page_count == 4 and dlg.grid.count() == 4

    dlg.select_rows([0])
    dlg.rotate_selected(90)
    assert dlg.refs()[0].rotation == 90
    dlg.select_rows([1])
    dlg.duplicate_selected()
    assert [r.page_index for r in dlg.refs()] == [0, 1, 1, 2, 3]
    dlg.select_rows([2])
    dlg.delete_selected()
    dlg.select_rows([3])
    dlg.insert_blank()
    assert [r.page_index for r in dlg.refs()] == [0, 1, 2, 3, None]
    dlg.select_rows([3])
    dlg.move_selected(-1)
    assert [r.page_index for r in dlg.refs()] == [0, 1, 3, 2, None]
    dlg.undo()
    assert [r.page_index for r in dlg.refs()] == [0, 1, 2, 3, None]
    dlg.redo()
    assert [r.page_index for r in dlg.refs()] == [0, 1, 3, 2, None]

    # Kéo thả (Qt gọi moveRow) → thứ tự lưới đổi theo
    dlg.grid.model().moveRow(QModelIndex(), 0, QModelIndex(), 3)
    app.processEvents()
    assert [r.page_index for r in dlg.refs()] == [1, 3, 0, 2, None]

    # Ghép thêm tệp B sau trang đang chọn, đặt điểm cắt
    dlg.select_rows([4])
    assert dlg.add_files([str(b)]) == 2
    assert [r.page_index for r in dlg.refs()][-2:] == [0, 1]
    dlg.select_rows([4])
    dlg.toggle_split()
    assert [len(p) for p in dlg.marker_parts()] == [5, 2]
    assert dlg.part_index_of(6) == 1

    out = tmp_path / "ket_qua.pdf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out), "")))
    dlg.save_all()
    assert dlg.result_kind == "file" and dlg.result_paths == [out]
    assert _texts(out) == ["A trang 2", "A trang 4", "A trang 1", "A trang 3", "", "B trang 1", "B trang 2"]
    with fitz.open(str(out)) as doc:
        assert doc[2].rotation == 90
        assert [t[1] for t in doc.get_toc()] == ["A", "B"]

    # Tách theo điểm cắt
    dlg2 = PageOrganizerDialog(sources=[(str(a), doc_a, "A.pdf")])
    dlg2.select_rows([1])
    dlg2.toggle_split()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(tmp_path / "phan")))
    (tmp_path / "phan").mkdir()
    dlg2.export_parts()
    assert dlg2.result_kind == "parts"
    assert [p.name for p in dlg2.result_paths] == ["A_phan_01.pdf", "A_phan_02.pdf"]
    assert _texts(dlg2.result_paths[1]) == ["A trang 3", "A trang 4"]
    assert not doc_a.is_closed  # tài liệu của tab không bị đóng
    doc_a.close()


def test_organizer_overwrite_open_document(sample_vietnamese_pdf: Path, monkeypatch) -> None:
    """Lưu đè lên tệp đang mở: tab được đóng, ghi tệp, mở lại đúng vị trí."""
    from PySide6.QtWidgets import QMessageBox

    app = _app()
    win = MainWindow(settings=AppSettings.load())
    win.show()
    tab = win.open_pdf_path(sample_vietnamese_pdf)
    app.processEvents()
    dlg = PageOrganizerDialog(
        win, sources=[(str(tab.reader.path), tab.reader.doc, "x")],
        is_locked=lambda p: win._tab_for_path(p) is not None, overwrite_handler=win._overwrite_open_document,
    )
    dlg.select_rows([1])
    dlg.delete_selected()
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(sample_vietnamese_pdf), "")))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    dlg.save_all()
    app.processEvents()
    assert dlg.result_kind == "overwrite"
    new_tab = win.active_tab()
    assert new_tab is not None and new_tab is not tab and new_tab.reader.page_count == 1
    win.close_tab_at(0, force=True)
    win.close()
