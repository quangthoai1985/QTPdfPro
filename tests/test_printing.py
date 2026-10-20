"""Kiểm thử lõi «In tài liệu» (`core/printing.py`) và lệnh `cli print` — không cần máy in, không cần Qt."""

from __future__ import annotations

import json
from pathlib import Path

import fitz  # PyMuPDF
import pytest

from qtpdfpro import cli
from qtpdfpro.core import printing as P
from qtpdfpro.core.settings import AppSettings

A4 = P.PAPER_SIZES["A4"]


def _mixed_pdf(path: Path) -> Path:
    """4 trang: A4 dọc (đỏ góc trên-trái), A4 ngang, A5 dọc, A3 dọc; trang 1 có chú thích tô sáng xanh."""
    doc = fitz.open()
    for w, h in [(595, 842), (842, 595), (420, 595), (842, 1191)]:
        page = doc.new_page(width=w, height=h)
        page.draw_rect(fitz.Rect(0, 0, 60, 60), color=None, fill=(1, 0, 0))
        page.insert_text((80, 60), f"Trang {doc.page_count}", fontsize=14)
    first = doc[0]  # giữ Page sống khi dùng Annot
    annot = first.add_highlight_annot(fitz.Rect(80, 200, 300, 260))
    annot.set_colors(stroke=(0, 0, 1))
    annot.update()
    doc.save(str(path))
    doc.close()
    return path


# ─── Khoảng trang ─────────────────────────────────────────────────────────


def test_parse_print_range_open_ranges_and_order() -> None:
    assert P.parse_print_range("1-3,5,8-", 10) == [0, 1, 2, 4, 7, 8, 9]
    assert P.parse_print_range("-3", 10) == [0, 1, 2]
    assert P.parse_print_range(" 9 - ", 10) == [8, 9]
    assert P.parse_print_range("5, 1-2, 2", 10) == [4, 0, 1]  # giữ thứ tự nhập, bỏ trùng
    assert P.parse_print_range("end", 10) == [9]
    assert P.parse_print_range("le", 5) == [0, 2, 4]
    assert P.parse_print_range("", 3) == [0, 1, 2]
    assert P.parse_print_range("tất cả", 3) == [0, 1, 2]
    assert P.parse_print_range("2–3", 5) == [1, 2]  # gạch ngang dài khi gõ từ Word
    for bad in ("abc", "12", "0", "3-x", ",,"):
        with pytest.raises(P.PrintError):
            P.parse_print_range(bad, 10)


def test_resolve_pages_scopes_and_subset() -> None:
    assert P.resolve_print_pages("all", "", 4) == [0, 1, 2, 3]
    assert P.resolve_print_pages("current", "", 4, current=2) == [2]
    assert P.resolve_print_pages("current", "", 4, current=99) == [3]
    assert P.resolve_print_pages("custom", "2-", 4) == [1, 2, 3]
    with pytest.raises(P.PrintError):
        P.resolve_print_pages("custom", "  ", 4)
    assert P.apply_subset([0, 1, 2, 3, 4], "odd") == [0, 2, 4]  # trang 1, 3, 5
    assert P.apply_subset([0, 1, 2, 3, 4], "even", reverse=True) == [3, 1]


# ─── Kế hoạch in ──────────────────────────────────────────────────────────


def test_plan_auto_orientation_rotates_landscape_page() -> None:
    sizes = [(595, 842), (842, 595), (595, 842)]
    plan = P.plan_print(sizes, [0, 1, 2], P.PrintOptions())
    assert plan.landscape is False and plan.paper_size == A4
    portrait, wide, _ = plan.sheets
    assert portrait.rotate == 0 and portrait.scale == pytest.approx(1.0, abs=0.002)
    # Trang ngang trên giấy dọc: xoay ngược chiều kim đồng hồ, lấp đầy chiều ngang tờ
    assert wide.rotate == 270
    x0, y0, x1, y1 = wide.target
    assert x1 - x0 == pytest.approx(A4[0], abs=1) and y1 - y0 == pytest.approx(A4[0] * 842 / 595, abs=1)

    # Đa số trang ngang → giấy ngang; trang dọc xoay thuận chiều kim đồng hồ
    plan = P.plan_print([(842, 595), (842, 595), (595, 842)], [0, 1, 2], P.PrintOptions())
    assert plan.landscape is True and plan.paper_size == (A4[1], A4[0])
    assert [s.rotate for s in plan.sheets] == [0, 0, 90]


def test_plan_forced_orientation_without_auto_rotate_shrinks_page() -> None:
    sizes = [(842, 595)]
    rotated = P.plan_print(sizes, [0], P.PrintOptions(orientation="portrait"))
    assert rotated.sheets[0].rotate == 270
    flat = P.plan_print(sizes, [0], P.PrintOptions(orientation="portrait", auto_rotate=False))
    sheet = flat.sheets[0]
    assert sheet.rotate == 0 and sheet.scale == pytest.approx(595.28 / 842, abs=0.002)
    assert sheet.target[1] > 100  # căn giữa theo chiều dọc
    land = P.plan_print([(595, 842)], [0], P.PrintOptions(orientation="landscape"))
    assert land.landscape is True and land.sheets[0].rotate == 90


