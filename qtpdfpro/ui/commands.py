"""Nguồn lệnh duy nhất của giao diện: nút thanh chức năng, menu ☰, phím tắt và bảng lệnh Ctrl+K.

Mỗi `Command` mô tả một lệnh (nhãn, biểu tượng Lucide, thẻ, phím tắt…); hàm xử lý nằm ở `MainWindow`
(`run_command(key)`), `QAction` của từng lệnh tạo một lần ở `MainWindow.command_actions`. Không import Qt ở đây.

Nhãn lưu dạng Qt: `&` thật viết `&&` (nhãn thành chữ của `QAction`/nút); `label_text()` trả nhãn để hiển thị.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    key: str               # "convert_word", "ocr", "rotate_left", "save", …
    label: str             # tên hiện trên nút / Ctrl+K (`&` viết `&&`)
    icon: str              # tên biểu tượng Lucide (`ui/icons.ICON_NAMES`)
    tab: str               # "read" | "convert" | "edit" | "fill" | "security" | "system"
    shortcut: str = ""     # "Ctrl+Shift+W"; nhiều phím cách nhau bằng dấu phẩy, phím đầu là phím chính
    group: str = ""        # nhóm ▾ trong thẻ ("word", "mark", "draw", "fill_mark", "pages", "process", "save")
    needs_document: bool = False
    summary: str = ""      # một dòng mô tả (Trang chủ, chú giải)
    keywords: str = ""     # tìm không dấu
    checkable: bool = False
    register_shortcut: bool = True  # False: phím do tab / `EditToolbar` đăng ký theo ngữ cảnh (V, H, phím chữ cái)
    palette: bool = True            # False: không liệt kê ở Ctrl+K

    def label_text(self) -> str:
        """Nhãn để hiển thị (bỏ cách viết `&&` của Qt)."""
        return self.label.replace("&&", "&")

    def shortcuts(self) -> tuple[str, ...]:
        return tuple(s.strip() for s in self.shortcut.split(",") if s.strip())


TABS: tuple[tuple[str, str], ...] = (
    ("read", "Đọc"),
    ("convert", "Chuyển đổi"),
    ("edit", "Chỉnh sửa"),
    ("fill", "Điền && Ký"),
    ("security", "Bảo mật"),
)
TAB_LABELS: dict[str, str] = {**dict(TABS), "system": "Hệ thống"}

_C = Command

# Công cụ chú thích: (khoá TOOL_DEFS, nhãn, biểu tượng, phím chữ cái của `EditToolbar`, nhóm ▾, từ khoá)
_EDIT_TOOLS: tuple[tuple[str, str, str, str, str, str], ...] = (
    ("select", "Chọn / di chuyển", "mouse-pointer-2", "V", "", "chon di chuyen chu thich select move"),
    ("highlight", "Tô sáng", "highlighter", "H", "mark", "to sang danh dau chu highlight mau"),
    ("underline", "Gạch chân", "underline", "U", "mark", "gach chan chu underline"),
    ("strikeout", "Gạch ngang", "strikethrough", "K", "mark", "gach ngang xoa chu strikeout"),
    ("squiggly", "Gạch sóng", "waves", "G", "mark", "gach song chu squiggly luu y"),
    ("pen", "Bút", "pen-line", "P", "draw", "but ve tay ve tu do pen"),
    ("marker", "Bút dạ quang", "brush", "M", "draw", "but da quang marker to de"),
    ("rect", "Khung", "square", "R", "draw", "khung chu nhat hinh vuong rectangle ve"),
    ("ellipse", "Elip", "circle", "O", "draw", "elip hinh tron ellipse ve"),
    ("line", "Đường thẳng", "minus", "L", "draw", "duong thang ke line ve"),
    ("arrow", "Mũi tên", "arrow-up-right", "A", "draw", "mui ten arrow ve"),
    ("text", "Hộp chữ", "type", "T", "", "hop chu chen chu go chu text box"),
    ("note", "Ghi chú", "message-square", "N", "", "ghi chu dan comment note binh luan"),
    ("stamp", "Dấu đóng", "stamp", "D", "", "dau dong da duyet ban sao mat khan stamp"),
    ("eraser", "Tẩy", "eraser", "X", "", "tay xoa chu thich eraser"),
)
_FILL_TOOLS: tuple[tuple[str, str, str, str, str, str], ...] = (
    ("fill_text", "Gõ chữ", "text-cursor-input", "T", "", "go chu dien dong cham bieu mau don to khai"),
    ("fill_check", "Dấu tích", "check", "C", "fill_mark", "dau tich danh dau o vuong check"),
    ("fill_cross", "Dấu nhân", "x", "K", "fill_mark", "dau nhan dau x o vuong cross"),
    ("fill_dot", "Chấm tròn", "circle-dot", "O", "fill_mark", "cham tron trac nghiem dot"),
    ("fill_line", "Dấu gạch", "minus", "L", "fill_mark", "dau gach ngang o khong chon line"),
    ("fill_date", "Ngày tháng", "calendar", "D", "", "ngay thang hom nay date nd30"),
    ("fill_sign", "Chữ ký", "signature", "S", "", "chu ky ky ten signature"),
    ("fill_initials", "Chữ ký nháy", "pen-tool", "N", "", "chu ky nhay ky tat initials"),
)


def _annot_commands(tools, tab: str) -> list[Command]:
    return [
        _C(f"annot.{key}", label, icon, tab, shortcut=letter, group=group, needs_document=True,
           summary=f"{label} — phím {letter} khi đang ở thẻ {TAB_LABELS[tab].replace('&&', '&')}",
           keywords=keywords, register_shortcut=False)
        for key, label, icon, letter, group, keywords in tools
    ]


COMMANDS: tuple[Command, ...] = (
    # ── Đọc ──
    _C("rotate_left", "Xoay trái", "rotate-ccw", "read", needs_document=True,
       summary="Xoay trang hiện tại sang trái 90° khi xem", keywords="xoay trai rotate left"),
    _C("rotate_right", "Xoay phải", "rotate-cw", "read", needs_document=True,
       summary="Xoay trang hiện tại sang phải 90° khi xem", keywords="xoay phai rotate right"),
    _C("read_mode", "Đọc tập trung", "book-open", "read", "F11", needs_document=True,
       summary="Ẩn bảng phụ, toàn màn hình", keywords="doc tap trung toan man hinh fullscreen"),
    _C("print", "In", "printer", "read", "Ctrl+P", needs_document=True,
       summary="Xem trước · Khổ giấy · 2 mặt · Đen trắng",
       keywords="in tai lieu print may in printer kho giay a4 a5 a3 hai mat den trang ban sao"),
    _C("doc_info", "Thuộc tính", "info", "read", "Ctrl+I", needs_document=True,
       summary="Metadata · Phông chữ · Bảo mật", keywords="thuoc tinh thong tin tai lieu metadata"),
    # ── Chuyển đổi ──
    _C("convert_word", "Xuất Word", "file-text", "convert", "Ctrl+Shift+W", needs_document=True,
       summary="Chuyển PDF sang Word (.docx) — văn bản hành chính tự dùng chuẩn NĐ30",
       keywords="xuat word chuyen doi pdf sang word docx"),
    _C("convert_word_nd30", "Xuất Word chuẩn NĐ30", "landmark", "convert", group="word", needs_document=True,
       summary="Văn bản hành chính · Bảng không viền · Lề chuẩn",
       keywords="nghi dinh 30 hanh chinh docx quoc hieu tieu ngu"),
    _C("convert_word_exact", "Xuất Word giữ vị trí 1:1", "ruler", "convert", group="word", needs_document=True,
       summary="Biểu mẫu · Hoá đơn · Bằng cấp", keywords="exact khung toa do giu vi tri docx"),
    _C("convert_word_flow", "Xuất Word dạng dòng chảy", "wrap-text", "convert", group="word", needs_document=True,
       summary="Tài liệu thường · pdf2docx + OpenXML", keywords="hybrid dong chay pdf2docx docx"),
    _C("ocr", "OCR tiếng Việt", "scan-text", "convert", "Ctrl+Shift+R",
       summary="PDF ảnh quét → PDF tìm kiếm được / Word NĐ30",
       keywords="ocr scan quet anh nhan dang chu vietocr pdf tim kiem duoc"),
    _C("nd30_check", "Kiểm tra thể thức NĐ30", "badge-check", "convert", "Ctrl+Shift+N",
       summary="Đo lề, cỡ chữ, giãn dòng · Đối chiếu từng thành phần",
       keywords="nghi dinh 30 the thuc kiem tra le can le"),
    _C("verify_docx", "Kiểm chứng DOCX", "microscope", "convert", needs_document=True,
       summary="Dựng bằng MS Word · So vị trí từng dòng với PDF", keywords="so sanh lech kiem chung word docx"),
    _C("layout_overlay", "Soi bố cục", "scan-eye", "convert", "F8", needs_document=True, checkable=True,
       summary="Lớp phủ khung bố cục, bảng, con dấu, chữ ký số trên trang",
       keywords="soi bo cuc layout inspector overlay con dau chu ky"),
    _C("batch_convert", "Chuyển đổi hàng loạt", "files", "convert", "Ctrl+Shift+B",
       summary="Nhiều PDF → DOCX · Bảng điểm từng tệp", keywords="batch nhieu tep hang loat thu muc keo tha"),
    # ── Chỉnh sửa ──
    *_annot_commands(_EDIT_TOOLS, "edit"),
    _C("undo", "Hoàn tác", "undo-2", "edit", "Ctrl+Z", needs_document=True,
       summary="Hoàn tác chú thích vừa thêm / sửa", keywords="hoan tac undo"),
    _C("redo", "Làm lại", "redo-2", "edit", "Ctrl+Y, Ctrl+Shift+Z", needs_document=True,
       summary="Làm lại thao tác vừa hoàn tác", keywords="lam lai redo"),
    _C("organize", "Sắp xếp && cắt ghép trang", "layers", "edit", "Ctrl+Shift+O", group="pages",
       needs_document=True, summary="Kéo thả · Xoay · Xoá · Trang trắng",
       keywords="organize xoay xoa trang sap xep keo tha cat ghep"),
    _C("combine", "Ghép tệp PDF", "combine", "edit", "Ctrl+Shift+M", group="pages",
       summary="Nhiều tệp thành một · Giữ mục lục", keywords="merge ghep noi tep"),
    _C("split", "Tách tệp PDF", "scissors", "edit", group="pages", needs_document=True,
       summary="Mỗi N trang · Theo khoảng · Theo điểm cắt", keywords="split tach chia cat tep"),
    _C("extract_pages", "Trích trang", "file-output", "edit", group="pages", needs_document=True,
       summary="Lưu các trang chọn thành tệp mới", keywords="trich trang extract"),
    _C("compress", "Nén PDF", "file-archive", "edit", group="process", needs_document=True,
       summary="Nhẹ · Vừa · Mạnh — báo dung lượng trước/sau", keywords="compress nen giam dung luong anh email"),
    _C("watermark", "Đóng dấu nước", "droplet", "edit", group="process", needs_document=True,
       summary="Chữ tiếng Việt · Độ mờ · Góc xoay · Lát gạch",
       keywords="watermark dau nuoc ban sao mat noi bo du thao chim"),
    _C("page_numbers", "Đánh số trang", "list-ordered", "edit", group="process", needs_document=True,
       summary="6 vị trí · «Trang 1 / 10» · Mẫu chuẩn NĐ30",
       keywords="page number danh so trang nd30 dau trang chan trang"),
    _C("save", "Lưu", "save", "edit", "Ctrl+S", needs_document=True,
       summary="Ghi bổ sung vào tệp gốc (giữ chữ ký số)", keywords="luu ghi save"),
    _C("save_as", "Lưu thành tệp mới…", "save-all", "edit", "Ctrl+Shift+S", group="save", needs_document=True,
       summary="Ghi toàn bộ thành tệp PDF mới", keywords="luu thanh tep moi save as"),
    _C("export_flattened", "Xuất bản làm phẳng chú thích…", "file-down", "edit", group="save",
       needs_document=True, summary="Vẽ chú thích vào nội dung trang", keywords="lam phang flatten xuat ban"),
    # ── Điền & Ký ──
    *_annot_commands(_FILL_TOOLS, "fill"),
    _C("signatures", "Thư viện chữ ký", "library", "fill", needs_document=True,
       summary="Vẽ · Gõ tên · Ảnh · Tách nền ảnh chụp chữ ký / con dấu",
       keywords="thu vien chu ky nhay signature initials anh chup tach nen con dau"),
    # ── Bảo mật ──
    _C("sig_inspect", "Soi chữ ký số && con dấu", "shield-check", "security", needs_document=True,
       summary="Phát hiện widget ký số VGCA, con dấu", keywords="chu ky so vgca con dau soi"),
    _C("protect", "Đặt mật khẩu", "lock", "security", needs_document=True,
       summary="AES-256 · Mật khẩu mở · Quyền in / sao chép / sửa",
       keywords="password mat khau bao ve ma hoa aes quyen protect encrypt"),
    _C("unlock", "Gỡ mật khẩu", "lock-open", "security", needs_document=True,
       summary="Khi biết mật khẩu · Gỡ hạn chế quyền", keywords="unlock go mat khau mo khoa decrypt password"),
    # ── Hệ thống ──
    _C("open", "Mở tệp…", "folder-open", "system", "Ctrl+O", summary="Mở một hoặc nhiều tệp PDF",
       keywords="mo tep file open"),
    _C("close_tab", "Đóng tài liệu", "x", "system", "Ctrl+F4, Ctrl+W", needs_document=True,
       summary="Đóng tài liệu đang xem", keywords="dong tai lieu tab close"),
    _C("home", "Trang chủ", "house", "system", "Alt+Home", summary="Về Trang chủ / quay lại tài liệu",
       keywords="trang chu home"),
    _C("quit", "Thoát", "log-out", "system", "Ctrl+Q", summary="Đóng QT PDF Pro", keywords="thoat quit exit"),
    _C("zoom_in", "Phóng to", "zoom-in", "system", "Ctrl++", needs_document=True, keywords="phong to zoom in"),
    _C("zoom_out", "Thu nhỏ", "zoom-out", "system", "Ctrl+-", needs_document=True, keywords="thu nho zoom out"),
    _C("fit_width", "Vừa chiều ngang", "move-horizontal", "system", "Ctrl+1", needs_document=True,
       keywords="vua chieu ngang fit width thu phong"),
    _C("fit_page", "Vừa trang", "maximize", "system", "Ctrl+0", needs_document=True,
       keywords="vua trang fit page thu phong"),
    _C("pointer_select", "Chọn chữ", "text-cursor", "system", "V", needs_document=True, checkable=True,
       summary="Kéo chọn liền nhiều trang · Bản scan tự nhận dạng",
       keywords="chon chu boi den sao chep copy text select con tro ban scan quet ocr vung keo",
       register_shortcut=False),
    _C("pointer_hand", "Bàn tay", "hand", "system", "H", needs_document=True, checkable=True,
       summary="Kéo chuột để cuộn trang · Giữ Space", keywords="ban tay hand pan keo cuon con tro",
       register_shortcut=False),
    _C("toggle_sidebar", "Ẩn/hiện ngăn bên phải", "panel-right", "system", "F4", needs_document=True,
       keywords="an hien ngan ben phai sidebar"),
    _C("toggle_theme", "Đổi giao diện Sáng / Tối", "sun-moon", "system", "Ctrl+Shift+T",
       keywords="doi giao dien sang toi theme dark light"),
    _C("palette", "Tìm lệnh…", "command", "system", "Ctrl+K", keywords="tim lenh cong cu", palette=False),
    _C("find", "Tìm trong tài liệu", "search", "system", "Ctrl+F", needs_document=True,
       summary="Tô sáng mọi vị trí khớp", keywords="tim kiem toan van search find"),
    _C("extract_text", "Trích xuất văn bản", "clipboard-list", "system", "Ctrl+T", needs_document=True,
       summary="Xem & sao chép chữ trang hiện tại", keywords="trich xuat van ban copy text sao chep"),
    _C("edit_mode", "Chế độ chỉnh sửa", "pencil", "system", "Ctrl+E", needs_document=True,
       summary="Tô màu · Đánh dấu · Vẽ · Chèn chữ", keywords="chinh sua annotate to mau danh dau ve chen chu"),
    _C("fill_mode", "Điền && Ký", "file-pen-line", "system", "Ctrl+Shift+F", needs_document=True,
       summary="Gõ chữ vào dòng chấm · ✓ ✕ ● · Ngày · Chữ ký",
       keywords="fill sign dien ky go chu dong cham danh dau tich ngay thang chu ky bieu mau"),
    _C("check_update", "Kiểm tra cập nhật…", "refresh-cw", "system", keywords="kiem tra cap nhat update ban moi"),
    _C("github", "Mã nguồn && báo lỗi (GitHub)", "code-xml", "system",
       keywords="ma nguon bao loi gop y github"),
    _C("about", "Giới thiệu QT PDF Pro", "info", "system", keywords="gioi thieu about phien ban"),
    _C("default_app", "Đặt làm trình xem PDF mặc định…", "settings", "system",
       keywords="trinh xem pdf mac dinh default app cai dat"),
    _C("auto_check_updates", "Tự kiểm tra cập nhật mỗi khi mở", "refresh-cw", "system", checkable=True,
       keywords="tu kiem tra cap nhat cai dat"),
    _C("auto_download_updates", "Tự tải bản mới && cài khi thoát", "download", "system", checkable=True,
       keywords="tu tai ban moi cai khi thoat cap nhat cai dat"),
)

BY_KEY: dict[str, Command] = {c.key: c for c in COMMANDS}


def get(key: str) -> Command:
    return BY_KEY[key]


_GROUP_NAMES = ("word", "mark", "draw", "fill_mark", "pages", "process", "save")
GROUPS: dict[str, tuple[str, ...]] = {g: tuple(c.key for c in COMMANDS if c.group == g) for g in _GROUP_NAMES}

# Phần tử: khoá lệnh · "group:<nhóm>" (nút ▾ nhớ kiểu vừa dùng) · "split:<khoá>:<nhóm>" (thân = lệnh, mũi tên =
# nhóm) · "date_formats" (nút Ngày ▾) · "|" (vạch ngăn)
TAB_LAYOUT: dict[str, tuple[str, ...]] = {
    "read": ("rotate_left", "rotate_right", "read_mode", "print", "doc_info"),
    "convert": ("split:convert_word:word", "ocr", "nd30_check", "verify_docx", "layout_overlay", "batch_convert"),
    "edit": ("annot.select", "group:mark", "group:draw", "annot.text", "annot.note", "annot.stamp",
             "annot.eraser", "undo", "redo", "|", "group:pages", "group:process", "|", "split:save:save"),
    "fill": ("annot.fill_text", "group:fill_mark", "date_formats", "annot.fill_sign", "annot.fill_initials",
             "signatures", "annot.eraser", "undo", "redo", "|", "split:save:save"),
    "security": ("sig_inspect", "protect", "unlock"),
}

HOME_QUICK_TOOLS: tuple[str, ...] = (
    "ocr", "batch_convert", "combine", "organize", "compress", "fill_mode", "protect", "print",
)


def expand_layout_item(item: str) -> tuple[str, ...]:
    """Các khoá lệnh mà một phần tử của `TAB_LAYOUT` tham chiếu."""
    if item == "|":
        return ()
    if item == "date_formats":
        return ("annot.fill_date",)
    if item.startswith("group:"):
        return GROUPS[item.split(":", 1)[1]]
    if item.startswith("split:"):
        _, key, group = item.split(":", 2)
        return (key, *GROUPS[group])
    return (item,)


def fold(text: str) -> str:
    """Bỏ dấu tiếng Việt + chữ thường để tìm kiếm không phân biệt dấu."""
    nfkd = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn").lower()


_TAB_ORDER = [k for k, _ in TABS] + ["system"]


def search(query: str, has_document: bool = True) -> list[Command]:
    """Lệnh cho Ctrl+K: khớp không dấu mọi từ của `query` trên nhãn + từ khoá + tên thẻ; bỏ `palette=False`.

    Rỗng → mọi lệnh theo thứ tự `TABS` rồi `system`. Có từ khoá → lệnh khớp ngay ở nhãn xếp trước; khi chưa
    có tài liệu, lệnh không cần tài liệu xếp trước lệnh cần tài liệu (cùng mức khớp)."""
    parts = fold(query).split()
    indexed = [(i, c) for i, c in enumerate(COMMANDS) if c.palette]
    if not parts:
        return [c for _, c in sorted(indexed, key=lambda ic: (_TAB_ORDER.index(ic[1].tab), ic[0]))]
    scored = []
    for i, c in indexed:
        label = fold(c.label_text())
        hay = " ".join((label, fold(c.keywords), fold(TAB_LABELS[c.tab].replace("&&", "&"))))
        if all(p in hay for p in parts):
            in_label = all(p in label for p in parts)
            scored.append(((not in_label, c.needs_document and not has_document,
                            _TAB_ORDER.index(c.tab), i), c))
    return [c for _, c in sorted(scored, key=lambda sc: sc[0])]
