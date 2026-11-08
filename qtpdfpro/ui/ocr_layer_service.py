"""Nhận dạng ngầm trang ảnh quét đang xem thành lớp chữ tạm (Đợt 2 của công cụ «Chọn chữ»).

Mỗi tab tài liệu có một `OcrLayerService`:
- Chỉ chạy khi máy **đã có** bộ mô hình OCR (`models_ready`) — không tự tải 88 MB ngầm; lần đầu tải vẫn do người
  dùng kích hoạt (kéo khung trên trang scan / hộp thoại OCR).
- Chỉ trang đang xem + trang kế (`request`); đổi trang thì trang mới được ưu tiên.
- Ảnh trang kết xuất ở luồng giao diện (PyMuPDF), nhận dạng ở `QThread` (chỉ ONNX Runtime + numpy).
- Lưu đệm theo SHA-256 nội dung tệp (`core.ocr_layer.OcrLayerCache`, băm tệp ở luồng nền): mở lại là có chữ ngay.
"""

from __future__ import annotations

import threading
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QApplication

from qtpdfpro.core import ocr_layer, ocr_models
from qtpdfpro.core import text_select as ts
from qtpdfpro.core.reader import PDFDocumentReader

_ENGINE = None
_ENGINE_LOCK = threading.Lock()


def shared_ocr_engine():
    """`OcrEngine` dùng chung cả ứng dụng, nạp lần đầu khi cần (gọi được từ luồng nền)."""
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            from qtpdfpro.core.ocr import OcrEngine

            _ENGINE = OcrEngine.load()
        return _ENGINE


