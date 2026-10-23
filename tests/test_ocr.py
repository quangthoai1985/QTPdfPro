"""Kiểm thử OCR tiếng Việt (`core/ocr.py`, `core/ocr_models.py`, lệnh `cli ocr`).

Không gọi mạng thật (thay `update_check._urlopen`) và không cần bộ mô hình thật: bộ máy OCR dùng bộ tìm dòng /
bộ đọc chữ giả. Bài cuối chạy mô hình thật nếu máy đã cài (đặt `QT_PDF_PRO_OCR_MODELS` hoặc đã `ocr --install`).
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
import pytest

from qtpdfpro import cli
from qtpdfpro.core import ocr, ocr_models
from qtpdfpro.core import update_check as uc
from qtpdfpro.core.annotations import system_font_dir

FONT = system_font_dir()
needs_font = pytest.mark.skipif(FONT is None, reason="cần phông Times New Roman của Windows")


class FakeResponse:
    def __init__(self, body: bytes, url: str) -> None:
        self._buf = io.BytesIO(body)
        self._url = url
        self.headers = {"Content-Length": str(len(body))}

    def read(self, n: int = -1) -> bytes:
        return self._buf.read(n)

    def geturl(self) -> str:
        return self._url

    def close(self) -> None:
        pass


# ─── Dữ liệu tự sinh ───────────────────────────────────────────────────────


def _ink_line(widths_gaps, h: int = 40) -> np.ndarray:
    """Ảnh xám dòng chữ giả: các khối mực rộng `w` cách nhau `g` điểm ảnh."""
    total = sum(w + g for w, g in widths_gaps) + 10
    img = np.full((h, total), 255, np.uint8)
    x = 5
    for w, g in widths_gaps:
        img[10:30, x:x + w] = 0
        x += w + g
    return img


def _scanned_pdf(path: Path, lines, dpi: int = 150, rotate: int = 0) -> Path:
    """PDF «ảnh quét»: trang chữ thật → ảnh → trang mới chỉ có ảnh (không lớp chữ)."""
    src = fitz.open()
    page = src.new_page(width=595, height=842)
    kw = {"fontname": "vn", "fontfile": str(FONT / "times.ttf")} if FONT else {"fontname": "tiro"}
    for x, y, text, size in lines:
        page.insert_text((x, y), text, fontsize=size, **kw)
    pix = page.get_pixmap(dpi=dpi)
    out = fitz.open()
    p = out.new_page(width=595, height=842)
    p.insert_image(p.rect, pixmap=pix)
    if rotate:
        p.set_rotation(rotate)
    out.save(str(path))
    return path


def _band_detector(bgr: np.ndarray):
    """Bộ tìm dòng giả: dải hàng có mực → một khung ngang phủ toàn bộ mực của dải."""
    ink = bgr.min(axis=2) < 128
    rows = np.convolve(ink.any(axis=1).astype(int), np.ones(9, int), "same") > 0  # gộp dấu thanh với chữ
    boxes, start = [], None
    for y, flag in enumerate(list(rows) + [False]):
        if flag and start is None:
            start = y
        elif not flag and start is not None:
            xs = np.where(ink[start:y].any(axis=0))[0]
            x0, x1, y0, y1 = xs[0] - 3, xs[-1] + 3, start - 3, y + 3
            boxes.append(np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float32))
            start = None
    return boxes


class _Reader:
    """Bộ đọc chữ giả: trả lần lượt các dòng cho trước (theo thứ tự gọi)."""

    def __init__(self, texts):
        self.texts = list(texts)
        self.calls = 0

    def __call__(self, gray):
        self.calls += 1
        return self.texts.pop(0) if self.texts else "Bộ trưởng Bộ Giáo dục"


def fake_engine(texts=()) -> ocr.OcrEngine:
    return ocr.OcrEngine(_band_detector, _Reader(texts))


# ─── Xử lý ảnh ─────────────────────────────────────────────────────────────


def test_remove_color_ink_keeps_black_text_under_red_seal():
    rgb = np.full((10, 30, 3), 255, np.uint8)
    rgb[:, 0:10] = (210, 40, 50)  # con dấu đỏ
    rgb[:, 10:20] = (40, 60, 170)  # chữ ký xanh
    rgb[:, 20:30] = (20, 20, 20)  # chữ in đen
    out = ocr.remove_color_ink(rgb)
    assert (out[:, 1:8] == 255).all() and (out[:, 12:18] == 255).all()
    assert (out[:, 22:30] == 20).all()


def test_split_long_line_cuts_in_gap_and_joins_with_space():
    img = _ink_line([(60, 12)] * 12)  # 12 «từ» cách nhau 12 px, cao 40 → tỷ lệ ~21:1
    parts = ocr.split_long_line(img)
    assert len(parts) == 2
    assert parts[0][1] == "" and parts[1][1] == " "
    assert sum(p.shape[1] for p, _j in parts) == img.shape[1]
    solid = _ink_line([(900, 0)])  # liền một khối (số «2008») → cắt ở cột ít mực, nối liền
    assert [j for _p, j in ocr.split_long_line(solid)][1:] == [""]
    assert len(ocr.split_long_line(_ink_line([(200, 0)]))) == 1


def test_leading_dash_detection():
    with_dash = np.full((48, 200), 255, np.uint8)
    with_dash[24:27, 10:20] = 0  # «-» mảnh giữa dòng
    with_dash[12:34, 28:120] = 0  # chữ phía sau
    assert ocr.has_leading_dash(with_dash)
    no_dash = np.full((48, 200), 255, np.uint8)
    no_dash[12:34, 10:120] = 0
    assert not ocr.has_leading_dash(no_dash)


def test_fix_stray_caps_only_touches_toned_words_in_lowercase_lines():
    assert ocr.fix_stray_caps("2. Chỉ thị số 52/2007/CT-BGDĐT NGÀY 31 tháng 8 năm 2007") == \
        "2. Chỉ thị số 52/2007/CT-BGDĐT ngày 31 tháng 8 năm 2007"
    assert ocr.fix_stray_caps("CỘNG HOÀ XÃ HỘI CHỦ NGHĨA VIỆT NAM") == "CỘNG HOÀ XÃ HỘI CHỦ NGHĨA VIỆT NAM"
    assert ocr.fix_stray_caps("HĐND, UBND các tỉnh, thành phố") == "HĐND, UBND các tỉnh, thành phố"


def test_column_spans_split_two_columns_not_words():
    row = _ink_line([(120, 10), (80, 70), (150, 0)])  # khoảng cách từ 10 px, khoảng trống cột 70 px (cao 40)
    spans = ocr.column_spans(row)
    assert len(spans) == 2
    assert spans[0][1] < spans[1][0]


def test_prepare_line_image_and_vocab():
    x = ocr.prepare_line_image(np.full((50, 400), 255, np.uint8))
    assert x.shape[:3] == (1, 3, 32) and x.shape[3] % 10 == 0 and x.shape[3] <= 512
    assert x.dtype == np.float32 and 0.99 <= x.max() <= 1.0
    vocab = ocr.Vocab("aăâbộ ")
    ids = [1] + [4 + "aăâbộ ".index(c) for c in "bộ"] + [2, 9]
    assert vocab.decode(ids) == "bộ"


def test_recognizer_greedy_decoding_with_fake_sessions():
    vocab = ocr.Vocab("Bộ ")

    class Enc:
        def run(self, _names, feeds):
            assert feeds["img"].shape[:3] == (1, 3, 32)
            return [np.zeros((1, 4), np.float32), np.zeros((3, 1, 8), np.float32)]

    class Dec:
        def __init__(self):
            self.step = 0

        def run(self, _names, feeds):
            seq = [4, 5, 2]  # «B», «ộ», kết thúc
            logits = np.zeros((1, 8), np.float32)
            logits[0, seq[min(self.step, 2)]] = 1.0
            self.step += 1
            return [logits, feeds["hidden"]]

    rec = ocr.TextRecognizer(Enc(), Dec(), vocab, {})
    assert rec(np.full((40, 120), 255, np.uint8)) == "Bộ"


def test_db_boxes_expands_kernel_like_pyclipper():
    pred = np.zeros((100, 300), np.float32)
    pred[40:50, 50:250] = 0.9  # nhân chữ 200 × 10
    boxes = ocr.db_boxes(pred, 100, 300)
    assert len(boxes) == 1
    b = boxes[0]
    w, h = np.linalg.norm(b[1] - b[0]), np.linalg.norm(b[3] - b[0])
    assert w > 210 and 20 < h < 30  # nới d = S·1,6 / C ≈ 7,6 px mỗi phía


def test_auto_dpi_follows_scan_resolution(tmp_path: Path):
    pdf = _scanned_pdf(tmp_path / "scan.pdf", [(60, 100, "Văn bản", 14)], dpi=200)
    with fitz.open(pdf) as doc:
        assert ocr.auto_dpi(doc[0]) == 200
        blank = fitz.open()
        assert ocr.auto_dpi(blank.new_page()) == ocr.MAX_DPI


# ─── Bộ máy OCR (bộ tìm dòng / đọc chữ giả) ────────────────────────────────


@needs_font
def test_ocr_image_splits_columns_and_estimates_styles(tmp_path: Path):
    pdf = _scanned_pdf(tmp_path / "scan.pdf", [
        (55, 80, "BỘ GIÁO DỤC VÀ ĐÀO TẠO", 13), (330, 80, "CỘNG HOÀ XÃ HỘI CHỦ NGHĨA", 13),
        (70, 140, "Căn cứ Luật Ban hành văn bản quy phạm pháp luật số 64/2025/QH15", 14),
    ])
    engine = fake_engine(["BỘ GIÁO DỤC VÀ ĐÀO TẠO", "CỘNG HOÀ XÃ HỘI CHỦ NGHĨA", "Căn cứ Luật Ban hành"])
    with fitz.open(pdf) as doc:
        res = engine.ocr_page(doc[0], dpi=150)
    assert [ln.text for ln in res.lines] == ["BỘ GIÁO DỤC VÀ ĐÀO TẠO", "CỘNG HOÀ XÃ HỘI CHỦ NGHĨA", "Căn cứ Luật Ban hành"]
    left, right, body = res.lines
    assert left.bbox[2] < right.bbox[0]  # hai cột cùng hàng thành hai dòng
    assert 60 < left.base_y < 85 and 135 < body.base_y < 145
    assert 9 <= body.size <= 20


@needs_font
def test_ocr_pdf_adds_searchable_vietnamese_text_layer(tmp_path: Path):
    pdf = _scanned_pdf(tmp_path / "scan.pdf", [(70, 120, "Bộ trưởng Bộ Giáo dục và Đào tạo", 14)])
    res = ocr.ocr_pdf(pdf, tmp_path / "scan_ocr.pdf", engine=fake_engine(["Bộ trưởng Bộ Giáo dục và Đào tạo"]))
    assert res.pages_ocr == 1 and res.lines == 1 and res.output_kind == "pdf"
    with fitz.open(tmp_path / "scan_ocr.pdf") as out:
        text = out[0].get_text()
        assert "Bộ trưởng Bộ Giáo dục và Đào tạo" in text
        assert "\xa0" not in text  # dấu cách chép ra U+0020
        hits = out[0].search_for("Giáo dục")
        assert hits and 60 < hits[0].y1 < 140
        assert len(out[0].get_images()) == 1  # ảnh quét giữ nguyên


@needs_font
@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_text_layer_on_rotated_pages(tmp_path: Path, rotation: int):
    pdf = _scanned_pdf(tmp_path / "scan.pdf", [(70, 120, "Bộ trưởng", 14)], rotate=rotation)

    class Engine(ocr.OcrEngine):
        def __init__(self):
            pass

        def ocr_page(self, page, dpi=0, clean_ink=True, keep_ink_images=False):
            r = ocr.OcrPage(page.number, page.rect.width, page.rect.height)
            r.lines = [ocr.OcrLine("Bộ trưởng Bộ Giáo dục", (60, 80, 300, 100), size=14, baseline=96)]
            return r

    ocr.ocr_pdf(pdf, tmp_path / "out.pdf", engine=Engine())
    with fitz.open(tmp_path / "out.pdf") as out:
        page = out[0]
        assert page.get_text().strip() == "Bộ trưởng Bộ Giáo dục"
        rect = page.search_for("Bộ trưởng Bộ Giáo dục")[0] * page.rotation_matrix
        assert abs(rect.x0 - 60) < 3 and abs(rect.x1 - 300) < 3 and 78 < rect.y0 < rect.y1 < 102


def test_pages_with_text_are_skipped(sample_vietnamese_pdf: Path, tmp_path: Path):
    reader = _Reader([])
    engine = ocr.OcrEngine(_band_detector, reader)
    res = ocr.ocr_pdf(sample_vietnamese_pdf, tmp_path / "out.pdf", engine=engine)
    assert res.pages_skipped == 2 and res.pages_ocr == 0 and reader.calls == 0
    assert "không cần OCR" in res.note


@needs_font
def test_ocr_to_text_and_docx(tmp_path: Path):
    lines = [(70, 120, "QUYẾT ĐỊNH", 14), (70, 160, "Điều 1. Ban hành quy chế làm việc", 14)]
    pdf = _scanned_pdf(tmp_path / "scan.pdf", lines)
    res = ocr.ocr_to_text(pdf, tmp_path / "scan.txt", engine=fake_engine(["QUYẾT ĐỊNH", "Điều 1. Ban hành quy chế làm việc"]))
    assert res.output_kind == "txt"
    assert (tmp_path / "scan.txt").read_text(encoding="utf-8").startswith("QUYẾT ĐỊNH\nĐiều 1.")

    res = ocr.ocr_to_docx(pdf, tmp_path / "scan.docx", engine=fake_engine(["QUYẾT ĐỊNH", "Điều 1. Ban hành quy chế làm việc"]))
    from docx import Document

    text = "\n".join(p.text for p in Document(str(tmp_path / "scan.docx")).paragraphs)
    assert "QUYẾT ĐỊNH" in text and "Ban hành quy chế" in text
    assert res.output_kind == "docx"


def test_output_must_not_overwrite_source(tmp_path: Path):
    pdf = _scanned_pdf(tmp_path / "scan.pdf", [(70, 120, "Văn bản", 14)])
    with pytest.raises(ocr.OcrError):
        ocr.ocr_pdf(pdf, pdf, engine=fake_engine())


def test_engine_load_without_models_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(ocr_models.MODELS_ENV, raising=False)
    with pytest.raises(ocr.OcrModelsMissing):
        ocr.OcrEngine.load()


# ─── Tải & cài bộ mô hình ──────────────────────────────────────────────────


def _bundle_zip(files: dict[str, bytes], extra: dict[str, bytes] | None = None, version: int = ocr_models.BUNDLE_VERSION) -> bytes:
    manifest = {
        "id": "ocr-vi", "version": version, "detector": {"file": "det.onnx"},
        "recognizer": {"encoder": "enc.onnx", "decoder": "dec.onnx", "vocab": "vocab.txt"},
        "files": {n: {"sha256": hashlib.sha256(b).hexdigest(), "size": len(b)} for n, b in files.items()},
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, body in {**files, **(extra or {})}.items():
            zf.writestr(name, body)
        zf.writestr("manifest.json", json.dumps(manifest))
    return buf.getvalue()


FILES = {"det.onnx": b"d" * 100, "enc.onnx": b"e" * 300, "dec.onnx": b"x" * 50, "vocab.txt": "aăâ".encode("utf-8")}


def _serve(monkeypatch: pytest.MonkeyPatch, body: bytes, url: str) -> uc.ReleaseAsset:
    monkeypatch.setattr(uc, "_urlopen", lambda req, timeout, hosts: FakeResponse(body, req.full_url))
    return uc.ReleaseAsset(name="QTPdfPro_OCR_vi_v1.zip", url=url, size=len(body), sha256=hashlib.sha256(body).hexdigest())


URL = "https://github.com/quangthoai1985/QTPdfPro/releases/download/ocr-models-v1/QTPdfPro_OCR_vi_v1.zip"


def test_install_models_downloads_verifies_and_installs(monkeypatch: pytest.MonkeyPatch, isolated_app_data: Path):
    monkeypatch.delenv(ocr_models.MODELS_ENV, raising=False)
    assert not ocr_models.is_installed()
    assert not (isolated_app_data / "modules").exists()  # xem trạng thái không tạo thư mục
    asset = _serve(monkeypatch, _bundle_zip(FILES), URL)
    seen = []
    bundle = ocr_models.install_models(progress_cb=lambda d, t: seen.append((d, t)), asset=asset)
    assert bundle.root == ocr_models.bundle_dir() and ocr_models.is_installed()
    assert bundle.recognizer["vocab"] == "vocab.txt"
    assert seen[-1] == (asset.size, asset.size)
    assert sorted(p.name for p in ocr_models.modules_dir().iterdir()) == ["ocr-vi-1"]  # không còn zip / thư mục tạm
    assert ocr_models.status()["installed"] and ocr_models.remove_models() and not ocr_models.is_installed()


def test_install_models_rejects_bad_hash_zip_slip_and_untrusted_host(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(ocr_models.MODELS_ENV, raising=False)
    asset = _serve(monkeypatch, _bundle_zip(FILES), URL)
    asset.sha256 = "0" * 64
    with pytest.raises(ocr_models.OcrModelError, match="SHA-256"):
        ocr_models.install_models(asset=asset)
    asset = _serve(monkeypatch, _bundle_zip(FILES, extra={"../evil.txt": b"x"}), URL)
    with pytest.raises(ocr_models.OcrModelError, match="không an toàn"):
        ocr_models.install_models(asset=asset)
    bad = dict(FILES)
    asset = _serve(monkeypatch, _bundle_zip(bad, version=99), URL)
    with pytest.raises(ocr_models.OcrModelError, match="phiên bản"):
        ocr_models.install_models(asset=asset)
    asset = _serve(monkeypatch, _bundle_zip(FILES), "http://example.com/model.zip")
    with pytest.raises(ocr_models.OcrModelError, match="không tin cậy"):
        ocr_models.install_models(asset=asset)
    assert not ocr_models.is_installed()
    assert not list(ocr_models.modules_dir().glob("*")) or \
        all(p.name not in ("ocr-vi-1", asset.name) for p in ocr_models.modules_dir().iterdir())


def test_install_models_cancel_leaves_nothing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(ocr_models.MODELS_ENV, raising=False)
    asset = _serve(monkeypatch, _bundle_zip(FILES), URL)
    with pytest.raises(ocr_models.OcrModelCancelled):
        ocr_models.install_models(asset=asset, should_cancel=lambda: True)
    assert not ocr_models.is_installed()
    assert not (ocr_models.modules_dir() / asset.name).exists()


def test_models_env_override_and_size_check(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    folder = tmp_path / "models"
    with zipfile.ZipFile(io.BytesIO(_bundle_zip(FILES))) as zf:
        zf.extractall(folder)
    monkeypatch.setenv(ocr_models.MODELS_ENV, str(folder))
    assert ocr_models.find_bundle().root == folder
    (folder / "enc.onnx").write_bytes(b"short")
    assert ocr_models.find_bundle() is None


def test_pinned_bundle_points_to_github_release():
    a = ocr_models.BUNDLE_ASSET
    uc.validate_url(a.url)  # chỉ https + host GitHub
    assert a.url.endswith(f"/{ocr_models.BUNDLE_TAG}/{a.name}") and len(a.sha256) == 64 and a.size > 50_000_000


# ─── Dòng lệnh ─────────────────────────────────────────────────────────────


def test_cli_ocr_status_and_missing_models(monkeypatch: pytest.MonkeyPatch, capsys, tmp_path: Path):
    monkeypatch.delenv(ocr_models.MODELS_ENV, raising=False)
    assert cli.main(["ocr", "--status", "--json"]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["installed"] is False and info["download_url"] == ocr_models.BUNDLE_ASSET.url
    pdf = _scanned_pdf(tmp_path / "scan.pdf", [(70, 120, "Văn bản", 14)])
    assert cli.main(["ocr", str(pdf)]) == 1
    assert "Chưa cài bộ mô hình OCR" in capsys.readouterr().err


@needs_font
def test_cli_ocr_writes_pdf_with_fake_engine(monkeypatch: pytest.MonkeyPatch, capsys, tmp_path: Path):
    pdf = _scanned_pdf(tmp_path / "scan.pdf", [(70, 120, "Bộ trưởng Bộ Giáo dục", 14)])
    monkeypatch.setattr(ocr.OcrEngine, "load", classmethod(lambda cls, threads=0: fake_engine(["Bộ trưởng Bộ Giáo dục"])))
    assert cli.main(["ocr", str(pdf), "-o", str(tmp_path / "ra.pdf"), "--json"]) == 0
    res = json.loads(capsys.readouterr().out)
    assert res["pages_ocr"] == 1 and Path(res["output_path"]).name == "ra.pdf"


# ─── Mô hình thật (chỉ khi máy đã cài) ─────────────────────────────────────


@needs_font
@pytest.mark.skipif(ocr_models.find_bundle() is None, reason="chưa cài bộ mô hình OCR (ocr --install)")
def test_real_models_read_vietnamese(tmp_path: Path):
    text = "Căn cứ Nghị định số 79/2025/NĐ-CP ngày 01 tháng 4 năm 2025 của Chính phủ"
    pdf = _scanned_pdf(tmp_path / "scan.pdf", [(60, 120, text, 13)], dpi=200)
    res = ocr.recognize_document(fitz.open(pdf))
    got = res[0].text
    import difflib

    assert difflib.SequenceMatcher(a=text, b=got).ratio() > 0.95, got
