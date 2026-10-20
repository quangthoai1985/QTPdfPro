"""Cập nhật ứng dụng từ GitHub Release (mục V4): tự kiểm tra lúc khởi động, thông báo, hộp thoại tải & cài.

- `UpdateController` gắn vào `MainWindow`: thêm hành động «Kiểm tra cập nhật...» vào menu Trợ giúp, tự kiểm tra
  tối đa 1 lần/ngày bằng `QThread` (không làm chậm lúc mở), hiện thông báo nổi «Đã có bản vX.Y.Z — Cập nhật»,
  và khi người dùng chọn cài thì chạy script cập nhật lúc cửa sổ đóng (sau khi `closeEvent` đã hỏi lưu các tab).
- `UpdateDialog`: ghi chú phát hành, dung lượng, «Tải về & cập nhật» / «Để sau» / «Bỏ qua bản này»,
  thanh tiến trình, nút Huỷ. Chạy từ mã nguồn thì chỉ mở trang phát hành.
"""

from __future__ import annotations

import os
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from qtpdfpro import __app_name__, __github_repo__, __version__
from qtpdfpro.core import update_check as uc
from qtpdfpro.core.settings import AppSettings

STARTUP_CHECK_DELAY_MS = 4000
RELEASES_PAGE = f"https://github.com/{__github_repo__}/releases/latest"


def _format_date(iso_text: str) -> str:
    try:
        return datetime.fromisoformat(iso_text.replace("Z", "+00:00")).astimezone().strftime("%d/%m/%Y")
    except ValueError:
        return ""


def _reveal_in_explorer(path: Path) -> None:
    try:
        if path.exists():
            subprocess.Popen(["explorer", "/select,", str(path)])
        elif path.parent.exists():
            os.startfile(str(path.parent))  # type: ignore[attr-defined]
    except Exception:
        pass


class UpdateCheckWorker(QThread):
    """Luồng nền hỏi GitHub bản phát hành mới nhất."""

    checked = Signal(object)  # UpdateCheckResult
    failed = Signal(str)

    def run(self) -> None:
        try:
            self.checked.emit(uc.check_for_update())
        except uc.UpdateError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # pragma: no cover - lỗi ngoài dự kiến không được làm sập ứng dụng
            self.failed.emit(f"Lỗi ngoài dự kiến: {exc}")


class UpdateDownloadWorker(QThread):
    """Luồng nền tải tệp .zip (+ giải nén và sinh script khi tự cài được)."""

    progress = Signal(object, object)  # (đã xử lý, tổng) byte — `object` vì tệp có thể vượt int32
    stage = Signal(str)
    finishedOk = Signal(object)  # {"zip": Path, "plan": InstallPlan | None}
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, release: uc.ReleaseInfo, install_dir: Optional[Path], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.release = release
        self.install_dir = install_dir
        self._cancel = False

    def request_cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        assert self.release.asset is not None
        try:
            zip_path = uc.download_asset(
                self.release.asset, progress_cb=self.progress.emit, should_cancel=lambda: self._cancel
            )
            plan = None
            if self.install_dir is not None:
                self.stage.emit("Đang giải nén bản mới…")
                try:
                    plan = uc.prepare_install(
                        zip_path,
                        self.release.version,
                        self.install_dir,
                        should_cancel=lambda: self._cancel,
                        progress_cb=self.progress.emit,
                    )
                except uc.InstallDirNotWritable:
                    plan = None
            self.finishedOk.emit({"zip": zip_path, "plan": plan})
        except uc.UpdateCancelled:
            self.cancelled.emit()
        except uc.UpdateError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # pragma: no cover - lỗi ngoài dự kiến hiển thị cho người dùng
            self.failed.emit(f"Lỗi ngoài dự kiến: {exc}")


