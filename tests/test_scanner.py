"""Kiểm thử tính năng Scan tích hợp từ PDFScanner: giải mã DIB, WIA đa thiết bị, xử lý ảnh, PDF/ảnh, phiên quét, CLI và ScanDialog."""

from __future__ import annotations

import io
import struct
from pathlib import Path
from types import SimpleNamespace

import comtypes
import cv2
import fitz  # PyMuPDF
import numpy as np
import pytest
from PySide6.QtCore import QRectF
from PySide6.QtWidgets import QApplication

from qtpdfpro import cli
from qtpdfpro.core import scanner, scanner_wia
from qtpdfpro.core.settings import AppSettings
from qtpdfpro.ui.main_window import MainWindow
from qtpdfpro.ui.scan_dialog import ScanDialog

rng = np.random.default_rng(0)


def _bmp_bytes(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".bmp", img)
    assert ok
    return buf.tobytes()


# ─── 1. Giải mã ảnh DIB / BMP / nén từ máy scan ─────────────────────────────


def test_decode_dib_variants() -> None:
    gray = rng.integers(0, 256, (23, 37), dtype=np.uint8)
    assert np.array_equal(scanner_wia._decode_dib(_bmp_bytes(gray)), gray)

    color = rng.integers(0, 256, (19, 31, 3), dtype=np.uint8)
    assert np.array_equal(scanner_wia._decode_dib(_bmp_bytes(color)), color)

    # MEMORYBMP không có 14-byte BITMAPFILEHEADER
    assert np.array_equal(scanner_wia._decode_dib(_bmp_bytes(gray)[14:]), gray)

    # Top-down DIB (height âm)
    dib = bytearray(_bmp_bytes(gray)[14:])
    bi_size, width, height = struct.unpack_from("<Iii", dib)
    offset = bi_size + 256 * 4
    stride = (width * 8 + 31) // 32 * 4
    rows = [bytes(dib[offset + i * stride : offset + (i + 1) * stride]) for i in range(height)]
    top_down = dib[:offset] + b"".join(reversed(rows))
    struct.pack_into("<i", top_down, 8, -height)
    assert np.array_equal(scanner_wia._decode_dib(top_down), gray)

    # PNG nén từ WIA 2.0 / WSD
    ok, png = cv2.imencode(".png", color)
    assert ok
    assert np.array_equal(scanner_wia._decode_dib(png.tobytes()), color)


# ─── 2. Tương thích mọi máy scan WIA (Mock WIA COM) ───────────────────────────


class _FakeProp:
    def __init__(self, pid: int, name: str, value, *, ro: bool = False, sub_type: int = 0,
                 mn: int = 0, mx: int = 10000, step: int = 1, vals=()) -> None:
        self.PropertyID = pid
        self.Name = name
        self.Value = value
        self.IsReadOnly = ro
        self.SubType = sub_type
        self.SubTypeMin = mn
        self.SubTypeMax = mx
        self.SubTypeStep = step
        self.SubTypeValues = list(vals)


class _FakeProps:
    def __init__(self, props: list[_FakeProp]) -> None:
        self._props = props

    def __iter__(self):
        return iter(self._props)

    def Item(self, name: str):
        for p in self._props:
            if p.Name == name:
                return p
        raise KeyError(name)


class _FakeItems:
    def __init__(self, items: list) -> None:
        self._items = items

    @property
    def Count(self) -> int:
        return len(self._items)

    def Item(self, idx: int):
        return self._items[idx - 1]


class _FakeWiaItem:
    def __init__(self, bmp_payload: bytes, fail_banded: bool = False) -> None:
        self._bmp = bmp_payload
        self._fail_banded = fail_banded

    def QueryInterface(self, _iface):
        if self._fail_banded:
            err = comtypes.COMError(-2147467262, "E_NOINTERFACE", ())  # 0x80004002
            raise err
        bmp = self._bmp

        class _Transfer:
            def idtGetBandedData(self_t, _info_ptr, cb):
                # Giả lập nhận 2 dải qua _Receiver
                raise NotImplementedError

        return _Transfer()


