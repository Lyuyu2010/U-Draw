# -*- coding: utf-8 -*-
"""U Draw - 统一的确认 / 提示对话框（中文按钮，跟主界面同一套深色皮肤）。

原来用的是 QMessageBox，按钮文字来自 Qt 自带翻译，没装翻译包时就是
Save / Discard / Cancel / Yes / No / OK —— 中文界面里弹出英文按钮很出戏。
这里自绘一套：按钮文字自己写，配色跟「关于 / 赞助」两个对话框保持一致。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from theme import C

# kind → (符号, 底色)
_KINDS = {
    "question": ("?", C.ACCENT),
    "warning": ("!", "#D9A038"),
    "info": ("i", C.ACCENT),
}


class _Badge(QLabel):
    """左边那颗圆形符号，替代 QMessageBox 的系统图标。"""

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        sym, color = _KINDS.get(kind, _KINDS["info"])
        self.setText(sym)
        self.setFixedSize(32, 32)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            f"background: {color}; color: #FFFFFF; border-radius: 16px;"
            "font-size: 17px; font-weight: 600;")


class MessageDialog(QDialog):
    """固定宽度、高度随内容；按钮文字与返回的 key 由调用方指定。"""

    def __init__(self, parent, title: str, text: str, buttons, default=None,
                 kind: str = "question", rich: bool = False, width: int = 430,
                 scroll: bool = False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setStyleSheet(f"QDialog {{ background: {C.DOCK}; }}")
        self.setFixedWidth(width)
        self.result_key = None
        self._cancel_key = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(16)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(14)
        body.addWidget(_Badge(kind), 0, Qt.AlignTop)

        lab = QLabel(text)
        lab.setWordWrap(True)
        lab.setTextFormat(Qt.RichText if rich else Qt.PlainText)
        lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lab.setStyleSheet(
            f"color: {C.TEXT}; font-size: 13px; line-height: 165%;"
            f"background: transparent;")

        if scroll:
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setFrameShape(QScrollArea.NoFrame)
            area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
            host = QWidget()
            host.setStyleSheet("background: transparent;")
            hl = QVBoxLayout(host)
            hl.setContentsMargins(0, 0, 6, 0)
            hl.addWidget(lab)
            hl.addStretch(1)
            area.setWidget(host)
            scr = QApplication.primaryScreen()
            avail = scr.availableGeometry().height() if scr is not None else 720
            # 高度取「换行后的真实内容高度」，再夹在 140~上限之间：
            # 内容短时不留一大片空，内容长时出滚动条而不是把窗口撑出屏幕。
            inner_w = width - 24 * 2 - 32 - 14 - 14
            need = lab.heightForWidth(inner_w)
            limit = max(220, min(430, int(avail * 0.55)))
            area.setFixedHeight(max(140, min(limit, (need if need > 0 else limit) + 4)))
            body.addWidget(area, 1)
        else:
            body.addWidget(lab, 1)
        lay.addLayout(body)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addStretch(1)
        made = []
        for key, label, role in buttons:
            b = QPushButton(label)
            b.setFixedHeight(28)
            b.setMinimumWidth(78)
            b.setCursor(Qt.PointingHandCursor)
            if role == "primary":
                b.setObjectName("primary")
            elif role == "danger":
                b.setStyleSheet(
                    f"QPushButton {{ background: {C.DANGER}; color: #FFFFFF;"
                    "border: 1px solid #C74A50; border-radius: 3px; padding: 0 12px; }"
                    "QPushButton:hover { background: #F06B72; }")
            else:
                b.setStyleSheet(
                    f"QPushButton {{ background: {C.FIELD}; color: {C.TEXT};"
                    f"border: 1px solid {C.FIELD_BORDER}; border-radius: 3px;"
                    "padding: 0 12px; }"
                    f"QPushButton:hover {{ background: {C.HOVER}; }}")
            if key in ("cancel", "close"):
                self._cancel_key = key
            b.clicked.connect(lambda _=False, k=key: self._done(k))
            row.addWidget(b)
            made.append((key, b))
        lay.addLayout(row)

        # 回车 = 默认按钮（一般是「保存 / 取消 / 关闭」里最安全的那个）。
        # 注意别用按钮在 layout 里的下标：前面有个 addStretch，下标会错一位。
        target = default or (buttons[0][0] if buttons else None)
        for key, b in made:
            if key == target:
                b.setDefault(True)
                b.setFocus()
                break

        self._fit_height(lay)

    def _fit_height(self, lay: QVBoxLayout):
        lay.activate()
        h = lay.totalHeightForWidth(self.width())
        if h > 0:
            self.setFixedHeight(h)

    def _done(self, key: str):
        self.result_key = key
        self.accept()

    def reject(self):
        # Esc / 关窗 = 取消，不能让调用方以为「确认了」
        if self.result_key is None and self._cancel_key is not None:
            self.result_key = self._cancel_key
        super().reject()


def ask(parent, title: str, text: str, buttons, default=None,
        kind: str = "question", rich: bool = False, scroll: bool = False,
        width: int = 430):
    """弹一个模态对话框，返回被点按钮的 key；直接关窗返回 None。

    buttons: [(key, 文字, 角色)]，角色取 "primary" / "danger" / 其它（普通）。
    """
    dlg = MessageDialog(parent, title, text, buttons, default=default, kind=kind,
                        rich=rich, scroll=scroll, width=width)
    dlg.exec()
    return dlg.result_key


def tell(parent, title: str, text: str, ok: str = "知道了",
         kind: str = "info", rich: bool = False, scroll: bool = False,
         width: int = 430):
    """只有「知道了 / 关闭」一个按钮的提示框。"""
    ask(parent, title, text, [("close", ok, "primary")], default="close",
         kind=kind, rich=rich, scroll=scroll, width=width)


def get_text(parent, title: str, label: str, text: str = "", ok: str = "确定"):
    """单行输入框（QInputDialog 的按钮默认是 OK / Cancel，这里换成中文）。"""
    from PySide6.QtWidgets import QInputDialog
    dlg = QInputDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setLabelText(label)
    dlg.setTextValue(text)
    dlg.setOkButtonText(ok)
    dlg.setCancelButtonText("取消")
    dlg.setFixedWidth(380)
    ok_pressed = dlg.exec() == QInputDialog.Accepted
    return dlg.textValue(), ok_pressed
