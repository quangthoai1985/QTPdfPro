"""Kiểm thử giao diện «Điền & Ký»: chế độ trên thanh chế độ, thao tác chuột thật trên khung đọc (gõ chữ bắt dòng chấm,
dấu ✓ vào ô, ngày, chữ ký — tạo chữ ký lần đầu rồi đặt luôn), hộp thoại tạo chữ ký & thư viện chữ ký.

Không mở hộp thoại modal thật (QInputDialog / SignatureCreateDialog.exec / QMessageBox được giả lập)."""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QDialog, QInputDialog, QMessageBox

from qtpdfpro.core import fill_sign as fs
from qtpdfpro.core.settings import AppSettings
from qtpdfpro.ui import main_window as mw
from qtpdfpro.ui.main_window import MainWindow
from qtpdfpro.ui.signature_dialog import SignatureCreateDialog, SignatureManagerDialog

FONT = r"C:\Windows\Fonts\times.ttf"
pytestmark = pytest.mark.skipif(not Path(FONT).exists(), reason="Cần phông Times New Roman của Windows")


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _mouse(widget, kind: QEvent.Type, pos: QPointF, buttons, button=Qt.MouseButton.LeftButton) -> None:
    gpos = QPointF(widget.mapToGlobal(pos.toPoint()))
    QApplication.sendEvent(widget, QMouseEvent(kind, pos, gpos, button, buttons, Qt.KeyboardModifier.NoModifier))


def _click(viewer, page: int, p, p_end=None) -> None:
    surface = viewer.widget()
    t = viewer.page_transform(page)
    a = t.map(QPointF(*p))
    b = t.map(QPointF(*(p_end or p)))
    left = Qt.MouseButton.LeftButton
    _mouse(surface, QEvent.Type.MouseMove, a, Qt.MouseButton.NoButton, Qt.MouseButton.NoButton)
    _mouse(surface, QEvent.Type.MouseButtonPress, a, left)
    if p_end is not None:
        for i in range(1, 5):
            q = QPointF(a.x() + (b.x() - a.x()) * i / 4, a.y() + (b.y() - a.y()) * i / 4)
            _mouse(surface, QEvent.Type.MouseMove, q, left, Qt.MouseButton.NoButton)
    _mouse(surface, QEvent.Type.MouseButtonRelease, b, Qt.MouseButton.NoButton)


