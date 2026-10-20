"""Danh mục "Tất cả công cụ" dùng chung cho Trang chủ, bảng công cụ và bảng lệnh (Ctrl+K).

Bố cục học theo PdfCraft: công cụ chia theo nhóm (Đọc, Chuyển đổi, Chỉnh sửa, Ký số & Bảo mật).
Công cụ chưa phát triển vẫn hiển thị với nhãn `COMING_SOON_LABEL` kèm giai đoạn dự kiến
(xem lộ trình tại `docs/DE_XUAT_TINH_NANG.md`) để người dùng thấy toàn cảnh sản phẩm.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import List, Optional

COMING_SOON_LABEL = "Coming Soon"


@dataclass(frozen=True)
class ToolSpec:
    """Mô tả một công cụ trong danh mục."""

    key: str
    name: str
    icon: str
    summary: str
    category: str  # "read" | "convert" | "edit" | "sign"
    ready: bool = True
    needs_document: bool = False
    milestone: str = ""
    keywords: str = ""

    @property
    def status_text(self) -> str:
        return "Dùng ngay" if self.ready else COMING_SOON_LABEL


CATEGORIES: list[tuple[str, str]] = [
    ("all", "Tất cả công cụ"),
    ("read", "Đọc"),
    ("convert", "Chuyển đổi"),
    ("edit", "Chỉnh sửa"),
    ("sign", "Ký số && Bảo mật"),
]

CATEGORY_TITLES = {
    "read": "ĐỌC & SOI BỐ CỤC",
    "convert": "CHUYỂN ĐỔI",
    "edit": "CHỈNH SỬA & TỔ CHỨC TRANG",
    "sign": "KÝ SỐ & BẢO MẬT",
}

TOOLS: list[ToolSpec] = [
    # ── Chuyển đổi ──
    ToolSpec("pdf_to_word_nd30", "PDF sang Word chuẩn NĐ30", "🏛️",
             "Văn bản hành chính · Bảng không viền · Lề chuẩn", "convert",
             keywords="nghi dinh 30 hanh chinh docx word quoc hieu tieu ngu"),
    ToolSpec("nd30_check", "Kiểm tra thể thức NĐ30", "✅",
             "Đo lề, cỡ chữ, giãn dòng · Đối chiếu từng thành phần", "convert",
             keywords="nghi dinh 30 the thuc kiem tra le can le"),
    ToolSpec("verify_docx", "Kiểm chứng DOCX với PDF", "🔬",
             "Dựng bằng MS Word · So vị trí từng dòng", "convert",
             keywords="so sanh lech kiem chung word"),
    ToolSpec("pdf_to_word_exact", "PDF sang Word giữ vị trí 1:1", "📐",
             "Biểu mẫu · Hoá đơn · Bằng cấp", "convert", keywords="exact khung toa do"),
    ToolSpec("pdf_to_word_flow", "PDF sang Word dạng dòng chảy", "📝",
             "Tài liệu thường · pdf2docx + OpenXML", "convert", keywords="hybrid pdf2docx"),
    ToolSpec("batch_convert", "Chuyển đổi hàng loạt", "🗂️",
             "Nhiều PDF → DOCX · Bảng điểm từng tệp (Ctrl+Shift+B)", "convert",
             keywords="batch nhieu tep hang loat thu muc keo tha"),
    ToolSpec("ocr", "Scan & OCR tiếng Việt", "🔤",
             "PDF ảnh quét → Word chỉnh sửa được", "convert", ready=False, milestone="v1.1",
             keywords="scan quet nhan dang chu tesseract vietocr"),
    ToolSpec("pdf_to_excel", "PDF sang Excel", "📊", "Bảng biểu tài chính → .xlsx", "convert",
             ready=False, milestone="v1.2", keywords="xlsx bang tinh"),
    ToolSpec("pdf_to_image", "PDF sang ảnh", "🖼️", "PNG · JPG · TIFF chất lượng cao", "convert",
             ready=False, milestone="v1.2", keywords="png jpg anh"),
    ToolSpec("pdf_to_pptx", "PDF sang PowerPoint", "📽️", "Mỗi trang thành một slide", "convert",
             ready=False, milestone="v1.2", keywords="pptx trinh chieu"),
    ToolSpec("create_pdf", "Tạo PDF từ Word / ảnh", "📄", "DOCX · Ảnh → PDF/A", "convert",
             ready=False, milestone="v1.2", keywords="tao pdf in"),
    # ── Đọc ──
    ToolSpec("open", "Mở tệp PDF", "📂", "Ctrl+O · Kéo thả nhiều tệp", "read",
             keywords="mo tep file"),
    ToolSpec("layout_inspect", "Soi bố cục & chữ ký số", "🔍",
             "Văn bản · Bảng · Con dấu · Vector (F8)", "read", needs_document=True,
             keywords="layout inspector overlay con dau chu ky"),
    ToolSpec("search", "Tìm kiếm toàn văn", "🔎", "Tô sáng mọi vị trí khớp (Ctrl+F)", "read",
             needs_document=True, keywords="tim kiem search"),
    ToolSpec("extract_text", "Trích xuất văn bản", "📋", "Xem & sao chép chữ trang hiện tại", "read",
             needs_document=True, keywords="copy text sao chep"),
    ToolSpec("bookmarks", "Mục lục tài liệu", "📑", "Bookmarks · Đi tới chương mục", "read",
             needs_document=True, keywords="toc muc luc"),
    ToolSpec("read_mode", "Chế độ đọc tập trung", "📖", "Ẩn bảng phụ · Toàn màn hình (F11)", "read",
             needs_document=True, keywords="doc tap trung fullscreen"),
    ToolSpec("rotate_view", "Xoay trang khi xem", "↻", "Xoay 90° trang hiện tại", "read",
             needs_document=True, keywords="xoay rotate"),
    ToolSpec("doc_info", "Thuộc tính tài liệu", "ℹ️", "Metadata · Phông chữ · Bảo mật", "read",
             needs_document=True, keywords="metadata thong tin"),
    ToolSpec("print", "In tài liệu", "🖨️", "Xem trước · Khổ giấy · 2 mặt · Đen trắng (Ctrl+P)", "read",
             needs_document=True, keywords="in print may in printer kho giay a4 a5 a3 hai mat den trang ban sao"),
    ToolSpec("two_up", "Xem 2 trang song song", "📰", "Two-up · Trang bìa riêng", "read",
             ready=False, milestone="v0.5", keywords="hai trang"),
    # ── Chỉnh sửa ──
    ToolSpec("edit_pdf", "Chỉnh sửa PDF", "✏️", "Tô màu · Đánh dấu · Vẽ · Chèn chữ (Ctrl+E)", "edit",
             needs_document=True, keywords="sua chinh sua annotate to mau danh dau ve chen chu"),
    ToolSpec("highlight_text", "Tô sáng & đánh dấu chữ", "🖍", "Tô màu · Gạch chân · Gạch ngang · Gạch sóng", "edit",
             needs_document=True, keywords="highlight underline strikeout to sang gach chan gach ngang mau"),
    ToolSpec("draw_shapes", "Vẽ & hình khối", "✏️", "Bút · Bút dạ quang · Khung · Elip · Mũi tên", "edit",
             needs_document=True, keywords="ve but marker khung mui ten hinh"),
    ToolSpec("organize", "Sắp xếp & cắt ghép trang", "🧩", "Kéo thả · Xoay · Xoá · Trang trắng (Ctrl+Shift+O)",
             "edit", keywords="organize xoay xoa trang sap xep keo tha cat ghep"),
    ToolSpec("combine", "Ghép tệp PDF", "🧷", "Nhiều tệp thành một · Giữ mục lục", "edit",
             keywords="merge ghep noi"),
    ToolSpec("split", "Tách tệp PDF", "✂️", "Mỗi N trang · Theo khoảng · Theo điểm cắt", "edit",
             keywords="split tach chia cat"),
    ToolSpec("extract_pages", "Trích trang", "📤", "Lưu các trang chọn thành tệp mới", "edit",
             keywords="trich trang extract"),
    ToolSpec("comments", "Thêm chú thích", "💬", "Ghi chú dán · Hộp chữ · Danh sách chú thích", "edit",
             needs_document=True, keywords="annotation ghi chu comment note hop chu"),
    ToolSpec("stamp", "Đóng dấu", "🔖", "ĐÃ DUYỆT · BẢN SAO · MẬT · KHẨN", "edit",
             needs_document=True, keywords="stamp dau dong dau"),
    ToolSpec("forms", "Điền biểu mẫu", "🧾", "Trường nhập liệu · Xoá biểu mẫu", "edit",
             ready=False, milestone="v1.2", keywords="form bieu mau"),
    ToolSpec("compress", "Nén PDF", "🗜️", "Giảm dung lượng giữ chất lượng", "edit", ready=False,
             milestone="v1.2", keywords="compress nen"),
    # ── Ký số & Bảo mật ──
    ToolSpec("sig_inspect", "Soi chữ ký số & con dấu", "🛡️", "Phát hiện widget ký số VGCA", "sign",
             needs_document=True, keywords="chu ky so vgca con dau"),
    ToolSpec("sign_pdf", "Ký số PDF", "✍️", "USB Token · VGCA · Viettel-CA · VNPT-CA", "sign",
             ready=False, milestone="v2.0", keywords="ky so token"),
    ToolSpec("verify_signature", "Xác thực chữ ký số", "🔏", "Kiểm tra chứng thư · Toàn vẹn", "sign",
             ready=False, milestone="v2.0", keywords="xac thuc chung thu"),
    ToolSpec("protect", "Đặt mật khẩu PDF", "🔐", "Mật khẩu mở · Quyền in / sửa", "sign",
             ready=False, milestone="v2.0", keywords="password mat khau"),
    ToolSpec("redact", "Xoá thông tin nhạy cảm", "⬛", "Redaction · Làm sạch metadata", "sign",
             ready=False, milestone="v2.0", keywords="redact an"),
    ToolSpec("compare", "So sánh 2 tệp PDF", "⚖️", "Tìm khác biệt nội dung", "sign", ready=False,
             milestone="v2.0", keywords="compare so sanh"),
]

RECOMMENDED: list[str] = [
    "pdf_to_word_nd30",
    "nd30_check",
    "edit_pdf",
    "organize",
    "layout_inspect",
    "ocr",
]

_BY_KEY = {t.key: t for t in TOOLS}


def get_tool(key: str) -> Optional[ToolSpec]:
    return _BY_KEY.get(key)


def _fold(text: str) -> str:
    """Bỏ dấu tiếng Việt + chữ thường để tìm kiếm không phân biệt dấu."""
    nfkd = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn").lower()


def matches(tool: ToolSpec, query: str) -> bool:
    q = _fold(query.strip())
    if not q:
        return True
    hay = _fold(" ".join((tool.name, tool.summary, tool.keywords, CATEGORY_TITLES.get(tool.category, ""))))
    return all(part in hay for part in q.split())


def tools_for(category: str = "all", query: str = "") -> List[ToolSpec]:
    """Danh sách công cụ theo nhóm & từ khoá (công cụ dùng được xếp trước)."""
    items = [t for t in TOOLS if (category in ("all", "") or t.category == category) and matches(t, query)]
    order = [c for c, _ in CATEGORIES]
    return sorted(items, key=lambda t: (order.index(t.category), not t.ready))