def test_plan_scale_modes_and_margins() -> None:
    a5, a3 = (420, 595), (842, 1191)
    fit = P.plan_print([a5], [0], P.PrintOptions(scale="fit")).sheets[0]
    assert fit.scale == pytest.approx(841.89 / 595, abs=0.01)
    shrink_small = P.plan_print([a5], [0], P.PrintOptions(scale="shrink")).sheets[0]
    assert shrink_small.scale == 1.0
    shrink_big = P.plan_print([a3], [0], P.PrintOptions(scale="shrink")).sheets[0]
    assert shrink_big.scale == pytest.approx(841.89 / 1191, abs=0.01)
    actual = P.plan_print([a3], [0], P.PrintOptions(scale="actual")).sheets[0]
    assert actual.scale == 1.0 and actual.clipped is True
    x0, y0, x1, y1 = actual.target
    assert (x0 + x1) / 2 == pytest.approx(A4[0] / 2) and (y0 + y1) / 2 == pytest.approx(A4[1] / 2)

    # Lề không in được của máy in: «Vừa khổ giấy» nằm trọn trong vùng in được
    m = 17.0
    sheet = P.plan_print([(595.28, 841.89)], [0], P.PrintOptions(), margins=(m, m, m, m)).sheets[0]
    x0, y0, x1, y1 = sheet.target
    assert x0 >= m - 0.01 and y0 >= m - 0.01 and x1 <= A4[0] - m + 0.01 and y1 <= A4[1] - m + 0.01
    assert sheet.scale < 1.0
    with pytest.raises(P.PrintError):
        P.plan_print([(100, 100)], [], P.PrintOptions())
    with pytest.raises(P.PrintError):
        P.plan_print([(100, 100)], [3], P.PrintOptions())


def test_job_sheets_copies_collate_and_duplex_padding() -> None:
    sizes = [(595, 842)] * 3

    def pages(opts: P.PrintOptions, manual: bool = True):
        plan = P.plan_print(sizes, [0, 1, 2], opts)
        return [s.page_index for s in plan.job_sheets(manual_copies=manual)]

    assert pages(P.PrintOptions(copies=2)) == [0, 1, 2, 0, 1, 2]
    assert pages(P.PrintOptions(copies=2, collate=False)) == [0, 0, 1, 1, 2, 2]
    assert pages(P.PrintOptions(copies=2), manual=False) == [0, 1, 2]
    # In 2 mặt: mỗi bộ bắt đầu ở mặt trước tờ mới → chèn tờ trắng sau bộ có số trang lẻ
    assert pages(P.PrintOptions(copies=2, duplex="long")) == [0, 1, 2, None, 0, 1, 2]
    assert pages(P.PrintOptions(copies=2, duplex="long", collate=False)) == [0, 1, 0, 1, 2, None, 2]


def test_options_normalize_and_settings_roundtrip() -> None:
    opts = P.PrintOptions(copies=0, paper="B9", orientation="xien", scale="?", duplex="3", subset="x", max_dpi=5000)
    norm = opts.normalized()
    assert (norm.copies, norm.paper, norm.orientation, norm.scale, norm.duplex, norm.subset, norm.max_dpi) == (
        1, "A4", "auto", "fit", "none", "all", 600)
    saved = P.PrintOptions(printer="Canon", copies=5, paper="A5", grayscale=True, duplex="long", max_dpi=300)
    data = saved.to_settings()
    assert "copies" not in data and "subset" not in data  # số bản / lọc trang không nhớ
    s = AppSettings.load()
    s.print_settings = data
    s.save()
    back = P.PrintOptions.from_settings(AppSettings.load().print_settings)
    assert (back.printer, back.paper, back.grayscale, back.duplex, back.max_dpi, back.copies) == (
        "Canon", "A5", True, "long", 300, 1)
    assert P.PrintOptions.from_settings({"paper": 42, "khoa_la": 1}).paper == "A4"
    assert P.PrintOptions.from_settings(None) == P.PrintOptions()


def test_clamp_dpi_between_300_and_600() -> None:
    assert P.clamp_print_dpi(1200) == 600
    assert P.clamp_print_dpi(96) == 300
    assert P.clamp_print_dpi(0) == 300
    assert P.clamp_print_dpi(600, max_dpi=300) == 300
    assert P.clamp_print_dpi(450) == 450
    # Trang A0 ở 600 dpi vượt trần điểm ảnh → hạ DPI cho riêng trang đó
    a0 = P.plan_print([(2384, 3370)], [0], P.PrintOptions(paper="A3", scale="actual")).sheets[0]
    assert P.effective_dpi(a0, 600) < 300


