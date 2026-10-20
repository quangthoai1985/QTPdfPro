"""Kiểm thử chú thích & đánh dấu (`core/annotations.py`), phiên chỉnh sửa có Hoàn tác (`core/edit_session.py`),
lưu qua `PDFDocumentReader` và lệnh CLI `annotate` / `annots`."""

from __future__ import annotations

import json
from pathlib import Path

import fitz  # PyMuPDF
import pytest

from qtpdfpro.cli import main as cli_main
from qtpdfpro.core import annotations as an
from qtpdfpro.core.edit_session import EditSession
from qtpdfpro.core.reader import PDFDocumentReader

ARIAL = Path(r"C:\Windows\Fonts\arial.ttf")
LINE1 = "Cộng hoà xã hội chủ nghĩa Việt Nam độc lập"
LINE2 = "Dòng thứ hai của văn bản mẫu kiểm thử"


def _make_doc(path: Path, rotation: int = 0) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=420, height=595)
    kw = {"fontname": "F0", "fontfile": str(ARIAL)} if ARIAL.exists() else {}
    page.insert_text((50, 80), LINE1, fontsize=12, **kw)
    page.insert_text((50, 100), LINE2, fontsize=12, **kw)
    if rotation:
        page.set_rotation(rotation)
    doc.save(str(path))
    doc.close()
    return path