def test_wia_canon_hp_missing_bed_props_and_step_snapping(monkeypatch) -> None:
    """Máy scan Canon/HP/Brother thiếu BED_WIDTH/HEIGHT, BRIGHTNESS ReadOnly, X_EXTENT step=4, X_RES dạng list."""
    sample = np.full((60, 80, 3), 240, dtype=np.uint8)
    bmp = _bmp_bytes(sample)

    item_props = _FakeProps([
        _FakeProp(scanner_wia.DATA_TYPE, "Data Type", 3, sub_type=2, vals=[2, 3]),
        _FakeProp(scanner_wia.X_RES, "Horizontal Resolution", 300, sub_type=2, vals=[150, 300, 600]),
        _FakeProp(scanner_wia.Y_RES, "Vertical Resolution", 300, sub_type=2, vals=[150, 300, 600]),
        _FakeProp(scanner_wia.X_POS, "Horizontal Start Position", 0, sub_type=1, mn=0, mx=2550, step=4),
        _FakeProp(scanner_wia.Y_POS, "Vertical Start Position", 0, sub_type=1, mn=0, mx=3510, step=4),
        _FakeProp(scanner_wia.X_EXTENT, "Horizontal Extent", 2550, sub_type=1, mn=16, mx=2550, step=4),
        _FakeProp(scanner_wia.Y_EXTENT, "Vertical Extent", 3510, sub_type=1, mn=16, mx=3510, step=4),
        _FakeProp(scanner_wia.BRIGHTNESS, "Brightness", 0, ro=True),
        _FakeProp(scanner_wia.TYMED, "Media Type", 128),
        _FakeProp(scanner_wia.FORMAT, "Format", scanner_wia.WIA_FORMAT_MEMORYBMP),
    ])

    class _FallbackItem:
        def __init__(self) -> None:
            self.Properties = item_props
            self.Items = _FakeItems([])
            self.WiaItem = _FakeWiaItem(bmp, fail_banded=True)

        def Transfer(self, _fmt=None):
            return SimpleNamespace(FileData=SimpleNamespace(BinaryData=bmp))

    dev_item = _FallbackItem()
    dev_props = _FakeProps([])  # cố tình không có BED_WIDTH (3074) / BED_HEIGHT (3075)
    dev = SimpleNamespace(Properties=dev_props, Items=_FakeItems([dev_item]))
    info_props = _FakeProps([_FakeProp(scanner_wia.WIA_DIP_DEV_NAME, "Name", "Canon LiDE 300 WIA")])
    dev_info = SimpleNamespace(
        DeviceID="canon-01",
        Type=0,  # thiết bị đa năng Type==0 vẫn phải nhận
        Properties=info_props,
        Connect=lambda: dev,
    )
    dm = SimpleNamespace(DeviceInfos=_FakeItems([dev_info]))
    monkeypatch.setattr(scanner_wia.comtypes.client, "CreateObject", lambda _prog: dm)

    devices = scanner_wia.list_scanners()
    assert devices == [("canon-01", "Canon LiDE 300 WIA")]

    # Yêu cầu 400 dpi nhưng máy chỉ hỗ trợ [150, 300, 600] → snap về 300 và trả actual_dpi=300
    img, actual_dpi = scanner_wia.scan_with_info(dpi=400, mode="gray", brightness=10, device_id="canon-01")
    assert actual_dpi == 300
    assert np.array_equal(img, sample)
    # X_EXTENT làm tròn về bội của step=4
    assert item_props.Item("Horizontal Extent").Value % 4 == 0


