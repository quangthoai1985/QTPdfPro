"""Kiểm thử «Điền & Ký» (`core/fill_sign.py`): bắt dòng chấm, dấu ✓ ✕, ngày tháng, chữ ký, tách nền ảnh, thư viện
chữ ký mã hoá DPAPI, phiên chỉnh sửa và lệnh CLI `fill` / `signature`."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import fitz  # PyMuPDF
import pytest

from qtpdfpro import cli
from qtpdfpro.core import annotations as an
from qtpdfpro.core import fill_sign as fs
from qtpdfpro.core.edit_session import EditSession

FONT = r"C:\Windows\Fonts\times.ttf"
pytestmark = pytest.mark.skipif(not Path(FONT).exists(), reason="Cần phông Times New Roman của Windows")


def _form(rotation: int = 0) -> fitz.Document:
    """Mẫu đơn: dòng chấm «……», «.....», gạch dưới «____», đường kẻ trống, ô vuông, chữ có gạch chân."""
    doc = fitz.open()
    page = doc.new_page()
    for y, line in ((100, "Họ và tên: ……………………………………………………"), (130, "Ngày sinh: ........................................"),
                    (160, "Địa chỉ: ____________________________"), (200, "TIÊU ĐỀ CÓ GẠCH CHÂN")):
        page.insert_text((72, y), line, fontsize=13, fontname="T", fontfile=FONT)
    page.draw_line((72, 203), (250, 203), width=0.6)  # gạch chân chữ in sẵn — không phải chỗ điền
    page.insert_text((72, 249), "Ghi chú:", fontsize=13, fontname="T", fontfile=FONT)
    page.draw_line((140, 250), (400, 250), width=0.6)  # đường kẻ trống để điền
    page.draw_rect(fitz.Rect(300, 280, 311, 291), width=0.8)  # ô vuông
    page.set_rotation(rotation)
    return doc


def _unrot(page: fitz.Page, x: float, y: float) -> fitz.Point:
    """Toạ độ trang đang hiển thị → toạ độ trang chưa xoay (như khung đọc truyền vào)."""
    return fitz.Point(x, y) * page.derotation_matrix


def _style() -> an.AnnotStyle:
    return an.AnnotStyle(color="#111827", text_color="#1E3A8A", font_family="serif", font_size=12)


def test_find_leaders_and_boxes() -> None:
    page = _form()[0]
    leaders = fs.find_leaders(page)
    text = [ld for ld in leaders if ld.source == "text"]
    rules = [ld for ld in leaders if ld.source == "rule"]
    assert [round(ld.baseline) for ld in text] == [100, 130, 160]
    assert all(ld.font_size == 13 and ld.width > 100 for ld in text)
    assert len(rules) == 1 and rules[0].x0 == pytest.approx(140) and rules[0].x1 == pytest.approx(400)
    boxes = fs.find_boxes(page)
    assert len(boxes) == 1 and boxes[0].contains(fitz.Point(305, 285))


def test_fill_text_snaps_onto_dotted_line_and_rule() -> None:
    doc = _form()
    page = doc[0]
    st = _style()
    # Nhấp hơi trên dòng chấm, giữa dòng → chữ bắt đầu tại chỗ nhấp, chân chữ ngay trên dòng chấm
    target = fs.snap_text_target(page, (200, 94), st.font_size)
    assert target.leader is not None and target.x == pytest.approx(200)
    assert 97 <= target.baseline < 100 and target.font_size == 13
    # Nhấp ở đầu dòng → chữ bắt đầu ngay đầu dòng chấm
    head = fs.snap_text_target(page, (140, 127), st.font_size)
    assert head.x == pytest.approx(head.leader.x0 + 1.0)
    # Đường kẻ trống: chân chữ sát trên đường kẻ, cỡ chữ theo kiểu dáng
    rule = fs.snap_text_target(page, (250, 245), st.font_size)
    assert rule.leader is not None and rule.leader.source == "rule" and rule.font_size == 12
    # Tắt bắt dòng / nhấp xa mọi dòng → đặt tại chỗ nhấp
    free = fs.snap_text_target(page, (300, 500), st.font_size)
    assert free.leader is None and free.x == 300

    annot = fs.add_fill_text(page, (200, 94), "Nguyễn Thị Hường", st, "Kiểm thử")
    rect = annot.rect
    assert rect.x0 < 200 < rect.x1 and rect.y0 < 99 < rect.y1
    data = an.qt_data(doc, annot.xref)
    assert data["kind"] == "filltext" and data["text"] == "Nguyễn Thị Hường"
    info = an.list_annotations(doc)[0]
    assert info.label == "Chữ điền" and info.content == "Nguyễn Thị Hường" and info.movable
    fs.add_date(page, (300, 500), st, "nd30", today=date(2026, 10, 23))
    assert an.list_annotations(doc)[1].content == "ngày 23 tháng 10 năm 2026"
    an.flatten_annotations(doc)
    text = doc[0].get_text()
    assert "Nguyễn Thị Hường" in text and "ngày 23 tháng 10 năm 2026" in text  # dấu cách thường, không phải U+00A0


@pytest.mark.parametrize("rotation", [90, 270])
def test_fill_on_rotated_page(rotation: int) -> None:
    doc = _form(rotation)
    page = doc[0]
    # Toạ độ đang hiển thị của dòng «Họ và tên» sau khi xoay
    leaders = fs.find_leaders(page)
    dotted = [ld for ld in leaders if ld.source == "text"]
    assert len(dotted) == 0  # chữ đứng dọc khi trang xoay → không coi là dòng chấm ngang
    fs.add_fill_text(page, _unrot(page, 100, 100), "Đúng chiều", _style())
    an.flatten_annotations(doc)
    blocks = doc[0].get_text("dict")["blocks"]
    line = next(ln for b in blocks for ln in b.get("lines", []) if "Đúng chiều" in "".join(s["text"] for s in ln["spans"]))
    d = fitz.Point(line["dir"]) * doc[0].rotation_matrix - fitz.Point(0, 0) * doc[0].rotation_matrix
    assert d.x > 0.99 and abs(d.y) < 0.01  # chữ điền nằm ngang khi xem


def test_marks_snap_to_box() -> None:
    doc = _form()
    page = doc[0]
    annot = fs.add_mark(page, (303, 283), "check", _style())
    r = annot.rect
    assert abs((r.x0 + r.x1) / 2 - 305.5) < 0.5 and abs((r.y0 + r.y1) / 2 - 285.5) < 0.5
    assert r.width < 11
    free = fs.add_mark(page, (100, 400), "cross", _style().copy(font_size=14))
    assert free.rect.width == pytest.approx(14, abs=0.5)
    line = fs.add_mark(page, (100, 450), "line", _style())
    assert line.rect.width > line.rect.height * 2
    labels = [i.content for i in an.list_annotations(doc)]
    assert labels == ["✓ Dấu tích", "✕ Dấu nhân", "─ Gạch ngang"]
    with pytest.raises(fs.FillSignError):
        fs.add_mark(page, (10, 10), "star", _style())


def test_format_date() -> None:
    d = date(2026, 3, 5)
    assert fs.format_date("dmy", d) == "05/03/2026"
    assert fs.format_date("nd30", d) == "ngày 05 tháng 03 năm 2026"
    assert fs.format_date("nd30_cap", d) == "Ngày 05 tháng 03 năm 2026"
    assert fs.format_date("dmy_dash", d) == "05-03-2026"


def _photo_bytes() -> bytes:
    """Ảnh chụp giả lập: giấy sáng không đều, bóng tay, mặt bàn tối, chữ ký mực xanh, con dấu đỏ, nhiễu."""
    import cv2
    import numpy as np

    rng = np.random.default_rng(1)
    h, w = 600, 800
    yy, xx = np.mgrid[0:h, 0:w]
    paper = (235 - 50 * (xx / w) - 25 * (yy / h)).astype(np.float32)
    img = np.dstack([paper * 0.97, paper * 0.99, paper])
    img[:, :60] = (70, 60, 55)
    img[380:, 480:] *= 0.75
    pts = np.array([[150, 280], [200, 200], [240, 320], [280, 180], [330, 300], [380, 210]], np.int32)
    cv2.polylines(img, [pts], False, (140, 50, 30), 5, cv2.LINE_AA)
    cv2.circle(img, (600, 420), 90, (40, 40, 200), 7, cv2.LINE_AA)
    img = np.clip(img + rng.normal(0, 4, img.shape), 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


def test_clean_signature_photo_keeps_ink_colors() -> None:
    import cv2
    import numpy as np

    png = fs.clean_signature_photo(_photo_bytes(), 50)
    res = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
    assert res.shape[2] == 4
    h, w = res.shape[:2]
    assert w < 700 and h < 400  # đã cắt sát nét (bỏ mặt bàn, bóng tay)
    alpha = res[:, :, 3]
    assert (alpha == 0).mean() > 0.7  # nền trong suốt
    solid = res[alpha > 200]
    blue = solid[(solid[:, 0] > solid[:, 2] + 40)]
    red = solid[(solid[:, 2] > solid[:, 0] + 40)]
    assert len(blue) > 200 and len(red) > 200  # giữ màu mực xanh và con dấu đỏ
    with pytest.raises(fs.FillSignError):
        blank = cv2.imencode(".png", np.full((200, 300, 3), 230, np.uint8))[1].tobytes()
        fs.clean_signature_photo(blank)
    with pytest.raises(fs.FillSignError):
        fs.clean_signature_photo(b"not an image")


def test_prepare_signature_image_keeps_transparent_png() -> None:
    import cv2
    import numpy as np

    rgba = np.zeros((100, 300, 4), np.uint8)
    cv2.line(rgba, (20, 60), (280, 40), (200, 60, 20, 255), 6)
    src = cv2.imencode(".png", rgba)[1].tobytes()
    out = fs.prepare_signature_image(src)
    res = cv2.imdecode(np.frombuffer(out, np.uint8), cv2.IMREAD_UNCHANGED)
    assert res.shape[2] == 4 and res.shape[1] <= 300 and res.shape[0] < 50  # cắt sát, giữ kênh trong suốt
    # Ảnh nền trắng (không có kênh trong suốt) → tự tách nền
    white = cv2.imencode(".png", np.full((100, 300, 3), 255, np.uint8) - (rgba[:, :, 3:4] > 0) * 200)[1].tobytes()
    out2 = fs.prepare_signature_image(white)
    res2 = cv2.imdecode(np.frombuffer(out2, np.uint8), cv2.IMREAD_UNCHANGED)
    assert (res2[:, :, 3] == 0).any()


def test_signatures_placed_and_library_encrypted(tmp_path: Path) -> None:
    drawn = fs.Signature("drawn", strokes=[[(0, 30), (10, 0), (20, 40), (30, 5), (45, 35)], [(5, 45), (60, 42)]],
                         name="Nguyễn Văn A")
    typed = fs.Signature("typed", text="Nguyễn Thị Hường", font="segoe_script")
    initials = fs.Signature("typed", initials=True, text="NTH")
    img_png = fs.prepare_signature_image(_photo_bytes(), clean=True)
    image = fs.Signature("image", png=img_png)
    assert fs.resolve_script_font("segoe_script", "Hường")[1] != "segoe_script" or fs.font_supports(
        "segoe_script", "Hường")  # Segoe Script thiếu chữ Việt → lùi về Times nghiêng
    doc = fitz.open()
    page = doc.new_page()
    a1 = fs.add_signature(page, drawn, center=(200, 400))
    w, h = fs.default_signature_size(drawn)  # rộng 150 pt, nhưng cao tối đa 70 pt → hẹp lại giữ tỷ lệ
    assert a1.rect.height == pytest.approx(fs.SIGNATURE_MAX_HEIGHT, abs=0.5) and a1.rect.width == pytest.approx(w, abs=0.5)
    assert w < fs.SIGNATURE_WIDTH
    a2 = fs.add_signature(page, typed, rect=fitz.Rect(300, 300, 500, 340))
    assert a2.rect.height <= 40.5 and a2.rect.width <= 200.5
    a3 = fs.add_signature(page, initials, center=(500, 600))
    assert a3.rect.width <= fs.INITIALS_WIDTH + 0.5
    fs.add_signature(page, image, center=(300, 600))
    infos = an.list_annotations(doc)
    assert [i.label for i in infos] == ["Chữ ký", "Chữ ký", "Chữ ký nháy", "Chữ ký"]
    pix = page.get_pixmap(dpi=40)
    assert pix.samples != fitz.open().new_page().get_pixmap(dpi=40).samples  # đã vẽ ra trang
    assert fs.render_signature_png(drawn).startswith(b"\x89PNG")
    with pytest.raises(fs.FillSignError):
        fs.add_signature(page, fs.Signature("typed", text="  "), center=(10, 10))

    lib = fs.SignatureLibrary(tmp_path / "sigs")
    for s in (drawn, typed, initials, image):
        lib.save(s)
    assert [s.id for s in lib.list()] == [drawn.id, typed.id, initials.id, image.id]
    assert [s.id for s in lib.list(initials=True)] == [initials.id]
    raw = (tmp_path / "sigs" / f"{drawn.id}.qtsig").read_bytes()
    if sys.platform == "win32":
        assert raw.startswith(b"QTSIG1D") and "Nguyễn".encode() not in raw  # mã hoá DPAPI, không lộ tên
    back = lib.get(image.id)
    assert back is not None and back.png == img_png and lib.get(drawn.id).strokes == drawn.strokes
    (tmp_path / "sigs" / "hong.qtsig").write_bytes(b"rac")
    assert len(lib.list()) == 4  # tệp hỏng bị bỏ qua
    assert lib.delete(typed.id) and not lib.delete(typed.id) and len(lib.list()) == 3
    with pytest.raises(fs.FillSignError):
        lib.save(fs.Signature("drawn"))


def test_edit_session_fill_undo_redo_and_edit(tmp_path: Path) -> None:
    doc = _form()
    ses = EditSession(doc, author="Kiểm thử")
    st = _style()
    xref = ses.add_fill_text(0, (200, 94), "Trần Văn Bình", st)
    ses.add_fill_mark(0, (303, 283), "check", st)
    ses.add_fill_text(0, (300, 500), fs.format_date("dmy"), st, kind="date")
    ses.add_signature(0, fs.Signature("typed", text="Bình"), center=(400, 600))
    assert [i.label for i in ses.list_annotations()] == ["Chữ điền", "Dấu điền", "Ngày tháng", "Chữ ký"]
    assert ses.undo_label == "Ký"
    ses.undo()
    assert len(ses.list_annotations()) == 3
    ses.redo()
    page = doc[0]  # giữ trang sống khi đọc chú thích (Annot của trang đã thu hồi gây lỗi bộ nhớ)
    before = page.load_annot(xref).rect
    assert ses.set_content(0, xref, "Trần Văn Bình Minh")
    after = page.load_annot(xref).rect
    assert after.x0 == pytest.approx(before.x0, abs=0.1) and after.x1 > before.x1
    assert an.qt_data(doc, xref)["text"] == "Trần Văn Bình Minh"
    ses.undo()
    assert an.qt_data(doc, xref)["text"] == "Trần Văn Bình"
    out = tmp_path / "da_dien.pdf"
    ses.prepare_save()
    doc.save(str(out))
    assert len(an.list_annotations(fitz.open(str(out)))) == 4


def test_cli_fill_and_signature(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    src = tmp_path / "don.pdf"
    _form().save(str(src))
    assert cli.main(["fill", str(src), "--leaders", "--json"]) == 0
    leaders = json.loads(capsys.readouterr().out)
    assert len(leaders[0]["leaders"]) == 4 and len(leaders[0]["boxes"]) == 1

    out = tmp_path / "don_da_dien.pdf"
    rc = cli.main(["fill", str(src), "-o", str(out), "--text", "1:200,94:Lê Thị Hoa", "--check", "1:303,283",
                   "--date", "1:300,500", "--date-format", "nd30", "--sign", "1:400,600",
                   "--signature-text", "Lê Thị Hoa", "--json"])
    assert rc == 0 and json.loads(capsys.readouterr().out)["added"] == 4
    labels = [i.label for i in an.list_annotations(fitz.open(str(out)))]
    assert labels == ["Chữ điền", "Ngày tháng", "Dấu điền", "Chữ ký"]

    photo = tmp_path / "anh_chup.jpg"
    photo.write_bytes(_photo_bytes())
    assert cli.main(["signature", "add", "--image", str(photo), "--name", "Hoa", "--json"]) == 0
    sig_id = json.loads(capsys.readouterr().out)["id"]
    assert cli.main(["signature", "list", "--json"]) == 0
    assert [s["id"] for s in json.loads(capsys.readouterr().out)] == [sig_id]
    flat = tmp_path / "phang.pdf"
    assert cli.main(["fill", str(src), "-o", str(flat), "--initials", "1:500,700", "--signature-id", sig_id,
                     "--flatten"]) == 0
    assert an.list_annotations(fitz.open(str(flat))) == []  # đã làm phẳng
    assert cli.main(["signature", "clean", str(photo)]) == 0
    assert (tmp_path / "anh_chup_tach_nen.png").exists()
    capsys.readouterr()
    assert cli.main(["fill", str(src), "--sign", "1:1,1"]) == 1  # thiếu nguồn chữ ký
    assert "Lỗi" in capsys.readouterr().err
    assert cli.main(["signature", "delete", sig_id]) == 0