# ─── Kết xuất ảnh trang ───────────────────────────────────────────────────


def test_render_sheet_grayscale_rotation_and_annotations(tmp_path: Path) -> None:
    pdf = _mixed_pdf(tmp_path / "tron.pdf")
    with fitz.open(str(pdf)) as doc:
        plan = P.plan_document(doc, [0, 1], P.PrintOptions())
        first, wide = plan.sheets
        color = P.render_sheet_pixmap(doc, first, 100)
        gray = P.render_sheet_pixmap(doc, first, 100, grayscale=True)
        assert color.n == 3 and gray.n == 1 and not color.alpha
        assert color.width == pytest.approx((first.target[2] - first.target[0]) * 100 / 72, abs=2)
        # Chú thích tô sáng màu xanh chỉ có khi in kèm chú thích
        x, y = int(150 * first.scale * 100 / 72), int(230 * first.scale * 100 / 72)
        r, g, b = color.pixel(x, y)
        assert b > 150 and r < 150
        assert P.render_sheet_pixmap(doc, first, 100, annotations=False).pixel(x, y) == (255, 255, 255)
        # Trang ngang xoay 270° (ngược chiều kim đồng hồ): ô đỏ ở góc trên-trái chuyển xuống góc dưới-trái
        pix = P.render_sheet_pixmap(doc, wide, 50)
        assert pix.height > pix.width
        assert pix.pixel(3, pix.height - 4)[0] > 200 and pix.pixel(3, 3) == (255, 255, 255)
        img = P.render_sheet(doc, first, 72, grayscale=True)
        assert img.grayscale and len(img.samples) == img.stride * img.height


def test_print_to_pdf_pages_orientation_and_copies(tmp_path: Path) -> None:
    pdf = _mixed_pdf(tmp_path / "tron.pdf")
    out = tmp_path / "ban_in.pdf"
    with fitz.open(str(pdf)) as doc:
        assert P.printing_allowed(doc)
        plan = P.plan_document(doc, P.parse_print_range("1-2,4", doc.page_count), P.PrintOptions(copies=2))
        steps = []
        res = P.print_to_pdf(doc, plan, out, dpi=72, progress=lambda d, t: steps.append((d, t)))
    assert res.sheets_printed == 6 and steps[-1] == (6, 6) and not res.cancelled
    with fitz.open(str(out)) as printed:
        assert printed.page_count == 6
        for page in printed:
            assert (page.rect.width, page.rect.height) == pytest.approx(A4, abs=0.5)
            assert len(page.get_images()) == 1

    with fitz.open(str(pdf)) as doc:
        plan = P.plan_document(doc, [0, 1, 2], P.PrintOptions())
        res = P.print_to_pdf(doc, plan, tmp_path / "huy.pdf", dpi=72, should_cancel=lambda: True)
    assert res.cancelled and res.sheets_printed == 0 and not (tmp_path / "huy.pdf").exists()


def test_printing_permission_flag(tmp_path: Path) -> None:
    src = tmp_path / "khoa_in.pdf"
    doc = fitz.open()
    doc.new_page()
    perm = fitz.PDF_PERM_ACCESSIBILITY | fitz.PDF_PERM_COPY  # không có quyền in
    doc.save(str(src), encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="chu", user_pw="", permissions=perm)
    doc.close()
    with fitz.open(str(src)) as locked:
        assert P.printing_allowed(locked) is False
    assert cli.main(["print", str(src), "--to-pdf", str(tmp_path / "x.pdf")]) == 1


# ─── Dòng lệnh ────────────────────────────────────────────────────────────


def test_cli_print_to_pdf_and_plan(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pdf = _mixed_pdf(tmp_path / "tron.pdf")
    out = tmp_path / "cli_ban_in.pdf"
    rc = cli.main(["print", str(pdf), "--pages", "2-", "--to-pdf", str(out), "--grayscale",
                   "--paper", "A5", "--dpi", "72", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["pages"] == [2, 3, 4]
    assert payload["result"]["sheets_printed"] == 3 and payload["plan"]["paper"] == "A5"
    with fitz.open(str(out)) as printed:
        assert printed.page_count == 3
        assert (printed[0].rect.width, printed[0].rect.height) == pytest.approx(P.PAPER_SIZES["A5"], abs=0.5)

    assert cli.main(["print", str(pdf), "--plan", "--subset", "even", "--json"]) == 0
    plan = json.loads(capsys.readouterr().out)["plan"]
    assert [s["page"] for s in plan["sheets"]] == [2, 4] and plan["sheets"][0]["rotate"] == 270

    assert cli.main(["print", str(pdf), "--pages", "9", "--plan"]) == 1
    assert "nằm ngoài" in capsys.readouterr().err
    with pytest.raises(SystemExit):  # phải chọn đích in — không tự in ra máy in mặc định
        cli.main(["print", str(pdf)])
