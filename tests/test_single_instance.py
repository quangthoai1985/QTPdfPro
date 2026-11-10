"""«Một cửa sổ duy nhất» (V1): mở nhiều PDF cùng lúc → một cửa sổ, mỗi tệp một tab (như Foxit Reader)."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from qtpdfpro.core import single_instance as si
from qtpdfpro.ui import single_instance as ui_si

ROOT = Path(__file__).resolve().parents[1]


def _pump_until(predicate, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def _unique_name() -> str:
    return f"QTPdfPro.Test.{uuid.uuid4().hex[:12]}"


def _child(code: str) -> subprocess.Popen:
    """Chạy phía gửi ở tiến trình riêng (như thật). Không dùng luồng Python: các hàm chờ chặn của QLocalSocket
    giữ GIL nên khe xử lý của máy chủ ở luồng chính không chạy được."""
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=str(ROOT))
    return subprocess.Popen([sys.executable, "-c", code], env=env)


# ─── Phần lõi (không Qt) ────────────────────────────────────────────────────


def test_channel_name_depends_on_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_PDF_PRO_DATA", str(tmp_path / "a"))
    a = si.channel_name()
    assert a == si.channel_name()
    monkeypatch.setenv("QT_PDF_PRO_DATA", str(tmp_path / "b"))
    b = si.channel_name()
    assert a != b
    assert a.startswith("QTPdfPro.Instance.") and "\\" not in a and "/" not in a


def test_normalize_paths_absolute_and_deduplicated(tmp_path):
    out = si.normalize_paths(["a.pdf", str(tmp_path / "a.pdf"), "", "sub/../b.pdf"], cwd=tmp_path)
    assert out == [str((tmp_path / "a.pdf").resolve()), str((tmp_path / "b.pdf").resolve())]


def test_message_roundtrip_vietnamese_paths():
    files = [r"C:\Tài liệu\Quyết định số 12.pdf", r"D:\a & b.pdf"]
    data = si.encode_message(files)
    assert data.endswith(b"\n") and data.count(b"\n") == 1
    assert si.decode_message(data) == files
    assert si.decode_message(si.encode_message([])) == []


@pytest.mark.parametrize("bad", [b"", b"not json\n", b"[1,2]\n", b'{"files": "x"}\n', b'{"files": [1]}\n', b"\xff\xfe\n"])
def test_decode_rejects_malformed(bad):
    assert si.decode_message(bad) is None


@pytest.mark.skipif(sys.platform != "win32", reason="mutex có tên chỉ có trên Windows")
def test_primary_lock_only_one_holder():
    name = _unique_name()
    first, second = si.PrimaryLock(name), si.PrimaryLock(name)
    try:
        assert first.acquire()
        assert first.acquire()  # gọi lại vẫn giữ
        assert not second.acquire()
        first.release()
        assert second.acquire()  # người giữ trước thoát → người sau thành tiến trình chính
    finally:
        first.release()
        second.release()


# ─── Kênh Qt ────────────────────────────────────────────────────────────────


def test_server_receives_files_and_acknowledges(qapp):
    name = _unique_name()
    server = ui_si.InstanceServer(name)
    assert server.listen()
    received: list = []
    server.filesRequested.connect(received.append)
    files = [r"C:\Văn bản\một.pdf", r"C:\Văn bản\hai.pdf"]
    proc = _child(
        "import sys\nfrom PySide6.QtCore import QCoreApplication\nfrom qtpdfpro.ui.single_instance import send_to_primary\n"
        f"app = QCoreApplication([])\nsys.exit(0 if send_to_primary({name!r}, {files!r}, 5000, 10000) else 3)"
    )
    try:
        assert _pump_until(lambda: received and proc.poll() is not None, timeout=40)
    finally:
        if proc.poll() is None:
            proc.kill()
        server.close()
    assert received == [files]
    assert proc.returncode == 0  # đã nhận xác nhận «ok»


def test_send_without_server_gives_up(qapp):
    started = time.monotonic()
    assert ui_si.send_to_primary(_unique_name(), ["x.pdf"], connect_timeout_ms=600) is False
    assert time.monotonic() - started < 5


def test_requests_before_attach_are_replayed_in_order(qapp):
    inst = ui_si.SingleInstance(name=_unique_name())
    try:
        assert inst.start([]) == ui_si.SingleInstance.PRIMARY
        inst.server.filesRequested.emit(["a.pdf"])
        inst.server.filesRequested.emit(["b.pdf", "c.pdf"])
        got: list = []
        inst.attach(got.append)
        assert got == [["a.pdf"], ["b.pdf", "c.pdf"]]
        inst.server.filesRequested.emit([])
        assert got[-1] == []
    finally:
        inst.shutdown()


@pytest.mark.skipif(sys.platform != "win32", reason="bầu tiến trình chính bằng mutex Windows")
def test_second_instance_forwards_to_running_one(qapp):
    name = _unique_name()
    primary = ui_si.SingleInstance(name=name)
    secondary = ui_si.SingleInstance(name=name)
    try:
        assert primary.start([]) == ui_si.SingleInstance.PRIMARY
        got: list = []
        primary.attach(got.append)
        assert not secondary.lock.acquire()  # mutex đã có người giữ
        proc = _child(
            "import sys\nfrom PySide6.QtCore import QCoreApplication\nfrom qtpdfpro.ui.single_instance import SingleInstance\n"
            f"app = QCoreApplication([])\nsys.exit(0 if SingleInstance(name={name!r}).start(['x.pdf']) == 'forwarded' else 3)"
        )
        try:
            assert _pump_until(lambda: got and proc.poll() is not None, timeout=40)
        finally:
            if proc.poll() is None:
                proc.kill()
        assert proc.returncode == 0
        assert got == [["x.pdf"]]
    finally:
        secondary.shutdown()
        primary.shutdown()


@pytest.mark.skipif(sys.platform != "win32", reason="bầu tiến trình chính bằng mutex Windows")
def test_real_second_process_forwards_files_and_exits(qapp, sample_pdf, tmp_path):
    """Tiến trình thật `python -m qtpdfpro tệp.pdf` thấy ứng dụng đang chạy → gửi tệp, thoát mã 0, không mở cửa sổ."""
    primary = ui_si.SingleInstance()  # cùng QT_PDF_PRO_DATA tạm (conftest) → cùng tên kênh với tiến trình con
    try:
        assert primary.start([]) == ui_si.SingleInstance.PRIMARY
        got: list = []
        primary.attach(got.append)
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=str(ROOT))
        rel = os.path.relpath(sample_pdf, tmp_path)
        proc = subprocess.Popen([sys.executable, "-m", "qtpdfpro", rel], cwd=tmp_path, env=env)
        try:
            assert _pump_until(lambda: got and proc.poll() is not None, timeout=60)
        finally:
            if proc.poll() is None:
                proc.kill()
        assert proc.returncode == 0
        assert got == [[str(Path(sample_pdf).resolve())]]  # đường dẫn tương đối → tuyệt đối theo thư mục của tiến trình con
    finally:
        primary.shutdown()


# ─── Cửa sổ chính ───────────────────────────────────────────────────────────


def test_open_files_from_instance_opens_tabs_and_restores_window(qapp, sample_pdf, sample_vietnamese_pdf):
    from qtpdfpro.core.settings import AppSettings
    from qtpdfpro.ui import app as gui_app
    from qtpdfpro.ui.main_window import MainWindow

    win = MainWindow(settings=AppSettings.load())
    try:
        win.show()
        win.setWindowState(Qt.WindowState.WindowMinimized)
        QApplication.processEvents()
        gui_app.open_files_from_instance(win, [str(sample_pdf), str(sample_vietnamese_pdf)])
        QApplication.processEvents()
        assert win.doc_tabs.count() == 2
        assert not win.windowState() & Qt.WindowState.WindowMinimized
        # Gửi lại tệp đã mở → chuyển tới tab đó, không mở thêm
        gui_app.open_files_from_instance(win, [str(sample_pdf)])
        assert win.doc_tabs.count() == 2
        assert win.doc_tabs.currentIndex() == 0
        # Danh sách rỗng (bấm lối tắt khi đang chạy) chỉ đưa cửa sổ lên
        gui_app.open_files_from_instance(win, [])
        assert win.doc_tabs.count() == 2
    finally:
        for i in reversed(range(win.doc_tabs.count())):
            win.close_tab_at(i, force=True)
        win.close()
