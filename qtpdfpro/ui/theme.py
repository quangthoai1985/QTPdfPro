"""Giao diện Sáng / Tối (Fluent QSS) cho QT PDF Pro."""

from __future__ import annotations


def get_stylesheet(theme: str = "dark") -> str:
    """Trả về chuỗi QSS theo chủ đề `'dark'` hoặc `'light'`."""
    if theme == "light":
        return _LIGHT_QSS
    return _DARK_QSS


_DARK_QSS = """
QMainWindow, QDialog {
    background-color: #181A20;
    color: #E6E8EC;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}
QMenuBar {
    background-color: #1E2128;
    color: #E6E8EC;
    border-bottom: 1px solid #2B2F3A;
    padding: 2px 6px;
}
QMenuBar::item:selected {
    background-color: #2E3440;
    border-radius: 4px;
}
QMenu {
    background-color: #22262E;
    color: #E6E8EC;
    border: 1px solid #343946;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #2563EB;
    color: #FFFFFF;
}
QToolBar {
    background-color: #1E2128;
    border-bottom: 1px solid #2B2F3A;
    spacing: 6px;
    padding: 5px 8px;
}
QPushButton, QToolButton {
    background-color: #282C37;
    color: #E6E8EC;
    border: 1px solid #383E4C;
    border-radius: 6px;
    padding: 5px 11px;
    font-weight: 500;
}
QPushButton:hover, QToolButton:hover {
    background-color: #323846;
    border-color: #4B5568;
}
QPushButton:pressed, QToolButton:pressed {
    background-color: #2563EB;
    border-color: #3B82F6;
}
QPushButton#primaryConvertBtn, QToolButton#primaryConvertBtn {
    background-color: #16A34A;
    color: #FFFFFF;
    border: 1px solid #22C55E;
    font-weight: 600;
    padding: 6px 14px;
}
QPushButton#primaryConvertBtn:hover, QToolButton#primaryConvertBtn:hover {
    background-color: #15803D;
}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {
    background-color: #14161B;
    color: #F3F4F6;
    border: 1px solid #343946;
    border-radius: 5px;
    padding: 5px 8px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-color: #3B82F6;
}
QTabWidget::pane {
    border: 1px solid #2B2F3A;
    background-color: #181A20;
}
QTabBar::tab {
    background-color: #1E2128;
    color: #9CA3AF;
    border: 1px solid #2B2F3A;
    border-bottom: none;
    padding: 7px 14px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    background-color: #282C37;
    color: #FFFFFF;
    font-weight: 600;
    border-bottom: 2px solid #3B82F6;
}
QListWidget, QTreeWidget {
    background-color: #14161B;
    color: #E6E8EC;
    border: 1px solid #2B2F3A;
    border-radius: 4px;
    outline: none;
}
QListWidget::item:selected, QTreeWidget::item:selected {
    background-color: #2563EB;
    color: #FFFFFF;
}
QGroupBox {
    border: 1px solid #2E3442;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 10px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #60A5FA;
}
QProgressBar {
    background-color: #14161B;
    border: 1px solid #343946;
    border-radius: 5px;
    text-align: center;
    color: #FFFFFF;
    height: 20px;
}
QProgressBar::chunk {
    background-color: #16A34A;
    border-radius: 4px;
}
QStatusBar {
    background-color: #1E2128;
    color: #9CA3AF;
    border-top: 1px solid #2B2F3A;
}
"""


_LIGHT_QSS = """
QMainWindow, QDialog {
    background-color: #F8FAFC;
    color: #1E293B;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}
QMenuBar {
    background-color: #FFFFFF;
    color: #1E293B;
    border-bottom: 1px solid #E2E8F0;
    padding: 2px 6px;
}
QMenuBar::item:selected {
    background-color: #E2E8F0;
    border-radius: 4px;
}
QMenu {
    background-color: #FFFFFF;
    color: #1E293B;
    border: 1px solid #CBD5E1;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #2563EB;
    color: #FFFFFF;
}
QToolBar {
    background-color: #FFFFFF;
    border-bottom: 1px solid #E2E8F0;
    spacing: 6px;
    padding: 5px 8px;
}
QPushButton, QToolButton {
    background-color: #FFFFFF;
    color: #1E293B;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 5px 11px;
    font-weight: 500;
}
QPushButton:hover, QToolButton:hover {
    background-color: #F1F5F9;
    border-color: #94A3B8;
}
QPushButton:pressed, QToolButton:pressed {
    background-color: #2563EB;
    color: #FFFFFF;
}
QPushButton#primaryConvertBtn, QToolButton#primaryConvertBtn {
    background-color: #16A34A;
    color: #FFFFFF;
    border: 1px solid #15803D;
    font-weight: 600;
    padding: 6px 14px;
}
QPushButton#primaryConvertBtn:hover, QToolButton#primaryConvertBtn:hover {
    background-color: #15803D;
}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {
    background-color: #FFFFFF;
    color: #0F172A;
    border: 1px solid #CBD5E1;
    border-radius: 5px;
    padding: 5px 8px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-color: #2563EB;
}
QTabWidget::pane {
    border: 1px solid #E2E8F0;
    background-color: #F8FAFC;
}
QTabBar::tab {
    background-color: #F1F5F9;
    color: #475569;
    border: 1px solid #CBD5E1;
    border-bottom: none;
    padding: 7px 14px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    background-color: #FFFFFF;
    color: #0F172A;
    font-weight: 600;
    border-bottom: 2px solid #2563EB;
}
QListWidget, QTreeWidget {
    background-color: #FFFFFF;
    color: #1E293B;
    border: 1px solid #E2E8F0;
    border-radius: 4px;
    outline: none;
}
QListWidget::item:selected, QTreeWidget::item:selected {
    background-color: #2563EB;
    color: #FFFFFF;
}
QGroupBox {
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 10px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #1D4ED8;
}
QProgressBar {
    background-color: #E2E8F0;
    border: 1px solid #CBD5E1;
    border-radius: 5px;
    text-align: center;
    color: #0F172A;
    height: 20px;
}
QProgressBar::chunk {
    background-color: #16A34A;
    border-radius: 4px;
}
QStatusBar {
    background-color: #FFFFFF;
    color: #475569;
    border-top: 1px solid #E2E8F0;
}
"""
