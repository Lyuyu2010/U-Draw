# -*- coding: utf-8 -*-
"""U Draw - 主窗口（布局沿用 PhotoCraft / Photoshop 习惯：顶部菜单+选项栏，
左侧工具栏，右侧颜色/笔刷/图层面板，中间画布）"""

import json
import os
import sys

try:
    import ctypes
except Exception:            # 非 Windows 环境没有，功能自动降级
    ctypes = None

from PySide6.QtCore import (QPoint, QPointF, QRect, QRectF, QSettings, QSize, Qt,
                            QTimer, Signal)
from PySide6.QtGui import (QAction, QColor, QCursor, QFont,
                           QGuiApplication,
                           QIcon, QKeySequence, QPainter, QPen, QPixmap, QPolygonF)
from PySide6.QtWidgets import (QApplication, QColorDialog, QComboBox,
                               QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMenu,
                               QPlainTextEdit, QPushButton,
                               QSpinBox, QSplitter, QStatusBar,
                               QTextEdit, QToolButton, QVBoxLayout,
                               QWidget)

import dialogs
import fonts as fontlib
import icons
import psd_export
from about_dialogs import AboutDialog, SponsorDialog
from canvas import Canvas, load_image_file
from core import (MAX_LAYERS, SPRAY_KINDS, STAMP_KINDS, SYM_MODES, SYM_NAMES,
                  Brush, Document, StructEdit, export_image, load_project,
                  open_image_as_document, save_project)
from panels import (BrushPanel, ColorPanel, LayersPanel, PresetBar, RecentStore,
                    RecentSwatches, SymmetryPanel)
from tab_strip import DocStrip  # noqa: F401  （测试与外部脚本按 main_window.DocStrip 取）
from theme import C

# 内部剪贴板：带「从哪张画布、哪个位置复制的」，所以能贴回原位。
# 放在模块级 —— 独立窗口之间共享，拖出来的窗口也能互相粘贴。
PASTE_BUF = {"image": None, "pos": None, "size": None, "title": ""}


if ctypes is not None:
    class _WinMSG(ctypes.Structure):
        """Windows 的 MSG 结构（只用 message 字段，用来抓 WM_EXITSIZEMOVE）。"""
        _fields_ = [("hwnd", ctypes.c_void_p), ("message", ctypes.c_uint),
                    ("wParam", ctypes.c_void_p), ("lParam", ctypes.c_void_p),
                    ("time", ctypes.c_uint), ("pt_x", ctypes.c_long),
                    ("pt_y", ctypes.c_long)]
else:                        # 非 Windows：占位，标题栏停靠功能自动关闭
    class _WinMSG:
        pass

APP_NAME = "U Draw"
DEFAULT_W, DEFAULT_H = 1920, 1080
# 必须和 app/version_info.txt 里的 FileVersion 保持一致（标题栏 / 关于窗口都读这里）
APP_VERSION = "2.15.42"

# (组键, 名称, 快捷键, 图标, 子工具列表)  —— 选区三个工具合并成一个按钮
TOOL_GROUPS = [
    ("move", "移动图层", "V", "move", None),
    ("brush", "画笔", "B", "brush", None),
    ("eraser", "橡皮擦", "E", "eraser", None),
    ("smudge", "涂抹", "S", "smudge", None),
    ("bucket", "油漆桶", "G", "bucket", None),
    ("eyedropper", "吸管", "I", "eyedropper", None),
    ("select", "选区", "M", "marquee",
     [("marquee", "矩形选框", "M"), ("ellipse", "椭圆选框", "Shift+M"),
      ("lasso", "套索", "L")]),
    ("shape", "形状", "U", "rect",
     [("rect", "矩形", "U"), ("ellipse_shape", "椭圆", "Shift+U"),
      ("line", "直线", "Shift+U")]),
    ("text", "文字", "T", "text", None),
    ("hand", "抓手（移动画布）", "H", "hand", None),
]
SELECT_TOOLS = ["marquee", "ellipse", "lasso"]
SELECT_NAMES = {"marquee": "矩形", "ellipse": "椭圆", "lasso": "套索"}
SHAPE_TOOLS = ["rect", "ellipse_shape", "line"]
SHAPE_NAMES = {"rect": "矩形", "ellipse_shape": "椭圆", "line": "直线"}
SHAPE_ICONS = {"rect": "rect", "ellipse_shape": "ellipse", "line": "line"}
TOOL_NAMES = {}
for _g in TOOL_GROUPS:
    if _g[4]:
        for _sub in _g[4]:
            TOOL_NAMES[_sub[0]] = _sub[1]
    else:
        TOOL_NAMES[_g[0]] = _g[1]


class PressureBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(52, 6)
        self.value = 0.0

    def set_value(self, v):
        self.value = max(0.0, min(1.0, v))
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#1A1A1A"))
        p.drawRoundedRect(self.rect(), 2, 2)
        w = int(self.width() * self.value)
        if w > 0:
            p.setBrush(QColor(C.ACCENT))
            p.drawRoundedRect(QRect(0, 0, max(2, w), self.height()), 2, 2)
        p.end()


class GroupButton(QToolButton):
    """工具组按钮：普通点击切工具，按住 0.4s 或点右下角小三角弹出子工具。"""

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.menu() is None:
            return
        # 右下角小三角：表示这一格是可展开的工具组，画在按钮角上（不占图标位置）
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#FFFFFF" if self.isChecked() else C.TEXT_DIM))
        w, h = self.width(), self.height()
        k = 5.2
        p.drawPolygon(QPolygonF([QPointF(w - 4.0 - k, h - 4.0),
                                 QPointF(w - 4.0, h - 4.0 - k),
                                 QPointF(w - 4.0, h - 4.0)]))
        p.end()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            gp = e.position()
            r = self.rect()
            if (r.width() - gp.x()) < 10 and (r.height() - gp.y()) < 10 and self.menu():
                self.showMenu()
                return
        super().mouseReleaseEvent(e)


class ToolRail(QWidget):
    toolChanged = Signal(str)
    colorsSwapped = Signal()
    zoomStep = Signal(bool)         # True = 放大

    def __init__(self, parent=None):
        super().__init__(parent)
        # 宽度可拖（42~78）：用大屏 / 触屏的人可以把工具栏拉宽一点
        self.setMinimumWidth(42)
        self.setMaximumWidth(78)
        self.setStyleSheet(f"background: {C.CHROME}; border-right: 1px solid {C.SEPARATOR};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 8, 4, 8)
        lay.setSpacing(4)
        self.buttons = {}
        self.current = None
        self.current_tool = "brush"
        self.group_tool = {"select": "marquee", "shape": "rect"}
        for gkey, name, sc, ic, subs in TOOL_GROUPS:
            b = GroupButton() if subs else QToolButton()
            b.setFixedSize(34, 34)
            b.setIconSize(QSize(21, 21))
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                "QToolButton { border: none; background: transparent; border-radius: 6px; }"
                f"QToolButton:hover {{ background: {C.HOVER}; }}"
                f"QToolButton:checked {{ background: {C.ACCENT}; }}"
                "QToolButton::menu-indicator { image: none; width: 0px; }")
            if subs:
                menu = QMenu(b)
                menu.setStyleSheet("QMenu { font-size: 12px; }")
                for tkey, tname, tsc in subs:
                    act = menu.addAction(icons.icon(tkey, C.ICON, 16), f"{tname}   {tsc}")
                    act.triggered.connect(lambda _=False, k=tkey: self.select(k))
                b.setMenu(menu)
                b.setPopupMode(QToolButton.DelayedPopup)   # 长按 0.4s 弹出子工具
                b.setToolTip(f"{name}  ({sc})\n长按或点右下角小三角切换矩形/椭圆/套索")
            else:
                b.setToolTip(f"{name}  ({sc})")
            b.clicked.connect(lambda _=False, k=gkey: self.select(k))
            lay.addWidget(b, 0, Qt.AlignHCenter)      # 工具栏拖宽后按钮仍然居中
            self.buttons[gkey] = b
            self._refresh_group_icon(gkey)
            if gkey in ("eyedropper", "select"):
                line = QFrame()
                line.setFixedHeight(1)
                line.setStyleSheet(f"background: {C.SEPARATOR}; margin: 2px 3px;")
                lay.addWidget(line, 0, Qt.AlignHCenter)
            b.toggled.connect(lambda on, k=gkey: self._refresh_group_icon(k))
        lay.addStretch(1)

        # 放大 / 缩小：数位板、触摸屏没有滚轮，靠这两个按钮缩放
        for ic, tip, up in (("zoom_in", "放大（Ctrl+= / 滚轮上）", True),
                            ("zoom_out", "缩小（Ctrl+- / 滚轮下）", False)):
            zb = QToolButton()
            zb.setFixedSize(34, 26)
            zb.setIconSize(QSize(16, 16))
            zb.setIcon(icons.icon(ic, C.TEXT_DIM, 16))
            zb.setCursor(Qt.PointingHandCursor)
            zb.setToolTip(tip)
            zb.setStyleSheet(
                "QToolButton { border: none; background: transparent; border-radius: 5px; }"
                f"QToolButton:hover {{ background: {C.HOVER}; }}"
                f"QToolButton:pressed {{ background: {C.PRESSED}; }}")
            zb.clicked.connect(lambda _=False, u=up: self.zoomStep.emit(u))
            lay.addWidget(zb, 0, Qt.AlignHCenter)
            if up:
                self.zoom_in = zb
            else:
                self.zoom_out = zb

        # 前景 / 背景色块
        holder = QWidget()
        holder.setFixedHeight(46)
        hl = QHBoxLayout(holder)
        hl.setContentsMargins(0, 0, 0, 0)
        self.swatch = QToolButton()
        self.swatch.setFixedSize(32, 32)
        self.swatch.setCursor(Qt.PointingHandCursor)
        self.swatch.setToolTip("单击交换前景色 / 背景色（X）")
        self.swatch.clicked.connect(self.colorsSwapped.emit)
        self.swatch.paintEvent = self._paint_swatch
        hl.addWidget(self.swatch)
        lay.addWidget(holder, 0, Qt.AlignHCenter)
        self.fg = QColor(20, 20, 20)
        self.bg = QColor(255, 255, 255)

    def _paint_swatch(self, e):
        p = QPainter(self.swatch)
        p.setRenderHint(QPainter.Antialiasing, True)
        # 背景色（右下、靠后）
        p.setBrush(self.bg)
        p.setPen(QPen(QColor("#909090"), 1))
        p.drawRoundedRect(QRectF(11, 11, 20, 20), 2.5, 2.5)
        # 前景色（左上、靠前）
        p.setBrush(self.fg)
        p.setPen(QPen(QColor("#C0C0C0"), 1.2))
        p.drawRoundedRect(QRectF(1, 1, 20, 20), 2.5, 2.5)
        # 右上角的交换小箭头，提示可点
        pen = QPen(QColor(C.TEXT_FAINT), 1.3)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(22.5, 3.5), QPointF(29.5, 3.5))
        p.drawLine(QPointF(29.5, 3.5), QPointF(27.5, 1.8))
        p.drawLine(QPointF(29.5, 7.5), QPointF(22.5, 7.5))
        p.drawLine(QPointF(22.5, 7.5), QPointF(24.5, 5.8))
        p.end()

    def set_color(self, c: QColor):
        self.fg = QColor(c)
        self.swatch.update()

    def set_bg(self, c: QColor):
        self.bg = QColor(c)
        self.swatch.update()

    def _refresh_group_icon(self, gkey):
        for g, name, sc, ic, subs in TOOL_GROUPS:
            if g != gkey:
                continue
            b = self.buttons.get(gkey)
            if b is None:
                return
            on = b.isChecked()
            col = "#FFFFFF" if on else C.ICON
            size = 21
            if not subs:
                b.setIcon(icons.icon(ic, col, size))
                return
            dpr = 3.0
            px = int(size * dpr)
            pm = QPixmap(px, px)
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setRenderHint(QPainter.SmoothPixmapTransform, True)
            sub_icon = SHAPE_ICONS.get(self.group_tool[gkey], self.group_tool[gkey])
            icons.icon(sub_icon, col, size).paint(p, QRect(0, 0, size, size))
            p.end()
            b.setIcon(QIcon(pm))

    def select(self, key):
        """key 可以是具体工具名（brush / marquee…）或组名（select）。"""
        for gkey, name, sc, ic, subs in TOOL_GROUPS:
            tools = [t[0] for t in subs] if subs else [gkey]
            if key == gkey or key in tools:
                if subs:
                    if key in tools:
                        self.group_tool[gkey] = key
                    tool = self.group_tool[gkey]
                    self._refresh_group_icon(gkey)
                else:
                    tool = gkey
                self.buttons[gkey].setChecked(True)
                self.current = gkey
                self.current_tool = tool
                self.toolChanged.emit(tool)
                return

    def set_tool(self, tool):
        self.select(tool)


class SizeTile(QWidget):
    """新建画布的尺寸预设块：大字写尺寸，小字写用途，一眼能挑。"""

    H = 44

    def __init__(self, title: str, sub: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.sub = sub
        self.selected = False
        self.setFixedHeight(self.H)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumWidth(150)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setBrush(QColor(C.PRESSED if self.selected else C.FIELD))
        p.setPen(QPen(QColor(C.ACCENT if self.selected else C.FIELD_BORDER),
                      1.4 if self.selected else 1.0))
        p.drawRoundedRect(r, 4, 4)
        f = QFont(self.font())
        f.setPointSizeF(9.4)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(C.TEXT))
        p.drawText(QRectF(8, 5, self.width() - 14, 18),
                   Qt.AlignLeft | Qt.AlignVCenter, self.title)
        f2 = QFont(self.font())
        f2.setPointSizeF(8.2)
        p.setFont(f2)
        p.setPen(QColor(C.TEXT_FAINT))
        p.drawText(QRectF(8, 23, self.width() - 14, 14),
                   Qt.AlignLeft | Qt.AlignVCenter, self.sub)
        p.end()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            cb = getattr(self, "clicked", None)
            if cb is not None:
                cb()


