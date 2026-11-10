"""«Một cửa sổ duy nhất» (mục V1): kênh `QLocalServer`/`QLocalSocket` giữa các tiến trình QT PDF Pro.

- `SingleInstance.start()` gọi ngay đầu `ui/app.main`, TRƯỚC khi dựng `MainWindow` (nạp PyMuPDF, ONNX… mất
  vài giây): tiến trình phụ gửi tệp rồi thoát nhanh, tiến trình chính bắt đầu nghe sớm để các tiến trình
  Explorer mở cùng lúc kết nối được.
- Yêu cầu đến trước khi có cửa sổ được giữ lại; `attach(handler)` phát lại theo đúng thứ tự.
- Phần không phụ thuộc Qt (tên kênh, mã hoá thông điệp, mutex) ở `core/single_instance.py`.
"""

from __future__ import annotations

import time
from typing import Callable, List, Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from qtpdfpro.core import single_instance as si

# Trên Windows `QLocalServer` chỉ giữ MỘT phiên bản ống chờ; phiên bản kế tiếp được tạo trong vòng lặp sự
# kiện — tức là khi cửa sổ chính dựng xong (nạp PyMuPDF, ONNX, mở tệp đầu… có lúc > 15 giây khi máy bận).
# Trong lúc đó tiến trình phụ thứ hai trở đi nhận ERROR_PIPE_BUSY và phải thử lại. Mutex đã cho biết chắc
# chắn có tiến trình chính, nên chờ lâu rồi mới chịu mở cửa sổ riêng.
CONNECT_TIMEOUT_MS = 60000
ACK_TIMEOUT_MS = 60000


class InstanceServer(QObject):
    """Nghe trên kênh cục bộ; mỗi kết nối gửi một dòng JSON, được trả `ok` rồi đóng."""

    filesRequested = Signal(list)

    def __init__(self, name: str, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.name = name
        self._server = QLocalServer(self)
        # Chỉ tài khoản đang đăng nhập kết nối được (mặc định Windows cho mọi người dùng cùng máy)
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self._server.newConnection.connect(self._on_new_connection)
        self._buffers: dict[QLocalSocket, bytearray] = {}

    def listen(self) -> bool:
        if self._server.listen(self.name):
            return True
        # Ngoài Windows: tệp socket cũ còn sót sau lần thoát đột ngột
        QLocalServer.removeServer(self.name)
        return self._server.listen(self.name)

    def close(self) -> None:
        self._server.close()

    def _on_new_connection(self) -> None:
        while self._server.hasPendingConnections():
            sock = self._server.nextPendingConnection()
            if sock is None:
                break
            self._buffers[sock] = bytearray()
            sock.readyRead.connect(lambda s=sock: self._on_ready_read(s))
            sock.disconnected.connect(lambda s=sock: self._drop(s))
            if sock.bytesAvailable():
                self._on_ready_read(sock)

    def _drop(self, sock: QLocalSocket) -> None:
        self._buffers.pop(sock, None)
        sock.deleteLater()

    def _on_ready_read(self, sock: QLocalSocket) -> None:
        buf = self._buffers.get(sock)
        if buf is None:
            return
        buf.extend(bytes(sock.readAll()))
        if len(buf) > si.MAX_MESSAGE_BYTES:
            self._buffers.pop(sock, None)
            sock.abort()
            return
        if b"\n" not in buf:
            return
        line = bytes(buf.split(b"\n", 1)[0])
        self._buffers.pop(sock, None)
        files = si.decode_message(line)
        if files is None:
            sock.abort()
            return
        sock.write(si.ACK)
        sock.flush()
        sock.disconnectFromServer()
        self.filesRequested.emit(files)


def send_to_primary(
    name: str,
    files: List[str],
    connect_timeout_ms: int = CONNECT_TIMEOUT_MS,
    ack_timeout_ms: int = ACK_TIMEOUT_MS,
) -> bool:
    """Gửi danh sách tệp tới tiến trình chính; `True` khi nó xác nhận đã nhận."""
    deadline = time.monotonic() + connect_timeout_ms / 1000
    sock = QLocalSocket()
    while True:
        sock.connectToServer(name)
        if sock.waitForConnected(500):
            break
        sock.abort()
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)
    sock.write(si.encode_message(files))
    if not sock.waitForBytesWritten(5000):
        sock.abort()
        return False
    reply = bytearray()
    ack_deadline = time.monotonic() + ack_timeout_ms / 1000
    while si.ACK not in reply:
        remaining = int((ack_deadline - time.monotonic()) * 1000)
        if remaining <= 0:
            break
        if not sock.waitForReadyRead(min(remaining, 1000)):
            if sock.state() != QLocalSocket.LocalSocketState.ConnectedState:
                reply.extend(bytes(sock.readAll()))
                break
            continue
        reply.extend(bytes(sock.readAll()))
    sock.abort()
    return si.ACK in reply


class SingleInstance(QObject):
    """Bầu tiến trình chính và chuyển yêu cầu mở tệp tới cửa sổ đang chạy."""

    PRIMARY = "primary"
    FORWARDED = "forwarded"
    STANDALONE = "standalone"  # không bầu / không gửi được → cư xử như trước (mở cửa sổ riêng)

    def __init__(self, name: Optional[str] = None, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.name = name or si.channel_name()
        self.lock = si.PrimaryLock(self.name)
        self.server: Optional[InstanceServer] = None
        self._pending: List[List[str]] = []
        self._handler: Optional[Callable[[List[str]], None]] = None

    def start(self, files: List[str]) -> str:
        if self.lock.acquire():
            server = InstanceServer(self.name, self)
            if server.listen():
                server.filesRequested.connect(self._on_files)
                self.server = server
                return self.PRIMARY
            return self.STANDALONE
        si.allow_foreground_for_any_process()
        if send_to_primary(self.name, files):
            return self.FORWARDED
        return self.STANDALONE

    def attach(self, handler: Callable[[List[str]], None]) -> None:
        """Nối cửa sổ chính; phát lại các yêu cầu đến trong lúc cửa sổ còn đang dựng."""
        self._handler = handler
        pending, self._pending = self._pending, []
        for files in pending:
            handler(files)

    def _on_files(self, files: list) -> None:
        if self._handler is None:
            self._pending.append(list(files))
        else:
            self._handler(list(files))

    def shutdown(self) -> None:
        if self.server is not None:
            self.server.close()
            self.server = None
        self.lock.release()