class UpdateDialog(QDialog):
    """Thông tin bản mới + tải về & cập nhật. Kết quả ở `outcome`: None | "later" | "skip" | "restart" | "on_exit"."""

    MODE_INSTALL = "install"  # bản đóng gói, thư mục cài ghi được → tự thay bản mới
    MODE_MANUAL = "manual"  # bản đóng gói, thư mục cài không ghi được → tải về rồi hướng dẫn chép tay
    MODE_SOURCE = "source"  # chạy từ mã nguồn → chỉ mở trang phát hành
    MODE_NO_ASSET = "no_asset"  # bản phát hành thiếu tệp QTPdfPro-v<x.y.z>-win64.zip

    def __init__(
        self,
        release: uc.ReleaseInfo,
        settings: AppSettings,
        parent: QWidget | None = None,
        install_dir: Optional[Path] = None,
        frozen: Optional[bool] = None,
    ) -> None:
        super().__init__(parent)
        self.release = release
        self.settings = settings
        self.outcome: Optional[str] = None
        self.plan: Optional[uc.InstallPlan] = None
        self.zip_path: Optional[Path] = None
        self._worker: Optional[UpdateDownloadWorker] = None
        self._running = False
        self._close_when_done = False
        self._stage_text = "Đang tải"

        frozen = uc.is_frozen() if frozen is None else frozen
        self.install_dir = install_dir if install_dir is not None else uc.current_install_dir()
        if not frozen or self.install_dir is None:
            self.mode = self.MODE_SOURCE
        elif release.asset is None:
            self.mode = self.MODE_NO_ASSET
        elif uc.can_write_install_dir(self.install_dir):
            self.mode = self.MODE_INSTALL
        else:
            self.mode = self.MODE_MANUAL

        self.setWindowTitle("Cập nhật QT PDF Pro")
        self.resize(640, 560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(8)

        self.title_lbl = QLabel(f"Đã có bản {__app_name__} v{release.version}")
        self.title_lbl.setStyleSheet("font-size: 18px; font-weight: 700;")
        lay.addWidget(self.title_lbl)

        facts = [f"Bạn đang dùng v{__version__}"]
        date_text = _format_date(release.published_at)
        if date_text:
            facts.append(f"Phát hành ngày {date_text}")
        if release.asset is not None and release.asset.size:
            facts.append(f"Dung lượng tải về {uc.format_size(release.asset.size)}")
        self.facts_lbl = QLabel(" · ".join(facts))
        self.facts_lbl.setTextFormat(Qt.TextFormat.PlainText)
        lay.addWidget(self.facts_lbl)
        if release.name:
            name_lbl = QLabel(release.name)
            name_lbl.setTextFormat(Qt.TextFormat.PlainText)
            name_lbl.setWordWrap(True)
            name_lbl.setStyleSheet("font-weight: 600;")
            lay.addWidget(name_lbl)

        self.notes_view = QTextBrowser()
        self.notes_view.setOpenExternalLinks(True)
        self.notes_view.setMarkdown(release.notes.strip() or "_(Bản phát hành không có ghi chú.)_")
        self.notes_view.setMinimumHeight(220)
        lay.addWidget(self.notes_view, 1)

        self.hint_lbl = QLabel(self._mode_hint())
        self.hint_lbl.setTextFormat(Qt.TextFormat.PlainText)
        self.hint_lbl.setWordWrap(True)
        lay.addWidget(self.hint_lbl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        lay.addWidget(self.progress_bar)
        self.status_lbl = QLabel("")
        self.status_lbl.setTextFormat(Qt.TextFormat.PlainText)
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setVisible(False)
        lay.addWidget(self.status_lbl)

        self.auto_check_box = QCheckBox("Tự kiểm tra bản mới khi khởi động (tối đa 1 lần/ngày)")
        self.auto_check_box.setChecked(settings.auto_check_updates)
        self.auto_check_box.toggled.connect(self._on_auto_check_toggled)
        lay.addWidget(self.auto_check_box)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.btn_skip = self._make_button("Bỏ qua bản này", self._on_skip)
        self.btn_skip.setToolTip("Không tự báo bản này nữa (vẫn xem được qua «Kiểm tra cập nhật...»)")
        row.addWidget(self.btn_skip)
        row.addStretch(1)
        no_download = self.mode in (self.MODE_SOURCE, self.MODE_NO_ASSET)
        self.btn_release = self._make_button("Mở trang phát hành", self._open_release_page, primary=no_download)
        self.btn_later = self._make_button("Để sau", self._on_later)
        self.btn_close = self._make_button("Đóng", self._on_later)
        self.btn_retry = self._make_button("Thử lại", self.start_download)
        self.btn_open_folder = self._make_button("Mở thư mục chứa tệp", self._reveal_zip)
        self.btn_cancel = self._make_button("Huỷ", self.request_cancel)
        self.btn_on_exit = self._make_button("Cài khi thoát ứng dụng", lambda: self._finish("on_exit"))
        self.btn_on_exit.setToolTip("Dùng tiếp bây giờ; bản mới được cài khi bạn đóng QT PDF Pro")
        self.btn_restart = self._make_button("Khởi động lại && cập nhật", lambda: self._finish("restart"), primary=True)
        label = "Tải về && cập nhật" if self.mode == self.MODE_INSTALL else "Tải về"
        self.btn_download = self._make_button(label, self.start_download, primary=True)
        for b in (  # nút chính nằm ngoài cùng bên phải
            self.btn_later, self.btn_close, self.btn_open_folder, self.btn_cancel, self.btn_on_exit,
            self.btn_release, self.btn_retry, self.btn_restart, self.btn_download,
        ):  # fmt: skip
            row.addWidget(b)
        lay.addLayout(row)
        self._set_state("info")

    # ─── Dựng giao diện ───────────────────────────────────────────────────

    def _make_button(self, text: str, slot, primary: bool = False) -> QPushButton:  # noqa: ANN001
        btn = QPushButton(text)
        if primary:
            btn.setObjectName("primaryConvertBtn")
        btn.setAutoDefault(False)
        btn.clicked.connect(lambda _checked=False: slot())
        return btn

    def _mode_hint(self) -> str:
        asset_name = uc.expected_asset_name(self.release.version)
        if self.mode == self.MODE_INSTALL:
            check = "mã SHA-256" if self.release.asset and self.release.asset.sha256 else "dung lượng"
            return (
                f"Bấm «Tải về & cập nhật»: ứng dụng tải {asset_name} từ GitHub (kiểm {check}), rồi đóng lại — "
                "hỏi lưu các tài liệu chưa lưu — thay bản mới và tự mở lại. Bản cũ được giữ dự phòng tới lần mở sau."
            )
        if self.mode == self.MODE_MANUAL:
            return (
                f"Thư mục cài đặt «{self.install_dir}» không ghi được (thường do nằm trong Program Files), nên "
                "ứng dụng chỉ tải tệp về rồi mở thư mục chứa tệp để bạn tự giải nén và chép đè."
            )
        if self.mode == self.MODE_NO_ASSET:
            return f"Bản phát hành này chưa có tệp {asset_name} — hãy mở trang phát hành để tải thủ công."
        return (
            "Bạn đang chạy QT PDF Pro từ mã nguồn (python -m qtpdfpro) nên ứng dụng không tự thay tệp. "
            "Hãy cập nhật mã nguồn (git pull) hoặc tải bản đóng gói ở trang phát hành."
        )

    def _set_state(self, state: str) -> None:
        """info | running | ready | manual | error — đổi bộ nút hiển thị."""
        self._state = state
        can_download = self.mode in (self.MODE_INSTALL, self.MODE_MANUAL)
        visible = {
            "info": {self.btn_skip, self.btn_later, self.btn_download if can_download else self.btn_release},
            "running": {self.btn_cancel},
            "ready": {self.btn_on_exit, self.btn_restart},
            "manual": {self.btn_open_folder, self.btn_close},
            "error": {self.btn_release, self.btn_close} | ({self.btn_retry} if can_download else set()),
        }[state]
        for btn in (
            self.btn_skip, self.btn_release, self.btn_later, self.btn_close, self.btn_retry,
            self.btn_open_folder, self.btn_cancel, self.btn_on_exit, self.btn_restart, self.btn_download,
        ):  # fmt: skip
            btn.setVisible(btn in visible)
        self.btn_cancel.setEnabled(True)
        self.auto_check_box.setEnabled(state != "running")
        self.progress_bar.setVisible(state in ("running", "ready"))
        default = {"info": self.btn_download if can_download else self.btn_release, "ready": self.btn_restart}
        if state in default:
            default[state].setDefault(True)
            default[state].setFocus()

    def _show_status(self, text: str, error: bool = False) -> None:
        self.status_lbl.setText(text)
        self.status_lbl.setStyleSheet("color: #DC2626; font-weight: 600;" if error else "")
        self.status_lbl.setVisible(bool(text))

    # ─── Tải về & cài ──────────────────────────────────────────────────────

    def is_running(self) -> bool:
        return self._running

    def start_download(self) -> bool:
        if self._running or self.release.asset is None or self.mode not in (self.MODE_INSTALL, self.MODE_MANUAL):
            return False
        self._running = True
        self._stage_text = "Đang tải"
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self._set_state("running")
        self._show_status("Đang kết nối tới GitHub…")
        install_dir = self.install_dir if self.mode == self.MODE_INSTALL else None
        self._worker = UpdateDownloadWorker(self.release, install_dir, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.stage.connect(self._on_stage)
        self._worker.finishedOk.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.start()
        return True

    def request_cancel(self) -> None:
        if self._worker is not None and self._running:
            self._worker.request_cancel()
            self.btn_cancel.setEnabled(False)
            self._show_status("Đang huỷ…")

    def wait_for_worker(self, timeout_ms: int = -1) -> bool:
        """Chờ luồng nền kết thúc (dùng khi kiểm thử). Tín hiệu còn xếp hàng cần `processEvents()`."""
        if self._worker is None:
            return True
        return self._worker.wait(timeout_ms) if timeout_ms >= 0 else self._worker.wait()

    def _finish_worker(self) -> None:
        # Tín hiệu kết thúc là câu lệnh cuối của run() → luồng thoát ngay; chờ để không huỷ QThread đang chạy
        if self._worker is not None:
            self._worker.wait(10000)
        self._running = False

    def _on_progress(self, done: int, total: int) -> None:
        if total and total > 0:
            if self.progress_bar.maximum() == 0:
                self.progress_bar.setRange(0, 1000)
            self.progress_bar.setValue(int(done * 1000 / total))
            pct = int(done * 100 / total)
            self._show_status(f"{self._stage_text}: {uc.format_size(done)} / {uc.format_size(total)} ({pct}%)")
        else:
            self.progress_bar.setRange(0, 0)
            self._show_status(f"{self._stage_text}: {uc.format_size(done)}")

    def _on_stage(self, text: str) -> None:
        self._stage_text = text.rstrip("…")
        self.progress_bar.setValue(0)
        self._show_status(text)

    def _on_finished(self, payload: dict) -> None:
        self._finish_worker()
        self.zip_path = payload.get("zip")
        self.plan = payload.get("plan")
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(1000)
        if self._close_when_done:
            super().reject()
            return
        verified = "đã kiểm mã SHA-256" if self.release.asset and self.release.asset.sha256 else "đã kiểm dung lượng"
        if self.plan is not None:
            self._set_state("ready")
            self.hint_lbl.setText(
                f"Bản v{self.release.version} đã tải xong ({verified}). «Khởi động lại & cập nhật» sẽ hỏi lưu các "
                "tài liệu chưa lưu, đóng ứng dụng, thay bản mới rồi tự mở lại. Hoặc dùng tiếp và cài khi thoát."
            )
            self._show_status("")
            return
        self.mode = self.MODE_MANUAL
        self._set_state("manual")
        target = self.install_dir or Path("…")
        self.hint_lbl.setText(
            f"Đã tải bản v{self.release.version} ({verified}) về:\n{self.zip_path}\n\n"
            f"Thư mục cài đặt «{target}» không ghi được nên cần cập nhật thủ công:\n"
            "  1. Thoát QT PDF Pro.\n"
            "  2. Giải nén tệp .zip vừa tải.\n"
            f"  3. Chép đè toàn bộ nội dung thư mục QTPdfPro vào «{target}» (đồng ý quyền quản trị khi Windows hỏi)."
        )
        self._show_status("")
        if self.zip_path is not None:
            _reveal_in_explorer(Path(self.zip_path))

    def _on_failed(self, message: str) -> None:
        self._finish_worker()
        if self._close_when_done:
            super().reject()
            return
        self._set_state("error")
        self.progress_bar.setVisible(False)
        self._show_status(f"Không cập nhật được: {message}", error=True)

    def _on_cancelled(self) -> None:
        self._finish_worker()
        if self._close_when_done:
            super().reject()
            return
        self._set_state("info")
        self._show_status("Đã huỷ tải bản cập nhật.")

    def _reveal_zip(self) -> None:
        if self.zip_path is not None:
            _reveal_in_explorer(Path(self.zip_path))

    # ─── Kết thúc ─────────────────────────────────────────────────────────

    def _on_auto_check_toggled(self, checked: bool) -> None:
        self.settings.auto_check_updates = bool(checked)
        self.settings.save()

    def _open_release_page(self) -> None:
        QDesktopServices.openUrl(QUrl(self.release.html_url or RELEASES_PAGE))

    def _on_skip(self) -> None:
        self._finish("skip")

    def _on_later(self) -> None:
        self._finish("later")

    def _finish(self, outcome: str) -> None:
        self.outcome = outcome
        if outcome in ("restart", "on_exit"):
            self.accept()
        else:
            super().reject()

    def reject(self) -> None:
        # Esc / nút ✕: đang tải thì huỷ rồi mới đóng
        if self._running:
            self._close_when_done = True
            self.request_cancel()
            return
        if self.outcome is None:
            self.outcome = "later"
        super().reject()


class UpdateNotice(QFrame):
    """Thông báo nổi không chặn ở góc dưới bên phải: «Đã có bản vX.Y.Z — Cập nhật»."""

    updateClicked = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("updateNotice")
        self.setStyleSheet(
            "QFrame#updateNotice { background: #2563EB; border-radius: 10px; }"
            "QFrame#updateNotice QLabel { color: #FFFFFF; font-weight: 600; background: transparent; }"
            "QFrame#updateNotice QPushButton { background: #FFFFFF; color: #1D4ED8; border: none;"
            " border-radius: 6px; padding: 4px 12px; font-weight: 700; }"
            "QFrame#updateNotice QPushButton:hover { background: #DBEAFE; }"
            "QFrame#updateNotice QPushButton#updateNoticeClose { background: transparent; color: #FFFFFF;"
            " padding: 2px 6px; font-weight: 400; }"
            "QFrame#updateNotice QPushButton#updateNoticeClose:hover { background: #1D4ED8; }"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 8, 8)
        lay.setSpacing(10)
        self.label = QLabel("")
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        lay.addWidget(self.label)
        self.btn_update = QPushButton("Cập nhật")
        self.btn_update.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_update.clicked.connect(self.updateClicked.emit)
        lay.addWidget(self.btn_update)
        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("updateNoticeClose")
        self.btn_close.setToolTip("Ẩn thông báo (xem lại qua ☰ Menu › Trợ giúp › Kiểm tra cập nhật...)")
        self.btn_close.clicked.connect(self.hide)
        lay.addWidget(self.btn_close)
        self.hide()
        parent.installEventFilter(self)

    def show_for(self, release: uc.ReleaseInfo) -> None:
        self.label.setText(f"🎉 Đã có bản v{release.version}")
        self.setToolTip(release.title)
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        bottom = 12
        if isinstance(parent, QMainWindow) and parent.statusBar().isVisible():
            bottom += parent.statusBar().height()
        self.move(max(8, parent.width() - self.width() - 16), max(8, parent.height() - self.height() - bottom))

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - API Qt
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize and self.isVisible():
            self.reposition()
        return False


class UpdateController(QObject):
    """Điều phối kiểm tra & cài bản cập nhật cho `MainWindow` (đặt ở `window.updater`)."""

    def __init__(self, window: QMainWindow, settings: AppSettings) -> None:
        super().__init__(window)
        self.window = window
        self.settings = settings
        self.latest: Optional[uc.ReleaseInfo] = None
        self.pending_plan: Optional[uc.InstallPlan] = None
        self.relaunch_after_install = True
        self._check_worker: Optional[UpdateCheckWorker] = None
        self._manual = False
        self._closing = False
        self._cleanup_thread: Optional[threading.Thread] = None
        self.notice = UpdateNotice(window)
        self.notice.updateClicked.connect(lambda: self.open_dialog())
        self.act_check = QAction("Kiểm tra cập nhật...", window)
        self.act_check.triggered.connect(self.check_now)
        self.act_auto = QAction("Tự kiểm tra cập nhật khi khởi động", window)
        self.act_auto.setCheckable(True)
        self.act_auto.setChecked(settings.auto_check_updates)
        self.act_auto.toggled.connect(self._on_auto_toggled)

    def add_menu_actions(self, menu: QMenu) -> None:
        menu.addAction(self.act_check)
        menu.addAction(self.act_auto)

    # ─── Khởi động ────────────────────────────────────────────────────────

    def on_startup(self, delay_ms: int = STARTUP_CHECK_DELAY_MS) -> None:
        """Gọi sau `window.show()`: báo kết quả lần cập nhật trước, dọn `.old`, hẹn giờ tự kiểm tra."""
        marker = uc.consume_pending_marker()
        if marker is not None:
            QTimer.singleShot(600, lambda: self._report_previous_update(marker))
        self._cleanup_thread = threading.Thread(target=self._cleanup_quietly, name="qtpdfpro-update-cleanup", daemon=True)
        self._cleanup_thread.start()
        QTimer.singleShot(max(0, delay_ms), self.start_auto_check)

    @staticmethod
    def _cleanup_quietly() -> None:
        try:
            uc.cleanup_previous_update()
        except Exception:
            pass

    def _report_previous_update(self, marker: dict) -> None:
        if marker.get("ok"):
            self._toast(f"Đã cập nhật lên {__app_name__} v{__version__}.", 6000)
        else:
            self._toast(
                f"Cập nhật lên v{marker.get('version')} chưa thành công — xem nhật ký: {marker.get('log', '')}", 9000
            )

    def _toast(self, text: str, msec: int = 4000) -> None:
        show = getattr(self.window, "_show_toast", None)
        if callable(show):
            show(text, msec)
        else:
            self.window.statusBar().showMessage(text, msec)

    # ─── Kiểm tra ─────────────────────────────────────────────────────────

    def start_auto_check(self) -> bool:
        """Tự kiểm tra (nếu bật và đã quá 1 ngày); trả về True nếu đã bắt đầu hỏi GitHub."""
        if self._closing or not self.settings.auto_check_updates:
            return False
        if not uc.should_auto_check(self.settings.last_update_check):
            return False
        return self._start_check(manual=False)

    def check_now(self) -> bool:
        """«Kiểm tra cập nhật...» trong menu — luôn hỏi GitHub, kể cả bản đã «Bỏ qua»."""
        self.window.statusBar().showMessage("Đang kiểm tra bản mới trên GitHub…", 5000)
        return self._start_check(manual=True)

    def is_checking(self) -> bool:
        return self._check_worker is not None and self._check_worker.isRunning()

    def wait_for_check(self, timeout_ms: int = 10000) -> bool:
        """Chờ luồng kiểm tra kết thúc (dùng khi kiểm thử). Tín hiệu còn xếp hàng cần `processEvents()`."""
        return self._check_worker.wait(timeout_ms) if self._check_worker is not None else True

    def _start_check(self, manual: bool) -> bool:
        if self.is_checking():
            self._manual = self._manual or manual
            return True
        self._manual = manual
        self._check_worker = UpdateCheckWorker(self)
        self._check_worker.checked.connect(self._on_checked)
        self._check_worker.failed.connect(self._on_check_failed)
        self._check_worker.start()
        return True

    def _finish_check(self) -> bool:
        if self._check_worker is not None:
            self._check_worker.wait(5000)
        manual, self._manual = self._manual, False
        return manual

    def _on_checked(self, result: uc.UpdateCheckResult) -> None:
        manual = self._finish_check()
        self.settings.last_update_check = uc.now_iso()
        self.settings.save()
        if self._closing:
            return
        self.latest = result.latest if result.update_available else None
        if self.latest is None:
            self.notice.hide()
            if manual:
                QMessageBox.information(self.window, "Kiểm tra cập nhật", result.message)
            return
        if manual:
            self.open_dialog(self.latest)
        elif self.latest.version != self.settings.skipped_update_version:
            self.notice.show_for(self.latest)

    def _on_check_failed(self, message: str) -> None:
        manual = self._finish_check()
        if self._closing:
            return
        if manual:
            QMessageBox.warning(self.window, "Kiểm tra cập nhật", f"Không kiểm tra được bản mới.\n\n{message}")
        else:
            self.window.statusBar().showMessage(f"Không tự kiểm tra được bản mới: {message}", 6000)

    def _on_auto_toggled(self, checked: bool) -> None:
        self.settings.auto_check_updates = bool(checked)
        self.settings.save()

    # ─── Hộp thoại & cài đặt ──────────────────────────────────────────────

    def open_dialog(self, release: Optional[uc.ReleaseInfo] = None) -> Optional[str]:
        release = release or self.latest
        if release is None:
            return None
        if self._cleanup_thread is not None and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(30)  # dọn thư mục tạm của lần trước xong rồi mới giải nén bản mới
        self.notice.hide()
        dlg = UpdateDialog(release, self.settings, parent=self.window)
        dlg.exec()
        self.act_auto.setChecked(self.settings.auto_check_updates)
        outcome = dlg.outcome
        if outcome == "skip":
            self.settings.skipped_update_version = release.version
            self.settings.save()
            self._toast(f"Sẽ không tự báo bản v{release.version} nữa.")
        elif outcome in ("restart", "on_exit") and dlg.plan is not None:
            self.pending_plan = dlg.plan
            self.relaunch_after_install = outcome == "restart"
            if outcome == "restart":
                if not self.window.close():
                    self.relaunch_after_install = False
                    self._toast(f"Chưa đóng ứng dụng — bản v{release.version} sẽ được cài khi bạn thoát.", 6000)
            else:
                self._toast(f"Bản v{release.version} sẽ được cài khi bạn thoát {__app_name__}.", 6000)
        return outcome

    def on_window_closing(self) -> None:
        """`MainWindow.closeEvent` gọi sau khi người dùng đã đồng ý đóng (đã hỏi lưu mọi tab)."""
        self._closing = True
        self.notice.hide()
        if self.is_checking():
            self._check_worker.wait(int((uc.API_TIMEOUT + 2) * 1000))  # type: ignore[union-attr]
        plan, self.pending_plan = self.pending_plan, None
        if plan is None:
            return
        try:
            uc.launch_install(plan, relaunch=self.relaunch_after_install)
        except Exception as exc:
            QMessageBox.warning(
                self.window,
                "Cập nhật",
                f"Không chạy được trình cập nhật: {exc}\n\nTệp đã tải: {plan.zip_path}",
            )
            return
        self._quit_app()

    def _quit_app(self) -> None:
        # Script đợi tiến trình thoát hẳn — thoát cả khi còn cửa sổ khác đang mở
        QTimer.singleShot(0, QCoreApplication.quit)
