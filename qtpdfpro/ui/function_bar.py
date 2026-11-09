"""Tầng 2: thanh chức năng khi đang xem tài liệu — 5 thẻ · công cụ của thẻ (tràn vào `⋯`) · cụm điều khiển xem.

Công cụ dựng từ `commands.TAB_LAYOUT`; mọi nút dùng chung `QAction` của `MainWindow.command_actions` nên trạng thái
bật / tắt / đã chọn đồng bộ với phím tắt, ☰ và Ctrl+K. Nút công cụ hiện nhãn ngắn (`QAction.iconText()` =
`Command.button_text()`), chú giải mang tên đầy đủ + phím tắt. Công cụ chú thích (thẻ Chỉnh sửa / Điền & Ký) chỉ có
biểu tượng; nhóm ▾ của chúng (Đánh dấu chữ, Vẽ, Dấu tích) mang thân nút = công cụ vừa dùng (`set_checked_tool`).
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QWidget,
)

from qtpdfpro.core import fill_sign as fs

from . import commands, icons

# Nhãn nút nhóm ▾ (thân nút mang biểu tượng của lệnh vừa dùng trong nhóm)
GROUP_LABELS = {
    "pages": "Trang", "process": "Xử lý", "mark": "Đánh dấu chữ", "draw": "Vẽ", "fill_mark": "Dấu tích",
    "word": "Xuất Word", "save": "Lưu",
}
# Thẻ có chế độ chỉnh sửa: nút «Lưu ▾» luôn hiện (thẻ khác: chỉ khi có thay đổi chưa lưu)
EDIT_TABS = ("edit", "fill")
SAVE_ITEM = "split:save:save"
DATE_ITEM = "date_formats"
# Lệnh có sẵn ở cụm điều khiển xem (nút Chọn chữ / Bàn tay, mục «Vừa ngang» / «Vừa trang» của ô thu phóng)
VIEW_CONTROL_KEYS = ("pointer_select", "pointer_hand", "fit_width", "fit_page")
ZOOM_CHOICES: tuple[tuple[str, str, int], ...] = (
    ("Vừa ngang", "fit_width", 100), ("Vừa trang", "fit_page", 100),
    *((f"{p}%", "percent", p) for p in (50, 75, 100, 125, 150, 200, 300)),
)
_ICON_ONLY_KEYS = frozenset({"undo", "redo"})


def _is_annotation_item(item: str) -> bool:
    keys = commands.expand_layout_item(item)
    return bool(keys) and all(k.startswith("annot.") for k in keys)


class _ToolsArea(QWidget):
    """Vùng công cụ co giãn: bề rộng do thanh quyết định (không đòi chỗ), đổi cỡ → xếp lại phần tràn."""

    resized = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)

    def resizeEvent(self, event) -> None:  # noqa: N802 (tên hàm Qt)
        super().resizeEvent(event)
        self.resized.emit()


class FunctionBar(QFrame):
    """Tầng 2: thẻ | vùng công cụ (`⋯` khi hẹp) | Chọn chữ / Bàn tay · ◀ trang / N ▶ · thu phóng."""

    tabRequested = Signal(str)
    dateFormatChosen = Signal(str)  # nút «Ngày ▾»: khoá mẫu ngày (`fill_sign.DATE_FORMATS`)

    def __init__(self, actions: dict[str, QAction], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("functionBar")
        self._actions = actions
        self._tab = "read"
        self._dirty = False
        self._items: list[str] = []
        self._sequence: list[tuple[str, QWidget]] = []  # (phần tử bố cục, nút / vạch ngăn) theo thứ tự
        self._pinned: Optional[QToolButton] = None  # «Lưu ▾»: không bao giờ vào ⋯, đứng sau nút ⋯
        self._hidden: list[str] = []
        self._group_last: dict[str, str] = {}  # nhóm → lệnh vừa dùng
        self._group_refreshers: list = []
        self._checked_tool: Optional[str] = None
        self.tool_buttons: dict[str, QToolButton] = {}
        # Mẫu ngày của nút «Ngày ▾» (dùng chung cho nút và mục trong `⋯`)
        self._date_format = fs.DATE_FORMATS[0][0]
        self._date_group = QActionGroup(self)
        self._date_group.setExclusive(True)
        self.date_format_actions: dict[str, QAction] = {}
        for key, _pattern in fs.DATE_FORMATS:
            act = QAction(self)  # nhãn = ngày hôm nay theo mẫu, đặt lại mỗi khi mở menu (`_refresh_date_labels`)
            act.setCheckable(True)
            act.setChecked(key == self._date_format)
            act.triggered.connect(lambda _c=False, k=key: self.dateFormatChosen.emit(k))
            self._date_group.addAction(act)
            self.date_format_actions[key] = act
        self._refresh_date_labels()
        self._date_submenu = QMenu("Mẫu ngày", self)  # dùng khi nút «Ngày ▾» nằm trong ⋯
        self._date_submenu.addActions(list(self.date_format_actions.values()))
        self._date_submenu.aboutToShow.connect(self._refresh_date_labels)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 3, 8, 3)
        lay.setSpacing(4)

        # ─── Thẻ ───
        self.tab_buttons: dict[str, QPushButton] = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        for i, (key, label) in enumerate(commands.TABS, start=1):
            btn = QPushButton(label)
            btn.setObjectName("fnTabBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f"{label.replace('&&', '&')} (Alt+{i})")
            btn.clicked.connect(lambda _c=False, k=key: self.tabRequested.emit(k))
            group.addButton(btn)
            lay.addWidget(btn)
            self.tab_buttons[key] = btn
        lay.addWidget(self._separator())

        # ─── Vùng công cụ + ⋯ ───
        self._tools_area = _ToolsArea()
        self._tools_area.resized.connect(self.relayout_overflow)
        self._tools_lay: QHBoxLayout = self._tools_area.layout()  # type: ignore[assignment]
        self._overflow_menu = QMenu(self)
        self.overflow_button = QToolButton()
        self.overflow_button.setObjectName("fnToolBtn")
        self.overflow_button.setToolTip("Công cụ khác")
        self.overflow_button.setIconSize(QSize(18, 18))
        self.overflow_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.overflow_button.setMenu(self._overflow_menu)
        icons.bind(self.overflow_button, "ellipsis")
        self.overflow_button.setVisible(False)
        self._tools_lay.addWidget(self.overflow_button)
        self._tools_lay.addStretch(1)
        lay.addWidget(self._tools_area, 1)
        lay.addWidget(self._separator())

        # ─── Cụm điều khiển xem (mọi thẻ) ───
        self.btn_pointer_select = self._action_icon_button(actions["pointer_select"])
        self.btn_pointer_hand = self._action_icon_button(actions["pointer_hand"])
        self.btn_prev_page = self._icon_button("chevron-left", "Trang trước")
        self.page_spin = QSpinBox()
        self.page_spin.setObjectName("pageSpin")
        self.page_spin.setRange(1, 1)
        self.page_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_spin.setFixedWidth(52)
        self.page_spin.setToolTip("Đi tới trang")
        self.total_page_lbl = QLabel("/ 0")
        self.total_page_lbl.setObjectName("pageTotalLbl")
        self.btn_next_page = self._icon_button("chevron-right", "Trang sau")
        self.zoom_combo = QComboBox()
        self.zoom_combo.setObjectName("zoomCombo")
        self.zoom_combo.setToolTip("Mức thu phóng (Ctrl++ / Ctrl+- · Ctrl+1 vừa ngang · Ctrl+0 vừa trang)")
        for text, mode, pct in ZOOM_CHOICES:
            self.zoom_combo.addItem(text, (mode, pct))
        self.zoom_combo.setMinimumContentsLength(6)
        for w in (self.btn_pointer_select, self.btn_pointer_hand, self._separator(), self.btn_prev_page,
                  self.page_spin, self.total_page_lbl, self.btn_next_page, self.zoom_combo):
            lay.addWidget(w)

        self.set_tab("read")

    # ─── Dựng ──────────────────────────────────────────────────────────────

    @staticmethod
    def _separator() -> QFrame:
        sep = QFrame()
        sep.setObjectName("fnSep")
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedWidth(9)
        return sep

    @staticmethod
    def _icon_button(icon_name: str, tip: str) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("fnIconBtn")
        btn.setToolTip(tip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setIconSize(QSize(18, 18))
        icons.bind(btn, icon_name)
        return btn

    @staticmethod
    def _action_icon_button(action: QAction) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("fnIconBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setIconSize(QSize(18, 18))
        btn.setDefaultAction(action)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        return btn

    def _tool_button(self, item: str) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("fnToolBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setIconSize(QSize(18, 18))
        keys = commands.expand_layout_item(item)
        icon_only = _is_annotation_item(item) or (len(keys) == 1 and keys[0] in _ICON_ONLY_KEYS)
        if item.startswith("group:"):
            self._setup_group_button(btn, item.split(":", 1)[1], icon_only)
        elif item == DATE_ITEM:
            self._setup_date_button(btn)
        else:
            body = keys[0]
            btn.setDefaultAction(self._actions[body])
            if item.startswith("split:"):
                menu = QMenu(btn)
                for key in keys[1:]:
                    menu.addAction(self._actions[key])
                btn.setMenu(menu)
                btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
            if body == "convert_word" or (body == "save" and self._dirty and self._tab != "convert"):
                btn.setObjectName("primaryConvertBtn")  # mỗi màn hình tối đa một nút chính (spec §2.6)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly if icon_only
                               else Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        return btn

    def _setup_group_button(self, btn: QToolButton, group: str, icon_only: bool) -> None:
        """Nút nhóm ▾: thân = lệnh vừa dùng trong nhóm (nhớ giữa các lần dựng lại), mũi tên = cả nhóm.

        Nhóm công cụ chú thích (chỉ biểu tượng): thân nút `setDefaultAction` = `QAction` của công cụ vừa dùng — nút
        mang trạng thái bật / tắt / đang chọn của công cụ đó; «vừa dùng» cập nhật cả khi chọn công cụ bằng `⋯`,
        Ctrl+K hay phím chữ cái (`set_checked_tool`). Nhóm khác (Trang, Xử lý): nhãn nhóm + biểu tượng lệnh vừa dùng."""
        keys = commands.GROUPS[group]
        menu = QMenu(btn)
        for key in keys:
            menu.addAction(self._actions[key])
        label = GROUP_LABELS.get(group, group)

        if icon_only:
            def show_last() -> None:
                act = self._actions[self._group_last.get(group, keys[0])]
                old = btn.defaultAction()
                if old is not act:
                    btn.setDefaultAction(act)
                    if old is not None:
                        btn.removeAction(old)
                btn.setToolTip(f"{label}: {act.toolTip()} — mũi tên: chọn kiểu khác")
        else:
            def show_last() -> None:
                act = self._actions[self._group_last.get(group, keys[0])]
                btn.setIcon(act.icon())
                btn.setToolTip(f"{label} — bấm: {act.toolTip()}")

            btn.setText(label)
            btn.clicked.connect(lambda _c=False: self._actions[self._group_last.get(group, keys[0])].trigger())

        def remember(act: QAction) -> None:
            for key in keys:
                if self._actions[key] is act:
                    self._group_last[group] = key
            show_last()

        show_last()
        btn.setMenu(menu)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        menu.triggered.connect(remember)
        self._group_refreshers.append(show_last)

    def _setup_date_button(self, btn: QToolButton) -> None:
        """Nút «Ngày ▾»: thân = công cụ «Ngày tháng» với mẫu đang chọn, mũi tên = các mẫu ngày (chọn → đặt ngày)."""
        act = self._actions["annot.fill_date"]
        btn.setDefaultAction(act)
        menu = QMenu(btn)
        menu.addActions(list(self.date_format_actions.values()))
        menu.aboutToShow.connect(self._refresh_date_labels)  # qua nửa đêm vẫn hiện đúng ngày hôm nay
        btn.setMenu(menu)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)

        def show_format() -> None:
            sample = fs.format_date(self._date_format)
            btn.setToolTip(f"{act.toolTip()} — mẫu: «{sample}» — mũi tên: chọn mẫu ngày")

        show_format()
        self._group_refreshers.append(show_format)

    def _refresh_date_labels(self) -> None:
        for key, act in self.date_format_actions.items():
            act.setText(fs.format_date(key).replace("&", "&&"))

    def refresh_icons(self) -> None:
        """Sau khi đổi giao diện: nút dùng `setDefaultAction` tự theo `QAction`; nút nhóm tô lại thân nút."""
        for refresh in self._group_refreshers:
            refresh()

    def set_checked_tool(self, key: Optional[str]) -> None:
        """Công cụ chú thích đang dùng (`AnnotationController.tool`, None = không ở chế độ chỉnh sửa): đánh dấu nút
        của nó; công cụ thuộc nhóm ▾ thì thân nút nhóm đổi sang công cụ đó (nhớ kiểu vừa dùng)."""
        self._checked_tool = key
        target = f"annot.{key}" if key else ""
        for k, act in self._actions.items():
            if k.startswith("annot.") and act.isCheckable() and act.isChecked() != (k == target):
                act.setChecked(k == target)
        if target in self._actions:
            for group, keys in commands.GROUPS.items():
                if target in keys:
                    self._group_last[group] = target
        self.refresh_icons()

    def checked_tool(self) -> Optional[str]:
        return self._checked_tool

    def set_date_format(self, key: str) -> None:
        """Mẫu ngày đang dùng của bộ điều khiển chú thích (đánh dấu trong menu «Ngày ▾», chú giải thân nút)."""
        act = self.date_format_actions.get(key)
        if act is None:
            return
        self._date_format = key
        if not act.isChecked():
            act.setChecked(True)
        self.refresh_icons()

    def _layout_items(self) -> list[str]:
        """Phần tử của thẻ đang chọn; thẻ không phải Chỉnh sửa / Điền & Ký thêm «Lưu ▾» khi có thay đổi chưa lưu.
        Bỏ vạch ngăn thừa ở đầu / cuối / liền nhau."""
        layout = list(commands.TAB_LAYOUT.get(self._tab, ()))
        if self._tab not in EDIT_TABS and self._dirty:
            layout += ["|", SAVE_ITEM]
        items: list[str] = []
        for it in layout:
            if it == "|" and (not items or items[-1] == "|"):
                continue
            items.append(it)
        while items and items[-1] == "|":
            items.pop()
        return items

    def _rebuild(self) -> None:
        old = [w for _i, w in self._sequence] + ([self._pinned] if self._pinned is not None else [])
        for widget in old:
            self._tools_lay.removeWidget(widget)
            widget.hide()  # deleteLater chỉ xoá khi về vòng lặp sự kiện — ẩn ngay để không đè nút mới
            widget.deleteLater()
        self._sequence = []
        self._pinned = None
        self._group_refreshers = []
        self.tool_buttons = {}
        self._items = self._layout_items()
        items = list(self._items)
        if items and items[-1] == SAVE_ITEM:  # «Lưu ▾» luôn hiện (spec §3): ghim sau ⋯, công cụ khác tràn trước
            items.pop()
            self._pinned = self._tool_button(SAVE_ITEM)
            self._tools_lay.insertWidget(self._tools_lay.indexOf(self.overflow_button) + 1, self._pinned)
        pos = 0
        for item in items:
            widget: QWidget = self._separator() if item == "|" else self._tool_button(item)
            if item != "|":
                self.tool_buttons[item] = widget  # type: ignore[assignment]
            self._tools_lay.insertWidget(pos, widget)
            pos += 1
            self._sequence.append((item, widget))
        if self._pinned is not None:
            self.tool_buttons[SAVE_ITEM] = self._pinned
        self.relayout_overflow()

    # ─── Thẻ & trạng thái ──────────────────────────────────────────────────

    def set_tab(self, key: str) -> None:
        if key not in commands.TAB_LAYOUT:
            return
        self._tab = key
        for k, btn in self.tab_buttons.items():
            btn.setChecked(k == key)
        self._rebuild()

    def current_tab(self) -> str:
        return self._tab

    def set_save_visible(self, visible: bool) -> None:
        """Tài liệu có / hết thay đổi chưa lưu: thẻ Đọc / Chuyển đổi / Bảo mật hiện / ẩn «Lưu ▾» cuối vùng công cụ;
        thẻ Chỉnh sửa / Điền & Ký đổi nút «Lưu» thành nút chính."""
        visible = bool(visible)
        if visible == self._dirty:
            return
        self._dirty = visible
        self._rebuild()

    def overflow_keys(self) -> list[str]:
        """Phần tử bố cục đang nằm trong menu `⋯`."""
        return list(self._hidden)

    def visible_command_keys(self) -> list[str]:
        """Phần tử bố cục của từng nút thật ở tầng 2 — một mục cho mỗi nút (kể cả mục đang nằm trong `⋯` và «Lưu ▾»
        ghim), phần tử đặt hai lần thì có hai mục — cộng cụm điều khiển xem: Chọn chữ / Bàn tay và hai mức «Vừa
        ngang» / «Vừa trang» của ô thu phóng.

        Phần tử là khoá lệnh hoặc `group:…` / `split:…` / `date_formats` — `commands.expand_layout_item` ra khoá lệnh."""
        items = [item for item, _w in self._sequence if item != "|"]
        if self._pinned is not None:
            items.append(SAVE_ITEM)
        return items + list(VIEW_CONTROL_KEYS)

    # ─── Tràn vào ⋯ ────────────────────────────────────────────────────────

    def resizeEvent(self, event) -> None:  # noqa: N802 (tên hàm Qt)
        super().resizeEvent(event)
        self.relayout_overflow()

    def relayout_overflow(self) -> None:
        """Hiện nút theo thứ tự tới khi hết chỗ; phần còn lại ẩn và vào menu `⋯` (giữ thứ tự)."""
        avail = self._tools_area.width()
        spacing = self._tools_lay.spacing()
        if self._pinned is not None:
            avail -= self._pinned.sizeHint().width() + spacing
        widths = [w.sizeHint().width() for _i, w in self._sequence]
        total = sum(widths) + spacing * max(0, len(widths) - 1)
        hidden_from = len(self._sequence)
        if total > avail:
            budget = avail - self.overflow_button.sizeHint().width() - spacing
            used = 0
            for idx, width in enumerate(widths):
                used += width + (spacing if idx else 0)
                if used > budget:
                    hidden_from = idx
                    break
        shown = self._sequence[:hidden_from]
        overflowing = hidden_from < len(self._sequence)
        while shown and shown[-1][0] == "|" and (overflowing or self._pinned is None):
            shown = shown[:-1]  # không để vạch ngăn lẻ ngay trước ⋯ (vạch trước «Lưu ▾» ghim thì giữ)
        visible_ids = {id(w) for _i, w in shown}
        for _item, widget in self._sequence:
            widget.setVisible(id(widget) in visible_ids)
        self._hidden = [item for item, _w in self._sequence[hidden_from:] if item != "|"]
        self._fill_overflow_menu(self._sequence[hidden_from:])
        self.overflow_button.setVisible(bool(self._hidden))

    def _fill_overflow_menu(self, rest: list[tuple[str, QWidget]]) -> None:
        menu = self._overflow_menu
        menu.clear()
        for item, _w in rest:
            keys = commands.expand_layout_item(item)
            if not keys:
                if menu.actions() and not menu.actions()[-1].isSeparator():
                    menu.addSeparator()
                continue
            grouped = len(keys) > 1 or item == DATE_ITEM
            if grouped and menu.actions() and not menu.actions()[-1].isSeparator():
                menu.addSeparator()
            for key in keys:
                menu.addAction(self._actions[key])
            if item == DATE_ITEM:  # mẫu ngày cũng chọn được khi nút «Ngày ▾» nằm trong ⋯
                menu.addMenu(self._date_submenu)
            if grouped:
                menu.addSeparator()
        while menu.actions() and menu.actions()[-1].isSeparator():
            menu.removeAction(menu.actions()[-1])

    # ─── Điều khiển xem ────────────────────────────────────────────────────

    def set_page(self, current: int, total: int) -> None:
        """`current` tính từ 1; `total` = 0 khi chưa có tài liệu."""
        self.page_spin.blockSignals(True)
        self.page_spin.setMaximum(max(1, total))
        self.page_spin.setValue(max(1, current))
        self.page_spin.blockSignals(False)
        self.total_page_lbl.setText(f"/ {total}")

    def set_zoom(self, mode: str, percent: int) -> None:
        """Ô thu phóng hiện mức đang dùng (mức không có sẵn trong danh sách → chữ «137%»)."""
        index = -1
        for i in range(self.zoom_combo.count()):
            m, p = self.zoom_combo.itemData(i)
            if m == mode and (mode != "percent" or p == percent):
                index = i
                break
        self.zoom_combo.blockSignals(True)
        self.zoom_combo.setPlaceholderText(f"{percent}%")
        self.zoom_combo.setCurrentIndex(index)
        self.zoom_combo.blockSignals(False)
