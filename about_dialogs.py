# -*- coding: utf-8 -*-
"""U Draw - 「关于」与「赞助」两个对话框。

单独放一个文件：主窗口已经足够长，这两块是自成一体的内容 + 排版，
改文案不该牵动交互逻辑。

两个对话框都用固定宽度 + 自动高度，跟随系统 DPI；收款码用 base64 内嵌
（sponsor_data.py），单文件 exe 换机器也不会找不到资源。
"""

import base64

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QApplication, QDialog, QFrame, QHBoxLayout,
                               QLabel, QPushButton, QToolButton, QVBoxLayout,
                               QWidget)

import icons
from theme import C

# 文案里反复出现的数字放一处，改版本号只改 main_window.APP_VERSION
CREATOR = "宇"
DOUYIN = "43770493238"
BILIBILI = "3546815037180153"


def _icon_pixmap(size: int):
    """顶部那颗 App 图标；资源缺失时返回 None，对话框照常显示。"""
    try:
        from appicon_data import ICON_PNG_B64
        pm = QPixmap()
        if pm.loadFromData(base64.b64decode(ICON_PNG_B64), "PNG"):
            return pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    except Exception:
        pass
    return None


class _Row(QWidget):
    """创作者信息的一行：字段名 + 值 + 复制按钮。"""

    def __init__(self, name: str, value: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        k = QLabel(name)
        k.setFixedWidth(64)
        k.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 12px;")
        v = QLabel(value)
        v.setStyleSheet(f"color: {C.TEXT}; font-size: 12px;")
        v.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.hint = QLabel("")
        self.hint.setStyleSheet(f"color: {C.ACCENT}; font-size: 11px;")
        self.hint.setFixedWidth(42)

        btn = QToolButton()
        btn.setIcon(icons.icon("copy", C.TEXT_DIM, 13))
        btn.setIconSize(QSize(13, 13))
        btn.setFixedSize(20, 20)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(f"复制：{value}")
        btn.setStyleSheet(
            "QToolButton { border: none; background: transparent; border-radius: 3px; }"
            f"QToolButton:hover {{ background: {C.HOVER}; }}")
        btn.clicked.connect(lambda: self._copy(value))

        lay.addWidget(k)
        lay.addWidget(v)
        lay.addWidget(self.hint)
        lay.addStretch(1)
        lay.addWidget(btn)

    def _copy(self, value: str):
        QApplication.clipboard().setText(value)
        self.hint.setText("已复制")
        QTimer.singleShot(1400, lambda: self.hint.setText(""))


class _Bullet(QWidget):
    """圆点 + 自动换行的说明文字。用控件而不是 HTML 列表，
    换行时第二行才能跟第一行对齐（QLabel 的 li 缩进在 Qt 里不可靠）。"""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        dot = QLabel("·")
        dot.setFixedSize(6, 17)
        dot.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        dot.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 12px;")
        lab = QLabel(text)
        lab.setWordWrap(True)
        lab.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 12px; line-height: 150%;")
        lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(dot, 0, Qt.AlignTop)
        lay.addWidget(lab, 1)


def _para(text: str, color: str = None, size: int = 12, bold: bool = False) -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setStyleSheet(
        f"color: {color or C.TEXT_DIM}; font-size: {size}px;"
        f"line-height: 158%; font-weight: {'600' if bold else '400'};")
    lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lab


def _section(title: str) -> QLabel:
    lab = QLabel(title)
    lab.setStyleSheet(
        f"color: {C.TEXT_FAINT}; font-size: 11px; letter-spacing: 1.2px;"
        "padding-top: 2px;")
    return lab


def _divider() -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {C.SEPARATOR}; border: none;")
    return line


def _dialog_shell(dlg: QDialog, title: str, width: int):
    """固定宽度、高度随内容的模态窗。

    宽度写死是有意的：文案是按这个宽度断行排的，跟着内容自适应会在
    不同字号下变成「一行两三个字」的窄条。
    """
    dlg.setWindowTitle(title)
    dlg.setModal(True)
    dlg.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
    dlg.setStyleSheet(f"QDialog {{ background: {C.DOCK}; }}")
    dlg.setFixedWidth(width)


def _fit_height(dlg: QDialog, lay: QVBoxLayout):
    """按「换行后的真实高度」定高。

    自动换行的 QLabel 给外层的 sizeHint 是按一个默认宽度估的，会多留出半行
    到一行的空白（段落后出现莫名其妙的大间距）。heightForWidth 才是准的。
    """
    lay.activate()
    h = lay.totalHeightForWidth(dlg.width())
    if h > 0:
        dlg.setFixedHeight(h)


def _head(dlg: QDialog, lay: QVBoxLayout, title: str, sub: str):
    row = QHBoxLayout()
    row.setSpacing(12)
    pm = _icon_pixmap(40)
    if pm is not None:
        ico = QLabel()
        ico.setPixmap(pm)
        ico.setFixedSize(40, 40)
        row.addWidget(ico, 0, Qt.AlignTop)
    col = QVBoxLayout()
    col.setSpacing(2)
    t = QLabel(title)
    t.setStyleSheet(f"color: {C.TEXT}; font-size: 17px; font-weight: 600;")
    s = QLabel(sub)
    s.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 11px;")
    col.addWidget(t)
    col.addWidget(s)
    row.addLayout(col, 1)
    lay.addLayout(row)


def _brush_counts():
    """统计内置笔刷数量与分类数（笔刷库变了文案自动跟着变）。"""
    try:
        import brushes
        n = len(brushes.DEFAULTS)
        g = len({b.group for b in brushes.DEFAULTS})
        if n > 0:
            return n, g
    except Exception:
        pass
    return 133, 17


class AboutDialog(QDialog):
    def __init__(self, app_name: str, version: str, parent=None):
        super().__init__(parent)
        _dialog_shell(self, f"关于 {app_name}", 520)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 14)
        lay.setSpacing(9)

        _head(self, lay, app_name, f"版本 {version}　·　Windows 平台轻量级数字绘画软件")

        lay.addWidget(_para(
            "面向手绘创作的桌面绘画软件。界面结构参照 Photoshop 的工具栏、选项栏与"
            "面板布局，聚焦笔刷、图层、选区三类核心流程，不含修图、调色、滤镜等模块。"))

        lay.addWidget(_section("核心能力"))
        # 数量直接从笔刷库统计，避免文案和实际笔刷数对不上（以前写死 102，实际 133）
        n_brush, n_group = _brush_counts()
        feats = [
            f"笔刷：内置 {n_brush} 支，分 {n_group} 类（铅笔 / 勾线 / 炭笔粉笔 / 马克笔 / "
            "水彩 / 油画 / 蜡笔色粉 / 喷枪 / 纹理 / 网点 / 特效 / 印章形状 / 植被花卉 / "
            "图案装饰 / 毛发织物 / 光效天气 等）；23 种笔尖形态，22 项参数分六组可调",
            "压感：笔迹粗细与浓度随压力变化，可设「最小直径」限定最细程度",
            "绘制辅助：对称绘制（垂直 / 水平 / 四象限 / 径向 2–24 轴）、涂抹混色、"
            "画布内文字编辑",
            "图层：最多 200 层，支持分组、显示隐藏、锁定、不透明度、拖动排序、合并与复制",
            "选区与变换：矩形 / 椭圆 / 套索选区，加选、减选、反选，配合自由变换做局部调整",
        ]
        blist = QVBoxLayout()
        blist.setContentsMargins(0, 2, 0, 2)
        blist.setSpacing(8)
        for f in feats:
            blist.addWidget(_Bullet(f))
        lay.addLayout(blist)

        lay.addWidget(_section("文件与运行环境"))
        env = [
            "导入位图作描摹参考；导出 PNG / JPEG；工程文件 .pcdraw 完整保留图层与笔刷状态",
            "Windows 10 / 11（64 位），单文件分发，无需额外运行库"
            "（Python 3.13 + Qt 6 / PySide6）",
        ]
        elist = QVBoxLayout()
        elist.setContentsMargins(0, 2, 0, 2)
        elist.setSpacing(8)
        for f in env:
            elist.addWidget(_Bullet(f))
        lay.addLayout(elist)

        lay.addWidget(_divider())
        lay.addWidget(_section("作者"))
        card = QFrame()
        card.setObjectName("creatorCard")
        card.setStyleSheet(
            "QFrame#creatorCard { background: #262626; border: 1px solid #3A3A3A;"
            " border-radius: 6px; }")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 10, 12, 10)
        cl.setSpacing(6)
        cl.addWidget(_Row("作者", CREATOR))
        cl.addWidget(_Row("抖音", DOUYIN))
        cl.addWidget(_Row("哔哩哔哩", BILIBILI))
        lay.addWidget(card)

        # 原软件声明：本软件是衍生作品，按 MIT / Apache-2.0 的要求把出处写在明面上
        lay.addWidget(_section("开源声明"))
        lay.addWidget(_para(
            "衍生于 <b>PhotoCraft 0.12.0</b>（ArtCraft 开源发布的 Photoshop 复刻，"
            "MIT / Apache-2.0 双许可，getartcraft.com/apps/photocraft）。界面结构与 "
            "Pro (Dark) 配色沿用原项目，绘制内核以 Python + Qt 重新实现；"
            "原项目名称与商标归 ArtCraft 所有，与本软件无隶属关系。",
            color=C.TEXT_FAINT, size=11))

        bottom = QHBoxLayout()
        cr = QLabel(f"© 2026 {CREATOR}　保留所有权利")
        cr.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 11px;")
        bottom.addWidget(cr)
        bottom.addStretch(1)
        ok = QPushButton("关闭")
        ok.setObjectName("primary")
        ok.setFixedWidth(84)
        ok.clicked.connect(self.accept)
        bottom.addWidget(ok)
        lay.addSpacing(2)
        lay.addLayout(bottom)
        _fit_height(self, lay)
        ok.setDefault(True)
        ok.setFocus()


class SponsorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        _dialog_shell(self, "支持 U Draw", 520)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 18)
        lay.setSpacing(14)

        _head(self, lay, "支持 U Draw", "免费 · 无广告 · 无内购，所有功能完整可用")
        lay.addWidget(_para(
            "U Draw 是个人项目，由我一个人开发与维护。它没有商业化，"
            "也不打算加入任何付费功能。"))
        lay.addWidget(_para(
            "如果它确实帮到了你的创作，欢迎扫码请我喝一杯咖啡。金额随意，"
            "心意更重要。"))

        codes = QHBoxLayout()
        codes.setSpacing(18)
        codes.addStretch(1)
        for key, label, accent in (("wechat", "微信支付", "#07C160"),
                                   ("alipay", "支付宝", "#1677FF")):
            codes.addWidget(self._qr_card(key, label, accent))
        codes.addStretch(1)
        lay.addLayout(codes)

        lay.addWidget(_divider())
        thanks = _para(
            "您的每一份赞助，我都会用于软件的维护与开发。",
            color=C.TEXT, size=13, bold=True)
        thanks.setAlignment(Qt.AlignHCenter)
        lay.addWidget(thanks)
        gentle = _para("赞助完全自愿，不影响任何功能与后续更新。感谢每一位使用 U Draw 的人。",
                       color=C.TEXT_FAINT, size=11)
        gentle.setAlignment(Qt.AlignHCenter)
        lay.addWidget(gentle)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        ok = QPushButton("关闭")
        ok.setObjectName("primary")
        ok.setFixedWidth(84)
        ok.clicked.connect(self.accept)
        bottom.addWidget(ok)
        lay.addLayout(bottom)
        _fit_height(self, lay)
        ok.setDefault(True)

    def _qr_card(self, key: str, label: str, accent: str) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        pm = self._load_qr(key, 216)
        pic = QLabel()
        pic.setAlignment(Qt.AlignCenter)
        # 两张卡写死同一个尺寸：源图留白略有差别，不锁死会出现一高一矮
        pic.setFixedSize(216, 251)
        if pm is not None:
            pic.setPixmap(pm)
            pic.setToolTip(f"扫码赞助（{label}）")
        else:
            pic.setText("收款码缺失")
            pic.setStyleSheet(f"color: {C.DANGER}; font-size: 11px;")
        v.addWidget(pic, 0, Qt.AlignHCenter)

        row = QHBoxLayout()
        row.setSpacing(6)
        row.addStretch(1)
        dot = QLabel()
        dot.setFixedSize(7, 7)
        dot.setStyleSheet(f"background: {accent}; border-radius: 3px;")
        name = QLabel(label)
        name.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 12px;")
        row.addWidget(dot, 0, Qt.AlignVCenter)
        row.addWidget(name)
        row.addStretch(1)
        v.addLayout(row)
        return w

    @staticmethod
    def _load_qr(key: str, width: int):
        try:
            import sponsor_data
            raw = (sponsor_data.QR_WECHAT_PNG_B64 if key == "wechat"
                   else sponsor_data.QR_ALIPAY_PNG_B64)
            pm = QPixmap()
            if not pm.loadFromData(base64.b64decode(raw), "PNG"):
                return None
        except Exception:
            return None
        # 按目标逻辑像素设置 DPR：高分屏上按原生分辨率绘制，不糊。
        # DPR 取「源图宽度 / 目标宽度」与 3 的较小值，避免把图放大。
        dpr = min(3.0, pm.width() / float(width))
        scaled = pm.scaledToWidth(int(round(width * dpr)), Qt.SmoothTransformation)
        scaled.setDevicePixelRatio(dpr)
        return scaled