def _ink_bbox(page: fitz.Page, clip: fitz.Rect, rgb_test) -> fitz.IRect | None:
    """Khung bao các điểm ảnh thoả `rgb_test` trong vùng `clip` (toạ độ hiển thị, 72 dpi)."""
    pix = page.get_pixmap(dpi=72, clip=clip)
    s, n, w = pix.samples, pix.n, pix.width
    xs, ys = [], []
    for i in range(0, len(s), n):
        if rgb_test(s[i], s[i + 1], s[i + 2]):
            k = i // n
            xs.append(k % w)
            ys.append(k // w)
    return fitz.IRect(min(xs), min(ys), max(xs), max(ys)) if xs else None


def test_parse_color_and_presets() -> None:
    assert an.parse_color("#ff0000") == (1.0, 0.0, 0.0)
    assert an.color_hex(an.parse_color("vàng")) == "#FACC15"
    assert an.color_hex(an.parse_color("Đỏ")) == "#DC2626"
    assert an.color_hex(an.parse_color((255, 255, 255))) == "#FFFFFF"
    assert an.tint("#000000", 0.5) == "#808080"
    with pytest.raises(an.AnnotationError):
        an.parse_color("khongphaimau")


def test_text_selection_reading_order(tmp_path: Path) -> None:
    doc = fitz.open(str(_make_doc(tmp_path / "a.pdf")))
    words = an.page_words(doc[0])
    rects = an.select_text_rects(words, (52, 75), (150, 98))
    assert len(rects) == 2  # hết dòng 1 + đầu dòng 2
    assert rects[0].x1 > 250 and rects[1].x0 < 60
    assert an.text_under_rects(doc[0], rects).startswith("Cộng hoà xã hội")
    area = an.words_in_rect(words, fitz.Rect(45, 85, 120, 105))
    assert len(area) == 1 and area[0].y0 > 85
    doc.close()


@pytest.mark.parametrize("rotation", [0, 90])
def test_edit_session_add_undo_redo_move_save(tmp_path: Path, rotation: int) -> None:
    pdf = _make_doc(tmp_path / f"s{rotation}.pdf", rotation)
    reader = PDFDocumentReader(pdf)
    session = reader.edit_session(author="Kiểm thử")
    assert reader.has_unsaved_changes is False

    rects = session.select_text(0, (52, 75), (150, 98))
    hl = session.add_markup(0, "highlight", rects, an.AnnotStyle())
    session.add_ink(0, [[(60, 200), (90, 230), (120, 210)]], an.AnnotStyle(color="#DC2626", width=2))
    session.add_shape(0, "arrow", (60, 300), (160, 260), an.AnnotStyle(color="#2563EB", width=2))
    box = session.add_text_box(0, fitz.Rect(200, 150, 380, 160), "Hộp chữ: Ỷ ỡ ữ", an.AnnotStyle(fill="#FEF9C3"))
    stamp = session.add_stamp(0, (300, 400), "đã duyệt", an.AnnotStyle(color="#16A34A", font_size=18),
                              date_text=an.stamp_date_text())
    note = session.add_note(0, (380, 60), "Cần bổ sung số liệu", an.AnnotStyle())
    assert reader.has_unsaved_changes is True

    items = session.list_annotations()
    assert [i.subtype for i in items] == ["Highlight", "Ink", "Line", "FreeText", "Stamp", "Text"]
    assert items[0].content.startswith("Cộng hoà")
    assert items[3].app_kind == "textbox" and items[4].app_kind == "stamp"
    assert "ĐÃ DUYỆT" in items[4].content and items[4].author == "Kiểm thử"
    assert session.annotation_at(0, (300, 400)) == stamp
    assert session.annotation_at(0, (5, 5)) is None
    assert session.annotation_at(0, (90, 230)) is not None  # trúng nét vẽ
    assert items[0].movable is False and items[4].movable is True

    # Di chuyển giữ nguyên kích thước, hoàn tác về chỗ cũ
    before = session.annotation_rect(0, stamp)
    assert session.move(0, stamp, 20, 30)
    after = session.annotation_rect(0, stamp)
    assert after.x0 == pytest.approx(before.x0 + 20, abs=0.05)
    assert after.y0 == pytest.approx(before.y0 + 30, abs=0.05)
    assert after.width == pytest.approx(before.width, abs=0.05)
    assert session.move(0, hl, 5, 5) is False  # tô sáng gắn với chữ — không di chuyển

    # Sửa nội dung hộp chữ (dựng lại hình hiển thị) rồi hoàn tác chuỗi
    assert session.set_content(0, box, "Nội dung mới")
    assert session.info(0, box).content == "Nội dung mới"
    session.undo()
    assert session.info(0, box).content == "Hộp chữ: Ỷ ỡ ữ"
    session.undo()
    assert session.annotation_rect(0, stamp).x0 == pytest.approx(before.x0, abs=0.05)
    session.redo()
    session.redo()

    # Xoá mềm + hoàn tác
    assert session.delete(0, note)
    assert len(session.list_annotations()) == 5
    session.undo()
    assert len(session.list_annotations()) == 6
    session.delete(0, note)

    saved = reader.save()
    assert saved == pdf.resolve()
    assert reader.has_unsaved_changes is False and session.can_undo is False
    reader.close()

    with fitz.open(str(pdf)) as doc:
        page = doc[0]
        kinds = [a.type[1] for a in page.annots()]
        assert kinds == ["Highlight", "Ink", "Line", "FreeText", "Stamp"]  # ghi chú đã xoá hẳn
        assert an.qt_data(doc, box)["text"] == "Nội dung mới"


def test_custom_appearance_uses_truetype_font(tmp_path: Path) -> None:
    """Hộp chữ dựng bằng phông TrueType nhúng (không phải Helvetica của MuPDF) và đứng thẳng trên trang xoay."""
    if an.system_font_dir() is None:
        pytest.skip("Máy không có phông Windows")
    for rotation in (0, 90, 180, 270):
        doc = fitz.open(str(_make_doc(tmp_path / f"r{rotation}.pdf", rotation)))
        page = doc[0]
        center = fitz.Point(140, 270)  # toạ độ trên trang đang hiển thị
        annot = an.add_stamp(page, center * page.derotation_matrix, "BẢN SAO",
                             an.AnnotStyle(color="#DC2626", font_size=20))
        xref = annot.xref
        del annot
        ap_kind, ap_ref = doc.xref_get_key(xref, "AP/N")
        assert ap_kind == "xref"
        # Hình hiển thị có phông nhúng (FontFile2 = TrueType) — không dùng Helvetica dựng sẵn của MuPDF
        ap_xref = int(ap_ref.split()[0])
        assert "/FontFile2" in "".join(doc.xref_object(x) for x in range(ap_xref - 12, ap_xref)
                                       if x > 0 and doc.xref_object(x))
        assert doc.xref_get_key(xref, "Name")[1] == f"/{an.APP_STAMP_NAME}"
        # Dấu đỏ nằm quanh tâm đã chọn trên trang hiển thị và rộng hơn cao (chữ ngang, không bị xoay)
        box = _ink_bbox(page, page.rect, lambda r, g, b: r > 180 and g < 90 and b < 90)
        assert box is not None
        assert abs((box.x0 + box.x1) / 2 - center.x) < 4
        assert abs((box.y0 + box.y1) / 2 - center.y) < 4
        assert box.width > box.height * 1.8
        doc.close()


def test_reader_save_as_and_flatten(tmp_path: Path) -> None:
    pdf = _make_doc(tmp_path / "goc.pdf")
    reader = PDFDocumentReader(pdf)
    session = reader.edit_session(author="A")
    session.add_markup(0, "underline", session.select_text(0, (52, 75), (200, 80)), an.AnnotStyle(color="#16A34A"))
    new_path = reader.save(tmp_path / "ban_moi.pdf")
    assert new_path == (tmp_path / "ban_moi.pdf").resolve() and reader.path == new_path
    flat = reader.export_flattened(tmp_path / "phang.pdf")
    reader.close()
    with fitz.open(str(pdf)) as doc:
        assert not list(doc[0].annots())  # tệp gốc không đổi
    with fitz.open(str(new_path)) as doc:
        assert [a.type[1] for a in doc[0].annots()] == ["Underline"]
    with fitz.open(str(flat)) as doc:
        assert not list(doc[0].annots())
        assert doc[0].get_drawings()  # nét gạch chân đã vẽ vào nội dung trang


def test_apply_operations_and_mark_text(tmp_path: Path) -> None:
    doc = fitz.open(str(_make_doc(tmp_path / "o.pdf", 90)))
    n = an.apply_operations(doc, [
        {"type": "highlight", "text": "Việt Nam"},
        {"type": "strikeout", "page": 1, "rect": [0, 0, 600, 600]},
        {"type": "note", "page": 1, "at": [60, 60], "text": "Ghi chú"},
        {"type": "stamp", "page": 1, "at": [300, 200], "label": "mật", "date": "Ngày 01/01/2026"},
        {"type": "text", "page": 1, "rect": [40, 200, 240, 220], "text": "Hộp chữ", "font_family": "serif"},
        {"type": "marker", "page": 1, "points": [[50, 300], [200, 300]]},
        {"type": "ellipse", "page": 1, "from": [50, 320], "to": [150, 380], "color": "xanh"},
    ], author="CLI")
    assert n == 7
    kinds = [i.subtype for i in an.list_annotations(doc)]
    assert kinds.count("Highlight") == 1 and "StrikeOut" in kinds and "Circle" in kinds
    stamp = [i for i in an.list_annotations(doc) if i.app_kind == "stamp"][0]
    assert stamp.content == "MẬT — Ngày 01/01/2026" and stamp.color == "#DC2626"
    with pytest.raises(an.AnnotationError):
        an.apply_operations(doc, [{"type": "khong_ho_tro", "page": 1}])
    doc.close()


def test_cli_annotate_and_list(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    pdf = _make_doc(tmp_path / "vb.pdf")
    ops = tmp_path / "ops.json"
    ops.write_text(json.dumps([{"type": "arrow", "page": 1, "from": [50, 300], "to": [150, 260]}]), encoding="utf-8")
    out = tmp_path / "vb_ct.pdf"
    code = cli_main([
        "annotate", str(pdf), "-o", str(out), "--highlight", "Việt Nam", "--underline", "Dòng thứ hai",
        "--stamp", "Đã duyệt", "--stamp-date", "--ops", str(ops), "--author", "Tester", "--json",
    ])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["added"] == 4

    assert cli_main(["annots", str(out), "--json"]) == 0
    items = json.loads(capsys.readouterr().out)
    assert [i["subtype"] for i in items] == ["Highlight", "Underline", "Line", "Stamp"]
    assert all(i["author"] == "Tester" for i in items)

    flat = tmp_path / "phang.pdf"
    assert cli_main(["annotate", str(out), "-o", str(flat), "--flatten"]) == 0
    capsys.readouterr()
    with fitz.open(str(flat)) as doc:
        assert not list(doc[0].annots())
