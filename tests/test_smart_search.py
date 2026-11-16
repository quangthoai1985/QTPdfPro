"""Kiểm thử Tìm kiếm thông minh (Smart Search) và Tìm kiếm trên văn bản ảnh scan."""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
from PySide6.QtWidgets import QApplication

from qtpdfpro.core import ocr_layer
from qtpdfpro.core.ocr import OcrLine
from qtpdfpro.core.reader import PDFDocumentReader
from qtpdfpro.core.settings import AppSettings
from qtpdfpro.core.smart_search import SearchOptions, search_document
from qtpdfpro.ui.main_window import MainWindow


def _font_kwargs() -> dict:
    font = Path(r"C:\Windows\Fonts\times.ttf")
    return {"fontname": "tnr", "fontfile": str(font)} if font.exists() else {"fontname": "helv"}


def _make_multipage_pdf(path: Path) -> Path:
    doc = fitz.open()
    kw = _font_kwargs()

    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((72, 100), "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", fontsize=14, **kw)
    p1.insert_text((72, 140), "Quyết định A thay thế Quyết định B ngày 05/03/2020.", fontsize=12, **kw)
    p1.insert_text((72, 180), "Ban hành văn bản theo Nghị định số 30/2020/NĐ-CP.", fontsize=12, **kw)
    p1.insert_text((72, 220), "Ủy ban nhân dân", fontsize=12, **kw)
    p1.insert_text((72, 240), "tỉnh An Giang thực hiện ngay.", fontsize=12, **kw)

    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((72, 100), "Phần II: Điều khoản thi hành", fontsize=14, **kw)
    p2.insert_text((72, 720), "Quyết định này có hiệu lực từ ngày ký.", fontsize=12, **kw)
    p2.insert_text((72, 760), "Từ khoá cuối trang: Nghiệm thu dự án.", fontsize=12, **kw)

    doc.save(str(path))
    doc.close()
    return path


