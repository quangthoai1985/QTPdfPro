"""Ghi bảng nhớ tạm chắc chắn.

Trên một số máy Windows, chương trình theo dõi bảng nhớ tạm (lịch sử bảng nhớ tạm, đồng bộ đám mây, phần mềm điều
khiển từ xa…) mở bảng nhớ tạm trong chốc lát ngay sau mỗi lần ghi. Lệnh ghi kế tiếp của Qt khi đó thất bại **im lặng**
(máy phát triển: 18/40 lần ghi – đọc liền nhau sai). Ghi rồi đọc lại; chưa khớp thì chờ một chút và ghi lại.
"""

from __future__ import annotations

import time

from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtWidgets import QApplication

ATTEMPTS = 10
SETTLE_S = 0.02  # chờ giữa hai lần đọc lại (giây)
READBACKS = 5  # số lần đọc lại sau mỗi lần ghi


def _pump() -> None:
    app = QApplication.instance()
    if app is not None:
        app.processEvents()


def set_text(text: str, attempts: int = ATTEMPTS, settle_s: float = SETTLE_S) -> bool:
    """Đặt chữ vào bảng nhớ tạm; True khi đọc lại đúng chữ đó (đa số lần đầu đã được, tối đa ~0,5 giây)."""
    cb = QGuiApplication.clipboard()
    if cb is None:
        return False
    for _ in range(max(1, attempts)):
        cb.setText(text)
        for _ in range(READBACKS):
            _pump()
            if cb.text() == text:
                return True
            if settle_s:
                time.sleep(settle_s)
    return False


def set_image(image: QImage, attempts: int = ATTEMPTS, settle_s: float = SETTLE_S) -> bool:
    """Đặt ảnh vào bảng nhớ tạm; True khi bảng nhớ tạm đọc lại được một ảnh cùng kích thước."""
    cb = QGuiApplication.clipboard()
    if cb is None:
        return False
    for _ in range(max(1, attempts)):
        cb.setImage(image)
        for _ in range(READBACKS):
            _pump()
            got = cb.image()
            if not got.isNull() and got.size() == image.size():
                return True
            if settle_s:
                time.sleep(settle_s)
    return False
