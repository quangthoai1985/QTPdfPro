"""Kiểm thử engine tổ chức trang (`core/page_ops.py`) và các lệnh CLI merge / split / organize / extract."""

from __future__ import annotations

import json
from pathlib import Path

import fitz  # PyMuPDF
import pytest

from qtpdfpro.cli import main as cli_main
from qtpdfpro.core import page_ops as po


def _make_pdf(path: Path, name: str, pages: int, size=(595, 842)) -> Path:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=size[0], height=size[1])
        page.insert_text((72, 72), f"{name} trang {i + 1}", fontsize=14)
    toc = [[1, f"{name} chương 1", 1]]
    if pages >= 2:
        toc.append([2, f"{name} mục 1.1", 2])
    toc.append([1, f"{name} chương cuối", pages])
    doc.set_toc(toc)
    doc.save(str(path))
    doc.close()
    return path


def _texts(path: Path) -> list[str]:
    with fitz.open(str(path)) as doc:
        return [p.get_text().strip() for p in doc]


@pytest.fixture()
def two_pdfs(tmp_path: Path) -> tuple[Path, Path]:
    return _make_pdf(tmp_path / "A.pdf", "A", 5), _make_pdf(tmp_path / "B.pdf", "B", 3, size=(842, 595))


def test_parse_order_spec_tokens() -> None:
    refs = po.parse_order_spec("3, 1-2r90, blank, end-4, le, chanr180", 5)
    assert [(r.page_index, r.rotation) for r in refs] == [
        (2, 0), (0, 90), (1, 90), (None, 0), (4, 0), (3, 0), (0, 0), (2, 0), (4, 0), (1, 180), (3, 180),
    ]
    assert po.parse_page_selection("4,2,2,le", 5) == [3, 1, 0, 2, 4]
    assert po.parse_page_selection("", 3) == [0, 1, 2]
    assert po.parse_split_ranges("1-2,3,4-5", 5) == [[0, 1], [2], [3, 4]]
    for bad in ("1,9", "abc", "2r45", ""):
        with pytest.raises(po.PageOpsError):
            po.parse_order_spec(bad, 5)


def test_split_input_spec_handles_windows_drive() -> None:
    assert po.split_input_spec(r"C:\tai lieu\a.pdf:1-3,5") == (r"C:\tai lieu\a.pdf", "1-3,5")
    assert po.split_input_spec(r"C:\tai lieu\a.pdf") == (r"C:\tai lieu\a.pdf", None)


def test_split_refs_every_and_after() -> None:
    refs = po.refs_for_document("x", 7)
    assert [len(p) for p in po.split_refs(refs, every=3)] == [3, 3, 1]
    assert [len(p) for p in po.split_refs(refs, after=[2, 5, 99])] == [2, 3, 2]
    assert [len(p) for p in po.split_refs(refs, after=[])] == [7]


def test_organize_reorders_rotates_and_remaps_bookmarks(two_pdfs, tmp_path: Path) -> None:
    a, _ = two_pdfs
    res = po.organize_pdf(a, "5-1,blank,2r90", tmp_path / "o.pdf")
    out = Path(res.output_paths[0])
    assert res.page_counts == [7]
    texts = _texts(out)
    assert texts[:5] == [f"A trang {i}" for i in (5, 4, 3, 2, 1)]
    assert texts[5] == "" and texts[6] == "A trang 2"
    with fitz.open(str(out)) as doc:
        assert doc[6].rotation == 90
        assert doc[5].rect.width == pytest.approx(595, abs=1)  # trang trắng theo cỡ trang trước
        toc = doc.get_toc()
    # Mục lục trỏ tới lần xuất hiện đầu tiên của trang gốc
    assert [1, "A chương 1", 5] in toc and [1, "A chương cuối", 1] in toc


def test_merge_with_ranges_and_file_bookmarks(two_pdfs, tmp_path: Path) -> None:
    a, b = two_pdfs
    res = po.merge_pdfs([f"{a}:1-2", b], tmp_path / "gop.pdf")
    out = Path(res.output_paths[0])
    assert _texts(out) == ["A trang 1", "A trang 2", "B trang 1", "B trang 2", "B trang 3"]
    with fitz.open(str(out)) as doc:
        toc = doc.get_toc()
        assert doc[2].rect.width == pytest.approx(842, abs=1)  # giữ khổ ngang của tệp B
    assert toc[0] == [1, "A", 1]
    assert [1, "B", 3] in toc and [2, "B chương 1", 3] in toc
    assert [2, "A chương cuối", 5] not in toc  # trang 5 của A không được ghép


def test_split_extract_and_refuse_overwrite_source(two_pdfs, tmp_path: Path) -> None:
    a, _ = two_pdfs
    res = po.split_pdf(a, tmp_path / "phan", every=2)
    assert [Path(p).name for p in res.output_paths] == ["A_phan_01.pdf", "A_phan_02.pdf", "A_phan_03.pdf"]
    assert res.page_counts == [2, 2, 1]
    assert po.split_pdf(a, tmp_path / "k", ranges="1-2,4-5").page_counts == [2, 2]
    assert po.split_pdf(a, tmp_path / "s", after=[1, 3]).page_counts == [1, 2, 2]
    ext = po.extract_pages(a, "4,2", tmp_path / "trich.pdf")
    assert _texts(Path(ext.output_paths[0])) == ["A trang 2", "A trang 4"]
    with pytest.raises(po.PageOpsError):
        po.organize_pdf(a, "1", a)
    with pytest.raises(po.PageOpsError):
        po.split_pdf(a, tmp_path / "x", every=2, after=[1])


def test_assemble_keeps_annotations(tmp_path: Path) -> None:
    src = _make_pdf(tmp_path / "C.pdf", "C", 2)
    with fitz.open(str(src)) as doc:
        page = doc[1]
        page.add_highlight_annot(page.search_for("C trang 2"))
        doc.saveIncr()
    with po.SourceSet() as sources:
        key = sources.open(src)
        out = po.assemble_pdf([po.PageRef(key, 1), po.PageRef(key, 0)], sources.docs)
        assert [a.type[1] for a in out[0].annots()] == ["Highlight"]
        out.close()


def test_cli_page_commands(two_pdfs, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    a, b = two_pdfs
    out = tmp_path / "gop.pdf"
    assert cli_main(["merge", str(a), f"{b}:3", "-o", str(out), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total_pages"] == 6

    assert cli_main(["organize", str(a), "--order", "end,1r180", "-o", str(tmp_path / "o.pdf")]) == 0
    assert "Đã sắp xếp" in capsys.readouterr().out
    assert _texts(tmp_path / "o.pdf") == ["A trang 5", "A trang 1"]

    assert cli_main(["split", str(a), "--after", "2", "-o", str(tmp_path / "t"), "--json"]) == 0
    assert [o["pages"] for o in json.loads(capsys.readouterr().out)["outputs"]] == [2, 3]

    assert cli_main(["extract", str(a), "--pages", "2-3"]) == 0
    assert _texts(a.with_name("A_trich.pdf")) == ["A trang 2", "A trang 3"]

    assert cli_main(["extract", str(a), "--pages", "9"]) == 1
    assert "ngoài tài liệu" in capsys.readouterr().err