class NewDocDialog(QDialog):
    PRESETS = [
        ("1920 × 1080", 1920, 1080, "屏幕 / 全高清"),
        ("1080 × 1080", 1080, 1080, "方形 · 社交"),
        ("1080 × 1920", 1080, 1920, "竖屏 · 手机"),
        ("2048 × 2048", 2048, 2048, "方图大画布"),
        ("2560 × 1440", 2560, 1440, "2K 屏"),
        ("3840 × 2160", 3840, 2160, "4K 屏"),
        ("3508 × 2480", 3508, 2480, "A4 横 · 300dpi"),
        ("2480 × 3508", 2480, 3508, "A4 竖 · 300dpi"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建画布")
        self.setFixedWidth(392)
        self.setStyleSheet(f"QDialog {{ background: {C.DOCK}; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        title = QLabel("新建画布")
        f = QFont(title.font())
        f.setPointSizeF(11)
        f.setBold(True)
        title.setFont(f)
        lay.addWidget(title)

        # 画布名称：会显示在文档标签上，之后「另存为」也用这个名字
        self.name = QLineEdit()
        self.name.setPlaceholderText("画布名称（显示在标签上，可留空）")
        self.name.setFixedHeight(26)
        self.name.setStyleSheet(
            f"QLineEdit {{ background: {C.FIELD}; color: {C.TEXT}; border: 1px solid "
            f"{C.FIELD_BORDER}; border-radius: 4px; padding: 0 8px; font-size: 12px; }}"
            f"QLineEdit:focus {{ border-color: {C.ACCENT}; }}")
        lay.addWidget(self.name)

        pick = QLabel("选一个常用尺寸（也可以直接改下面的宽高）")
        pick.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 10px;")
        lay.addWidget(pick)

        grid = QGridLayout()
        grid.setSpacing(6)
        self.tiles = []
        for i, (name, w, h, sub) in enumerate(self.PRESETS):
            tile = SizeTile(name, sub)
            tile.clicked = (lambda ww=w, hh=h, tt=tile:
                            self._pick_preset(ww, hh, tt))
            self.tiles.append(tile)
            grid.addWidget(tile, i // 2, i % 2)
        lay.addLayout(grid)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setSpacing(8)
        self.w = QSpinBox()
        self.w.setRange(16, 20000)
        self.w.setValue(1920)
        self.w.setSuffix(" px")
        self.h = QSpinBox()
        self.h.setRange(16, 20000)
        self.h.setValue(1080)
        self.h.setSuffix(" px")
        self.w.valueChanged.connect(self._manual)
        self.h.valueChanged.connect(self._manual)
        form.addRow("宽度", self.w)
        form.addRow("高度", self.h)
        self.bg = QComboBox()
        self.bg.addItems(["白色", "透明"])
        form.addRow("背景", self.bg)
        lay.addLayout(form)

        btns = QDialogButtonBox()
        ok = QPushButton("创建")
        ok.setObjectName("primary")
        cancel = QPushButton("取消")
        btns.addButton(ok, QDialogButtonBox.AcceptRole)
        btns.addButton(cancel, QDialogButtonBox.RejectRole)
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        lay.addWidget(btns)

        self._pick_preset(1920, 1080, self.tiles[0], only_select=True)

    def _pick_preset(self, w, h, tile, only_select=False):
        for t in self.tiles:
            t.selected = (t is tile)
            t.update()
        if only_select:
            return
        for box, v in ((self.w, w), (self.h, h)):
            box.blockSignals(True)
            box.setValue(v)
            box.blockSignals(False)

    def _manual(self, *_):
        # 手改了宽高就不算预设了
        for t in self.tiles:
            if t.selected:
                t.selected = False
                t.update()

    def values(self):
        bg = QColor(255, 255, 255, 255) if self.bg.currentIndex() == 0 else QColor(0, 0, 0, 0)
        name = (self.name.text() or "").strip() or "未命名"
        return self.w.value(), self.h.value(), bg, name


class MainWindow(QWidget):
    # 从标签拖出来的独立窗口：不参与「记住窗口大小 / 布局」那套设置
    _secondary = False
    # 最后一个文档被搬走时，关窗口不要弹「还有未保存的修改」
    _force_close = False
    # 标题栏拖动的落点提示（拖到别的窗口标签条上会亮）
    _dock_target = None

    def __init__(self, secondary: bool = False):
        super().__init__()
        self._secondary = bool(secondary)
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1000, 760)
        self.resize(1440, 900)
        self.setStyleSheet(f"background: {C.DOCK};")
        self.doc = self.make_blank_doc(DEFAULT_W, DEFAULT_H, QColor(255, 255, 255, 255))
        self.docs = [self.doc]
        self.doc_index = 0
        self._views = {}          # id(doc) -> (zoom, ox, oy)
        self.brush = Brush()
        self.current_tool = "brush"
        self._syncing_brush_sliders = False
        # 文字颜色 + 它自己的一排「最近使用」（跟颜色面板那份分开存）
        self._text_store = RecentStore("color/recent_text", 8)
        self._text_recent = self._text_store.load()
        self._text_color_saved = QColor(
            self._qsettings().value("text/color", "#141414"))
        self._build_ui()
        self._build_actions()
        self._bind()
        self._restore_window_state()
        self._restore_prefs()
        self._bind_layout_save()
        # 布局恢复完再压一次对称面板：去掉说明文字省下的高度转给图层。
        QTimer.singleShot(0, self.sym_panel._cap_content_height)
        # 首帧自适应画布。注意：拖出独立窗口时文档会带着自己的缩放进来，
        # 这一下 fit 会把刚还原的缩放冲掉（用户反馈「拖进去画布位置变了」），
        # 所以拖出时用 _skip_initial_fit 跳过。
        self._skip_initial_fit = False
        QTimer.singleShot(0, self._initial_fit)
        # 启动后悄悄把 .pcdraw 关联到本 exe（已指向本 exe 时什么也不做）
        if not self._secondary:
            QTimer.singleShot(900, self.auto_file_assoc)

    def _initial_fit(self):
        """首帧自适应画布（拖出窗口时跳过，别把文档自带的缩放冲掉）。"""
        if self._skip_initial_fit:
            self._skip_initial_fit = False
            return
        self.canvas.fit()

    def _bind_layout_save(self):
        """工作区一改就（防抖 600ms）存盘，关掉软件再打开还是上次的样子。"""
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.setInterval(600)
        self._layout_timer.timeout.connect(self._save_window_state)
        for key in self.SPLIT_KEYS:
            sp = getattr(self, key, None)
            if sp is not None:
                sp.splitterMoved.connect(lambda *_: self._layout_timer.start())
        for sec in (self.color_panel, self.sym_panel, self.brush_panel):
            try:
                sec.chev.clicked.connect(lambda *_: self._layout_timer.start())
            except Exception:
                pass

    # ------------------------------------------------------------ UI
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 顶部菜单条
        bar = QWidget()
        bar.setFixedHeight(26)
        bar.setStyleSheet(f"background: {C.CHROME};")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(2, 0, 8, 0)
        bl.setSpacing(2)
        self.menu_holder = bl
        root.addWidget(bar)

        # 选项栏（高度可拖：顶栏 ↔ 画布）
        self.options_bar = QWidget()
        self.options_bar.setMinimumHeight(30)
        self.options_bar.setMaximumHeight(110)
        self.options_bar.setStyleSheet(
            f"background: {C.CHROME}; border-bottom: 1px solid {C.SEPARATOR};")
        bar_lay = QVBoxLayout(self.options_bar)
        bar_lay.setContentsMargins(0, 0, 0, 0)
        bar_lay.setSpacing(0)
        self.options_inner = QWidget()
        self.options_layout = QHBoxLayout(self.options_inner)
        self.options_layout.setContentsMargins(10, 0, 10, 0)
        self.options_layout.setSpacing(10)
        bar_lay.addStretch(1)                       # 拖高以后内容仍然居中
        bar_lay.addWidget(self.options_inner)
        bar_lay.addStretch(1)

        # 中部
        mid = QWidget()
        ml = QHBoxLayout(mid)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)

        self.rail = ToolRail()
        ml.addWidget(self.rail)

        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        self.strip = DocStrip()
        cl.addWidget(self.strip)
        self.canvas = Canvas(self.doc)
        # 画笔参数面板（放右栏）
        self.brush_panel = BrushPanel(self.brush)
        # 画布下方：画笔预设条（只挑笔，参数在右栏）
        self.preset_bar = PresetBar(self.brush_panel)
        self.brush_panel.bar = self.preset_bar
        # 关键：画布与右侧笔刷面板必须共用同一个 Brush 对象，
        # 否则面板/选项栏上的参数永远传不到实际落笔的引擎里。
        self.canvas.brush = self.brush
        # 橡皮 / 涂抹的笔尖参数是分开存的，读回上次调好的样子
        self._restore_tool_brushes()
        if self._text_color_saved.isValid():
            self.canvas.text_color = QColor(self._text_color_saved)
        # 文字工具编辑时点选项栏改字体/字号不算「离开」，别急着落字
        self.canvas.text_keep_parent = self.options_bar
        # 上下可拖：画布 ←→ 画笔工作区
        self.canvas_split = QSplitter(Qt.Vertical)
        self.canvas_split.setChildrenCollapsible(False)
        self.canvas_split.setHandleWidth(4)
        self.canvas_split.addWidget(self.canvas)
        self.canvas_split.addWidget(self.preset_bar)
        self.canvas_split.setStretchFactor(0, 1)
        self.canvas_split.setStretchFactor(1, 0)
        self.canvas_split.setSizes([520, 236])   # 预设区：分类标签 + 两三排笔
        self.preset_bar.setMinimumHeight(140)
        cl.addWidget(self.canvas_split, 1)

        # 右侧面板：颜色 + 画笔（可上下滚动） / 图层
        dock = QWidget()
        dock.setMinimumWidth(248)
        dock.setStyleSheet(f"background: {C.DOCK}; border-left: 1px solid {C.SEPARATOR};")
        dl = QVBoxLayout(dock)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(0)

        # 一律带 parent 建：无父控件的面板在构造期间只要有子控件调了 show()，
        # 就会自己变成一个独立小窗口闪一下（启动时那个 215×193 的小窗就是这么来的）。
        self.color_panel = ColorPanel(self)
        self.sym_panel = SymmetryPanel(self.canvas.symmetry, self)
        # 对称默认展开：画笔已经搬到画布下面，右栏放得下，展开着才看得见这个功能
        self.sym_panel.set_collapsed(False)
        self.layers_panel = LayersPanel(self)

        # 右栏：颜色 · 对称 · 图层 一条竖排（三段都能拖，各自内部滚动）
        self.dock_split = QSplitter(Qt.Vertical)
        self.dock_split.setChildrenCollapsible(False)
        self.dock_split.setHandleWidth(4)
        for w in (self.color_panel, self.sym_panel, self.brush_panel, self.layers_panel):
            self.dock_split.addWidget(w)
        self.dock_split.setStretchFactor(0, 0)
        self.dock_split.setStretchFactor(1, 0)
        self.dock_split.setStretchFactor(2, 0)
        self.dock_split.setStretchFactor(3, 1)       # 多出来的高度给图层
        self.dock_split.setSizes([300, 128, 155, 190])
        self.brush_panel.setMinimumHeight(150)
        self.layers_panel.setMinimumHeight(190)
        dl.addWidget(self.dock_split)

        # 左右可拖：画布 ←→ 右面板（像原版那样自己调宽度）
        self.main_split = QSplitter(Qt.Horizontal)
        self.main_split.setChildrenCollapsible(False)
        self.main_split.setHandleWidth(4)
        self.main_split.addWidget(center)
        self.main_split.addWidget(dock)
        self.main_split.setStretchFactor(0, 1)
        self.main_split.setStretchFactor(1, 0)
        self.main_split.setSizes([1000, 282])

        # 左右可拖：左侧工具栏 ←→ 画布
        self.left_split = QSplitter(Qt.Horizontal)
        self.left_split.setChildrenCollapsible(False)
        self.left_split.setHandleWidth(4)
        self.left_split.addWidget(self.rail)
        self.left_split.addWidget(self.main_split)
        self.left_split.setStretchFactor(0, 0)
        self.left_split.setStretchFactor(1, 1)
        self.left_split.setSizes([42, 1200])
        ml.addWidget(self.left_split, 1)

        # 上下可拖：顶部选项栏 ←→ 画布
        self.top_split = QSplitter(Qt.Vertical)
        self.top_split.setChildrenCollapsible(False)
        self.top_split.setHandleWidth(4)
        self.top_split.addWidget(self.options_bar)
        self.top_split.addWidget(mid)
        self.top_split.setStretchFactor(0, 0)
        self.top_split.setStretchFactor(1, 1)
        self.top_split.setSizes([30, 800])
        root.addWidget(self.top_split, 1)

        # 状态栏
        self.status = QStatusBar()
        self.status.setFixedHeight(24)
        self.status.setSizeGripEnabled(False)
        root.addWidget(self.status)
        self.hint = QLabel("就绪")
        self.hint.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 11px; padding-left: 8px;")
        self.status.addWidget(self.hint)
        self.pos_label = QLabel("x: —   y: —")
        self.pos_label.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 11px; padding-left: 14px;")
        self.status.addWidget(self.pos_label)

        self.pressure_label = QLabel("笔压")
        self.pressure_label.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 11px;")
        self.status.addPermanentWidget(self.pressure_label)
        self.pressure_bar = PressureBar()
        self.status.addPermanentWidget(self.pressure_bar)
        self.pressure_val = QLabel("—")
        self.pressure_val.setFixedWidth(34)
        self.pressure_val.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 11px;")
        self.status.addPermanentWidget(self.pressure_val)

        self.layer_count = QLabel("1 图层")
        self.layer_count.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 11px; padding: 0 10px;")
        self.status.addPermanentWidget(self.layer_count)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setStyleSheet(f"color: {C.TEXT}; font-size: 11px; padding: 0 12px;")
        self.status.addPermanentWidget(self.zoom_label)

        self._build_options()
        QTimer.singleShot(0, self.canvas.warm_brush_cache)
        self.layers_panel.controller = self
        self.layers_panel.set_document(self.doc)
        self.rail.select("brush")
        self._refresh_title()
        # 分隔条样式：窗口级一次下发（以前 5 个分栏各设一次，每次都要重新 polish
        # 整棵子树，合计 86ms；这样只要 17ms，新建窗口 / 拖出独立窗口都更快）
        self.setStyleSheet(
            f"background: {C.DOCK};"
            f"QSplitter::handle {{ background: #3C3C3C; }}"
            f"QSplitter::handle:hover {{ background: #4E4E4E; }}"
            f"QSplitter::handle:pressed {{ background: {C.ACCENT}; }}"
            f"QSplitter::handle:vertical {{ height: 4px; }}"
            f"QSplitter::handle:horizontal {{ width: 4px; }}")
        self.hint.setText("提示：画笔 / 橡皮 / 涂抹的选项栏里有「对称」下拉，选中即开镜像绘图；"
                          "图层右键可新建组 / 解散组；背景层固定在最底层，铺满画布的色块"
                          "拖动时会自动吸附对齐")

    def _qsettings(self):
        # 键名沿用旧的 PhotoCraftDraw：改名 U Draw 后，用户原有的窗口尺寸、
        # 面板布局、最近文件仍能读回来，不会像第一次启动那样重置。
        return QSettings("PhotoCraftDraw", "PhotoCraftDraw")

    # 右侧面板改版后，旧的分栏比例会把画笔面板压得太窄，这里只在版本一致时恢复
    # v11：预设区去掉了分类标签、末尾多了「新建画笔」格子，旧比例会把格子挤成一条缝
    LAYOUT_VERSION = 11

    SPLIT_KEYS = ("main_split", "dock_split", "left_split", "top_split",
                  "canvas_split")

    def _splitter_defaults(self, sp):
        """各分栏的默认尺寸（「复位工作区」用）。"""
        if sp is self.main_split:
            return [1000, 282]
        if sp is self.dock_split:
            return [330, 180, 170, 170]
        if sp is self.canvas_split:
            return [520, 236]
        if sp is self.left_split:
            return [42, 1200]
        if sp is self.top_split:
            return [30, 800]
        return sp.sizes()

    def _restore_window_state(self):
        if getattr(self, "_secondary", False):
            return          # 独立窗口用默认大小，别把主窗口的位置抄过来
        st = self._qsettings()
        geo = st.value("window/geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        try:
            ver = int(st.value("window/layout_version", 1))
        except (TypeError, ValueError):
            ver = 1
        if ver != self.LAYOUT_VERSION:
            return
        # 折叠状态要先恢复：它会改分栏高度，晚于 setSizes 就会把比例冲掉
        for key, sec in (("color", self.color_panel), ("sym", self.sym_panel),
                         ("brush", self.brush_panel)):
            val = st.value("window/collapsed_" + key)
            if val is not None:
                sec.set_collapsed(str(val).lower() in ("true", "1"))
        for key in self.SPLIT_KEYS:
            sp = getattr(self, key, None)
            data = st.value("window/" + key)
            if sp is not None and data is not None:
                sp.restoreState(data)

    def _save_window_state(self):
        if getattr(self, "_secondary", False):
            return          # 独立窗口不写「主窗口大小 / 布局」，免得把主窗口的设置冲掉
        st = self._qsettings()
        st.setValue("window/geometry", self.saveGeometry())
        for key in self.SPLIT_KEYS:
            sp = getattr(self, key, None)
            if sp is not None:
                st.setValue("window/" + key, sp.saveState())
        for key, sec in (("color", self.color_panel), ("sym", self.sym_panel),
                         ("brush", self.brush_panel)):
            st.setValue("window/collapsed_" + key, bool(sec._collapsed))
        st.setValue("window/layout_version", self.LAYOUT_VERSION)
        st.sync()

    # ------------------------------------------------------------ 使用偏好
    # 这些是「关掉软件再打开应该还是老样子」的东西：颜色、当前工具、对称、
    # 形状参数、文字参数、模拟压感 / 移动自动选择。
    def set_smooth_zoom(self, on: bool):
        """放大时是否平滑插值（默认关 = 像素清晰）。"""
        self.canvas.smooth_zoom = bool(on)
        self.canvas.update()
        self.hint.setText("放大显示：平滑插值（边缘会变柔）" if on
                          else "放大显示：像素清晰（硬笔边缘保持锐利）")

    def _save_prefs(self):
        st = self._qsettings()
        c = self.canvas
        st.setValue("color/fg", QColor(c.color).name())
        st.setValue("color/bg", QColor(c.secondary).name())
        st.setValue("tool/current", self.current_tool)
        st.setValue("sym/mode", str(c.symmetry.get("mode", "off")))
        st.setValue("sym/count", int(c.symmetry.get("count", 6)))
        st.setValue("shape/fill", bool(c.shape_fill))
        st.setValue("shape/width", float(c.shape_width))
        st.setValue("text/size", float(c.text_size))
        st.setValue("text/family", str(c.text_family))
        st.setValue("text/align", str(c.text_align))
        st.setValue("text/bold", bool(c.text_bold))
        st.setValue("text/italic", bool(c.text_italic))
        st.setValue("canvas/simulate_pressure", bool(c.simulate_pressure))
        st.setValue("canvas/smooth_zoom", bool(c.smooth_zoom))
        st.setValue("move/auto_select", bool(c.move_auto_select))
        st.sync()

    def _restore_prefs(self):
        st = self._qsettings()
        c = self.canvas

        def _flag(key, default=False):
            v = st.value(key)
            if v is None:
                return default
            return str(v).lower() in ("true", "1")

        def _num(key, default, cast=float):
            v = st.value(key)
            if v is None:
                return default
            try:
                return cast(v)
            except (TypeError, ValueError):
                return default

        # 前景 / 背景色
        for key, setter in (("color/fg", "fg"), ("color/bg", "bg")):
            raw = st.value(key)
            if not raw:
                continue
            col = QColor(raw)
            if not col.isValid():
                continue
            if setter == "fg":
                self.color_panel.set_color(col)      # 会走 _on_color 同步到画布
            else:
                c.secondary = QColor(col)
                self.rail.set_bg(c.secondary)

        # 形状 / 文字 / 开关
        c.shape_fill = _flag("shape/fill", c.shape_fill)
        c.shape_width = max(0.5, min(200.0, _num("shape/width", c.shape_width)))
        c.text_size = max(4.0, min(400.0, _num("text/size", c.text_size)))
        fam = st.value("text/family")
        if isinstance(fam, str) and fam:
            c.text_family = fam
        align = st.value("text/align")
        if isinstance(align, str) and align in ("left", "center", "right"):
            c.text_align = align
        c.text_bold = _flag("text/bold", c.text_bold)
        c.text_italic = _flag("text/italic", c.text_italic)
        c.simulate_pressure = _flag("canvas/simulate_pressure", c.simulate_pressure)
        c.move_auto_select = _flag("move/auto_select", c.move_auto_select)
        c.smooth_zoom = _flag("canvas/smooth_zoom", False)
        if hasattr(self, "a_smooth"):
            self.a_smooth.setChecked(c.smooth_zoom)

        # 对称：只恢复模式 / 份数，轴心还是用当前画布的中心
        mode = st.value("sym/mode")
        if isinstance(mode, str) and mode in SYM_MODES:
            c.symmetry["mode"] = mode
            c.symmetry["count"] = max(2, min(24, _num("sym/count", 6, int)))
            c.symmetry["guides"] = mode != "off"
            self.sym_panel.sync()
            self._sync_sym_bar()      # 顶部选项栏的对称下拉也要跟着亮起来

        # 当前工具：放在最后（它会重建选项栏、切面板绑定）
        tool = st.value("tool/current")
        if isinstance(tool, str) and tool in TOOL_NAMES and tool != self.current_tool:
            self.rail.select(tool)

    # ------------------------------------------------------------ 菜单/动作
    def _act(self, text, slot, shortcut=None, checkable=False):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
            a.setShortcutContext(Qt.WindowShortcut)
        if checkable:
            a.setCheckable(True)
        a.triggered.connect(slot)
        self.addAction(a)
        return a

    def _build_actions(self):
        m_file = QMenu("文件", self)
        a_new = self._act("新建…", self.new_document, "Ctrl+N")
        a_open = self._act("打开项目…", self.open_project, "Ctrl+O")
        a_import = self._act("打开图片…", self.import_image, "Ctrl+Shift+O")
        a_save = self._act("保存", self.save_project, "Ctrl+S")
        a_saveas = self._act("另存为…", self.save_project_as, "Ctrl+Shift+S")
        a_export = self._act("导出 PNG / JPG…", self.export, "Ctrl+Alt+S")
        a_psd = self._act("导出 PSD 工程（分层）…", self.export_psd_file)
        a_close = self._act("关闭当前文档", lambda: self._close_doc(self.doc_index), "Ctrl+W")
        a_quit = self._act("退出", self.close, "Ctrl+Q")
        for w in (a_new, a_open, a_import):
            m_file.addAction(w)
        m_file.addSeparator()
        for w in (a_save, a_saveas, a_export, a_psd):
            m_file.addAction(w)
        m_file.addSeparator()
        m_file.addAction(a_close)
        m_file.addSeparator()
        m_file.addAction(a_quit)

        m_edit = QMenu("编辑", self)
        self.a_undo = self._act("撤销", self.undo, "Ctrl+Z")
        self.a_redo = self._act("重做", self.redo, "Ctrl+Y")
        a_tf = self._act("自由变换…", self.free_transform, "Ctrl+T")
        a_clear = self._act("清除图层内容", self.clear_area)
        # 快捷键只做展示、不注册成 QAction：否则在图层改名输入框里按回退键
        # 会先被窗口级快捷键截走，把整层删掉。实际处理在 keyPressEvent 里，
        # 那里会先判断焦点是不是在输入框（_typing）。
        a_clear.setText("清除图层内容\tShift+Backspace")
        a_fill = self._act("用前景色填充", self.fill_foreground, "Ctrl+Backspace")
        m_edit.addAction(self.a_undo)
        m_edit.addAction(self.a_redo)
        m_edit.addSeparator()
        # 复制 / 粘贴：快捷键同样只做展示（真绑成 QAction 会抢走文字编辑框里的
        # Ctrl+C / Ctrl+V），实际处理在 keyPressEvent
        a_copy = self._act("复制", self.copy_selection)
        a_copy.setText("复制\tCtrl+C")
        a_paste = self._act("粘贴为新图层", self.paste_clipboard)
        a_paste.setText("粘贴为新图层\tCtrl+V")
        m_edit.addAction(a_copy)
        m_edit.addAction(a_paste)
        m_edit.addSeparator()
        m_edit.addAction(a_tf)
        m_edit.addAction(a_clear)
        m_edit.addAction(a_fill)

        m_sel = QMenu("选择", self)
        a_all = self._act("全选", self.select_all, "Ctrl+A")
        a_none = self._act("取消选择", self.deselect, "Ctrl+D")
        a_inv = self._act("反选", self.invert_selection, "Ctrl+Shift+I")
        for w in (a_all, a_none, a_inv):
            m_sel.addAction(w)

        m_layer = QMenu("图层", self)
        a_newlayer = self._act("新建图层", lambda: self.layer_action(1), "Ctrl+Shift+N")
        a_dup = self._act("复制图层", lambda: self.layer_action(2), "Ctrl+J")
        a_del = self._act("删除图层", lambda: self.layer_action(3))
        # 菜单里把实际按键标出来（Backspace / Delete 都直接删层，见 keyPressEvent）
        a_del.setText("删除图层\tBackspace")
        a_merge = self._act("合并图层", lambda: self.layer_action(4), "Ctrl+E")
        a_up = self._act("上移图层", lambda: self.layer_action(5), "Ctrl+]")
        a_down = self._act("下移图层", lambda: self.layer_action(6), "Ctrl+[")
        a_group = self._act("新建组…", lambda: self.layer_action(7), "Ctrl+G")
        a_ungroup = self._act("解散组", self.ungroup, "Ctrl+Shift+G")
        for w in (a_newlayer, a_dup, a_del):
            m_layer.addAction(w)
        m_layer.addSeparator()
        for w in (a_merge, a_up, a_down):
            m_layer.addAction(w)
        m_layer.addSeparator()
        m_layer.addAction(a_group)
        m_layer.addAction(a_ungroup)

        m_view = QMenu("视图", self)
        a_fit = self._act("适应窗口", self.fit_view, "Ctrl+0")
        a_100 = self._act("实际像素 100%", lambda: self.canvas.set_zoom(1.0), "Ctrl+1")
        a_zin = self._act("放大", lambda: self.canvas.zoom_step(True), "Ctrl+=")
        a_zout = self._act("缩小", lambda: self.canvas.zoom_step(False), "Ctrl+-")
        for w in (a_fit, a_100, a_zin, a_zout):
            m_view.addAction(w)
        m_view.addSeparator()
        # 放大时的显示方式：默认「像素清晰」（关掉平滑），描线看边缘用这个
        self.a_smooth = QAction("放大时平滑显示", self)
        self.a_smooth.setCheckable(True)
        self.a_smooth.setChecked(False)
        self.a_smooth.setToolTip("关（默认）：放大后每个像素是清晰的方块，硬笔边缘真实\n"
                                 "开：放大后做平滑插值，看着柔但边缘会糊")
        self.a_smooth.toggled.connect(self.set_smooth_zoom)
        m_view.addAction(self.a_smooth)
        # 工作区：几块面板都能拖，拖乱了用这一项一键还原
        a_reset = self._act("复位工作区", self.reset_workspace)
        m_view.addAction(a_reset)

        m_help = QMenu("帮助", self)
        a_keys = self._act("快捷键一览", self.show_shortcuts)
        a_about = self._act(f"关于 {APP_NAME}", self.show_about)
        a_support = self._act("支持 U Draw（赞助）…", self.show_sponsor)
        m_help.addAction(a_keys)
        m_help.addSeparator()
        m_help.addAction(a_support)
        m_help.addAction(a_about)

        for m in (m_file, m_edit, m_sel, m_layer, m_view, m_help):
            self.menu_holder.addWidget(self._menu_button(m))
        # 「赞助」不是下拉菜单，点一下就开：入口要显眼，但不该占用户两下手
        self.support_btn = self._menu_button(None, "赞助", self.show_sponsor)
        self.menu_holder.addWidget(self.support_btn)
        self.menu_holder.addStretch(1)
        brand = QLabel(f"{APP_NAME} · 绘画版")
        brand.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 10px; padding-right: 4px;")
        self.menu_holder.addWidget(brand)
        self.menus = (m_file, m_edit, m_sel, m_layer, m_view, m_help)

        # 压感的两个开关给纯键盘快捷键（不进菜单，挂在窗口上就能生效）
        self.a_psize = self._act("压感控制大小（开 / 关）",
                                 lambda: self._toggle_pressure("size"), "Shift+P")
        self.a_popacity = self._act("压感控制浓淡（开 / 关）",
                                    lambda: self._toggle_pressure("opacity"), "Shift+O")

    def _toggle_pressure(self, which: str):
        """Shift+P / Shift+O：不开面板也能切压感。"""
        bp = getattr(self, "brush_panel", None)
        if bp is None:
            return
        cb = bp.cb_psize if which == "size" else bp.cb_popacity
        cb.toggle()                  # 触发 toggled -> 写回笔刷
        name = "压感控制大小" if which == "size" else "压感控制浓淡"
        self.hint.setText(f"{name}：{'开' if cb.isChecked() else '关'}"
                          "　（Shift+P / Shift+O 随时切换）")

    def _menu_button(self, menu: QMenu, title: str = None, slot=None) -> QToolButton:
        b = QToolButton()
        b.setText(title or menu.title())
        if slot is not None:
            b.clicked.connect(slot)
            b.setCursor(Qt.PointingHandCursor)
        else:
            b.setMenu(menu)
            b.setPopupMode(QToolButton.InstantPopup)
        b.setStyleSheet(
            "QToolButton { border: none; background: transparent; color: " + C.TEXT +
            "; padding: 3px 10px; font-size: 12px; }"
            f"QToolButton:hover {{ background: {C.HOVER}; border-radius: 3px; }}"
            f"QToolButton::menu-indicator {{ image: none; }}")
        return b

    # ------------------------------------------------------------ 选项栏
    def _build_options(self):
        while self.options_layout.count():
            item = self.options_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                # 必须立刻摘掉父级并隐藏：只 deleteLater 的话在事件循环轮到之前
                # 旧控件仍会画在选项栏上，出现「两套控件叠在一起」
                w.hide()
                w.setParent(None)
                w.deleteLater()
        # 选项栏重建后旧控件就没了，引用必须一起清掉，否则 _sync_sym_bar 会摸到野指针
        self.sym_combo = None
        self.sym_lbl = None
        self.text_color_btn = None
        self.text_recent = None

        # 自由变换进行中：选项栏换成「应用 / 取消 + 旋转 + 缩放 + 翻转」
        if self.canvas.has_transform():
            cap = QLabel("自由变换")
            f = QFont(cap.font())
            f.setBold(True)
            f.setPointSizeF(9.2)
            cap.setFont(f)
            cap.setStyleSheet(f"color: {C.ACCENT}; padding-right: 6px;")
            self.options_layout.addWidget(cap)

            self._opt_slider("旋转", -180, 180, int(round(self.canvas._tf.angle)), "°",
                             self.canvas.tf_set_angle, width=104)
            self._opt_slider("缩放", 5, 400, int(round(self.canvas.tf_scale_pct())), " %",
                             self.canvas.tf_set_scale, width=104)
            for text, horiz in (("水平翻转", True), ("垂直翻转", False)):
                b = QPushButton(text)
                b.setFixedHeight(24)
                b.clicked.connect(lambda _=False, h=horiz: self.canvas.tf_flip(h))
                self.options_layout.addWidget(b)


            self.options_layout.addStretch(1)
            tip = QLabel("框内拖动移动 · 拖角缩放 · 框外旋转 · 双击/Enter 应用 · Esc 取消")
            tip.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 10px;")
            self.options_layout.addWidget(tip)

            b_cancel = QPushButton("取消")
            b_cancel.setFixedHeight(24)
            b_cancel.setToolTip("放弃这次变换（Ctrl+Z / Esc 同效）")
            b_cancel.clicked.connect(self.canvas.cancel_transform)
            self.options_layout.addWidget(b_cancel)

            b_ok = QPushButton("✔ 应用")
            b_ok.setFixedHeight(24)
            b_ok.setToolTip("确认变换（Enter 同效）")
            b_ok.setStyleSheet(
                f"QPushButton {{ background: {C.ACCENT}; color: #FFFFFF; border: none; "
                f"border-radius: 3px; padding: 0 12px; font-size: 11px; font-weight: bold; }}"
                f"QPushButton:hover {{ background: #4A9CF5; }}")
            b_ok.clicked.connect(self.canvas.commit_transform)
            self.options_layout.addWidget(b_ok)
            return

        cap = QLabel(self._tool_label())
        f = QFont(cap.font())
        f.setBold(True)
        f.setPointSizeF(9.2)
        cap.setFont(f)
        cap.setStyleSheet(f"color: {C.TEXT}; padding-right: 6px;")
        self.options_layout.addWidget(cap)

        if self.current_tool in ("brush", "eraser"):
            b = self._tool_brush()
            self._size_slider = self._opt_slider("大小", 1, 400, int(b.size), " px",
                                                 self._set_size, width=112)
            self._range_slider = None
            # 图章笔 / 喷点笔才显示「密度」；普通圆笔、铅笔等不占这一栏。
            if b.kind in STAMP_KINDS or b.kind in SPRAY_KINDS:
                s = self._opt_slider("密度", 0, 100,
                                     int(round(b.density * 100)), " %",
                                     self._set_density, width=76)
                s.setToolTip("图章笔：越大图章排得越密；喷点笔：越大点更多、更聚拢")
            if b.kind in SPRAY_KINDS:
                self._range_slider = self._opt_slider(
                    "范围", 0, 600, int(round(b.range_diameter())), " px",
                    self._set_spread, width=76)
                self._range_slider.setToolTip(
                    "喷点范围（外圈直径，像素）：调大只扩大喷洒面积，不放大喷点。\n"
                    "笔尖大小会被限制在这个范围内；画布上会显示范围光圈。")
            self._opt_slider("不透明度", 1, 100, int(b.opacity * 100), " %",
                             self._set_opacity, width=84)
            self._opt_slider("流量", 1, 100, int(b.flow * 100), " %",
                             self._set_flow, width=72)
            self._opt_slider("硬度", 0, 100, int(b.hardness * 100), " %",
                             self._set_hardness, width=72)
            self._build_sym_options()
        elif self.current_tool == "smudge":
            b = self._tool_brush()
            self._size_slider = self._opt_slider("大小", 1, 400, int(b.size), " px",
                                                 self._set_size, width=112)
            self._range_slider = None
            s = self._opt_slider("力度", 6, 100,
                                 int(round(self.canvas.smudge_strength * 100)), " %",
                                 self._set_smudge, width=96)
            s.setToolTip(
                "涂抹力度 = 笔走过一个笔径之后，颜色被带走多少。\n"
                "20% 左右接近 PS 的默认手感：颜色能拖出一段距离再慢慢淡掉；\n"
                "往右拖带得更狠（像手指用力抹），往左更轻（只把边缘揉柔）。")
            self._opt_slider("硬度", 0, 100, int(b.hardness * 100), " %",
                             self._set_hardness, width=72)
            self._build_sym_options()
            tip = QLabel("按住拖动把颜色抹开　力度越大带得越远")
            tip.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 11px; padding-left: 4px;")
            self.options_layout.addWidget(tip)
        elif self.current_tool == "text":
            self._build_text_options()
        elif self.current_tool in SELECT_TOOLS:
            seg = QWidget()
            sl = QHBoxLayout(seg)
            sl.setContentsMargins(0, 0, 0, 0)
            sl.setSpacing(2)
            for tkey in SELECT_TOOLS:
                b = QToolButton()
                b.setText(SELECT_NAMES[tkey])
                b.setIcon(icons.icon(tkey, C.ICON, 15))
                b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
                b.setCheckable(True)
                b.setAutoExclusive(True)
                b.setChecked(self.current_tool == tkey)
                b.setFixedHeight(24)
                b.setStyleSheet(
                    f"QToolButton {{ border: 1px solid {C.FIELD_BORDER}; "
                    f"background: {C.FIELD}; color: {C.TEXT_DIM}; padding: 2px 7px; "
                    f"border-radius: 3px; font-size: 11px; }}"
                    f"QToolButton:hover {{ background: {C.HOVER}; }}"
                    f"QToolButton:checked {{ background: {C.ACCENT}; color: #FFFFFF; "
                    f"border-color: #2B7BD8; }}")
                b.clicked.connect(lambda _=False, k=tkey: self.rail.select(k))
                sl.addWidget(b)
            self.options_layout.addWidget(seg)
            tip = QLabel("Shift 加选　Alt 减选")
            tip.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 11px; padding-left: 6px;")
            self.options_layout.addWidget(tip)
            for text, slot, key in (("取消选择", self.deselect, "Ctrl+D"),
                                    ("反选", self.invert_selection, "Ctrl+Shift+I"),
                                    ("全选", self.select_all, "Ctrl+A")):
                b = QPushButton(text)
                b.setFixedHeight(24)
                b.setToolTip(f"{text}（{key}）")
                b.clicked.connect(slot)
                self.options_layout.addWidget(b)
        elif self.current_tool in SHAPE_TOOLS:
            seg = QWidget()
            sl = QHBoxLayout(seg)
            sl.setContentsMargins(0, 0, 0, 0)
            sl.setSpacing(2)
            for tkey in SHAPE_TOOLS:
                b = QToolButton()
                b.setText(SHAPE_NAMES[tkey])
                b.setIcon(icons.icon(SHAPE_ICONS[tkey], C.ICON, 15))
                b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
                b.setCheckable(True)
                b.setAutoExclusive(True)
                b.setChecked(self.current_tool == tkey)
                b.setFixedHeight(24)
                b.setStyleSheet(
                    f"QToolButton {{ border: 1px solid {C.FIELD_BORDER}; "
                    f"background: {C.FIELD}; color: {C.TEXT_DIM}; padding: 2px 7px; "
                    f"border-radius: 3px; font-size: 11px; }}"
                    f"QToolButton:hover {{ background: {C.HOVER}; }}"
                    f"QToolButton:checked {{ background: {C.ACCENT}; color: #FFFFFF; "
                    f"border-color: #2B7BD8; }}")
                b.clicked.connect(lambda _=False, k=tkey: self.rail.select(k))
                sl.addWidget(b)
            self.options_layout.addWidget(seg)

            self._opt_slider("粗细", 1, 200, int(self.canvas.shape_width), " px",
                             self._set_shape_width, width=84)
            from panels import CheckBox
            cb = CheckBox("填充", self.canvas.shape_fill)
            cb.toggled.connect(self._set_shape_fill)
            self.options_layout.addWidget(cb)

            tip = QLabel("Shift 约束正方形 / 45°")
            tip.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 11px; padding-left: 4px;")
            self.options_layout.addWidget(tip)
        elif self.current_tool == "move":
            from panels import CheckBox
            cb = CheckBox("自动选择", self.canvas.move_auto_select)
            cb.setToolTip("勾选后：在画布上按下时自动选中光标下最上层有内容的图层\n"
                          "图层面板里 Ctrl / Shift 多选后，拖动会一起移动这些图层")
            cb.toggled.connect(self._set_move_auto)
            self.options_layout.addWidget(cb)
            tip = QLabel("拖动移动图层内容；多选图层时一起移动；有选区时只移动选区内的像素")
            tip.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 11px; padding-left: 4px;")
            self.options_layout.addWidget(tip)
        elif self.current_tool == "hand":
            tip = QLabel("拖动画布　空格键可临时切换到抓手")
            tip.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 11px;")
            self.options_layout.addWidget(tip)
        elif self.current_tool == "bucket":
            tip = QLabel("点击填充相近颜色区域（容差 32）")
            tip.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 11px;")
            self.options_layout.addWidget(tip)
            b = QPushButton("用前景色填满整层")
            b.setFixedHeight(24)
            b.clicked.connect(self.fill_foreground)
            self.options_layout.addWidget(b)
        elif self.current_tool == "eyedropper":
            tip = QLabel("点击画布取色，取到的颜色即前景色")
            tip.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 11px;")
            self.options_layout.addWidget(tip)

        self.options_layout.addStretch(1)
        b_tf = QToolButton()
        b_tf.setText("自由变换")
        b_tf.setIcon(icons.icon("transform", C.ICON, 14))
        b_tf.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        b_tf.setFixedHeight(24)
        b_tf.setToolTip("自由变换当前图层（Ctrl+T）")
        b_tf.setStyleSheet(
            f"QToolButton {{ border: 1px solid {C.FIELD_BORDER}; background: {C.FIELD}; "
            f"color: {C.TEXT_DIM}; border-radius: 3px; padding: 0 8px; font-size: 11px; }}"
            f"QToolButton:hover {{ background: {C.HOVER}; color: {C.TEXT}; }}")
        b_tf.clicked.connect(self.free_transform)
        self.options_layout.addWidget(b_tf)

        zoom_hint = QLabel(f"{int(round(self.canvas.zoom * 100))}%　滚轮缩放 / 空格拖动画布")
        zoom_hint.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 10px;")
        self.options_layout.addWidget(zoom_hint)

    def _build_text_options(self):
        """文字工具选项栏：文字库（字体）+ 字号 + 粗斜体 + 对齐。"""
        combo = QComboBox()
        combo.setFixedHeight(24)
        combo.setMinimumWidth(196)
        combo.setMaxVisibleItems(16)
        combo.setStyleSheet(
            f"QComboBox {{ background: {C.FIELD}; color: {C.TEXT}; border: 1px solid "
            f"{C.FIELD_BORDER}; border-radius: 3px; padding: 1px 6px; font-size: 11px; }}"
            f"QComboBox QAbstractItemView {{ background: {C.CARD}; color: {C.TEXT}; "
            f"selection-background-color: {C.ACCENT}; outline: none; font-size: 12px; }}")
        combo.setToolTip("文字库：原版 PhotoCraft 内置字体 + 本机中文字体\n"
                         "每一项都用它自己的字体显示，挑字体不用猜")
        cur = 0
        for i, e in enumerate(fontlib.entries()):
            combo.addItem(e["label"])
            combo.setItemData(i, QFont(e["family"]), Qt.ItemDataRole.FontRole)
            combo.setItemData(i, e["family"], Qt.ItemDataRole.UserRole)
            if e["family"] == self.canvas.text_family:
                cur = i
        combo.blockSignals(True)
        combo.setCurrentIndex(cur)
        combo.blockSignals(False)
        combo.currentIndexChanged.connect(self._set_text_font)
        self.text_combo = combo
        self.options_layout.addWidget(combo)

        self._opt_slider("字号", 6, 400, int(self.canvas.text_size), " px",
                         self._set_text_size, width=96)

        # 文字自己的颜色：不跟前景色走，旁边配一排「最近用过的文字颜色」
        lbl = QLabel("颜色")
        lbl.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 11px;")
        self.options_layout.addWidget(lbl)
        self.text_color_btn = QToolButton()
        self.text_color_btn.setFixedSize(34, 24)
        self.text_color_btn.setToolTip("文字颜色（和前景色互不影响）\n点一下打开调色板")
        self.text_color_btn.setCursor(Qt.PointingHandCursor)
        self.text_color_btn.setStyleSheet(
            f"QToolButton {{ background: {self.canvas.text_color.name()}; "
            f"border: 1px solid {C.FIELD_BORDER}; border-radius: 3px; }}"
            f"QToolButton:hover {{ border-color: {C.ACCENT}; }}")
        self.text_color_btn.clicked.connect(self._pick_text_color)
        self.options_layout.addWidget(self.text_color_btn)

        self.text_recent = RecentSwatches(self._text_recent, 8)
        self.text_recent.setFixedWidth(150)
        self.text_recent.picked.connect(self._set_text_color)
        self.text_recent.setToolTip("最近用过的文字颜色：点一下直接套用\n"
                                    "与右侧「颜色」面板的最近使用分开记录")
        self.options_layout.addWidget(self.text_recent)

        for text, tip, attr in (("B", "粗体", "text_bold"), ("I", "斜体", "text_italic")):
            b = QToolButton()
            b.setText(text)
            b.setCheckable(True)
            b.setChecked(bool(getattr(self.canvas, attr)))
            b.setFixedSize(27, 24)
            b.setToolTip(tip)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                f"QToolButton {{ border: 1px solid {C.FIELD_BORDER}; background: {C.FIELD}; "
                f"color: {C.TEXT_DIM}; border-radius: 3px; font-size: 12px; }}"
                f"QToolButton:hover {{ background: {C.HOVER}; color: {C.TEXT}; }}"
                f"QToolButton:checked {{ background: {C.ACCENT}; color: #FFFFFF; "
                f"border-color: #2B7BD8; }}")
            f = QFont(b.font())
            f.setBold(text == "B")
            f.setItalic(text == "I")
            f.setPointSizeF(10.5)
            b.setFont(f)
            b.toggled.connect(lambda on, a=attr: self._set_text_flag(a, on))
            self.options_layout.addWidget(b)

        # 对齐按钮已按需求移除（这不是排版软件）；内部固定左对齐
        tip = QLabel("Enter 换行 · Esc 落字")
        tip.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 11px; padding-left: 4px;")
        self.options_layout.addWidget(tip)
        self.options_layout.addStretch(1)

        # 手动确认：✓ 落字 / × 放弃这次编辑（和 PS 文字工具一致）
        editing = self.canvas.has_text()

        def confirm_style(color):
            # 两个按钮必须同一套边框/底色，只让图标颜色不同；
            # 否则一个实心、一个描边，看起来像两种控件。
            return (
                f"QToolButton {{ background: {C.FIELD}; color: {color}; "
                f"border: 1px solid {C.FIELD_BORDER}; border-radius: 3px; "
                "font-size: 16px; font-weight: bold; padding: 0; }"
                f"QToolButton:hover {{ background: {C.HOVER}; border-color: {C.ACCENT}; }}"
                f"QToolButton:disabled {{ background: {C.FIELD}; color: {C.TEXT_FAINT}; "
                f"border-color: {C.SEPARATOR}; }}")

        b_ok = QToolButton()
        b_ok.setText("✓")
        b_ok.setFixedSize(28, 24)
        b_ok.setToolTip("落字：把这段文字定到画布上\n快捷键：Esc（或 Ctrl+Enter）")
        b_ok.setCursor(Qt.PointingHandCursor)
        b_ok.setFocusPolicy(Qt.NoFocus)
        b_ok.setEnabled(editing)
        b_ok.setStyleSheet(confirm_style(C.ACCENT))
        b_ok.clicked.connect(self._commit_text)
        self.options_layout.addWidget(b_ok)

        b_cancel = QToolButton()
        b_cancel.setText("×")
        b_cancel.setFixedSize(28, 24)
        b_cancel.setToolTip("取消落字：放弃这次编辑，画布上不留字\n快捷键：Shift+Esc")
        b_cancel.setCursor(Qt.PointingHandCursor)
        b_cancel.setFocusPolicy(Qt.NoFocus)
        b_cancel.setEnabled(editing)
        b_cancel.setStyleSheet(confirm_style("#D66A6A"))
        b_cancel.clicked.connect(self._cancel_text)
        self.options_layout.addWidget(b_cancel)
        self.text_ok_btn = b_ok
        self.text_cancel_btn = b_cancel

    def _build_sym_options(self):
        """选项栏上的「对称」下拉：画笔 / 橡皮 / 涂抹都能就地开镜像。

        之前对称只藏在右侧一个默认折叠的面板里，新用户根本找不到；
        画图时最常看的就是这条选项栏，放这里才符合直觉。
        """
        # 「对称」两个字做成可点的小按钮：既是标签，也是「展开面板」的入口
        lbl = QToolButton()
        lbl.setText("对称")
        lbl.setIcon(icons.icon("symmetry", C.TEXT_DIM, 13))
        lbl.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        lbl.setFixedHeight(24)
        lbl.setCursor(Qt.PointingHandCursor)
        lbl.setToolTip("对称绘图：笔迹同时落在所有镜像位置上\n点这里展开右侧「对称」面板")
        lbl.clicked.connect(self.open_sym_panel)
        self.sym_lbl = lbl
        self.options_layout.addWidget(lbl)

        combo = QComboBox()
        combo.setFixedHeight(24)
        combo.setMinimumWidth(104)
        combo.setToolTip("对称绘图：笔迹同时落在所有镜像位置上\n"
                         "关 / 垂直（左右）/ 水平（上下）/ 四象限 / 径向（绕轴心转一圈）\n"
                         "份数、轴心在右侧「对称」面板里调（参考线随对称自动显示）")
        for key in SYM_MODES:
            combo.addItem(SYM_NAMES.get(key, key))
            combo.setItemData(combo.count() - 1, key, Qt.ItemDataRole.UserRole)
        mode = self.canvas.symmetry.get("mode", "off")
        idx = SYM_MODES.index(mode) if mode in SYM_MODES else 0
        combo.blockSignals(True)
        combo.setCurrentIndex(idx)
        combo.blockSignals(False)
        combo.currentIndexChanged.connect(self._set_sym_mode_from_bar)
        self.sym_combo = combo
        self.options_layout.addWidget(combo)
        self._sync_sym_bar()

    def _sync_sym_bar(self):
        """把 canvas.symmetry 的状态刷回选项栏（面板改动 / 切文档时用）。"""
        combo = getattr(self, "sym_combo", None)
        if combo is None:
            return
        mode = self.canvas.symmetry.get("mode", "off")
        count = int(self.canvas.symmetry.get("count", 6))
        on = mode != "off"
        # 开着的时候边框变强调色：一眼看出「对称是开着的」
        combo.setStyleSheet(
            f"QComboBox {{ background: {C.FIELD}; color: "
            f"{C.ACCENT if on else C.TEXT}; border: 1px solid "
            f"{C.ACCENT if on else C.FIELD_BORDER}; border-radius: 3px; "
            f"padding: 1px 6px; font-size: 11px; }}"
            f"QComboBox QAbstractItemView {{ background: {C.CARD}; color: {C.TEXT}; "
            f"selection-background-color: {C.ACCENT}; outline: none; font-size: 12px; }}")
        lbl = getattr(self, "sym_lbl", None)
        if lbl is not None:
            lbl.setIcon(icons.icon("symmetry", C.ACCENT if on else C.TEXT_DIM, 13))
            lbl.setStyleSheet(
                f"QToolButton {{ border: none; background: transparent; padding: 0 2px; "
                f"font-size: 11px; font-weight: {'bold' if on else 'normal'}; "
                f"color: {C.ACCENT if on else C.TEXT_FAINT}; }}"
                f"QToolButton:hover {{ color: {C.TEXT}; }}")
        combo.blockSignals(True)
        for i, key in enumerate(SYM_MODES):
            text = SYM_NAMES.get(key, key)
            if key == "radial":
                text = f"径向 {count} 份"
            combo.setItemText(i, text)
        combo.setCurrentIndex(SYM_MODES.index(mode) if mode in SYM_MODES else 0)
        combo.blockSignals(False)

    def _set_sym_mode_from_bar(self, idx):
        combo = getattr(self, "sym_combo", None)
        if combo is None or idx < 0:
            return
        mode = combo.itemData(idx, Qt.ItemDataRole.UserRole)
        if not mode:
            return
        self.canvas.symmetry["mode"] = mode
        self.sym_panel.sync()
        self.canvas.update()
        self._on_symmetry_changed()
        if mode == "radial":
            self.hint.setText(
                f"径向对称：{self.canvas.symmetry.get('count', 6)} 份"
                "　在右侧「对称」面板里可改份数与轴心位置")

    def open_sym_panel(self):
        """把右侧「对称」面板展开并滚到可见。"""
        self.sym_panel.set_collapsed(False)
        try:
            self.dock_split.ensureWidgetVisible(self.sym_panel, 0, 8)
        except Exception:
            pass
        self.hint.setText("右侧「对称」面板：选模式 / 改份数 / 点选轴心（参考线自动显示）")

    def _opt_slider(self, name, lo, hi, val, suffix, slot, width=120):
        holder = QWidget()
        lay = QHBoxLayout(holder)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lbl = QLabel(name)
        lbl.setMinimumWidth(48)
        lbl.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 11px;")
        lay.addWidget(lbl)

        from panels import NoWheelSlider
        s = NoWheelSlider(Qt.Horizontal)
        s.setRange(lo, hi)
        s.setValue(val)
        s.setFixedWidth(width)
        s.setFixedHeight(16)
        lay.addWidget(s)

        val_lbl = QLabel(f"{val}{suffix}")
        val_lbl.setFixedWidth(50)
        val_lbl.setStyleSheet(f"color: {C.TEXT}; font-size: 11px;")
        lay.addWidget(val_lbl)

        def on_change(v):
            val_lbl.setText(f"{v}{suffix}")
            slot(v)
        s.valueChanged.connect(on_change)
        self.options_layout.addWidget(holder)
        return s

    def _tool_label(self):
        if self.current_tool in SELECT_TOOLS:
            return f"选区 · {SELECT_NAMES[self.current_tool]}"
        if self.current_tool in SHAPE_TOOLS:
            return f"形状 · {SHAPE_NAMES[self.current_tool]}"
        return TOOL_NAMES.get(self.current_tool, "")

    # ------------------------------------------------------------ 参数联动
    def _tool_brush(self):
        """当前工具用的那支笔。画笔 / 橡皮 / 涂抹各有独立的一套参数，
        选项栏、快捷键、滚轮都改「当前这支」，不会互相覆盖。"""
        return self.canvas.active_brush()

    TOOL_BRUSH_ATTRS = ("eraser_brush", "smudge_brush")

    def _save_tool_brushes(self):
        """橡皮 / 涂抹的笔尖参数单独存一份（和画笔预设库无关）。"""
        st = self._qsettings()
        for attr in self.TOOL_BRUSH_ATTRS:
            b = getattr(self.canvas, attr, None)
            if b is None:
                continue
            try:
                st.setValue("tool/" + attr, json.dumps(b.as_dict(), ensure_ascii=False))
            except (TypeError, ValueError):
                pass
        st.setValue("tool/smudge_strength", float(self.canvas.smudge_strength))

    def _restore_tool_brushes(self):
        st = self._qsettings()
        for attr in self.TOOL_BRUSH_ATTRS:
            b = getattr(self.canvas, attr, None)
            raw = st.value("tool/" + attr)
            if b is None or not raw:
                continue
            try:
                d = json.loads(raw) if isinstance(raw, str) else raw
            except ValueError:
                continue
            if isinstance(d, dict):
                try:
                    b.apply_from(Brush.from_dict(d))
                except (TypeError, ValueError):
                    pass
        try:
            v = float(st.value("tool/smudge_strength", self.canvas.smudge_strength))
        except (TypeError, ValueError):
            v = self.canvas.smudge_strength
        self.canvas.smudge_strength = max(0.06, min(1.0, v))

    def _bind_brush_panel(self, tool):
        """右侧「画笔」面板跟着当前工具走：橡皮 / 涂抹显示它们自己的参数。
        这两支笔不属于预设库，所以不把改动写回预设（否则调橡皮会覆盖画笔）。"""
        if tool == "eraser":
            self.brush_panel.bind(self.canvas.eraser_brush, False, "橡皮")
        elif tool == "smudge":
            self.brush_panel.bind(self.canvas.smudge_brush, False, "涂抹")
        else:
            self.brush_panel.bind(self.brush, True, "画笔")

    def _set_size(self, v):
        if getattr(self, "_syncing_brush_sliders", False):
            return
        v = float(v)
        b = self._tool_brush()
        if b.kind in SPRAY_KINDS and b.spread > 0.001 and v > b.spread:
            # 喷点类：笔尖大小不能超过范围外圈。
            v = float(b.spread)
            slider = getattr(self, "_size_slider", None)
            if slider is not None and slider.value() != int(round(v)):
                self._syncing_brush_sliders = True
                slider.setValue(int(round(v)))
                self._syncing_brush_sliders = False
            self.hint.setText(f"喷点笔尖不能大于范围（{int(round(b.spread))} px）")
        b.size = v
        if b is self.brush:
            self.brush_panel.sync_size(v)
        # 范围还是「跟随大小」时，顶部范围数字跟着笔尖一起变。
        if b.kind in SPRAY_KINDS and b.spread <= 0.001:
            slider = getattr(self, "_range_slider", None)
            if slider is not None and slider.value() != int(round(v)):
                self._syncing_brush_sliders = True
                slider.setValue(int(round(v)))
                self._syncing_brush_sliders = False
        self.canvas.refresh_brush_cursor()

    def _set_density(self, v):
        b = self._tool_brush()
        if b is self.brush:
            self.brush_panel.set_field("density", v / 100.0)
        else:
            b.density = max(0.0, min(1.0, v / 100.0))
        if b.kind in SPRAY_KINDS:
            self.canvas.show_range_preview()

    def _set_spread(self, v):
        if getattr(self, "_syncing_brush_sliders", False):
            return
        v = float(v)
        b = self._tool_brush()
        b.spread = max(0.0, min(600.0, v))
        if b.spread > 0.001 and b.size > b.spread:
            # 范围是外圈：把笔尖压到范围以内，并同步顶部大小滑杆。
            b.size = b.spread
            self.brush_panel.sync_size(b.size)
            slider = getattr(self, "_size_slider", None)
            if slider is not None and slider.value() != int(round(b.size)):
                self._syncing_brush_sliders = True
                slider.setValue(int(round(b.size)))
                self._syncing_brush_sliders = False
        self.brush_panel.set_field("spread", b.spread)
        self.canvas.show_range_preview()
        self.canvas.refresh_brush_cursor()

    def _set_brush_field(self, attr: str, v: float):
        """选项栏的滑杆：改「当前工具那支笔」。

        画笔走 BrushPanel（那边要同步滑杆、预设、试笔条）；
        橡皮 / 涂抹直接写自己那支笔 —— 以前这里一律调 brush_panel，
        结果在橡皮上拖不透明度 / 流量 / 硬度，改的是画笔，橡皮一点反应都没有。
        """
        val = max(0.0, min(1.0, v / 100.0))
        b = self._tool_brush()
        if b is self.brush:
            self.brush_panel.set_param(attr, val)
        else:
            setattr(b, attr, val)
            self.canvas.refresh_brush_cursor()

    def _set_opacity(self, v):
        self._set_brush_field("opacity", v)

    def _set_flow(self, v):
        self._set_brush_field("flow", v)

    def _set_hardness(self, v):
        self._set_brush_field("hardness", v)

    def _set_move_auto(self, on):
        self.canvas.move_auto_select = bool(on)

    def _set_shape_fill(self, on):
        self.canvas.shape_fill = bool(on)

    def _set_shape_width(self, v):
        self.canvas.shape_width = float(v)

    # ------------------------------------------------------------ 涂抹 / 文字 / 对称
    def _set_smudge(self, v):
        # 下限 6%：再低每步混合量不到 1 级色阶，柔边会被 8bit 量化成硬边
        self.canvas.smudge_strength = max(0.06, min(1.0, v / 100.0))

    def _commit_text(self):
        self.canvas.commit_text()
        for b in (getattr(self, "text_ok_btn", None), getattr(self, "text_cancel_btn", None)):
            if b is not None:
                b.setEnabled(False)

    def _cancel_text(self):
        self.canvas.cancel_text()
        for b in (getattr(self, "text_ok_btn", None), getattr(self, "text_cancel_btn", None)):
            if b is not None:
                b.setEnabled(False)

    def _set_text_font(self, idx):
        combo = getattr(self, "text_combo", None)
        if combo is None or idx < 0:
            return
        fam = combo.itemData(idx, Qt.ItemDataRole.UserRole)
        if not fam:
            return
        self.canvas.text_family = fam
        ov = self.canvas.text_overlay()
        if ov is not None:
            ov.set_style(family=fam)

    def _set_text_size(self, v):
        self.canvas.text_size = float(v)
        ov = self.canvas.text_overlay()
        if ov is not None:
            ov.set_style(px=float(v))

    def _set_text_flag(self, attr, on):
        setattr(self.canvas, attr, bool(on))
        ov = self.canvas.text_overlay()
        if ov is not None:
            ov.set_style(bold=self.canvas.text_bold,
                         italic=self.canvas.text_italic)

    def _set_text_align(self, key):
        self.canvas.text_align = key

    def _pick_text_color(self):
        ov = self.canvas.text_overlay()
        if ov is not None:
            ov.hold(True)        # 调色板是模态窗口，别让失焦把正在写的字落下去
        try:
            c = QColorDialog.getColor(
                QColor(self.canvas.text_color), self, "文字颜色",
                QColorDialog.ShowAlphaChannel)
        finally:
            if ov is not None:
                ov.hold(False)
        if c.isValid():
            self._set_text_color(c)
        if ov is not None and self.canvas.text_overlay() is ov:
            ov.setFocus()        # 回到编辑框，接着打字

    def _set_text_color(self, c: QColor):
        c = QColor(c)
        self.canvas.text_color = c
        ov = self.canvas.text_overlay()
        if ov is not None:
            ov.set_color(c)          # 正在打的字立刻变色
        btn = getattr(self, "text_color_btn", None)
        if btn is not None:
            btn.setStyleSheet(
                f"QToolButton {{ background: {c.name()}; "
                f"border: 1px solid {C.FIELD_BORDER}; border-radius: 3px; }}"
                f"QToolButton:hover {{ border-color: {C.ACCENT}; }}")
        self._text_store.push(self._text_recent, c.name())
        rec = getattr(self, "text_recent", None)
        if rec is not None:
            rec.set_colors(self._text_recent)
        try:
            self._qsettings().setValue("text/color", c.name())
        except Exception:
            pass
        self.hint.setText(f"文字颜色 {c.name()}（只影响文字，不动前景色）")

    def _on_symmetry_changed(self):
        self.canvas.update()
        self._sync_sym_bar()
        mode = self.canvas.symmetry.get("mode", "off")
        if mode == "off":
            self.hint.setText("对称已关闭")
        else:
            self.hint.setText(f"对称：{SYM_NAMES.get(mode, '')}"
                              f"（{self.canvas.symmetry.get('count', 6)} 份）"
                              "　笔迹会同时出现在所有镜像位置上")

    def _on_sym_pick(self, on):
        self.canvas.pick_symmetry = bool(on)
        if on:
            self.hint.setText("在画布上点一下，对称轴心就落在那里")
            self.canvas.setFocus()

    def _on_sym_center(self):
        self.canvas.symmetry["cx"] = self.doc.w / 2.0
        self.canvas.symmetry["cy"] = self.doc.h / 2.0
        self.canvas.update()
        self.hint.setText("对称轴心已放回画布正中")

    def _on_sym_center_picked(self):
        self.sym_panel.set_picking(False)
        s = self.canvas.symmetry
        self.hint.setText(f"对称轴心：({int(s['cx'])}, {int(s['cy'])})"
                          "　画布上可以直接按住轴心圆点拖动")
        self.canvas.update()

    def _on_text_committed(self, layer_name: str, index: int = -1):
        # 刚落字 / 刚改完的那段文字自动选中：右下角垃圾桶删的就是它
        idx = index if 0 <= index < len(self.doc.texts) else (
            len(self.doc.texts) - 1 if self.doc.texts else None)
        if idx is not None:
            self.layers_panel.active_text = idx
            self.layers_panel.selected_texts = {idx}
        self.layers_panel.refresh()
        self._refresh_title()
        for b in (getattr(self, "text_ok_btn", None), getattr(self, "text_cancel_btn", None)):
            if b is not None:
                b.setEnabled(False)
        self.hint.setText(f"文字「{layer_name}」已保存为可再编辑的文字对象"
                          "　在图层面板最上面：双击接着改，单击选中后垃圾桶可删")

    def _on_text_editing(self, index: int):
        # 从画布点到某段已有文字：选项栏要显示这段文字自己的字体 / 字号 / 颜色
        self._build_options()
        # 图层面板也跟着高亮这段文字 —— 这样按垃圾桶删的一定是这段字，
        # 不会再去删「列表里下面那个图层」（用户反馈的那个 bug）
        if index is not None and 0 <= index < len(self.doc.texts):
            self.layers_panel.active_text = index
            self.layers_panel.selected_texts = {index}
            self.layers_panel.selected = set()
        self.layers_panel.refresh()

    def edit_text(self, index: int):
        """图层面板里点了文字行：切到文字工具并打开这段文字的编辑框。"""
        if not (0 <= index < len(self.doc.texts)):
            return
        self.rail.select("text")
        self.canvas.begin_edit_text(index)
        self.hint.setText("正在编辑这段文字：改字 / 字体 / 字号 / 颜色都立刻生效"
                          "　Enter 换行 · Esc 或点别处完成")

    # ------------------------------------------------------------ 绑定
    def _bind(self):
        self.rail.toolChanged.connect(self._on_tool)
        self.rail.colorsSwapped.connect(self.swap_colors)
        self.rail.zoomStep.connect(self._on_rail_zoom)
        self.canvas.zoomChanged.connect(self._on_zoom)
        self.canvas.pressureChanged.connect(self._on_pressure)
        self.canvas.cursorMoved.connect(self._on_cursor)
        self.canvas.docChanged.connect(self._on_doc_paint)
        self.canvas.historyChanged.connect(self._sync_history)
        self.canvas.colorPicked.connect(self._on_color_picked)
        self.canvas.brushSizeChanged.connect(self._on_brush_size_outside)
        self.canvas.brushOpacityChanged.connect(self._on_brush_opacity_outside)
        self.canvas.brushUsed.connect(self.brush_panel.record_recent)
        self.color_panel.colorChanged.connect(self._on_color)
        self.brush_panel.changed.connect(self.canvas.refresh_brush_cursor)
        self.brush_panel.presetChanged.connect(self._on_preset_changed)
        self.layers_panel.changed.connect(self._on_layers_changed)
        self.layers_panel.activeChanged.connect(self._on_active_layer)
        self.layers_panel.selectionChanged.connect(self._sync_layer_selection)
        self.canvas.layerPicked.connect(self._on_layer_picked)
        self.layers_panel.added.connect(self.layer_action)
        self.layers_panel.hintRequested.connect(self.hint.setText)
        self.canvas.blocked.connect(lambda msg: self.hint.setText(msg))
        self.canvas.transformChanged.connect(self._on_transform_changed)
        self.canvas.canvasTouched.connect(self._on_canvas_touched)
        self.canvas.filesDropped.connect(self._on_files_dropped)
        self.sym_panel.changed.connect(self._on_symmetry_changed)
        self.sym_panel.pickRequested.connect(self._on_sym_pick)
        self.sym_panel.centerRequested.connect(self._on_sym_center)
        self.canvas.symmetryChanged.connect(self._on_sym_center_picked)
        self.canvas.textCommitted.connect(self._on_text_committed)
        self.canvas.textEditing.connect(self._on_text_editing)
        self.layers_panel.textEditRequested.connect(self.edit_text)
        self.strip.tabActivated.connect(self._switch_doc)
        self.strip.tabClosed.connect(self._close_doc)
        self.strip.newRequested.connect(self.new_document)
        self.strip.tabDragEnded.connect(self._on_tab_drag_ended)
        self.strip.tabTearRequested.connect(self._tear_off_here)
        self.strip.thumb_provider = self._tab_thumb
        self._on_color(self.color_panel.color)

    def _on_preset_changed(self):
        # 换笔刷后，选项栏上的大小/不透明度等滑块要跟着变
        self._build_options()
        self.canvas.update()
        QTimer.singleShot(0, self.canvas.warm_brush_cache)

    def _on_tool(self, key):
        self.current_tool = key
        self.canvas.set_tool(key)
        self._bind_brush_panel(key)
        self._build_options()
        hints = {
            "brush": "左键绘画 · [ ] 调笔刷大小 · 滚轮缩放 · 空格拖动画布",
            "eraser": "擦除当前图层像素 · 可配合选区限定范围",
            "smudge": "按住拖动把颜色抹开 · 力度越大带得越远",
            "text": "在画布或画布外点一下就地打字 · Enter 换行 · Esc 落字 · ✓ 确认 / ✕ 取消",
            "bucket": "点击填充相近颜色区域（边缘自动消白边）",
            "eyedropper": "点击取色",
            "marquee": "拖动创建矩形选区 · Shift 加选 · Alt 减选",
            "ellipse": "拖动创建椭圆选区",
            "lasso": "按住拖动自由套索",
            "rect": "拖动画矩形/椭圆/直线 · Shift 约束 · 选项栏可切填充",
            "ellipse_shape": "拖动画椭圆 · Shift 变正圆",
            "line": "拖动画直线 · Shift 约束 45°",
            "move": "拖动移动当前图层内容（有选区时只移动选区内）",
            "hand": "拖动画布 · 滚轮缩放",
        }
        self.hint.setText(hints.get(key, ""))

    def _on_zoom(self, z):
        self.zoom_label.setText(f"{z * 100:.0f}%" if z >= 0.1 else f"{z * 100:.1f}%")
        self._refresh_title()

    def _on_pressure(self, p):
        self.pressure_bar.set_value(p)
        self.pressure_val.setText(f"{int(p * 100)}%")
        # 标出这次压力是数位板真实读数还是按速度模拟的 —— 一眼看出驱动有没有生效
        real = getattr(self.canvas, "pressure_source", "mouse") == "tablet"
        want = "笔压·笔" if real else "笔压·模拟"
        if self.pressure_label.text() != want:
            self.pressure_label.setText(want)
            self.pressure_label.setToolTip(
                "数位板真实压力" if real else
                "没收到数位板压力，正按运笔速度模拟。\n"
                "想让真实压感生效：在数位板驱动里打开「Windows Ink」，"
                "然后在画布上重新落笔。")

    def _on_cursor(self, pos: QPointF):
        self.pos_label.setText(f"x: {int(pos.x())}   y: {int(pos.y())}")

    def _doc_structure(self):
        """文档「结构」指纹：图层顺序 / 分组 / 文字数量 / 当前层。

        画一笔只会改内容、不改结构；结构没变就不用把图层面板整表重建。
        """
        doc = self.doc
        return (tuple(id(l) for l in doc.layers), tuple(sorted(doc.groups)),
                len(doc.texts), doc.active)

    def _on_doc_paint(self):
        # 以前这里无条件 layers_panel.refresh()：每抬一次笔就把整个图层列表
        # 销毁重建（40 层要 77ms），画得越久越明显 —— 用户说的「突然卡一下」。
        # 现在只有结构变了才重建，否则只重画当前层的缩略图。
        st = self._doc_structure()
        if st == getattr(self, "_paint_structure", None):
            self.layers_panel.update_active_thumb()
        else:
            self._paint_structure = st
            self.layers_panel.refresh()
        self._refresh_title()

    def _on_transform_changed(self, active: bool):
        self._build_options()
        if active:
            self.hint.setText("自由变换：框内拖动移动 · 拖角缩放（Shift 等比）· 框外旋转"
                              "（Shift 15°）· Enter/双击应用 · Esc 取消")
        else:
            self.canvas.setFocus()

    def _sync_layer_selection(self):
        sel = sorted(getattr(self.layers_panel, "selected", set()))
        self.canvas.layer_selection = sel

    def _on_layer_picked(self, index, mods=0):
        # 移动工具自动选中：连修饰键一起交给图层面板，Ctrl 加选 / Shift 区间选
        mods = Qt.KeyboardModifiers(mods)
        self.layers_panel.select(index, mods)
        self.canvas.layer_selection = sorted(getattr(self.layers_panel, "selected", {index}))
        sel = self.canvas.layer_selection
        if len(sel) > 1:
            self.hint.setText(f"自动选中 {len(sel)} 个图层，拖动可一起移动")
        else:
            self.hint.setText(f"自动选中「{self.doc.layers[index].name}」")
        skipped = getattr(self.canvas, "_pick_skipped", None)
        if skipped is not None:
            self.hint.setText(self.hint.text() + f"（「{skipped.name}」已锁定，略过）")

    def _on_active_layer(self):
        # 只是切换选中图层，不需要重绘画布；刷新标题与图层数即可
        self._refresh_title()

    def _on_layers_changed(self):
        # 只重绘画布和标题；这里绝不能 refresh 图层列表，
        # 否则鼠标一按下行就被重建，拖动排序会立刻断掉。
        self.canvas.update()
        self._refresh_title()
        self._sync_history()      # 图层面板里删文字 / 改分组也能正确反映撤销按钮状态

    def _on_color_picked(self, c: QColor):
        self.color_panel.set_color(c)

    def _on_color(self, c: QColor):
        self.canvas.color = QColor(c)
        self.rail.set_color(c)
        self._refresh_swatch()

    def _refresh_swatch(self):
        self.rail.swatch.update()

    def swap_colors(self):
        c = self.canvas
        fg, bg = QColor(c.color), QColor(c.secondary)
        c.color, c.secondary = bg, fg
        self.rail.set_bg(c.secondary)
        self.color_panel.set_color(QColor(c.color))
        self.hint.setText(f"前景色 ⇄ 背景色：{c.color.name()} / {c.secondary.name()}")

    def _on_brush_size_outside(self, size):
        self.brush_panel.sync_size(size)
        # 触摸板 / Ctrl+滚轮改大小后，顶部大小和范围数字也跟着走。
        b = self._tool_brush()
        slider = getattr(self, "_size_slider", None)
        if slider is not None and slider.value() != int(round(size)):
            self._syncing_brush_sliders = True
            slider.setValue(int(round(size)))
            self._syncing_brush_sliders = False
        if (b.kind in SPRAY_KINDS and b.spread <= 0.001):
            rslider = getattr(self, "_range_slider", None)
            if rslider is not None and rslider.value() != int(round(size)):
                self._syncing_brush_sliders = True
                rslider.setValue(int(round(size)))
                self._syncing_brush_sliders = False

    def _on_brush_opacity_outside(self, value):
        self.brush_panel.set_param("opacity", value)

    def _sync_history(self):
        a_undo = getattr(self, "a_undo", None)
        a_redo = getattr(self, "a_redo", None)
        if a_undo is not None:
            a_undo.setEnabled(self.doc.can_undo())
        if a_redo is not None:
            a_redo.setEnabled(self.doc.can_redo())

    # ------------------------------------------------------------ 文档
    def _doc_title(self):
        name = self.doc.title
        return ("• " if self.doc.modified else "") + name

    def _refresh_title(self):
        t = self._doc_title()
        self.setWindowTitle(f"{t} @ {self.canvas.zoom * 100:.0f}% — {APP_NAME}  v{APP_VERSION}")
        self._refresh_tabs()
        self.layer_count.setText(f"{len(self.doc.layers)} 图层")
        self._sync_history()

    def _refresh_tabs(self):
        items = [{"title": d.title,
                  "zoom": (self.canvas.zoom if i == self.doc_index
                           else self._views.get(id(d), (1.0,))[0]),
                  "modified": d.modified}
                 for i, d in enumerate(self.docs)]
        self.strip.set_tabs(items, self.doc_index)

    def _save_view(self):
        """记住视图：除了 zoom / 偏移，还记「画布中心对应的文档坐标」。

        文档换到另一个窗口（窗口大小不同）时，只还原 ox/oy 会让内容跑到别处 ——
        用户反馈「拖进去画布的位置怎么会改变」就是这个。用中心点换算才能保持原样。
        """
        c = self.canvas
        cx = (c.width() / 2.0 - c.ox) / max(1e-6, c.zoom)
        cy = (c.height() / 2.0 - c.oy) / max(1e-6, c.zoom)
        self._views[id(self.doc)] = (c.zoom, c.ox, c.oy, cx, cy,
                                     c.width(), c.height())

    def _restore_view(self, doc, fit=False):
        c = self.canvas
        state = None if fit else self._views.get(id(doc))
        if not state:
            c.fit()
            return
        zoom = state[0]
        c.zoom = zoom
        if len(state) >= 7 and (state[5], state[6]) != (c.width(), c.height()):
            # 窗口尺寸变了（拖出 / 合并 / 换窗口）：按「文档中心点」还原
            c.ox = c.width() / 2.0 - state[3] * zoom
            c.oy = c.height() / 2.0 - state[4] * zoom
        else:
            c.ox, c.oy = state[1], state[2]
        c.zoomChanged.emit(c.zoom)
        c.update()

    def _apply_doc(self, doc: Document, fit=False):
        """把某个文档接到画布/面板上（不动文档列表）。"""
        self.canvas.commit_transform()
        self.doc = doc
        self.canvas.set_document(doc, fit=False)
        self.canvas.set_tool(self.current_tool)
        self.layers_panel.set_document(doc)
        self._restore_view(doc, fit=fit)
        if getattr(self, "sym_panel", None) is not None:
            self.sym_panel.sync()
            self._sync_sym_bar()
        self._refresh_title()

    def _add_doc(self, doc: Document, activate=True):
        self._save_view()
        # 同名文档自动编号，标签上才分得清
        names = {d.title for d in self.docs}
        if doc.title in names:
            n = 2
            while f"{doc.title} {n}" in names:
                n += 1
            doc.title = f"{doc.title} {n}"
        self.docs.append(doc)
        if activate:
            self.doc_index = len(self.docs) - 1
            self._apply_doc(doc, fit=True)
        else:
            self._refresh_tabs()
        self.hint.setText(f"已打开「{doc.title}」，共 {len(self.docs)} 个文档")

    def _switch_doc(self, index: int):
        if not (0 <= index < len(self.docs)) or index == self.doc_index:
            return
        self._save_view()
        self.doc.clear_session()      # 切走的文档不再占着会话快照（一张整图）
        self.doc_index = index
        self._apply_doc(self.docs[index])
        self.hint.setText(f"切换到「{self.doc.title}」")

    # ------------------------------------------------------------ 标题栏拖到标签条 = 合并
    def _titlebar_rect(self) -> QRect:
        """系统标题栏那一条（全局坐标）。拖动窗口时用户抓的就是这里。"""
        fg = self.frameGeometry()
        border = max(26, self.geometry().top() - fg.top())
        return QRect(fg.left(), fg.top(), fg.width(), border + 6)

    def _dock_candidate(self):
        """标题栏压在哪个窗口的标签条上（没有就 None）。

        双向都行：主窗口拖到独立窗口上、独立窗口拖回主窗口，都可以。
        多个窗口都有重叠时，取重叠面积最大的那个（更符合直觉）。
        """
        bar = self._titlebar_rect()
        best, best_area = None, 0
        for w in QApplication.topLevelWidgets():
            if not isinstance(w, MainWindow) or w is self or not w.isVisible():
                continue
            g = w.strip.mapToGlobal(QPoint(0, 0))
            band = QRect(g.x() - 40, g.y() - 18, w.strip.width() + 80,
                         w.strip.height() + 36)
            inter = band.intersected(bar)
            if inter.isEmpty():
                continue
            area = inter.width() * inter.height()
            if area > best_area:
                best, best_area = w, area
        return best

    def moveEvent(self, e):
        super().moveEvent(e)
        # 拖动窗口时：靠近谁，就把谁的标签条框起来（松手就合并到那儿）
        tgt = self._dock_candidate()
        if tgt is not self._dock_target:
            if self._dock_target is not None:
                self._dock_target.strip.set_drop_hint(False)
            self._dock_target = tgt
            if tgt is not None:
                tgt.strip.set_drop_hint(True)

    def _clear_dock_hint(self):
        if self._dock_target is not None:
            self._dock_target.strip.set_drop_hint(False)
            self._dock_target = None

    def nativeEvent(self, etype, message):
        """松开标题栏（WM_EXITSIZEMOVE）时，如果正压在别的窗口标签条上就合并过去。"""
        if ctypes is not None and (etype == b"windows_generic_MSG"
                                   or etype == b"windows_dispatcher_MSG"):
            try:
                msg = ctypes.cast(int(message), ctypes.POINTER(_WinMSG)).contents
                self._on_native_message(msg.message)
            except Exception:
                pass
        return super().nativeEvent(etype, message)

    def _on_native_message(self, code: int):
        if code == 0x0232:              # WM_EXITSIZEMOVE = 标题栏拖动结束
            QTimer.singleShot(0, self._dock_if_ready)

    def _dock_if_ready(self):
        tgt = self._dock_target or self._dock_candidate()
        self._clear_dock_hint()
        if tgt is None:
            return
        self._dock_into(tgt)

    def _dock_into(self, target):
        """把这个窗口里的文档全部合并到 target（停靠）。"""
        moved = 0
        while self.docs:
            before = len(self.docs)
            self._hand_off_doc(0, target)
            if len(self.docs) >= before:
                break
            moved += 1
        target.raise_()
        target.activateWindow()
        target.hint.setText(f"已合并 {moved} 个文档过来")

    # ------------------------------------------------------------ 标签拖出
    def _tab_thumb(self, index):
        """拖动预览用的缩略图（按文档比例缩到 96px 见方）。"""
        if not (0 <= index < len(self.docs)):
            return None
        img = self.docs[index].composite
        if img is None or img.isNull():
            return None
        return QPixmap.fromImage(img).scaled(96, 56, Qt.KeepAspectRatio,
                                             Qt.SmoothTransformation)

    def _on_tab_drag_ended(self, index: int, gpos: QPoint, inside: bool):
        """拖标签只做一件事：拖到窗口外 = 变成独立窗口。

        判定很宽松：**只要松手时已经离开标签条**（拖到画布区域也算）就建窗口，
        不用非得拖到窗口外面去。
        """
        if not (0 <= index < len(self.docs)):
            return
        if self.frameGeometry().contains(gpos):
            if self._secondary:
                return          # 独立窗口内部松手：不动作
            local = self.mapFromGlobal(gpos)
            strip_bottom = self.strip.mapTo(self, QPoint(0, self.strip.height())).y()
            if local.y() < strip_bottom + 2:
                return          # 还在标签条里：手抖，不算拖出
        self._tear_off_doc(index, gpos)

    def _take_secondary_window(self):
        return MainWindow(secondary=True)

    def _tear_off_here(self, index: int):
        """右键菜单「拖出为独立窗口」。"""
        if 0 <= index < len(self.docs):
            self._tear_off_doc(index, QCursor.pos())

    def _tear_off_doc(self, index: int, gpos: QPoint):
        """把标签拖成一个独立窗口。"""
        doc = self.docs[index]
        win = self._take_secondary_window()
        win._skip_initial_fit = True      # 别在下一帧把文档的缩放 fit 掉
        win._views.clear()
        win.docs = []
        win.doc_index = 0
        # 别开得比主窗口还大：以前固定 1440×930，一拖出来就把主窗口整个盖住，
        # 用户想拖回去的时候连主窗口的标签条都看不见（就以为「拖不回去」）。
        w = max(860, min(1180, int(self.width() * 0.82)))
        h = max(600, min(860, int(self.height() * 0.82)))
        win.resize(w, h)
        win.show()
        # 落点放在鼠标**右下方**：让主窗口的标签条露出来，随时能拖回去
        scr = QGuiApplication.screenAt(gpos) or QGuiApplication.primaryScreen()
        area = scr.availableGeometry()
        x = min(max(area.left(), gpos.x() - 120), area.right() - w)
        y = min(max(area.top(), gpos.y() + 24), area.bottom() - h)
        win.move(max(area.left(), x), max(area.top(), y))
        win._clear_dock_hint()            # 刚摆好的位置不算「拖到标签条上」
        self._hand_off_doc(index, win, gpos)
        self.hint.setText(f"「{doc.title}」已拖成独立窗口"
                          "　把它的标签拖回主窗口的标签条就能合并回去")

    def _hand_off_doc(self, index: int, target, gpos=None):
        """把第 index 个文档交给另一个窗口。"""
        if target is self or not (0 <= index < len(self.docs)):
            return
        doc = self.docs[index]
        if self.doc is doc:
            self._save_view()
        view = self._views.pop(id(doc), None)
        doc.clear_session()
        self.docs.pop(index)
        if self.docs:
            if self.doc_index > index:
                self.doc_index -= 1
            self.doc_index = max(0, min(self.doc_index, len(self.docs) - 1))
            self._apply_doc(self.docs[self.doc_index])
            self._refresh_tabs()
        else:
            # 最后一个文档被搬走了：这个窗口没内容了，直接关掉
            self._force_close = True
            self.close()
        target._adopt_doc(doc, view)
        target.raise_()
        target.activateWindow()

    def _adopt_doc(self, doc, view=None):
        """从别的窗口接过来一个文档。"""
        names = {d.title for d in self.docs}
        if doc.title in names:
            n = 2
            while f"{doc.title} {n}" in names:
                n += 1
            doc.title = f"{doc.title} {n}"
        self.docs.append(doc)
        if view is not None:
            self._views[id(doc)] = view
        self.doc_index = len(self.docs) - 1
        self._apply_doc(doc, fit=view is None)
        self._refresh_tabs()
        self.hint.setText(f"已接收「{doc.title}」（共 {len(self.docs)} 个文档）")

    def _close_doc(self, index: int):
        if not (0 <= index < len(self.docs)):
            return
        doc = self.docs[index]
        if doc.modified:
            r = dialogs.ask(
                self, "关闭文档", f"「{doc.title}」还没保存，先保存吗？",
                [("save", "保存", "primary"),
                 ("discard", "不保存", "normal"),
                 ("cancel", "取消", "normal")],
                default="save", kind="question")
            if r is None or r == "cancel":
                return
            if r == "save":
                self._save_view()
                self.doc_index = index
                self._apply_doc(doc)
                if not self.save_project():
                    return
        if len(self.docs) == 1:
            blank = self.make_blank_doc(DEFAULT_W, DEFAULT_H, QColor(255, 255, 255, 255))
            self.docs = [blank]
            self.doc_index = 0
            self._views.pop(id(doc), None)
            self._apply_doc(blank, fit=True)
            return
        self._views.pop(id(doc), None)
        self.docs.pop(index)
        if index < self.doc_index:
            self.doc_index -= 1
        elif self.doc_index >= len(self.docs):
            self.doc_index = len(self.docs) - 1
        self._apply_doc(self.docs[self.doc_index])
        self.hint.setText(f"已关闭「{doc.title}」")

    @staticmethod
    def make_blank_doc(w: int, h: int, bg: QColor) -> Document:
        """新建画布。

        白底：背景层默认**锁住**，再给一张空图层用来画 —— 一上手就不会误涂到背景上，
        想改背景再点锁头解锁。透明底：保持原样（就一层，直接画）。
        """
        doc = Document(w, h, bg)
        if bg is not None and bg.alpha() > 0:
            doc.layers[0].locked = True
            doc.layers[0].name = "背景（已锁定）"
            doc.add_layer(name="图层 1", above=True, select=True)
        return doc

    def new_document(self):
        dlg = NewDocDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        w, h, bg, name = dlg.values()
        doc = self.make_blank_doc(w, h, bg)
        doc.title = name
        self._add_doc(doc)
        self.hint.setText(f"新建画布「{doc.title}」 {w} × {h}（共 {len(self.docs)} 个文档）"
                          + ("　背景层已锁定，直接在新图层上画"
                             if bg.alpha() > 0 else "　透明背景，直接画"))

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "打开项目", "", "U Draw 项目 (*.pcdraw *.zip);;所有文件 (*)")
        if not path:
            return
        self.open_project_file(path)

    def open_project_file(self, path: str) -> bool:
        """直接打开一个项目文件（双击 .pcdraw 关联到本程序时也走这里）。"""
        if not path or not os.path.isfile(path):
            return False
        # 已经打开过这个文件就切过去，别开两份
        for i, d in enumerate(self.docs):
            if d.path and os.path.normcase(os.path.abspath(d.path)) == \
                    os.path.normcase(os.path.abspath(path)):
                self._switch_doc(i)
                return True
        try:
            doc = load_project(path)
        except Exception as e:
            dialogs.tell(self, "打开失败", f"无法读取项目：\n{e}", kind="warning")
            return False
        self._add_doc(doc)
        self.hint.setText(f"已打开「{doc.title}」")
        return True

    def import_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "打开图片", "", "图片 (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff);;所有文件 (*)")
        if not path:
            return
        doc = open_image_as_document(path)
        if doc is None:
            dialogs.tell(self, "打开失败", "这个图片格式无法读取。", kind="warning")
            return
        self._add_doc(doc)

    def save_project(self):
        if not self.doc.path:
            return self.save_project_as()
        try:
            save_project(self.doc, self.doc.path)
        except Exception as e:
            dialogs.tell(self, "保存失败", str(e), kind="warning")
            return
        self._refresh_title()
        self.hint.setText(f"已保存 {os.path.basename(self.doc.path)}")
        return True

    def save_project_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "另存为", self.doc.title.split(".")[0] + ".pcdraw",
            "U Draw 项目 (*.pcdraw)")
        if not path:
            return False
        if not path.lower().endswith(".pcdraw"):
            path += ".pcdraw"
        try:
            save_project(self.doc, path)
        except Exception as e:
            dialogs.tell(self, "保存失败", str(e), kind="warning")
            return False
        self._refresh_title()
        self.hint.setText(f"已保存 {os.path.basename(path)}")
        return True

    def export(self):
        base = self.doc.title.rsplit(".", 1)[0]
        path, flt = QFileDialog.getSaveFileName(
            self, "导出图片", base + ".png", "PNG 图片 (*.png);;JPEG 图片 (*.jpg)")
        if not path:
            return
        if "jpg" in flt.lower() and not path.lower().endswith((".jpg", ".jpeg")):
            path += ".jpg"
        if export_image(self.doc, path):
            self.hint.setText(f"已导出 {os.path.basename(path)}")
        else:
            dialogs.tell(self, "导出失败", "无法写入文件。", kind="warning")

    # ------------------------------------------------------------ 文件关联
    def auto_file_assoc(self):
        """启动时自动把 .pcdraw 关联到当前 exe。

        绿色版没有安装程序，只能在第一次运行时写注册表（HKCU，不需要管理员）。
        注册表里已经指向本 exe 时一个字节都不写；用户把整个文件夹挪走后，
        下次启动会自动改到新路径 —— 所以不需要「关联」按钮。
        """
        if sys.platform != "win32" or not getattr(sys, "frozen", False):
            return False
        try:
            import winreg
            exe = os.path.abspath(sys.executable)
            want = f'"{os.path.normpath(exe)}" "%1"'
            cur = ""
            try:
                with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        r"Software\Classes\UDraw.Project\shell\open\command") as k:
                    cur = winreg.QueryValueEx(k, "")[0]
            except OSError:
                cur = ""
            if cur == want:
                return False
            if self._write_assoc(exe):
                self.hint.setText("已把 .pcdraw 工程文件关联到本程序：以后双击工程文件直接打开")
                return True
        except Exception:
            pass
        return False

    def _write_assoc(self, exe: str) -> bool:
        try:
            import ctypes
            import winreg
            prog = "UDraw.Project"
            cmd = f'"{os.path.normpath(exe)}" "%1"'
            base = os.path.basename(exe)
            keys = [
                (r"Software\Classes\.pcdraw",
                 {"": prog, "Content Type": "application/x-udraw-project"}),
                (r"Software\Classes\.pcdraw\OpenWithProgids", {prog: ""}),
                (r"Software\Classes\UDraw.Project", {"": "U Draw 项目"}),
                (r"Software\Classes\UDraw.Project\DefaultIcon",
                 {"": os.path.normpath(exe) + ",0"}),
                (r"Software\Classes\UDraw.Project\shell\open\command", {"": cmd}),
                (rf"Software\Classes\Applications\{base}",
                 {"FriendlyAppName": APP_NAME}),
                (rf"Software\Classes\Applications\{base}\shell\open\command",
                 {"": cmd}),
                (rf"Software\Classes\Applications\{base}\SupportedTypes",
                 {".pcdraw": ""}),
            ]
            for path, vals in keys:
                with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0,
                                        winreg.KEY_WRITE) as k:
                    for name, v in vals.items():
                        winreg.SetValueEx(k, name, 0, winreg.REG_SZ, v)
            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
            return True
        except Exception:
            return False

    def export_psd_file(self):
        """导出 Photoshop 工程：图层顺序 / 位置 / 可见性 / 不透明度都保留。"""
        base = self.doc.title.rsplit(".", 1)[0]
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 PSD 工程", base + ".psd", "Photoshop 工程 (*.psd)")
        if not path:
            return
        if not path.lower().endswith(".psd"):
            path += ".psd"
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            n = psd_export.export_psd(self.doc, path)
        except Exception as e:      # noqa: BLE001
            QApplication.restoreOverrideCursor()
            dialogs.tell(self, "导出失败", f"无法写入 PSD：\n{e}", kind="warning")
            return
        QApplication.restoreOverrideCursor()
        self.hint.setText(
            f"已导出 {os.path.basename(path)}（{n / 1048576:.1f} MB，"
            f"{len(self.doc.layers)} 层，可用 Photoshop 直接打开继续修）")

    # ------------------------------------------------------------ 编辑
    def copy_selection(self):
        """复制：有选区就复制选区内的像素，没有就复制整层。"""
        doc = self.doc
        layer = doc.layer
        if layer is None:
            return
        if doc.has_selection():
            r = doc.selection.boundingRect().toAlignedRect()
            r = r.intersected(QRect(0, 0, doc.w, doc.h))
            if r.isEmpty():
                self.hint.setText("选区是空的，没有可复制的内容")
                return
            img = layer.image.copy(r)
            pos = r.topLeft()
            what = f"选区 {r.width()}×{r.height()}"
        else:
            img = layer.image.copy()
            pos = QPoint(0, 0)
            what = f"整层「{layer.name}」"
        PASTE_BUF.update(image=img, pos=pos, size=(doc.w, doc.h), title=doc.title)
        # 同时放进系统剪贴板：可以贴到别的软件（QQ / PS / 浏览器都认）
        QApplication.clipboard().setImage(img)
        self.hint.setText(f"已复制{what}　Ctrl+V 可以贴到当前画布或另一个文档 / 窗口")

    def paste_clipboard(self):
        """粘贴：贴成新图层（原位置优先，尺寸不同就居中）。"""
        doc = self.doc
        if len(doc.layers) >= MAX_LAYERS:
            dialogs.tell(self, "图层已满", f"当前版本上限 {MAX_LAYERS} 个图层。")
            return
        img = None
        pos = None
        # 内部缓冲区优先（它带着「从哪儿复制的」位置信息）；
        # 但系统剪贴板里的图如果换过了（比如刚从别的软件复制了一张），就用那一张。
        buf_img = PASTE_BUF.get("image")
        clip_img = QApplication.clipboard().image()
        if buf_img is not None and not buf_img.isNull() and (
                clip_img.isNull() or clip_img.size() == buf_img.size()):
            img = buf_img
            if PASTE_BUF.get("size") == (doc.w, doc.h):
                pos = PASTE_BUF.get("pos") or QPoint(0, 0)
        elif not clip_img.isNull():
            img = clip_img
        if img is None or img.isNull():
            self.hint.setText("剪贴板里没有可粘贴的图片　先 Ctrl+C 复制图层或选区")
            return
        if pos is None:
            pos = QPoint(int((doc.w - img.width()) / 2), int((doc.h - img.height()) / 2))

        n = 1
        existing = {l.name for l in doc.layers}
        while f"粘贴 {n}" in existing:
            n += 1
        name = f"粘贴 {n}"
        holder = {}

        def apply():
            layer = doc.add_layer(name=name, above=True, select=True)
            layer.set_ext(img, (pos.x(), pos.y()), doc.w, doc.h)
            layer.has_content = True
            layer.touch()
            doc.recompose()
            holder["layer"] = layer
            return True

        if self.run_struct("粘贴", apply):
            self.canvas.update()
            self.hint.setText(
                f"已粘贴为「{name}」（{img.width()}×{img.height()}）"
                "　移动工具可以接着摆位置")

    def undo(self):
        if self.canvas.has_transform():
            # 自由变换里：一次退一步（回到上一次调整之前），退到头了才取消整个变换
            if self.canvas.tf_step_back():
                self.hint.setText("自由变换：退回上一步（继续按可一路退，退完再按才是取消变换）")
            else:
                self.canvas.cancel_transform()
                self.hint.setText("已撤回到变换前（自由变换取消）")
            return
        if self.doc.undo():
            self.layers_panel.refresh()
            self.canvas.sync_selection_ants()
            self._refresh_title()

    def redo(self):
        if self.doc.redo():
            self.layers_panel.refresh()
            self.canvas.sync_selection_ants()
            self._refresh_title()

    def clear_area(self):
        if self.doc.layer is not None and self.doc.is_locked(self.doc.layer):
            self.hint.setText(f"「{self.doc.layer.name}」已锁定，先解锁再清除")
            return
        edit = self.doc.clear_area()
        if edit:
            self.doc.push(edit)
            self.layers_panel.refresh()
            self.canvas.update()
            self._sync_history()

    def fill_foreground(self):
        if self.doc.layer is not None and self.doc.is_locked(self.doc.layer):
            self.hint.setText(f"「{self.doc.layer.name}」已锁定，先解锁再填充")
            return
        edit = self.doc.fill_area(self.canvas.color)
        if edit:
            self.doc.push(edit)
            self.layers_panel.refresh()
            self.canvas.update()
            self._sync_history()

    def select_all(self):
        self.doc.select_all()
        self.canvas.update()

    def deselect(self):
        self.doc.clear_selection()
        self.canvas.update()

    def invert_selection(self):
        self.doc.invert_selection()
        self.canvas.update()

    # ------------------------------------------------------------ 图层
    def _panel_focused(self) -> bool:
        """焦点（或它的父级）是不是在图层面板里。"""
        w = QApplication.focusWidget()
        if w is None:
            return False
        return w is self.layers_panel or self.layers_panel.isAncestorOf(w)

    def _on_canvas_touched(self):
        """在画布上开始画 / 移动 / 填充：取消图层面板里的文字选中。"""
        if getattr(self.layers_panel, "active_text", None) is None:
            return
        self.layers_panel.active_text = None
        self.layers_panel._sync_active()

    # ------------------------------------------------------------ 拖入图片
    def _on_files_dropped(self, paths, pos):
        """从资源管理器拖进来的图片：每张图一个图层，落在鼠标位置。"""
        paths = [p for p in (paths or []) if os.path.isfile(p)]
        if not paths:
            return
        doc = self.doc
        if len(doc.layers) + len(paths) > MAX_LAYERS:
            dialogs.tell(self, "图层已满",
                         f"当前版本上限 {MAX_LAYERS} 个图层，这次拖进来 "
                         f"{len(paths)} 张图放不下了。")
            return
        added, failed = [], []

        def apply():
            for path in paths:
                img = load_image_file(path)
                if img.isNull():
                    failed.append(os.path.basename(path))
                    continue
                name = os.path.splitext(os.path.basename(path))[0].strip() or "图片"
                layer = doc.add_layer(name=name[:24], above=True, select=True)
                # 以落点为中心：拖到哪儿就放哪儿，超出画布的部分也会保留
                x = int(round(pos.x() - img.width() / 2.0))
                y = int(round(pos.y() - img.height() / 2.0))
                layer.set_ext(img, (x, y), doc.w, doc.h)
                layer.has_content = True
                layer.touch()
                added.append((layer, img))
            doc.recompose()
            return bool(added)

        if not self.run_struct("拖入图片", apply):
            self.hint.setText("拖进来的文件读不出图像　支持 png / jpg / bmp / gif / webp / tif")
            return
        first, img = added[0]
        more = f" 等 {len(added)} 张" if len(added) > 1 else ""
        self.hint.setText(
            f"已把「{first.name}」{img.width()}×{img.height()} 拖成新图层{more}"
            "　移动工具可以接着摆位置")
        if failed:
            self.hint.setText(self.hint.text() + f"（{len(failed)} 个文件读不出图像）")
        self.layers_panel.refresh()
        self.canvas.update()

    def run_struct(self, label: str, fn):
        """执行一次图层结构变更，并记录成可撤销的一步。"""
        doc = self.doc
        edit = StructEdit(doc, label)
        ok = fn()
        if ok is False:
            return False
        edit.capture(doc)
        doc.push(edit)
        # 结构变了：允许面板重新自动选中当前图层（比如刚新建的那一层）
        self.layers_panel._empty_ok = False
        self.layers_panel.refresh()
        self.canvas.update()
        self._refresh_title()
        return True

    def layer_action(self, code: int):
        doc = self.doc
        cur = doc.layer
        bg_cur = bool(cur is not None and getattr(cur, "is_bg", False))
        # 正在编辑某段文字时点「垃圾桶」= 删掉这段文字，不是删图层
        if code == 3:
            # 图层面板里选中了文字对象：垃圾桶 / Backspace 删的就是这段字。
            # （以前这里只认「正在编辑」的那段，选中文字后按垃圾桶会删掉
            #   列表里下面那个图层 —— 用户反馈的 bug。）
            if self.layers_panel.remove_selection():
                self._sync_history()
                return
            idx = getattr(self.canvas, "_edit_index", None)
            if idx is not None and 0 <= idx < len(doc.texts):
                from core import TextEdit as _TextEdit
                self.canvas.cancel_text()
                edit = _TextEdit(doc, "删除文字")
                doc.remove_text(idx)
                edit.capture(doc)
                doc.push(edit)
                self.layers_panel.refresh()
                self.canvas.update()
                self._sync_history()
                self.hint.setText("已删除这段文字")
                return
            # 用户主动取消了选中（再点一下同一行）：这时按删除不该删掉当前图层
            if not (self.layers_panel.selected
                    or getattr(self.layers_panel, "selected_texts", set())):
                self.hint.setText(
                    "没有选中任何图层 / 文字　点一下图层面板里的行选中，再按删除")
                return
        if code == 8:                     # 解散组（工具条按钮 / 右键菜单 / 菜单）
            self.ungroup()
            return
        if code in (1, 2) and len(doc.layers) >= MAX_LAYERS:
            dialogs.tell(self, "图层已满",
                          f"当前版本上限 {MAX_LAYERS} 个图层（远高于 50 个的下限）。")
            return
        if code == 3 and bg_cur:
            self.hint.setText("背景层不能删除；想变白用「用前景色填充」，想清空用「清除图层内容」")
            return
        if code in (5, 6) and bg_cur:
            self.hint.setText("背景层固定在最底层，不能上移 / 下移")
            return
        if code == 3 and len(doc.layers) <= 1:
            self.hint.setText("至少要保留一个图层")
            return
        sel_now = sorted(getattr(self.layers_panel, "selected", set()))
        if code == 4 and len(sel_now) < 2 and doc.active == 0:
            self.hint.setText("最底层无法向下合并（可 Ctrl 多选几个图层再合并）")
            return
        if code == 7:
            # 选中的文字对象（可能多段）也一起装进新组
            tsel = sorted(k for k in getattr(self.layers_panel, "selected_texts", set())
                          if 0 <= k < len(doc.texts))
            at = getattr(self.layers_panel, "active_text", None)
            if not tsel and at is not None and 0 <= at < len(doc.texts):
                tsel = [at]
            sel = sorted(getattr(self.layers_panel, "selected", set()))
            if not sel and not tsel:
                sel = [doc.active]      # 什么都没选就按当前图层来
            # 背景层固定在最底层，不进组：否则整组一隐藏画布就全黑了
            sel = [i for i in sel if not getattr(doc.layers[i], "is_bg", False)]
            if not sel and not tsel:
                self.hint.setText("背景层不能加入组　请先选中组以外的图层")
                return
            name, ok = dialogs.get_text(
                self, "新建图层组", "组名：", text=f"组 {len(doc.groups) + 1}")
            if not ok:
                return
            gname = (name or f"组 {len(doc.groups) + 1}").strip()
            if self.run_struct("新建图层组",
                               lambda: doc.add_group(gname, sel, tsel) is not None):
                bits = []
                if sel:
                    bits.append(f"{len(sel)} 个图层")
                if tsel:
                    bits.append(f"{len(tsel)} 段文字")
                self.hint.setText("已把 " + " + ".join(bits) + f" 放进「{gname}」"
                                  "　右键组标题可重命名 / 解散，双击组名也能改")
            return

        labels = {1: "新建图层", 2: "复制图层", 3: "删除图层",
                  4: "合并图层", 5: "上移图层", 6: "下移图层"}

        def apply():
            if code == 1:
                return doc.add_layer() is not None
            if code == 2:
                return doc.duplicate_layer() is not None
            if code == 3:
                return doc.remove_layer()
            if code == 4:
                sel = sorted(getattr(self.layers_panel, "selected", set()))
                if len(sel) >= 2:
                    return doc.merge_layers(sel)
                return doc.merge_down()
            if code == 5:
                return doc.move_layer(doc.active, 1)
            if code == 6:
                return doc.move_layer(doc.active, -1)
            return False

        if self.run_struct(labels.get(code, "图层操作"), apply):
            self.hint.setText(labels.get(code, ""))

    def ungroup(self):
        doc = self.doc
        at = getattr(self.layers_panel, "active_text", None)
        if at is not None and 0 <= at < len(doc.texts):
            it = doc.texts[at]
            gid = getattr(it, "group", "")
            if not gid or gid not in doc.groups:
                self.hint.setText("这段文字不在任何组里　把它拖到组标题上就能进组")
                return
            g = doc.groups[gid]
            if self.run_struct("解散图层组", lambda: doc.dissolve_group(gid)):
                self.hint.setText(f"已解散「{g.name}」，里面的图层和文字都还在")
            return
        g = doc.group_of(doc.layer)
        if g is None:
            self.hint.setText("当前图层不在任何组里　先在组里选一个图层，"
                              "或用「新建组」把几个图层装起来")
            return
        gid = doc.layer.group
        n = len(doc.group_members(gid)) + len(doc.group_texts(gid))
        if self.run_struct("解散图层组", lambda: doc.dissolve_group(gid)):
            self.hint.setText(f"已解散「{g.name}」，{n} 项内容都还在（只是不再成组）")

    # ------------------------------------------------------------ 自由变换
    def free_transform(self):
        if self.canvas.begin_transform():
            self.canvas.setFocus()
            self.hint.setText("自由变换：拖角缩放（Shift 等比）· 框内移动 · 框外旋转（Shift 15°）"
                              "· Enter 应用 · Esc 取消")

    # ------------------------------------------------------------ 视图
    def fit_view(self):
        self.canvas.fit()

    def _on_rail_zoom(self, up: bool):
        self.canvas.zoom_step(bool(up))
        self.hint.setText(f"缩放 {int(round(self.canvas.zoom * 100))}%"
                          "　（触摸板双指捏合也能缩放，双指滑动平移画布）")

    def reset_workspace(self):
        """复位工作区：左侧工具栏宽度、顶部选项栏高度、右侧各栏比例都回到默认。"""
        self._apply_workspace_defaults()
        self._save_window_state()
        self.hint.setText("工作区已复位（左侧工具栏 / 顶部选项栏 / 右侧面板比例都回到默认）")

    def _apply_workspace_defaults(self):
        # 先恢复各面板默认的折叠状态：对称展开着的时候按 25px 分配，
        # 会算出「分栏 25、面板最小 30」这种对不上的情况，看起来就是重叠。
        self.sym_panel.set_collapsed(False)      # 对称默认展开，别让人以为没这功能
        self.color_panel.set_collapsed(False)
        self.brush_panel.set_collapsed(False)
        for sp in (self.main_split, self.dock_split,
                   self.top_split, self.left_split, self.canvas_split):
            if sp is not None:
                sp.setSizes(self._splitter_defaults(sp))
        self.canvas.update()

    # ------------------------------------------------------------ 其它
    def show_shortcuts(self):
        text = (
            "<b>绘画</b><br>"
            "B 画笔　E 橡皮　S 涂抹　G 油漆桶　I 吸管　X 交换前景/背景<br>"
            "V 移动图层　U 形状（Shift+U 切换矩形/椭圆/直线）　T 文字<br>"
            "「压感控制大小」管粗细，「压感控制浓淡」管深浅，可单独开<br>"
            "　　纯键盘开关：<b>Shift+P</b> 压感控制大小　<b>Shift+O</b> 压感控制浓淡<br>"
            "抖动修正：往右拖（60% 以上）画长直线最省力<br>"
            "笔刷大小：<b>[ / ]</b> 纯键盘缩小 / 放大；Ctrl+滚轮也可以<br>"
            "触摸板：双指滑动=平移　捏合=缩放　Alt+双指上下=笔刷大小　Shift+双指上下=不透明度<br><br>"
            "<b>对称</b><br>"
            "画笔 / 橡皮 / 涂抹的<b>选项栏</b>上有「对称」下拉：关 / 垂直 / 水平 / 四象 / 径向<br>"
            "份数（2~24）和轴心在右侧「对称」面板里调；开了对称就一定显示参考线<br>"
            "「点选轴心」后再点画布 = 把对称轴放到那里；「轴心居中」= 回画布正中<br>"
            "对称作用在画笔 / 橡皮 / 涂抹上，光标会把镜像位置一起画出来<br><br>"
            "<b>涂抹</b><br>"
            "按住拖动把笔下的颜色抹开，力度越大带得越远<br>"
            "在透明图层上涂抹会连透明一起抹，边界自然淡出<br><br>"
            "<b>文字</b><br>"
            "T 选文字工具 → 点画布或画布外就地打字 → Enter 换行，Esc 落字；上方 ✓ / ✕ 手动确认<br>"
            "选项栏可挑字体（内置原版字体 + 系统中文字体）、字号、粗体/斜体、文字颜色<br>"
            "落字后是一段「文字对象」：<b>双击它</b>（或双击图层面板最上面的 T 行）就能接着改；"
            "单击 T 行是选中，右下角垃圾桶删的就是这段字<br>"
            "文字浮在图层之上，不占图层、不受锁定 / 不透明度影响；也能拖进 / 拖出图层组<br><br>"
            "<b>画布</b><br>"
            "空格 + 拖动 / 中键拖动 = 移动画布　H 抓手<br>"
            "滚轮 = 以光标为中心放大 / 缩小<br>"
            "Shift+滚轮 横向平移　Alt+滚轮 纵向平移<br>"
            "Ctrl+0 适应窗口　Ctrl+1 实际像素<br><br>"
            "<b>选区</b><br>"
            "M 矩形　Shift+M 椭圆　L 套索（工具条上是一个按钮，长按切换）<br>"
            "Shift = 加选　Alt = 减选　Ctrl+D 取消<br>"
            "Ctrl+A 全选　Ctrl+Shift+I 反选　Shift+Backspace 清除内容<br><br>"
            "<b>图层</b><br>"
            "Backspace 删除当前图层（只剩一层时会提示保留）<br>"
            "Ctrl+Shift+N 新建　Ctrl+J 复制　Ctrl+E 合并（选中多个就合并它们）<br>"
            "Ctrl+G 新建组（把选中的图层装进一个组）　Ctrl+Shift+G 解散组<br>"
            "图层右键 = 新建组 / 解散组 / 重命名 / 复制 / 删除；<b>单击组标题 = 选中整组</b>，"
            "双击组名 = 改名，右键还能隐藏 / 锁定<br>"
            "背景层固定在最底层：拖不动、删不掉、不进组<br>"
            "铺满整个画布的色块拖动时，离原位 8px 内会自动吸附对齐（不会留缝）<br>"
            "Ctrl+Z 撤销　Ctrl+Y 重做　Ctrl+S 保存　Ctrl+Alt+S 导出图片<br>"
            "工程文件（.pcdraw）可以直接双击打开；<b>文件 → 导出 PSD 工程…</b> 可分层给 PS 用<br>"
            "拖动行排序　双击改名　点锁头锁定（锁定后不能绘画 / 填充 / 移动）"
        )
        dialogs.ask(self, "快捷键一览", text, [("close", "关闭", "primary")],
                    default="close", kind="info", rich=True, scroll=True,
                    width=560)

    def show_about(self):
        AboutDialog(APP_NAME, APP_VERSION, self).exec()

    def show_sponsor(self):
        SponsorDialog(self).exec()

    def _typing(self):
        w = QApplication.focusWidget()
        return isinstance(w, (QLineEdit, QSpinBox, QTextEdit, QPlainTextEdit))

    def _nudge_size(self, up: bool):
        # 改的是「当前工具那支笔」：橡皮 / 涂抹 各有自己的笔径，
        # 以前这里写死 self.brush，所以在橡皮上按 [ ] 改的其实是画笔。
        b = self._tool_brush()
        size = b.size * (1.18 if up else 0.85)
        size = max(1.0, min(400.0, size))
        # 喷点类的笔尖不能超过范围；键盘调大时也守这个规则。
        if b.kind in SPRAY_KINDS and b.spread > 0.001:
            size = min(size, b.spread)
        self._set_size(size)
        self._build_options()
        self.canvas.update()
        self.hint.setText(f"笔刷大小 {int(round(size))} px")

    def keyPressEvent(self, e):
        # 复制 / 粘贴：只在「不是正在输入文字」时才接管。
        # 文字编辑框里的 Ctrl+C / Ctrl+V 是它自己的复制粘贴，不能被抢。
        if not self._typing() and (e.modifiers() & Qt.ControlModifier):
            k = e.key()
            if k == Qt.Key_C and not (e.modifiers() & Qt.ShiftModifier):
                self.copy_selection()
                return
            if k == Qt.Key_V and not (e.modifiers() & Qt.ShiftModifier):
                self.paste_clipboard()
                return
        if self.canvas.has_transform() and not self._typing():
            if e.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.canvas.commit_transform()
                return
            if e.key() == Qt.Key_Escape:
                self.canvas.cancel_transform()
                return
        if (e.key() in (Qt.Key_Backspace, Qt.Key_Delete)
                and not self._typing() and not self.canvas.has_transform()):
            if self.doc.has_selection():
                # 有选区时回退键 = 清掉选区内的内容（PS 的用法）
                self.clear_area()
                return
            if e.modifiers() & Qt.ShiftModifier:
                self.clear_area()
            else:
                self.layer_action(3)
            return
        if not self._typing():
            k = e.key()
            shift = bool(e.modifiers() & Qt.ShiftModifier)
            tool_keys = {Qt.Key_B: "brush", Qt.Key_E: "eraser", Qt.Key_G: "bucket",
                         Qt.Key_I: "eyedropper", Qt.Key_L: "lasso",
                         Qt.Key_S: "smudge", Qt.Key_T: "text",
                         Qt.Key_H: "hand", Qt.Key_V: "move"}
            if k == Qt.Key_M:
                self.rail.select("ellipse" if shift else "marquee")
                return
            if k == Qt.Key_U:
                seq = SHAPE_TOOLS
                cur = self.current_tool if self.current_tool in seq else seq[0]
                if shift:
                    idx = (seq.index(cur) + 1) % len(seq)
                    self.rail.select(seq[idx])
                else:
                    self.rail.select(cur)
                return
            if k in tool_keys:
                self.rail.select(tool_keys[k])
                return
            if k == Qt.Key_BracketLeft:
                self._nudge_size(False)
                return
            if k == Qt.Key_BracketRight:
                self._nudge_size(True)
                return
            if k == Qt.Key_X:
                self.swap_colors()
                return
        super().keyPressEvent(e)

    def closeEvent(self, e):
        self._save_window_state()
        self._save_tool_brushes()             # 橡皮 / 涂抹的笔径、硬度
        self._save_prefs()                    # 前景/背景色、当前工具、对称…
        try:
            self.brush_panel.flush_save()     # 画笔调过的参数要存下来
        except Exception:
            pass
        if self.doc.modified and not getattr(self, "_force_close", False):
            r = dialogs.ask(
                self, "退出 U Draw", "当前作品有未保存的修改，仍然退出吗？",
                [("cancel", "取消", "primary"), ("quit", "退出", "normal")],
                default="cancel", kind="question")
            if r != "quit":
                e.ignore()
                return
        e.accept()
