"""Ghi bảng nhớ tạm chắc chắn (`ui/clipboard.py`): một số máy Windows có chương trình theo dõi bảng nhớ tạm giữ nó
trong chốc lát ngay sau khi ghi → lệnh ghi của Qt thất bại im lặng (đo được 18/40 lần trên máy phát triển)."""

from __future__ import annotations

from PySide6.QtGui import QGuiApplication, QImage

from qtpdfpro.ui import clipboard


class _FlakyClipboard:
    """Bảng nhớ tạm giả: hai lần ghi đầu «bị chương trình khác giữ» nên không có tác dụng."""

    def __init__(self, fail_first: int = 2) -> None:
        self.fail_left = fail_first
        self.value = ""
        self.writes = 0

    def setText(self, text: str) -> None:  # noqa: N802 - API Qt
        self.writes += 1
        if self.fail_left > 0:
            self.fail_left -= 1
            return
        self.value = text

    def text(self) -> str:
        return self.value


def test_set_text_retries_until_clipboard_holds_text(qapp, monkeypatch) -> None:
    fake = _FlakyClipboard(fail_first=2)
    monkeypatch.setattr(QGuiApplication, "clipboard", staticmethod(lambda: fake))
    assert clipboard.set_text("Cộng hoà xã hội chủ nghĩa Việt Nam") is True
    assert fake.value == "Cộng hoà xã hội chủ nghĩa Việt Nam"
    assert fake.writes == 3


def test_set_text_gives_up_and_reports_failure(qapp, monkeypatch) -> None:
    fake = _FlakyClipboard(fail_first=10_000)
    monkeypatch.setattr(QGuiApplication, "clipboard", staticmethod(lambda: fake))
    assert clipboard.set_text("abc", attempts=4, settle_s=0.0) is False
    assert fake.writes == 4


def test_set_text_and_image_on_real_clipboard(qapp) -> None:
    assert clipboard.set_text("Độc lập - Tự do - Hạnh phúc")
    assert QGuiApplication.clipboard().text() == "Độc lập - Tự do - Hạnh phúc"
    img = QImage(8, 6, QImage.Format.Format_RGB32)
    img.fill(0xFF2563EB)
    assert clipboard.set_image(img)