def _make_tcvn3_pdf(path: Path) -> Path:
    """Tạo PDF dùng phông TCVN3 giả lập theo kỹ thuật CLAUDE.md §5 (helv + /BaseFont /.VnTime)."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # Chuỗi TCVN3 của "Cộng hòa" = "Céng hßa", "Quyết định" = "QuyÕt ®Þnh"
    page.insert_text((72, 120), "Céng hßa x· héi chñ nghÜa ViÖt Nam", fontname="helv", fontsize=14)
    for f in page.get_fonts(full=True):
        doc.xref_set_key(f[0], "BaseFont", "/.VnTime")
    doc.save(str(path))
    doc.close()
    return path


def _make_scanned_pdf(path: Path) -> Path:
    """Tạo PDF ảnh quét 2 trang (không có lớp chữ): trang 1 trên cùng 2 dòng, trang 2 dưới 2 dòng."""
    out = fitz.open()
    kw = _font_kwargs()
    pages_lines = [
        ["CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", "Độc lập tự do hạnh phúc"],
        ["Ủy ban nhân dân tỉnh", "Quyết định phê duyệt kế hoạch"],
    ]
    for idx, lines in enumerate(pages_lines):
        src = fitz.open()
        p = src.new_page(width=595, height=842)
        y = 120 if idx == 0 else 560
        for line in lines:
            p.insert_text((72, y), line, fontsize=18, **kw)
            y += 60
        pix = p.get_pixmap(dpi=150)
        out.new_page(width=595, height=842).insert_image(fitz.Rect(0, 0, 595, 842), pixmap=pix)
        src.close()
    out.save(str(path))
    out.close()
    return path


class _MultiPageBandOcrEngine:
    """Engine OCR giả phân biệt trang dựa trên toạ độ dải mực (trên y<350 = trang 1, dưới y>=350 = trang 2)."""

    def ocr_image(self, rgb: np.ndarray, zoom: float, clean_ink: bool = True):
        mask = rgb.mean(axis=2) < 128
        rows = np.where(mask.any(axis=1))[0]
        bands, start, prev = [], None, None
        for y in rows:
            if start is None:
                start = prev = y
            elif y > prev + 3:
                bands.append((start, prev))
                start = y
            prev = y
        if start is not None:
            bands.append((start, prev))

        is_page2 = bool(bands and (bands[0][0] / zoom) > 350)
        texts = (
            ["Ủy ban nhân dân tỉnh", "Quyết định phê duyệt kế hoạch"]
            if is_page2
            else ["CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", "Độc lập tự do hạnh phúc"]
        )
        out = []
        for (y0, y1), text in zip(bands, texts):
            cols = np.where(mask[y0 : y1 + 1].any(axis=0))[0]
            out.append(
                OcrLine(
                    text,
                    (cols[0] / zoom, y0 / zoom, (cols[-1] + 1) / zoom, (y1 + 1) / zoom),
                    size=14.0,
                    baseline=(y1 + 1) / zoom,
                )
            )
        return out


# ─── 1. Lõi Tìm kiếm thông minh ──────────────────────────────────────────────


def test_smart_search_exact_and_accent_insensitive(tmp_path: Path) -> None:
    pdf = _make_multipage_pdf(tmp_path / "smart.pdf")
    with PDFDocumentReader(pdf) as reader:
        # Gõ không dấu tìm ra đủ cả chữ có dấu ở trang 1 và trang 2
        hits = reader.search("quyet dinh")
        assert len(hits) == 3
        assert [h.page_index for h in hits] == [0, 0, 1]

        # Cụm từ số hiệu
        hits_nd = reader.search("nghi dinh so 30")
        assert len(hits_nd) == 1
        assert "30/2020/NĐ-CP" in hits_nd[0].snippet

        # Tìm chính xác có dấu và kiểm tra snippet căn riêng cho từng kết quả trên cùng 1 dòng
        hits_acc = reader.search("Quyết định")
        assert len(hits_acc) == 3
        assert hits_acc[0].bbox != hits_acc[1].bbox
        assert hits_acc[0].bbox[0] < hits_acc[1].bbox[0]
        assert hits_acc[0].exact is True


def test_smart_search_multiline_phrase_and_whole_word(tmp_path: Path) -> None:
    pdf = _make_multipage_pdf(tmp_path / "multiline.pdf")
    with PDFDocumentReader(pdf) as reader:
        # Cụm từ vắt từ dòng 1 ("Ủy ban nhân dân") xuống dòng 2 ("tỉnh An Giang")
        hits = reader.search("nhân dân tỉnh An")
        assert len(hits) == 1
        assert len(hits[0].rects) == 2

        # Nguyên từ: tìm "an" không được khớp "ban" hay "văn" (khớp đúng 2 từ độc lập: "An" ở tr.1 và "án" ở tr.2)
        hits_all = reader.search("an", whole_word=False)
        hits_whole = reader.search("an", whole_word=True)
        assert len(hits_all) > len(hits_whole)
        assert len(hits_whole) == 2
        # Phân biệt hoa/thường chỉ khớp "An" ở trang 1
        hits_an_exact = reader.search("An", whole_word=True, case_sensitive=True)
        assert len(hits_an_exact) == 1 and hits_an_exact[0].page_index == 0


def test_smart_search_tcvn3_font(tmp_path: Path) -> None:
    pdf = _make_tcvn3_pdf(tmp_path / "tcvn3.pdf")
    with PDFDocumentReader(pdf) as reader:
        assert len(reader.search("Cộng hòa")) == 1
        assert len(reader.search("cong hoa")) == 1
        assert reader.search("cong hoa")[0].bbox[2] > reader.search("cong hoa")[0].bbox[0]


def test_smart_search_ocr_accent_relaxed_fallback(tmp_path: Path) -> None:
    pdf = _make_scanned_pdf(tmp_path / "scan_only.pdf")
    with fitz.open(str(pdf)) as doc:
        # Giả lập lớp OCR bị thiếu 1 dấu sắc ở "duyêt"
        fake_ocr = {
            1: [(72.0, 600.0, 140.0, 620.0, "phê", 0, 0, 0), (145.0, 600.0, 220.0, 620.0, "duyêt", 0, 0, 1)]
        }
        hits = search_document(doc, "phê duyệt", SearchOptions(smart_accents=True), ocr_words=fake_ocr)
        assert len(hits) == 1
        assert hits[0].page_index == 1
        assert hits[0].source == "ocr"
        assert hits[0].exact is False


# ─── 2. Điều hướng tức thì & Tìm trên văn bản ảnh scan qua Giao diện ──────────


def test_search_navigates_viewer_immediately_continuous_and_single_page(qapp, tmp_path: Path) -> None:
    pdf = _make_multipage_pdf(tmp_path / "nav.pdf")
    win = MainWindow(settings=AppSettings.load())
    win.resize(1100, 750)
    win.show()
    tab = win.open_pdf_path(pdf)
    assert tab is not None
    QApplication.processEvents()

    # Đang ở trang 1, tìm cụm chỉ có ở cuối trang 2 → nhảy thẳng sang trang 2 và cuộn xuống
    tab.focus_search()
    tab.search_input.setText("nghiem thu du an")
    tab.run_search()
    QApplication.processEvents()

    assert len(tab._search_hits) == 1
    assert tab.viewer.current_page == 1
    assert tab.viewer.verticalScrollBar().value() > 0
    assert tab.search_pos_lbl.text() == "1 / 1"

    # Chuyển sang chế độ xem Từng trang và tìm lại ở trang 1 → nhảy ngay về trang 1
    tab.viewer.set_continuous_mode(False)
    tab.search_input.setText("quyet dinh")
    tab.run_search()
    QApplication.processEvents()
    # Đang ở trang 2 nên chọn kết quả trên trang 2 trước ("3 / 3"), bấm F3/next vòng sang trang 1 ("1 / 3")
    assert tab.viewer.current_page == 1
    assert tab.search_pos_lbl.text() == "3 / 3"
    tab.next_search_hit()
    QApplication.processEvents()
    assert tab.viewer.current_page == 0
    assert tab.search_pos_lbl.text() == "1 / 3"

    tab.prev_search_hit()
    QApplication.processEvents()
    assert tab.viewer.current_page == 1
    assert tab.search_pos_lbl.text() == "3 / 3"

    win.close_tab_at(0, force=True)
    win.close()


def test_smart_search_on_scanned_pdf_auto_ocrs_and_navigates(qapp, tmp_path: Path) -> None:
    pdf = _make_scanned_pdf(tmp_path / "scanned_doc.pdf")
    win = MainWindow(settings=AppSettings.load())
    win.resize(1100, 750)
    win.show()
    tab = win.open_pdf_path(pdf)
    assert tab is not None
    tab.wait_for_document_analysis()

    engine = _MultiPageBandOcrEngine()
    tab.ocr_layer.engine_factory = lambda: engine
    tab.ocr_layer.models_ready = lambda: True

    # Tìm từ khoá không dấu ở trang 2 trên tài liệu ảnh quét hoàn toàn không có lớp chữ
    tab.focus_search()
    tab.search_input.setText("phe duyet")
    tab.run_search()
    tab.ocr_layer.wait_idle()
    QApplication.processEvents()

    assert len(tab._search_hits) >= 1
    assert tab._search_hits[0].page_index == 1
    assert tab._search_hits[0].source == "ocr"
    assert tab.viewer.current_page == 1
    assert tab.search_pos_lbl.text() == "1 / 1"
    assert not tab.search_ocr_bar.isVisible()

    # Đóng và mở lại cùng tệp scan → đọc từ OcrLayerCache tìm thấy ngay lập tức
    win.close_tab_at(0, force=True)
    tab2 = win.open_pdf_path(pdf)
    assert tab2 is not None
    tab2.ocr_layer.engine_factory = lambda: (_ for _ in ()).throw(AssertionError("Phải lấy từ cache!"))
    tab2.ocr_layer.models_ready = lambda: True
    tab2.ocr_layer.request(0)
    tab2.ocr_layer.wait_idle()
    tab2.search_input.setText("phe duyet")
    tab2.run_search()
    QApplication.processEvents()

    assert len(tab2._search_hits) == 1
    assert tab2.viewer.current_page == 1

    win.close_tab_at(0, force=True)
    win.close()
