# -*- coding: utf-8 -*-
"""U Draw - 主题令牌（取自原版 PhotoCraft "Pro (Dark)" 调色板）"""

from PySide6.QtGui import QColor, QPalette, QFont


class C:
    """原版 theme.rs -> Tokens::for_kind(Pro) 的 RGB 值"""

    CHROME = "#323232"        # 50,50,50   窗口框架 / 工具栏
    CANVAS = "#282828"        # 40,40,40   画布外围
    DOCK = "#1E1E1E"          # 30,30,30   面板底
    CARD = "#323232"          # 50,50,50   卡片 / 面板
    CARD_BORDER = "#1E1E1E"   # 30,30,30
    FIELD = "#242424"         # 36,36,36   输入框
    FIELD_BORDER = "#4A4A4A"  # 74,74,74
    HOVER = "#424242"         # 66,66,66
    PRESSED = "#4E4E4E"       # 78,78,78
    TEXT = "#DEDEDE"          # 222
    TEXT_DIM = "#B2B2B2"      # 178
    TEXT_FAINT = "#808080"    # 128
    ICON = "#C8C8C8"          # 200
    ACCENT = "#378EF0"        # 55,142,240
    ACCENT_SOFT = "#4E4E4E"
    SEPARATOR = "#1E1E1E"
    TAB_STRIP = "#262626"     # 38,38,38
    ROW_SELECTED = "#525252"  # 82,82,82
    DANGER = "#EC5B62"
    SHADOW = "#141414"

    RADIUS = 4
    RADIUS_SM = 3


def qcolor(name_or_hex, alpha=255):
    if isinstance(name_or_hex, QColor):
        c = QColor(name_or_hex)
    else:
        c = QColor(name_or_hex)
    if alpha != 255:
        c.setAlpha(alpha)
    return c


def hex_str(c: QColor) -> str:
    return "#%02X%02X%02X" % (c.red(), c.green(), c.blue())


STYLESHEET = f"""
* {{
    font-family: "Microsoft YaHei UI", "Segoe UI", "PingFang SC", sans-serif;
    font-size: 12px;
    outline: none;
}}
QWidget {{
    color: {C.TEXT};
}}
QMainWindow, QDialog {{ background: {C.DOCK}; }}

QMenuBar {{
    background: {C.CHROME};
    color: {C.TEXT};
    padding: 1px 4px;
    border-bottom: 1px solid {C.SEPARATOR};
}}
QMenuBar::item {{ background: transparent; padding: 3px 9px; border-radius: 3px; }}
QMenuBar::item:selected {{ background: {C.HOVER}; }}
QMenuBar::item:pressed {{ background: {C.PRESSED}; }}

QMenu {{
    background: {C.CARD};
    border: 1px solid #101010;
    padding: 4px;
    color: {C.TEXT};
}}
QMenu::item {{ padding: 5px 26px 5px 22px; border-radius: 3px; }}
QMenu::item:selected {{ background: {C.ACCENT}; color: #FFFFFF; }}
QMenu::item:disabled {{ color: {C.TEXT_FAINT}; }}
QMenu::separator {{ height: 1px; background: #3C3C3C; margin: 4px 8px; }}
QMenu::indicator {{ width: 12px; height: 12px; margin-left: 5px; }}

QToolTip {{
    background: #101010;
    color: {C.TEXT};
    border: 1px solid #3C3C3C;
    padding: 4px 6px;
}}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {C.FIELD};
    border: 1px solid {C.FIELD_BORDER};
    border-radius: {C.RADIUS_SM}px;
    color: {C.TEXT};
    padding: 2px 5px;
    selection-background-color: {C.ACCENT};
    selection-color: #FFFFFF;
    min-height: 18px;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {C.ACCENT};
}}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    width: 12px; background: transparent; border: none;
}}
QComboBox::drop-down {{ border: none; width: 16px; }}
QComboBox QAbstractItemView {{
    background: {C.CARD};
    border: 1px solid #101010;
    color: {C.TEXT};
    selection-background-color: {C.ACCENT};
    outline: none;
}}

QPushButton {{
    background: {C.FIELD};
    border: 1px solid {C.FIELD_BORDER};
    border-radius: {C.RADIUS_SM}px;
    color: {C.TEXT};
    padding: 4px 10px;
    min-height: 16px;
}}
QPushButton:hover {{ background: {C.HOVER}; }}
QPushButton:pressed {{ background: {C.PRESSED}; }}
QPushButton:disabled {{ color: {C.TEXT_FAINT}; border-color: #3A3A3A; }}
QPushButton#primary {{
    background: {C.ACCENT}; color: #FFFFFF; border: 1px solid #2B7BD8;
}}
QPushButton#primary:hover {{ background: #4A9DF5; }}

QCheckBox {{ spacing: 6px; color: {C.TEXT_DIM}; }}
QCheckBox::indicator {{
    width: 13px; height: 13px;
    border: 1px solid {C.FIELD_BORDER};
    background: {C.FIELD};
    border-radius: 2px;
}}
QCheckBox::indicator:checked {{
    background: {C.ACCENT};
    border-color: {C.ACCENT};
}}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: #555555; border-radius: 5px; min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: #6E6E6E; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{
    background: #555555; border-radius: 5px; min-width: 24px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QScrollArea {{ border: none; background: transparent; }}

QStatusBar {{
    background: {C.CHROME};
    border-top: 1px solid {C.SEPARATOR};
    color: {C.TEXT_DIM};
}}
QStatusBar::item {{ border: none; }}

QSplitter::handle {{ background: {C.SEPARATOR}; }}
QSplitter::handle:horizontal {{ width: 2px; }}

QLabel#panelTitle {{
    color: {C.TEXT_DIM};
    font-size: 11px;
    letter-spacing: 0.6px;
}}
QLabel#hint {{ color: {C.TEXT_FAINT}; font-size: 11px; }}
"""


def apply_theme(app):
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(C.DOCK))
    pal.setColor(QPalette.WindowText, QColor(C.TEXT))
    pal.setColor(QPalette.Base, QColor(C.FIELD))
    pal.setColor(QPalette.AlternateBase, QColor(C.CARD))
    pal.setColor(QPalette.Text, QColor(C.TEXT))
    pal.setColor(QPalette.Button, QColor(C.CARD))
    pal.setColor(QPalette.ButtonText, QColor(C.TEXT))
    pal.setColor(QPalette.Highlight, QColor(C.ACCENT))
    pal.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ToolTipBase, QColor("#101010"))
    pal.setColor(QPalette.ToolTipText, QColor(C.TEXT))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(C.TEXT_FAINT))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(C.TEXT_FAINT))
    app.setPalette(pal)
    f = QFont("Microsoft YaHei UI", 9)
    f.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(f)
    app.setStyleSheet(STYLESHEET)
