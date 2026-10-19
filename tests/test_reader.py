"""Kiểm thử Engine đọc tài liệu PDF (`reader.py` & `layout_analyzer.py`)."""

from __future__ import annotations

from pathlib import Path

from qtpdfpro.core.reader import PDFDocumentReader


def test_pdf_reader_info_toc_and_text(sample_vietnamese_pdf: Path) -> None:
    with PDFDocumentReader(sample_vietnamese_pdf) as reader:
        assert reader.page_count == 2
        info = reader.get_info()
        assert info.page_count == 2
        assert "Quyết định" in info.title
        assert info.author == "Quang Thoại"

        # Kiểm tra mục lục (TOC)
        bookmarks = reader.get_bookmarks()
        assert len(bookmarks) == 3
        assert bookmarks[0].title == "Phần I: Quyết định hành chính"
        assert bookmarks[0].page_index == 0
        assert bookmarks[2].page_index == 1

        # Kiểm tra văn bản tiếng Việt trên trang 1
        p1_text = reader.get_page_text(0)
        assert "CỘNG HOÀ XÃ HỘI CHỦ NGHĨA VIỆT NAM" in p1_text
        assert "Độc lập - Tự do - Hạnh phúc" in p1_text
        assert "Bảo toàn phông chữ tiếng Việt" in p1_text


def test_pdf_reader_render_rotation_and_search(sample_vietnamese_pdf: Path) -> None:
    with PDFDocumentReader(sample_vietnamese_pdf) as reader:
        w0, h0 = reader.get_page_size(0)
        assert abs(w0 - 595.0) < 1.0
        assert abs(h0 - 842.0) < 1.0

        buf1 = reader.render_page(0, scale=1.0)
        assert buf1.width == 595
        assert buf1.height == 842
        assert len(buf1.rgb_bytes) == buf1.height * buf1.stride

        # Xoay trang 90 độ
        reader.rotate_page(0, 90)
        w_rot, h_rot = reader.get_page_size(0)
        assert abs(w_rot - 842.0) < 1.0
        assert abs(h_rot - 595.0) < 1.0

        # Tìm kiếm từ khoá tiếng Việt
        hits = reader.search("Quyết định")
        assert len(hits) >= 1
        assert hits[0].page_index == 0
        assert hits[0].bbox[2] > hits[0].bbox[0]


def test_pdf_layout_analyzer_detects_tables_images_and_text(sample_vietnamese_pdf: Path) -> None:
    with PDFDocumentReader(sample_vietnamese_pdf) as reader:
        ly1 = reader.get_page_layout(0)
        assert ly1.text_block_count >= 3
        assert ly1.table_count >= 1
        assert ly1.image_count >= 1
        assert ly1.vector_count >= 6
        assert ly1.is_scanned is False
