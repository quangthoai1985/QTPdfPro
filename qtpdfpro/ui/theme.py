"""Giao diện Sáng / Tối (Fluent & PdfCraft-inspired QSS) cho QT PDF Pro."""

from __future__ import annotations


def get_stylesheet(theme: str = "dark") -> str:
    """Trả về chuỗi QSS theo chủ đề `'dark'` hoặc `'light'`."""
    if theme == "light":
        return _LIGHT_QSS
    return _DARK_QSS


_DARK_QSS = """
QMainWindow, QDialog, QWidget {
    background-color: #16181D;
    color: #E6E8EC;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}
QLabel, QCheckBox {
    background-color: transparent;
    color: #E6E8EC;
}
QMenuBar {
    background-color: #1C1F26;
    color: #E6E8EC;
    border-bottom: 1px solid #2A2E39;
    padding: 2px 6px;
}
QMenuBar::item:selected {
    background-color: #2D3340;
    border-radius: 4px;
}
QMenu {
    background-color: #20242D;
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
    background-color: #1C1F26;
    border-bottom: 1px solid #2A2E39;
    spacing: 6px;
    padding: 6px 10px;
}
QPushButton, QToolButton {
    background-color: #252934;
    color: #E6E8EC;
    border: 1px solid #353B49;
    border-radius: 6px;
    padding: 5px 11px;
    font-weight: 500;
}
QPushButton:hover, QToolButton:hover {
    background-color: #2F3543;
    border-color: #4B5568;
}
QPushButton:pressed, QToolButton:pressed {
    background-color: #2563EB;
    border-color: #3B82F6;
    color: #FFFFFF;
}
QPushButton#modePillBtn {
    background-color: transparent;
    color: #9CA3AF;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 5px 12px;
    font-weight: 600;
}
QPushButton#modePillBtn:hover {
    background-color: #252934;
    color: #F3F4F6;
}
QPushButton#modePillBtn:checked {
    background-color: #2563EB;
    color: #FFFFFF;
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
QPushButton#themeToggleBtn {
    background-color: #262B38;
    color: #FBBF24;
    border: 1px solid #3B4254;
    border-radius: 6px;
    padding: 5px 12px;
    font-weight: 600;
}
QPushButton#themeToggleBtn:hover {
    background-color: #32394A;
    border-color: #60A5FA;
}
QFrame#leftToolsPanel {
    background-color: #1C1F26;
    border-right: 1px solid #2A2E39;
}
QPushButton#toolCardBtn {
    background-color: #232731;
    color: #E5E7EB;
    border: 1px solid #313745;
    border-radius: 7px;
    padding: 8px 10px;
    text-align: left;
    font-weight: 500;
}
QPushButton#toolCardBtn:hover {
    background-color: #2B313E;
    border-color: #3B82F6;
}
QPushButton#toolCardPrimaryBtn {
    background-color: #1E3A8A;
    color: #FFFFFF;
    border: 1px solid #3B82F6;
    border-radius: 7px;
    padding: 9px 10px;
    text-align: left;
    font-weight: 600;
}
QPushButton#toolCardPrimaryBtn:hover {
    background-color: #1D4ED8;
}
QFrame#signatureBanner {
    background-color: #1E293B;
    border-bottom: 1px solid #334155;
    padding: 4px 10px;
}
QFrame#signatureBanner QLabel {
    color: #E2E8F0;
}
QFrame#leftToolsPanel QLabel {
    color: #F3F4F6;
}
QFrame#rightRail QLabel {
    color: #E5E7EB;
}
QFrame#rightRail {
    background-color: #1C1F26;
    border-left: 1px solid #2A2E39;
}
QPushButton#railIconBtn {
    background-color: #242832;
    color: #D1D5DB;
    border: 1px solid #323846;
    border-radius: 6px;
    padding: 6px 4px;
    font-size: 11px;
    font-weight: 600;
}
QPushButton#railIconBtn:hover {
    background-color: #2E3442;
    border-color: #4B5568;
}
QPushButton#railIconBtn:checked {
    background-color: #2563EB;
    color: #FFFFFF;
    border-color: #3B82F6;
}
QFrame#welcomeCard {
    background-color: #1E222B;
    border: 1px solid #2E3442;
    border-radius: 12px;
    padding: 18px;
}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {
    background-color: #121419;
    color: #F3F4F6;
    border: 1px solid #323744;
    border-radius: 6px;
    padding: 5px 8px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-color: #3B82F6;
}
QTabWidget::pane {
    border: 1px solid #2A2E39;
    background-color: #181A20;
}
QTabBar::tab {
    background-color: #1C1F26;
    color: #9CA3AF;
    border: 1px solid #2A2E39;
    border-bottom: none;
    padding: 7px 14px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    background-color: #262B36;
    color: #FFFFFF;
    font-weight: 600;
    border-bottom: 2px solid #3B82F6;
}
QListWidget, QTreeWidget {
    background-color: #14161B;
    color: #E6E8EC;
    border: 1px solid #2A2E39;
    border-radius: 5px;
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
    background-color: #1C1F26;
    color: #9CA3AF;
    border-top: 1px solid #2A2E39;
}
"""