def _form_pdf(path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Họ và tên: ……………………………………………………", fontsize=13, fontname="T", fontfile=FONT)
    page.insert_text((72, 140), "Đồng ý:", fontsize=13, fontname="T", fontfile=FONT)
    page.draw_rect(fitz.Rect(130, 129, 141, 140), width=0.8)
    doc.save(str(path))
    return path


def _photo() -> bytes:
    import cv2
    import numpy as np

    img = np.full((300, 500, 3), 225, np.uint8)
    cv2.polylines(img, [np.array([[60, 200], [120, 80], [180, 220], [260, 90], [400, 200]], np.int32)],
                  False, (150, 60, 30), 5, cv2.LINE_AA)
    return cv2.imencode(".jpg", img)[1].tobytes()


def test_fill_mode_with_mouse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app()
    win = MainWindow(settings=AppSettings.load())
    win.resize(1400, 900)
    win.show()
    tab = win.open_pdf_path(_form_pdf(tmp_path / "don.pdf"))
    app.processEvents()
    viewer = tab.viewer
    ctl = tab.annot_controller

    # Nút chế độ «Điền & Ký» → thanh Điền & Ký hiện, thanh Chỉnh sửa ẩn
    assert "fill" in win.mode_buttons and "fill" in mw.STRIP_TOOLS
    win.mode_buttons["fill"].click()
    app.processEvents()
    assert tab.edit_mode and tab.toolset == "fill"
    assert tab.fill_toolbar.isVisible() and not tab.edit_toolbar.isVisible()
    assert ctl.tool == "fill_text"
    assert set(tab.fill_toolbar.tool_buttons) >= {"fill_text", "fill_check", "fill_date", "fill_sign", "select"}
    assert "highlight" not in tab.fill_toolbar.tool_buttons
    assert tab.fill_toolbar.minimumSizeHint().width() < 500 and win.minimumSizeHint().width() <= 1400

    # Rê chuột lên dòng chấm → khung xem trước nằm trên dòng chấm
    t = viewer.page_transform(0)
    _mouse(viewer.widget(), QEvent.Type.MouseMove, t.map(QPointF(220, 95)), Qt.MouseButton.NoButton,
           Qt.MouseButton.NoButton)
    assert ctl._fill_hover is not None and ctl._fill_hover[2] == "text"
    assert ctl._fill_hover[1].y1 == pytest.approx(100, abs=4)

    # Gõ chữ: nhấp lên dòng chấm → chữ tự nằm đúng dòng
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Phạm Minh Châu", True)))
    _click(viewer, 0, (220, 95))
    app.processEvents()
    ses = ctl.session
    infos = ses.list_annotations()
    assert [i.label for i in infos] == ["Chữ điền"] and infos[0].content == "Phạm Minh Châu"
    assert infos[0].rect[1] < 100 < infos[0].rect[3]
    assert tab.reader.has_unsaved_changes

    # ✓ vào ô vuông
    tab.fill_toolbar.tool_buttons["fill_check"].click()
    _click(viewer, 0, (137, 137))
    # Ngày theo mẫu NĐ30
    ctl.set_tool("fill_date")
    tab.fill_toolbar.date_combo.setCurrentIndex(tab.fill_toolbar.date_combo.findData("nd30"))
    assert ctl.date_format == "nd30"
    _click(viewer, 0, (350, 300))
    app.processEvents()
    infos = ses.list_annotations()
    mark = next(i for i in infos if i.label == "Dấu điền")
    assert abs((mark.rect[0] + mark.rect[2]) / 2 - 135.5) < 0.6
    assert any(i.content == fs.format_date("nd30") for i in infos)

    # Chữ ký: thư viện trống → hộp thoại tạo chữ ký (giả lập) → đặt luôn vào chỗ đã nhấp
    created = []

    class FakeCreate:
        def __init__(self, library, initials=False, name="", parent=None):
            self.library = library
            self.signature = fs.Signature("typed", initials, text="P.M.Châu")

        def exec(self):
            self.library.save(self.signature)
            created.append(self.signature)
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(mw, "SignatureCreateDialog", FakeCreate)
    ctl.set_tool("fill_sign")
    _click(viewer, 0, (400, 600))
    app.processEvents()
    assert len(created) == 1
    sig_info = [i for i in ses.list_annotations() if i.label == "Chữ ký"]
    assert len(sig_info) == 1
    cx = (sig_info[0].rect[0] + sig_info[0].rect[2]) / 2
    assert cx == pytest.approx(400, abs=1)
    assert ctl.current_signature(False).id == created[0].id
    assert tab.fill_toolbar.sig_combo.findData(created[0].id) >= 0
    # Lần sau: đặt thẳng (kéo khung để chọn cỡ), không hỏi lại
    _click(viewer, 0, (100, 650), (200, 690))
    app.processEvents()
    assert len(created) == 1
    sigs = [i for i in ses.list_annotations() if i.label == "Chữ ký"]
    assert len(sigs) == 2 and sigs[1].rect[2] - sigs[1].rect[0] <= 100.5

    # Hoàn tác / sửa chữ điền bằng nhấp đúp
    assert ctl.undo() and len(ses.list_annotations()) == 4
    xref = ses.list_annotations()[0].xref
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Phạm Minh Châu Anh", True)))
    assert ctl.edit_annotation(0, xref)
    assert ses.list_annotations()[0].content == "Phạm Minh Châu Anh"

    # Chuyển sang «Chỉnh sửa» → thanh Chỉnh sửa, công cụ của bộ đó; Ctrl+Shift+F quay lại Điền & Ký rồi tắt
    win.set_mode_category("edit")
    app.processEvents()
    assert tab.toolset == "edit" and tab.edit_toolbar.isVisible() and not tab.fill_toolbar.isVisible()
    assert ctl.tool == "highlight"
    win.act_fill_sign.trigger()
    assert tab.toolset == "fill" and tab.fill_toolbar.isVisible() and win.mode_buttons["fill"].isChecked()
    win.act_fill_sign.trigger()
    assert not tab.edit_mode

    # Lưu (ghi bổ sung) giữ chú thích
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    win.action_save()
    reopened = fitz.open(str(tmp_path / "don.pdf"))
    assert sum(1 for _ in reopened[0].annots()) == 4
    reopened.close()
    win.close()


def test_signature_create_dialog_tabs(tmp_path: Path) -> None:
    _app()
    lib = fs.SignatureLibrary(tmp_path / "sigs")
    dlg = SignatureCreateDialog(lib, initials=False, name="Chính")
    assert not dlg.btn_ok.isEnabled()
    # Vẽ
    dlg.pad.set_strokes([[(20, 100), (60, 40), (100, 120), (150, 50)], [(30, 130), (200, 125)]])
    sig = dlg.build_signature()
    assert sig is not None and sig.kind == "drawn" and sig.name == "Chính" and 0.005 < sig.pen < 0.05
    assert dlg.btn_ok.isEnabled()
    # Gõ tên: phông thiếu chữ Việt → báo lùi về Times nghiêng
    dlg.tabs.setCurrentIndex(dlg.TAB_TYPE)
    dlg.type_edit.setText("Phạm Thị Hường")
    idx = dlg.font_combo.findData("segoe_script")
    if idx >= 0:
        dlg.font_combo.setCurrentIndex(idx)
        assert "Times New Roman" in dlg.type_note.text()
    assert dlg.build_signature().kind == "typed" and dlg.type_preview.pixmap() is not None
    # Ảnh chụp → tách nền; độ nhạy đổi thì xử lý lại
    dlg.set_image_bytes(_photo(), photo=True)
    assert dlg._photo_png and dlg.build_signature().kind == "image"
    dlg.kind_ini.setChecked(True)
    dlg._on_save()
    assert dlg.result() == QDialog.DialogCode.Accepted and dlg.signature.initials
    assert [s.id for s in lib.list(initials=True)] == [dlg.signature.id]
    # Ảnh có sẵn: ảnh hỏng báo lỗi, không cho lưu
    dlg2 = SignatureCreateDialog(lib)
    dlg2.set_image_bytes(b"khong phai anh", photo=False)
    assert dlg2._image_png is None and not dlg2.btn_ok.isEnabled()


def test_signature_manager_dialog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _app()
    lib = fs.SignatureLibrary(tmp_path / "sigs")
    lib.save(fs.Signature("typed", text="Cũ"))
    calls = []

    def fake_create(parent, initials):
        sig = fs.Signature("typed", initials, text="Mới")
        lib.save(sig)
        calls.append(initials)
        return sig

    dlg = SignatureManagerDialog(lib, None, create_dialog=fake_create)
    assert dlg.list.count() == 1
    sig = dlg.create_new(True)
    assert calls == [True] and dlg.list.count() == 2 and dlg.created == [sig]
    assert dlg._current_id() == sig.id
    dlg._use()
    assert dlg.chosen_id == sig.id
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    dlg.list.setCurrentRow(0)
    dlg._delete()
    assert dlg.list.count() == 1 and len(lib.list()) == 1