def test_wia_adf_item_selection_and_batch_stops_on_paper_empty(monkeypatch) -> None:
    """Chọn item Feeder khi source='adf' và scan nhiều trang tới khi WIA_ERROR_PAPER_EMPTY."""
    page1 = np.full((30, 40), 210, dtype=np.uint8)
    page2 = np.full((30, 40), 180, dtype=np.uint8)
    payloads = [_bmp_bytes(page1), _bmp_bytes(page2)]
    calls = {"n": 0}

    def _make_item(name: str, cat: str):
        props = _FakeProps([
            _FakeProp(scanner_wia.ITEM_CATEGORY, "Category", cat),
            _FakeProp(9999, "Item Name", name),
            _FakeProp(scanner_wia.DATA_TYPE, "Data Type", 2),
            _FakeProp(scanner_wia.X_RES, "Horizontal Resolution", 300),
            _FakeProp(scanner_wia.Y_RES, "Vertical Resolution", 300),
            _FakeProp(scanner_wia.X_POS, "Horizontal Start Position", 0, mn=0, mx=2550),
            _FakeProp(scanner_wia.Y_POS, "Vertical Start Position", 0, mn=0, mx=3510),
            _FakeProp(scanner_wia.X_EXTENT, "Horizontal Extent", 2550, mn=1, mx=2550),
            _FakeProp(scanner_wia.Y_EXTENT, "Vertical Extent", 3510, mn=1, mx=3510),
            _FakeProp(scanner_wia.TYMED, "Media Type", 128),
        ])

        class _Item:
            def __init__(self) -> None:
                self.Properties = props
                self.Items = _FakeItems([])
                self.WiaItem = _FakeWiaItem(b"", fail_banded=True)

            def Transfer(self, _fmt=None):
                assert name == "Feeder"
                idx = calls["n"]
                calls["n"] += 1
                if idx < len(payloads):
                    return SimpleNamespace(FileData=SimpleNamespace(BinaryData=payloads[idx]))
                raise comtypes.COMError(scanner_wia.WIA_ERROR_PAPER_EMPTY - 0x100000000, "PAPER_EMPTY", ())

        return _Item()

    flatbed = _make_item("Flatbed", scanner_wia.WIA_CATEGORY_FLATBED)
    feeder = _make_item("Feeder", scanner_wia.WIA_CATEGORY_FEEDER)
    dev = SimpleNamespace(Properties=_FakeProps([]), Items=_FakeItems([flatbed, feeder]))
    dm = SimpleNamespace(
        DeviceInfos=_FakeItems([
            SimpleNamespace(
                DeviceID="brother-adf",
                Type=1,
                Properties=_FakeProps([_FakeProp(scanner_wia.WIA_DIP_DEV_NAME, "Name", "Brother ADS")]),
                Connect=lambda: dev,
            )
        ])
    )
    monkeypatch.setattr(scanner_wia.comtypes.client, "CreateObject", lambda _prog: dm)

    pages = scanner_wia.scan_adf_pages(dpi=300, device_id="brother-adf")
    assert len(pages) == 2
    assert np.array_equal(pages[0][0], page1)
    assert np.array_equal(pages[1][0], page2)


# ─── 3. Lõi xử lý ảnh, xuất PDF/ảnh, phiên scan tạm ─────────────────────────


def test_processing_deskew_diacritics_and_red_stamp() -> None:
    raw_color = scanner.degraded_page(angle=1.5, color=True)
    s = scanner.Settings()
    res = scanner.process(raw_color, s)

    assert abs(res.skew_angle + 1.5) < 0.25
    # Nền lề trái có bóng gáy sách phải trở thành trắng
    margin = res.gray[400:3200, 40:180]
    assert (margin < 230).mean() < 0.01
    # Chữ phải đen rõ
    assert np.median(res.gray[res.gray < 128]) < 70
    # Giữ dấu đỏ trên bản màu
    b, g, r = (res.color[..., i].astype(int) for i in range(3))
    assert ((r > 150) & (g < 110) & (b < 110)).sum() > 3000
    # Đen trắng giữ phần tô đặc (không thủng lõi dấu)
    solid = np.full((300, 300), 250, np.uint8)
    cv2.circle(solid, (150, 150), 60, 110, -1)
    bw_solid = scanner.render(scanner.Prepared(solid, None, 0.0), s, "bw")
    assert (bw_solid[125:175, 125:175] == 0).all()


def test_save_pdf_and_images_keep_real_dimensions_and_dpi(tmp_path: Path) -> None:
    page = np.full((3508, 2480), 255, np.uint8)
    page[1000:1080, 400:1400] = 0
    color = cv2.cvtColor(page[::2, ::2], cv2.COLOR_GRAY2BGR)

    pdf_path = tmp_path / "scan_out.pdf"
    scanner.save_pdf(
        pdf_path,
        [
            scanner.encode_page(page, "gray", 300),
            scanner.encode_page(page, "bw", 300),
            scanner.encode_page(color, "color", 150),
        ],
        title="Thử nghiệm",
        dpis=[300, 300, 150],
    )
    doc = fitz.open(str(pdf_path))
    assert len(doc) == 3
    for p in doc:
        assert abs(p.rect.width - 595.2) < 1.0 and abs(p.rect.height - 841.9) < 1.0
    assert doc.metadata.get("title") == "Thử nghiệm"
    doc.close()

    # Lưu ảnh có đường dẫn tiếng Việt và giữ DPI
    vn_dir = tmp_path / "Thư mục tiếng Việt"
    for fmt, kind, img_in in (("png", "bw", page), ("jpg", "color", color), ("tif", "gray", page)):
        out = vn_dir / f"trang.{fmt}"
        scanner.save_image(out, img_in, kind, 200, fmt)
        loaded, dpi = scanner.imread(out)
        assert dpi == 200
        assert loaded.shape[:2] == img_in.shape[:2]