class _CacheWorker(QThread):
    done = Signal(str, object)  # khoá (sha256, "" nếu không băm được), {trang: PageOcr}

    def __init__(self, path: str, cache: ocr_layer.OcrLayerCache, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.path = path
        self.cache = cache

    def run(self) -> None:
        try:
            key = ocr_layer.file_sha256(self.path)
        except OSError:
            self.done.emit("", {})
            return
        self.done.emit(key, self.cache.load(key))


class _PageWorker(QThread):
    done = Signal(object)  # PageOcr
    failed = Signal(int, str)

    def __init__(self, region: ts.RegionImage, rotation: int, engine_factory: Callable[[], object],
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.region = region
        self.rotation = rotation
        self._engine_factory = engine_factory

    def run(self) -> None:
        try:
            self.done.emit(ocr_layer.recognize_page(self._engine_factory(), self.region, self.rotation))
        except Exception as exc:  # báo về luồng giao diện
            self.failed.emit(self.region.page_index, str(exc))


class OcrLayerService(QObject):
    """Lớp chữ nhận dạng tạm của một tài liệu (bộ nhớ + lưu đệm đĩa)."""

    pageReady = Signal(int)
    busyChanged = Signal()
    message = Signal(str)

    def __init__(
        self,
        reader: PDFDocumentReader,
        engine_factory: Optional[Callable[[], object]] = None,
        models_ready: Optional[Callable[[], bool]] = None,
        cache: Optional[ocr_layer.OcrLayerCache] = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.reader = reader
        self.engine_factory = engine_factory or shared_ocr_engine
        self.models_ready = models_ready or ocr_models.is_installed
        self.cache = cache or ocr_layer.OcrLayerCache()
        self.pages: Dict[int, ocr_layer.PageOcr] = {}
        self.key: Optional[str] = None  # None = chưa băm tệp; "" = không lưu đệm được
        self.enabled = True
        self._scanned: Dict[int, bool] = {}
        self._failed: set[int] = set()
        self._queue: List[int] = []
        self._worker: Optional[_PageWorker] = None
        self._cache_worker: Optional[_CacheWorker] = None

    # ─── Trạng thái ───────────────────────────────────────────────────────

    @property
    def busy_page(self) -> Optional[int]:
        return self._worker.region.page_index if self._worker is not None else None

    @property
    def idle(self) -> bool:
        return self._worker is None and self._cache_worker is None and not self._queue

    def is_scanned(self, page_index: int) -> bool:
        if page_index not in self._scanned:
            try:
                self._scanned[page_index] = ts.is_scanned_page(self.reader.doc[page_index])
            except Exception:
                self._scanned[page_index] = False
        return self._scanned[page_index]

    def layer(self, page_index: int) -> Optional[ocr_layer.PageOcr]:
        p = self.pages.get(page_index)
        if p is None or self.reader.is_closed or p.view_rotation != self.reader.get_page_rotation(page_index) % 360:
            return None
        return p

    def has_layer(self, page_index: int) -> bool:
        return self.layer(page_index) is not None

    def words(self, page_index: int) -> Optional[List[ts.Word]]:
        p = self.layer(page_index)
        return p.words if p is not None else None

    # ─── Yêu cầu nhận dạng ────────────────────────────────────────────────

    def request(self, page_index: int, prefetch: int = 1) -> bool:
        """Nhận dạng ngầm trang `page_index` (+ `prefetch` trang kế) nếu là trang ảnh quét chưa có lớp chữ.
        Trả về True nếu đã xếp hàng / đang chạy."""
        if not self.enabled or self.reader.is_closed:
            return False
        total = self.reader.page_count
        targets = [p for p in range(page_index, min(total, page_index + prefetch + 1))
                   if self.is_scanned(p) and not self.has_layer(p) and p not in self._failed]
        if not targets or not self.models_ready():
            return False
        busy = self.busy_page
        self._queue = [p for p in targets if p != busy]  # trang đang xem được ưu tiên, bỏ hàng đợi cũ
        self._kick()
        return True

    def _kick(self) -> None:
        if not self.enabled or self.reader.is_closed:
            return
        if self.key is None:
            if self._cache_worker is None:
                self._cache_worker = _CacheWorker(str(self.reader.path), self.cache, self)
                self._cache_worker.done.connect(self._on_cache_loaded)
                self._cache_worker.finished.connect(self._on_cache_worker_finished)
                self._cache_worker.start()
            return
        while self._worker is None and self._queue:
            p = self._queue.pop(0)
            if self.has_layer(p) or p in self._failed:
                continue
            rotation = self.reader.get_page_rotation(p) % 360
            try:
                region = ocr_layer.prepare_page_image(self.reader.doc[p], view_rotation=rotation)
            except Exception:
                self._failed.add(p)
                continue
            worker = _PageWorker(region, rotation, self.engine_factory, self)
            worker.done.connect(self._on_page_done)
            worker.failed.connect(self._on_page_failed)
            worker.finished.connect(self._on_worker_finished)
            self._worker = worker
            worker.start()
            self.busyChanged.emit()
            self.message.emit(f"🔤 Đang nhận dạng chữ trang {p + 1} (ảnh quét) — xong sẽ chọn chữ được như PDF thường…")

    def _on_cache_loaded(self, key: str, pages: dict) -> None:
        self.key = key
        had = dict(self.pages)
        for i, p in pages.items():
            self.pages.setdefault(i, p)
        for i in pages:
            if i not in had:
                self.pageReady.emit(i)
        if key and had and any(i not in pages for i in had):  # tệp vừa đổi (đã lưu): ghi lớp chữ theo khoá mới
            self._save()
        self._kick()

    def _on_cache_worker_finished(self) -> None:
        worker, self._cache_worker = self._cache_worker, None
        if worker is not None:
            worker.wait()
            worker.deleteLater()
        if self.key is None:
            self.key = ""
        self._kick()

    def _save(self) -> None:
        if not self.key:
            return
        try:
            self.cache.save(self.key, self.pages)
        except OSError:
            pass

    def _on_page_done(self, res: ocr_layer.PageOcr) -> None:
        self.pages[res.page_index] = res
        self._save()
        self.pageReady.emit(res.page_index)
        secs = f"{res.seconds:.1f}".replace(".", ",")
        self.message.emit(f"✅ Đã nhận dạng chữ trang {res.page_index + 1} ({len(res.words)} từ, {secs} giây) — "
                          "chọn và sao chép chữ như PDF thường.")

    def _on_page_failed(self, page_index: int, message: str) -> None:
        self._failed.add(page_index)
        self.message.emit(f"⚠️ Không nhận dạng được trang {page_index + 1}: {message}")

    def _on_worker_finished(self) -> None:
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.wait()
            worker.deleteLater()
        self.busyChanged.emit()
        self._kick()

    # ─── Vòng đời ─────────────────────────────────────────────────────────

    def file_changed(self) -> None:
        """Tệp vừa được lưu (nội dung đổi → khoá lưu đệm đổi): băm lại, ghi lớp chữ đã có theo khoá mới."""
        self.key = None
        self._scanned.clear()
        if self.pages:
            self._kick()

    def cancel(self) -> None:
        """Đóng tab: dừng nhận, đợi luồng đang chạy."""
        self.enabled = False
        self._queue.clear()
        for worker in (self._worker, self._cache_worker):
            if worker is not None:
                worker.wait()

    def wait_idle(self, rounds: int = 400) -> None:
        """Đợi hết việc (kiểm thử)."""
        for _ in range(rounds):
            if self.idle:
                break
            for worker in (self._worker, self._cache_worker):
                if worker is not None:
                    worker.wait(50)
            QApplication.processEvents()
        QApplication.processEvents()