_LIGHT_QSS = """
QMainWindow, QDialog, QWidget {
    background-color: #F1F5F9;
    color: #0F172A;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}
QLabel, QCheckBox {
    background-color: transparent;
    color: #0F172A;
}
QMenuBar {
    background-color: #FFFFFF;
    color: #0F172A;
    border-bottom: 1px solid #E2E8F0;
    padding: 2px 6px;
}
QMenuBar::item:selected {
    background-color: #E2E8F0;
    border-radius: 4px;
}
QMenu {
    background-color: #FFFFFF;
    color: #0F172A;
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
    padding: 6px 10px;
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
QPushButton#modePillBtn {
    background-color: transparent;
    color: #475569;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 5px 12px;
    font-weight: 600;
}
QPushButton#modePillBtn:hover {
    background-color: #F1F5F9;
    color: #0F172A;
}
QPushButton#modePillBtn:checked {
    background-color: #2563EB;
    color: #FFFFFF;
    border-color: #1D4ED8;
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
QPushButton#themeToggleBtn {
    background-color: #F8FAFC;
    color: #0F172A;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 5px 12px;
    font-weight: 600;
}
QPushButton#themeToggleBtn:hover {
    background-color: #E2E8F0;
    border-color: #2563EB;
}
QFrame#leftToolsPanel {
    background-color: #FFFFFF;
    border-right: 1px solid #E2E8F0;
}
QPushButton#toolCardBtn {
    background-color: #F8FAFC;
    color: #1E293B;
    border: 1px solid #E2E8F0;
    border-radius: 7px;
    padding: 8px 10px;
    text-align: left;
    font-weight: 500;
}
QPushButton#toolCardBtn:hover {
    background-color: #EFF6FF;
    border-color: #3B82F6;
}
QPushButton#toolCardPrimaryBtn {
    background-color: #EFF6FF;
    color: #1D4ED8;
    border: 1px solid #93C5FD;
    border-radius: 7px;
    padding: 9px 10px;
    text-align: left;
    font-weight: 600;
}
QPushButton#toolCardPrimaryBtn:hover {
    background-color: #DBEAFE;
    border-color: #2563EB;
}
QFrame#signatureBanner {
    background-color: #EFF6FF;
    border-bottom: 1px solid #BFDBFE;
    padding: 4px 10px;
}
QFrame#rightRail {
    background-color: #FFFFFF;
    border-left: 1px solid #E2E8F0;
}
QPushButton#railIconBtn {
    background-color: #F8FAFC;
    color: #334155;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    padding: 6px 4px;
    font-size: 11px;
    font-weight: 600;
}
QPushButton#railIconBtn:hover {
    background-color: #F1F5F9;
    border-color: #94A3B8;
}
QPushButton#railIconBtn:checked {
    background-color: #2563EB;
    color: #FFFFFF;
    border-color: #1D4ED8;
}
QFrame#welcomeCard {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 18px;
}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {
    background-color: #FFFFFF;
    color: #0F172A;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
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
    border-radius: 5px;
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