def test_scan_session_create_reopen_and_discard(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    s = scanner.ScanSession.create(cache)
    img = np.full((120, 100), 200, np.uint8)
    pg = scanner.Page(img, scanner.Settings(dpi=300), output="bw", rotation=90)
    s.add(pg)
    s.update([pg])
    assert scanner.ScanSession.open(s.folder) is None  # đang khoá không mở trùng được
    s.release()

    s2 = scanner.ScanSession.open(s.folder)
    assert s2 is not None
    pages = s2.load_pages()
    assert len(pages) == 1
    assert pages[0].output == "bw" and pages[0].rotation == 90
    assert np.array_equal(pages[0].raw, img)
    s2.discard()
    assert not s.folder.exists()


# ─── 4. Giao diện ScanDialog, chèn vào tab đang mở và CLI scan ────────────────


def test_scan_dialog_preview_crop_saves_a5_pdf(qapp, tmp_path: Path) -> None:
    dlg = ScanDialog(interactive=False, auto_refresh_devices=False)
    dlg.panel.set_save_folder(tmp_path)
    dlg.panel.ask_name.setChecked(False)
    dlg.load_synthetic_preview(dpi=300)
    assert dlg.preview_raw is not None

    dlg.panel.area.setCurrentIndex(dlg.panel.area.findData("a5"))
    dlg._on_area_key_changed("a5")
    crop = dlg.preview_view.crop()
    assert crop is not None
    assert abs(crop.width() / scanner.PREVIEW_DPI * 25.4 - 148) < 1.5

    saved: list[str] = []
    dlg.pdfSaved.connect(lambda p, _o: saved.append(p))
    dlg.save_preview_pdf()
    for t in list(dlg._exports):
        t.wait(10000)
    for _ in range(20):
        QApplication.processEvents()
        if saved:
            break
    assert saved and Path(saved[0]).exists()
    doc = fitz.open(saved[0])
    assert abs(doc[0].rect.width / 72 * 25.4 - 148) < 1.5
    assert abs(doc[0].rect.height / 72 * 25.4 - 210) < 1.5
    doc.close()
    dlg.close()


def test_scan_insert_into_open_pdf_and_undo(qapp, sample_vietnamese_pdf: Path) -> None:
    win = MainWindow(settings=AppSettings.load())
    tab = win.open_pdf_path(sample_vietnamese_pdf)
    assert tab is not None
    orig_count = tab.reader.page_count

    dlg = ScanDialog(win.settings, has_active_doc=True, interactive=False, auto_refresh_devices=False, parent=win)
    dlg.add_synthetic_page("gray")

    def _on_insert(pdf_bytes: bytes) -> None:
        cur = tab.viewer.current_page
        src = fitz.open("pdf", pdf_bytes)
        try:
            tab.annot_controller.session.run_doc_operation(
                "Chèn trang từ máy scan",
                cur,
                lambda d: d.insert_pdf(src, start_at=cur + 1),
            )
        finally:
            src.close()
        tab.reader.invalidate_all()
        tab._refresh_after_page_edit(cur + 1, "Đã chèn trang scan", rebuild_thumbs=True)

    dlg.insertPagesRequested.connect(_on_insert)
    dlg.insert_into_open_pdf()
    assert tab.reader.page_count == orig_count + 1
    assert tab.reader.has_unsaved_changes

    tab.annot_controller.undo()
    assert tab.reader.page_count == orig_count
    dlg.close()
    win.close_tab_at(0, force=True)
    win.close()


def test_cli_scan_synthetic_outputs_pdf(tmp_path: Path, capsys) -> None:
    out = tmp_path / "cli_scan.pdf"
    rc = cli.main(["scan", "--synthetic", "--preset", "1", "-o", str(out), "--json"])
    assert rc == 0
    assert out.is_file()
    doc = fitz.open(str(out))
    assert doc.page_count == 1
    doc.close()
