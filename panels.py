# -*- coding: utf-8 -*-
"""U Draw - 右侧面板：颜色 / 笔刷 / 图层"""

from PySide6.QtCore import (QEvent, QObject, QPoint, QPointF, QRect, QRectF, QSettings,
                            QSize, Qt, QTimer, Signal)
from PySide6.QtGui import (QBrush, QColor, QFont, QGuiApplication,
                           QLinearGradient, QPainter, QPen,
                           QPolygonF)
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QLayout, QLineEdit, QMenu,
                               QScrollArea, QSizePolicy, QToolButton, QVBoxLayout,
                               QWidget)

import brushes
import dialogs
import icons
from brush_thumbs import popup_pixmap, thumb_pixmap
from brushes import (DEFAULTS, USER_GROUP, all_groups, builtin_origin, export_brush,
                     export_group as export_group_file, import_pack, load_library,
                     save_library)
from core import (KIND_NAMES, MAX_LAYERS, SYM_NAMES, Brush, StructEdit,
                  TextEdit)
from theme import C, hex_str


# ---------------------------------------------------------------- 基础件
class Section(QFrame):
    """PS / PhotoCraft 风格的面板块：标题条 + 内容区

    scroll=True 时内容区自带滚动条：面板被拖矮了内容也不会被切掉，
    右侧「颜色 / 对称 / 画笔」三栏才能上下拖着调高度。
    """

    def __init__(self, title: str, parent=None, scroll: bool = False):
        super().__init__(parent)
        self.setObjectName("section")
        self.setStyleSheet(
            f"QFrame#section {{ background: {C.TAB_STRIP}; border: none; }}")
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)

        head = QWidget()
        head.setFixedHeight(24)
        head.setStyleSheet(f"background: {C.TAB_STRIP};")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(8, 0, 6, 0)
        hl.setSpacing(4)
        self.title_label = QLabel(title.upper())
        self.title_label.setObjectName("panelTitle")
        f = QFont(self.title_label.font())
        f.setPointSizeF(9.4)
        f.setBold(True)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 0.6)
        self.title_label.setFont(f)
        hl.addWidget(self.title_label)
        hl.addStretch(1)

        # 标题栏右侧的小控件都放进 head_extra，折叠箭头始终在最右
        self.head_extra = QHBoxLayout()
        self.head_extra.setContentsMargins(0, 0, 0, 0)
        self.head_extra.setSpacing(4)
        hl.addLayout(self.head_extra)
        self.head_layout = hl       # 面板想在标题左边加个图标时用

        self.chev = QToolButton()
        self.chev.setFixedSize(16, 16)
        self.chev.setCursor(Qt.PointingHandCursor)
        self.chev.setToolTip("折叠 / 展开这个面板")
        self.chev.setText("▾")
        self.chev.setStyleSheet(
            f"QToolButton {{ border: none; background: transparent; color: {C.TEXT_FAINT}; "
            f"font-size: 9px; padding: 0; }}"
            f"QToolButton:hover {{ color: {C.TEXT}; }}")
        self.chev.clicked.connect(self.toggle_collapsed)
        hl.addWidget(self.chev)
        self._collapsed = False
        self._min_h = 30              # 展开时的最小高度（折叠时会临时压到 25）
        self._hint_h = 200            # 展开时的大致高度（折叠后 sizeHint 量不出来）
        self._hint_real = False       # _hint_h 是不是按屏幕上的真实高度记下来的
        self._outer.addWidget(head)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {C.SEPARATOR};")
        self._outer.addWidget(sep)

        self.body = QWidget()
        # 用 ID 选择器只给面板底板上色，避免样式级联到子控件
        # （否则图层行自绘的背景上会浮出一块块标签底色）
        self.body.setObjectName("panelBody")
        self.body.setStyleSheet(f"QWidget#panelBody {{ background: {C.CARD}; }}")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(9, 6, 9, 7)
        self.body_layout.setSpacing(6)
        self._scroll = None
        if scroll:
            self._scroll = QScrollArea()
            self._scroll.setWidgetResizable(True)
            self._scroll.setFrameShape(QFrame.NoFrame)
            self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._scroll.setStyleSheet(f"background: {C.CARD}; border: none;")
            self._scroll.setWidget(self.body)
            self._outer.addWidget(self._scroll, 1)
        else:
            self._outer.addWidget(self.body)

    def toggle_collapsed(self):
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, on: bool):
        if not self._collapsed:
            # 折叠前先记住展开时有多高：body 一藏起来 sizeHint 就量不出来了
            # 已经在屏幕上了就以实际高度为准：取色方块的 sizeHint 很小，
            # 只按 sizeHint 恢复的话颜色栏会明显变矮；画笔面板反过来（sizeHint 偏大）
            if self.isVisible() and self.height() > 60:
                self._hint_h = self.height()
                self._hint_real = True
            else:
                h = self.body.sizeHint().height() + 26
                if h > 60:
                    self._hint_h = h
        self._collapsed = bool(on)
        target = self._scroll if self._scroll is not None else self.body
        target.setVisible(not self._collapsed)
        self.chev.setText("▸" if self._collapsed else "▾")
        # 折起来就把高度压到标题条那么高：放在可拖分栏里才不会白占一大块。
        # 注意 min 和 max 必须一起改，否则 min(30) > max(25) 会让分栏算出
        # 「每栏 30 但内容只画 25」，看起来就像两块面板叠在一起。
        if self._collapsed:
            self.setMinimumHeight(25)
            self.setMaximumHeight(25)
        else:
            self.setMinimumHeight(self._min_h)
            self.setMaximumHeight(16777215)
        self.updateGeometry()
        self._rebalance_splitter()

    def _rebalance_splitter(self):
        """在可拖分栏里：展开时跟邻居借一块高度，折起来时把空间还回去。"""
        from PySide6.QtWidgets import QSplitter
        sp = self.parentWidget()
        if not isinstance(sp, QSplitter) or sp.orientation() != Qt.Vertical:
            return
        i = sp.indexOf(self)
        sizes = sp.sizes()
        if i < 0 or not sizes:
            return
        if self._collapsed:
            free = sizes[i] - 25
            sizes[i] = 25
            # 还回去的空间给「展开着且最大」的那块（通常是图层），
            # 这样折叠颜色 / 对称时不会把另一块小面板撑得离谱
            target = None
            below = [j for j in range(i + 1, len(sizes))
                     if not getattr(sp.widget(j), "_collapsed", False)]
            above = [j for j in range(i - 1, -1, -1)
                     if not getattr(sp.widget(j), "_collapsed", False)]
            if below:
                target = max(below, key=lambda k: sizes[k])
            elif above:
                target = max(above, key=lambda k: sizes[k])
            if target is not None and free > 0:
                sizes[target] += free
            sp.setSizes(sizes)
            self._fit_splitter_height(sp)
            return
        sp.setMaximumHeight(16777215)     # 之前可能被 _fit_splitter_height 压扁过
        # 内容自己的理想高度（body 在滚动区里，section 的 sizeHint 不算数）
        h = self.body.sizeHint().height() + 26      # body 现在可见了，量得出来
        # 折叠前记过「真实高度」就按那个还原（画笔面板要回到 130，而不是内容需要的 217）
        need = self._hint_h if self._hint_real else max(h, 160)
        need = min(max(need, 100 if self._hint_real else 160), 400)
        if sizes[i] >= need - 20:
            return
        want = need - sizes[i]
        # 只从「下面」的展开面板借高度：这样本面板的顶边不动，内容向下长，
        # 不会把上面的取色区顶上去/盖住。下面的空间不够时就让本面板短一点，
        # 由面板自己的滚动区兜底，用户还可以手动拖分栏。
        donors = [j for j in range(i + 1, len(sizes))
                  if not getattr(sp.widget(j), "_collapsed", False)]
        for j in sorted(donors, key=lambda k: sizes[k], reverse=True):
            take = min(want, max(0, sizes[j] - 120))
            if take > 0:
                sizes[i] += take
                sizes[j] -= take
                want -= take
            if want <= 0:
                break
        sp.setSizes(sizes)
        # 本栏里借不到（比如隔壁也折叠着），就找父分栏要回高度
        if want > 0:
            self._borrow_from_parent(sp, want)
            return
        self._fit_splitter_height(sp)

    @staticmethod
    def _borrow_from_parent(sp, want):
        from PySide6.QtWidgets import QSplitter
        parent = sp.parentWidget()
        if not isinstance(parent, QSplitter):
            return
        ps = parent.sizes()
        j = parent.indexOf(sp)
        others = [x for x in range(len(ps)) if x != j]
        if j < 0 or not others:
            return
        k = max(others, key=lambda x: ps[x])
        take = min(want, max(0, ps[k] - 120))
        if take <= 0:
            return
        ps[k] -= take
        ps[j] += take
        parent.setSizes(ps)

    @staticmethod
    def _fit_splitter_height(sp):
        """这一栏里的面板全折起来了：把分栏本身压到只剩标题条，别留一大块空白。"""
        from PySide6.QtWidgets import QSplitter
        total = 0
        for k in range(sp.count()):
            if not getattr(sp.widget(k), "_collapsed", False):
                sp.setMaximumHeight(16777215)
                return
            total += 29          # 25 标题 + 4 手柄
        keep = max(29, total)
        sp.setMaximumHeight(keep)
        # 父分栏也要重新分配：只压 max 的话它还会占着原来那么高，中间留一大块空白
        parent = sp.parentWidget()
        if isinstance(parent, QSplitter):
            sizes = parent.sizes()
            j = parent.indexOf(sp)
            if j >= 0 and sizes[j] > keep:
                give = sizes[j] - keep
                sizes[j] = keep
                others = [x for x in range(len(sizes)) if x != j]
                if others:
                    k2 = max(others, key=lambda x: sizes[x])
                    sizes[k2] += give
                parent.setSizes(sizes)


class NoWheelSlider(QWidget):
    """自绘滑杆：点哪儿跳哪儿、拖动跟手，滚轮交给外层滚动区。

    没用 QSlider 有两个原因：
    1. QSlider 点凹槽是「翻一页」而不是跳到点击位置，想调到某个值得来回挪；
    2. 深色皮肤靠 QSS 画凹槽和滑柄，每次重绘都要过一遍样式表，拖动时发涩。
    自绘之后点击位置一步到位，重绘只是一条线 + 一个圆点。
    """

    valueChanged = Signal(int)
    pressed = Signal()
    released = Signal()

    R = 5.0                  # 滑柄半径（直径 10，塞得进 13px 的行高）

    def __init__(self, orientation=Qt.Horizontal, parent=None):
        super().__init__(parent)
        self._min = 0
        self._max = 100
        self._val = 0
        self._drag = False
        self._hover = False
        self.setFixedHeight(14)
        self.setMinimumWidth(50)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)      # 免得方向键在没注意时改参数

    # ---- QSlider 同名接口（面板和自测脚本都在用） ----
    def setRange(self, lo: int, hi: int):
        self._min, self._max = int(lo), int(hi)
        if self._max < self._min:
            self._max = self._min
        v = max(self._min, min(self._max, self._val))
        if v != self._val:
            self._val = v
            self.valueChanged.emit(v)
        self.update()

    def setMinimum(self, v: int):
        self.setRange(v, self._max)

    def setMaximum(self, v: int):
        self.setRange(self._min, v)

    def minimum(self) -> int:
        return self._min

    def maximum(self) -> int:
        return self._max

    def value(self) -> int:
        return self._val

    def setValue(self, v: int):
        v = max(self._min, min(self._max, int(round(v))))
        if v == self._val:
            return
        self._val = v
        self.update()
        self.valueChanged.emit(v)

    # ---- 坐标 ↔ 数值 ----
    def _span(self) -> float:
        return max(1.0, self.width() - self.R * 2)

    def _value_at(self, x: float) -> int:
        u = (x - self.R) / self._span()
        u = 0.0 if u < 0.0 else (1.0 if u > 1.0 else u)
        return int(round(self._min + u * (self._max - self._min)))

    def _x_of(self, v: int) -> float:
        d = self._max - self._min
        u = 0.0 if d <= 0 else (v - self._min) / float(d)
        return self.R + u * self._span()

    # ---- 交互 ----
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = True
            self.pressed.emit()
            self.setValue(self._value_at(e.position().x()))
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag:
            self.setValue(self._value_at(e.position().x()))
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._drag and e.button() == Qt.LeftButton:
            self._drag = False
            self.setValue(self._value_at(e.position().x()))
            self.released.emit()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def wheelEvent(self, e):
        e.ignore()

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        cy = self.height() / 2.0
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#1A1A1A"))
        p.drawRoundedRect(QRectF(0, cy - 1.5, self.width(), 3), 1.5, 1.5)
        kx = self._x_of(self._val)
        if kx > 0.5:
            p.setBrush(QColor("#6B6B6B"))
            p.drawRoundedRect(QRectF(0, cy - 1.5, kx, 3), 1.5, 1.5)
        p.setPen(QPen(QColor("#101010"), 1.0))
        p.setBrush(QColor("#FFFFFF" if (self._hover or self._drag) else "#DCDCDC"))
        p.drawEllipse(QPointF(kx, cy), self.R - 0.9, self.R - 0.9)
        p.end()


class ParamGroup(QWidget):
    """可折叠的参数分组：标题条点击展开 / 收起。

    builder 用来「用到时才建内容」：默认收起的组（形状动态 / 传递 / 纹理 /
    颜色动态 / 笔锋）启动时就不建那二十来个滑杆了 —— 建它们 + 把它们 setVisible(False)
    在启动路径上要花 200ms 左右，而用户一开始根本看不到。
    """

    toggled = Signal(bool)

    def __init__(self, title: str, expanded: bool = True, builder=None, parent=None):
        super().__init__(parent)
        self.title = title
        self._expanded = bool(expanded)
        self._builder = builder
        self._built = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        self.head = QWidget()
        self.head.setFixedHeight(20)
        self.head.setCursor(Qt.PointingHandCursor)
        hl = QHBoxLayout(self.head)
        hl.setContentsMargins(1, 0, 2, 0)
        hl.setSpacing(4)
        self.chev = QLabel("▾" if self._expanded else "▸")
        self.chev.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 9px;")
        hl.addWidget(self.chev)
        self.label = QLabel(title)
        self.label.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 10px; font-weight: bold;")
        hl.addWidget(self.label)
        hl.addStretch(1)
        self.head.mouseReleaseEvent = self._on_head_click
        lay.addWidget(self.head)

        # 必须先挂到布局里、再设可见性：无父控件的 QWidget 一旦 setVisible(True)
        # 就会立刻变成一个独立的顶层窗口 —— 启动时那个「一闪而过的小窗」就是这么来的
        # （640×480 的默认尺寸，出现在建画笔面板的时候）。
        self.body = QWidget(self)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(5)
        lay.addWidget(self.body)
        if self._expanded:
            self._build()
        self.body.setVisible(self._expanded)

    def _build(self):
        if self._built:
            return
        self._built = True
        if self._builder is not None:
            self._builder(self.body_layout)

    def _on_head_click(self, e):
        if e.button() == Qt.LeftButton:
            self.set_expanded(not self._expanded)

    def set_expanded(self, on: bool, emit: bool = True):
        on = bool(on)
        changed = on != self._expanded
        self._expanded = on
        if on:
            self._build()          # 第一次展开时才把滑杆建出来
        self.body.setVisible(on)
        self.chev.setText("▾" if on else "▸")
        if emit and changed:
            self.toggled.emit(on)

    def add(self, w):
        self._build()
        self.body_layout.addWidget(w)


class LabeledSlider(QWidget):
    valueChanged = Signal(float)

    def __init__(self, name: str, minimum: int, maximum: int, value: int,
                 suffix: str = "", parent=None, decimals: int = 0):
        super().__init__(parent)
        self.decimals = decimals
        self.suffix = suffix
        self._factor = 1.0 if decimals == 0 else 10 ** decimals
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(4)
        self.name = QLabel(name)
        self.name.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 10px;")
        self.value = QLabel()
        self.value.setStyleSheet(f"color: {C.TEXT}; font-size: 10px;")
        self.value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(self.name)
        top.addStretch(1)
        top.addWidget(self.value)
        lay.addLayout(top)
        self.slider = NoWheelSlider(Qt.Horizontal)
        self.slider.setRange(minimum, maximum)
        self.slider.setValue(value)
        self.slider.valueChanged.connect(self._on_change)
        self.slider.setFixedHeight(13)
        lay.addWidget(self.slider)
        self._update_text()

    def _fmt(self, v: int) -> str:
        if self.decimals:
            return f"{v / self._factor:.{self.decimals}f}{self.suffix}"
        return f"{v}{self.suffix}"

    def _update_text(self):
        self.value.setText(self._fmt(self.slider.value()))

    def _on_change(self, v):
        self._update_text()
        self.valueChanged.emit(v / self._factor)

    def set_value(self, real: float):
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(real * self._factor)))
        self.slider.blockSignals(False)
        self._update_text()


# ---------------------------------------------------------------- 自绘复选框
class CheckBox(QWidget):
    """自绘复选框：勾选后是白底蓝框 + 显式对勾，一眼能看出开没开。"""

    toggled = Signal(bool)

    def __init__(self, text: str, checked: bool = False, parent=None):
        super().__init__(parent)
        self._text = text
        self._checked = bool(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(20)
        f = QFont(self.font())
        f.setPointSizeF(9.0)
        self.setFont(f)
        fm = self.fontMetrics()
        self.setMinimumWidth(20 + fm.horizontalAdvance(text) + 4)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, on: bool, emit: bool = False):
        on = bool(on)
        if on == self._checked:
            return
        self._checked = on
        self.update()
        if emit:
            self.toggled.emit(on)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        box = QRectF(0.5, (self.height() - 13) / 2.0, 13, 13)
        if self._checked:
            p.setPen(QPen(QColor(C.ACCENT), 1.4))
            p.setBrush(QColor(C.ACCENT))
        else:
            p.setPen(QPen(QColor("#7A7A7A"), 1.3))
            p.setBrush(QColor(C.FIELD))
        p.drawRoundedRect(box, 2.5, 2.5)
        if self._checked:
            pen = QPen(QColor("#FFFFFF"), 2.0)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPolyline(QPolygonF([QPointF(3.4, 7.2), QPointF(6.0, 9.8),
                                      QPointF(10.8, 4.4)]))
        p.setPen(QColor(C.TEXT if self._checked else C.TEXT_DIM))
        p.drawText(QRectF(19, 0, self.width() - 19, self.height()),
                   Qt.AlignVCenter | Qt.AlignLeft, self._text)
        p.end()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.setChecked(not self._checked, emit=True)


# ---------------------------------------------------------------- 颜色
class SVSquare(QWidget):
    changed = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.h = 0.0
        self.s = 1.0
        self.v = 1.0
        self._grad = None
        self.setMinimumHeight(110)          # 默认就大一点：取色主要看这块
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.CrossCursor)

    def set_hue(self, h):
        self.h = h
        self._grad = None
        self.update()

    def set_sv(self, s, v):
        self.s, self.v = s, v
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        base = QColor.fromHsvF(self.h, 1.0, 1.0)
        g = QLinearGradient(r.topLeft(), r.topRight())
        g.setColorAt(0.0, QColor(255, 255, 255))
        g.setColorAt(1.0, base)
        p.fillRect(r, QBrush(g))
        g2 = QLinearGradient(r.topLeft(), r.bottomLeft())
        g2.setColorAt(0.0, QColor(0, 0, 0, 0))
        g2.setColorAt(1.0, QColor(0, 0, 0, 255))
        p.fillRect(r, QBrush(g2))
        p.setPen(QPen(QColor(0, 0, 0, 160), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r)

        x = r.left() + self.s * r.width()
        y = r.top() + (1.0 - self.v) * r.height()
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 190), 2))
        p.drawEllipse(QPointF(x, y), 5, 5)
        p.setPen(QPen(QColor(255, 255, 255, 230), 1.4))
        p.drawEllipse(QPointF(x, y), 5, 5)
        p.end()

    def _pick(self, pos):
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        self.s = max(0.0, min(1.0, (pos.x() - r.left()) / max(1.0, r.width())))
        self.v = max(0.0, min(1.0, 1.0 - (pos.y() - r.top()) / max(1.0, r.height())))
        self.changed.emit(self.s, self.v)
        self.update()

    def mousePressEvent(self, e):
        self._pick(QPointF(e.position()))

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._pick(QPointF(e.position()))


class HueBar(QWidget):
    changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.h = 0.0
        self.setFixedWidth(18)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.setCursor(Qt.SizeVerCursor)

    def set_hue(self, h):
        self.h = h
        self.update()

    def paintEvent(self, e):
        from PySide6.QtGui import QLinearGradient
        p = QPainter(self)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        for i in range(0, 7):
            g.setColorAt(i / 6.0, QColor.fromHsvF(min(0.999, i / 6.0), 1.0, 1.0))
        p.fillRect(r, QBrush(g))
        p.setPen(QPen(QColor(0, 0, 0, 140), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r)
        y = r.top() + self.h * r.height()
        p.setPen(QPen(QColor(0, 0, 0), 2))
        p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
        p.setPen(QPen(QColor(255, 255, 255), 1))
        p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
        p.end()

    def _pick(self, pos):
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        self.h = max(0.0, min(0.999, (pos.y() - r.top()) / max(1.0, r.height())))
        self.changed.emit(self.h)
        self.update()

    def mousePressEvent(self, e):
        self._pick(QPointF(e.position()))

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._pick(QPointF(e.position()))


class SwatchGrid(QWidget):
    picked = Signal(QColor)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.colors = [
            "#000000", "#404040", "#808080", "#BFBFBF", "#FFFFFF", "#7F0000", "#FF0000", "#FF7F00",
            "#FFD400", "#7FFF00", "#00A000", "#00FFFF", "#0070FF", "#00007F", "#7F00FF", "#FF00FF",
            "#8B5A2B", "#D2B48C", "#F5DEB3", "#2F4F4F", "#1E3A8A", "#4B0082", "#8B008B", "#FFC0CB",
        ]
        self.COLS = 12
        self.ROWS = 2
        self.setFixedHeight(42)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, e):
        p = QPainter(self)
        cols = self.COLS
        rows = self.ROWS
        w = self.width() / cols
        h = self.height() / rows
        for i, c in enumerate(self.colors[:cols * rows]):
            x = (i % cols) * w
            y = (i // cols) * h
            p.fillRect(QRectF(x, y, w - 1, h - 1), QColor(c))
            p.setPen(QPen(QColor(0, 0, 0, 120), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(x + 0.5, y + 0.5, w - 2, h - 2))
        p.end()

    def mousePressEvent(self, e):
        cols = self.COLS
        w = self.width() / cols
        h = self.height() / self.ROWS
        i = int(e.position().y() // h) * cols + int(e.position().x() // w)
        if 0 <= i < len(self.colors):
            self.picked.emit(QColor(self.colors[i]))


class RecentSwatches(QWidget):
    """最近使用的颜色：一行小色块，点一下就换前景色（重启软件后还在）。"""

    picked = Signal(QColor)
    SLOTS = 10

    def __init__(self, colors=None, slots=None, parent=None):
        super().__init__(parent)
        self.slots = int(slots or self.SLOTS)
        self.colors = list(colors or [])
        self.setFixedHeight(18)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)
        self._hover = -1
        self.setToolTip("最近使用过的颜色：点一下换成前景色\n"
                        "拖动色板 / 吸管取色都会记进来，关掉软件也不会丢")

    def set_colors(self, colors):
        self.colors = list(colors)[:self.slots]
        self.update()

    def _chip(self, i: int) -> QRectF:
        w = self.width() / max(1, self.slots)
        return QRectF(i * w, 0, max(4.0, w - 2.0), self.height() - 1)

    def _index_at(self, x: float) -> int:
        i = int(x // max(1.0, self.width() / max(1, self.slots)))
        return i if 0 <= i < len(self.colors) else -1

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        for i in range(self.slots):
            r = self._chip(i)
            if i < len(self.colors):
                p.fillRect(r, QColor(self.colors[i]))
                p.setPen(QPen(QColor(0, 0, 0, 130), 1))
            else:
                # 空槽画个虚位：行高不会因为颜色少就跳来跳去
                p.setPen(QPen(QColor(C.FIELD_BORDER), 1, Qt.DotLine))
                p.setBrush(QColor(C.FIELD))
                p.drawRect(r)
            p.setBrush(Qt.NoBrush)
            p.drawRect(r)
            if i == self._hover and i < len(self.colors):
                p.setPen(QPen(QColor(C.ACCENT), 2))
                p.drawRect(r.adjusted(0.5, 0.5, -0.5, -0.5))
        p.end()

    def mouseMoveEvent(self, e):
        i = self._index_at(e.position().x())
        if i != self._hover:
            self._hover = i
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def mousePressEvent(self, e):
        i = self._index_at(e.position().x())
        if 0 <= i < len(self.colors):
            self.picked.emit(QColor(self.colors[i]))


class RecentStore:
    """最近使用颜色的读写（颜色面板 / 文字颜色各存一份，互不干扰）。"""

    def __init__(self, key: str, slots: int = 10):
        self.key = key
        self.slots = slots

    @staticmethod
    def _settings():
        # 与主窗口同一组键：改名 U Draw 后老设置还能读回来
        return QSettings("PhotoCraftDraw", "PhotoCraftDraw")

    def load(self):
        try:
            vals = self._settings().value(self.key, [])
        except Exception:
            return []
        if isinstance(vals, str):
            vals = [vals]
        out = []
        for v in (vals or []):
            c = QColor(str(v))
            if c.isValid() and c.name() not in out:
                out.append(c.name())
        return out[:self.slots]

    def save(self, colors):
        try:
            self._settings().setValue(self.key, list(colors)[:self.slots])
        except Exception:
            pass

    def push(self, colors, hexv: str):
        """把新颜色插到最前，返回新列表（原地改也行，这里给个返回值方便用）。"""
        if colors and colors[0] == hexv:
            return colors
        if hexv in colors:
            colors.remove(hexv)
        colors.insert(0, hexv)
        del colors[self.slots:]
        self.save(colors)
        return colors


class ColorPanel(Section):
    colorChanged = Signal(QColor)

    def __init__(self, parent=None):
        super().__init__("颜色", parent, scroll=True)
        self.color = QColor(20, 20, 20)
        self._h = 0.0
        self._s = 1.0
        self._v = 0.9
        self._updating = False

        row = QHBoxLayout()
        row.setSpacing(6)
        self.sv = SVSquare()
        self.hue = HueBar()
        self.sv.changed.connect(self._from_sv)
        self.hue.changed.connect(self._from_hue)
        row.addWidget(self.sv, 1)
        row.addWidget(self.hue)
        self.body_layout.addLayout(row)

        line = QHBoxLayout()
        line.setSpacing(5)
        self.fg = QToolButton()
        self.fg.setFixedSize(30, 24)
        self.fg.setToolTip("前景色")
        self.fg.setStyleSheet(
            f"QToolButton {{ background: {C.FIELD}; border: 1px solid #8A8A8A; border-radius: 3px; }}")
        self.fg.paintEvent = self._paint_fg
        line.addWidget(self.fg)

        self.hex = QLineEdit("#141414")
        self.hex.setFixedHeight(24)
        self.hex.setMaxLength(7)
        self.hex.editingFinished.connect(self._from_hex)
        line.addWidget(self.hex, 1)
        self.body_layout.addLayout(line)

        self.swatches = SwatchGrid()
        self.swatches.picked.connect(self.set_color)
        self.body_layout.addWidget(self.swatches)

        # 最近使用：标题 + 一行色块（持久化到 QSettings，重启还在）
        self._recent = self._load_recent()
        self._pending = None
        self._recent_timer = QTimer(self)
        self._recent_timer.setSingleShot(True)
        self._recent_timer.setInterval(700)      # 拖色板时只在停手后记一次
        self._recent_timer.timeout.connect(self._commit_recent)

        head = QLabel("最近")
        head.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 9px;")
        head.setFixedWidth(24)
        head.setToolTip("最近使用过的颜色")
        self.recent = RecentSwatches(self._recent)
        self.recent.picked.connect(self.set_color)
        rec_row = QHBoxLayout()
        rec_row.setContentsMargins(0, 0, 0, 0)
        rec_row.setSpacing(4)
        rec_row.addWidget(head)
        rec_row.addWidget(self.recent, 1)
        self.body_layout.addLayout(rec_row)
        self.colorChanged.connect(self._note_recent)

        self._sync_widgets()

    # -- 最近使用
    @staticmethod
    def _settings():
        return RecentStore._settings()

    def _load_recent(self):
        return RecentStore("color/recent", RecentSwatches.SLOTS).load()

    def _save_recent(self):
        RecentStore("color/recent", RecentSwatches.SLOTS).save(self._recent)

    def _note_recent(self, c: QColor):
        self._pending = QColor(c)
        self._recent_timer.start()

    def _commit_recent(self):
        c = self._pending
        if c is None:
            return
        before = list(self._recent)
        RecentStore("color/recent", RecentSwatches.SLOTS).push(self._recent, c.name())
        if self._recent != before:
            self.recent.set_colors(self._recent)

    # -- 绘制前景色块
    def _paint_fg(self, e):
        p = QPainter(self.fg)
        p.fillRect(self.fg.rect().adjusted(0, 0, -1, -1), self.color)
        p.setPen(QPen(QColor(0, 0, 0, 180), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(self.fg.rect().adjusted(0, 0, -1, -1))
        p.end()

    def _sync_widgets(self):
        self._updating = True
        h, s, v, _ = self.color.getHsvF()
        if h is not None and h >= 0:
            self._h = h
        self._s, self._v = s, v
        self.sv.set_hue(self._h)
        self.sv.set_sv(self._s, self._v)
        self.hue.set_hue(self._h)
        self.hex.setText(hex_str(self.color).lower())
        self._updating = False
        self.fg.update()

    def _from_sv(self, s, v):
        if self._updating:
            return
        self._s, self._v = s, v
        self.sv.set_hue(self._h)
        self.hue.set_hue(self._h)
        c = QColor.fromHsvF(self._h, s, v)
        self.color = c
        self._updating = True
        self.hex.setText(hex_str(c).lower())
        self._updating = False
        self.fg.update()
        self.colorChanged.emit(QColor(c))

    def _from_hue(self, h):
        if self._updating:
            return
        self._h = h
        # 当前是黑/灰（饱和度≈0）时，只转色相是看不到颜色的，
        # 这里自动给一点饱和度，让拖动色相条立刻出现对应颜色。
        if self._s < 0.10:
            # 黑色/深灰：给足饱和度和亮度，拖色相就能直接看到那个颜色
            self._s = 1.0
            self._v = max(self._v, 0.65)
        self.sv.set_hue(h)
        self.sv.set_sv(self._s, self._v)
        c = QColor.fromHsvF(h, self._s, self._v)
        self.color = c
        self._updating = True
        self.hex.setText(hex_str(c).lower())
        self._updating = False
        self.fg.update()
        self.colorChanged.emit(QColor(c))

    def _from_hex(self):
        if self._updating:
            return
        t = self.hex.text().strip()
        if not t.startswith("#"):
            t = "#" + t
        c = QColor(t)
        if c.isValid():
            self.set_color(c)
        else:
            self.hex.setText(hex_str(self.color).lower())

    def set_color(self, c: QColor):
        self.color = QColor(c)
        self._sync_widgets()
        self.colorChanged.emit(QColor(self.color))


# ---------------------------------------------------------------- 笔刷
class BrushPreviewPopup(QWidget):
    """悬停试笔浮窗：鼠标停在预设格子上才弹出，不占预设区的宽度。

    以前试笔条常驻在预设区右侧（210px），笔一多就少看好几列；改成浮窗后
    整条宽度都留给格子，想细看哪支停一下就行。
    """

    W, H = 340, 150

    def __init__(self, parent=None):
        super().__init__(parent, Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)   # 不抢鼠标，移开就消失
        self.setFixedSize(self.W, self.H)
        self.brush = None

    def show_for(self, brush: Brush, chip: QWidget):
        self.brush = brush
        g = chip.mapToGlobal(QPoint(chip.width() // 2, 0))
        scr = QGuiApplication.screenAt(g) or QGuiApplication.primaryScreen()
        avail = scr.availableGeometry() if scr is not None else QRect(0, 0, 1920, 1080)
        x = g.x() - self.W // 2
        y = g.y() - self.H - 8
        if y < avail.top() + 4:              # 上面放不下就翻到格子下面
            y = chip.mapToGlobal(QPoint(0, chip.height())).y() + 8
        x = max(avail.left() + 4, min(x, avail.right() - self.W - 4))
        self.move(x, y)
        self.show()
        self.raise_()
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setBrush(QColor(C.CARD))
        p.setPen(QPen(QColor(C.FIELD_BORDER), 1))
        p.drawRoundedRect(QRectF(0.5, 0.5, self.W - 1, self.H - 1), 6, 6)
        b = self.brush
        if b is None:
            p.end()
            return
        f = QFont(self.font())
        f.setPointSizeF(9.5)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(C.TEXT))
        p.drawText(QRectF(12, 7, self.W - 24, 18), Qt.AlignLeft | Qt.AlignVCenter, b.name)
        f.setBold(False)
        f.setPointSizeF(8.0)
        p.setFont(f)
        p.setPen(QColor(C.TEXT_FAINT))
        p.drawText(QRectF(12, 7, self.W - 24, 18), Qt.AlignRight | Qt.AlignVCenter,
                   f"{KIND_NAMES.get(b.kind, b.kind)} · {int(round(b.size))}px")
        p.drawPixmap(QPointF(12, 29), popup_pixmap(b))
        p.end()


class PresetChip(QWidget):
    """画笔预设小方块：名字 + 一笔真实样品。"""

    W, H = 78, 54

    def __init__(self, brush: Brush, parent=None):
        super().__init__(parent)
        self.brush = brush
        self.selected = False
        self.idx = -1               # 在 panel.presets 里的下标（分类筛选后不再是行号）
        self.setFixedSize(self.W, self.H)
        self.setCursor(Qt.PointingHandCursor)
        self.refresh_tooltip()

    def refresh_tooltip(self):
        b = self.brush
        self.setToolTip(
            f"画笔：{b.name}\n分类：{b.group} · 笔型：{KIND_NAMES.get(b.kind, b.kind)}\n"
            f"{brushes.brush_description(b)}\n大小：{b.size:g} px")

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        bg = QColor(C.PRESSED) if self.selected else QColor(C.FIELD)
        p.setBrush(bg)
        p.setPen(QPen(QColor(C.ACCENT if self.selected else C.FIELD_BORDER),
                      1.4 if self.selected else 1.0))
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.H - 1), 4, 4)

        p.drawPixmap(QPointF(5, 18), thumb_pixmap(self.brush))

        p.setPen(QColor(C.TEXT if self.selected else C.TEXT_DIM))
        f = QFont(self.font())
        f.setPointSizeF(8.0)
        f.setBold(self.selected)
        p.setFont(f)
        if self.selected:
            p.fillRect(QRectF(3, 4, 3, 10), QColor(C.ACCENT))
        fm = p.fontMetrics()
        name = fm.elidedText(self.brush.name, Qt.ElideRight, self.width() - 16)
        p.drawText(QRectF(2, 2, self.width() - 4, 14), Qt.AlignCenter, name)
        p.end()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and getattr(self, "panel", None) is not None:
            self.panel.select_chip(self)

    def enterEvent(self, e):
        super().enterEvent(e)
        if getattr(self, "panel", None) is not None:
            self.panel.hover_chip(self)

    def leaveEvent(self, e):
        super().leaveEvent(e)
        if getattr(self, "panel", None) is not None:
            self.panel.unhover_chip(self)

    def mouseDoubleClickEvent(self, e):
        # 双击改名（内置笔也能改，原名会记下来，「重置」照样能用）
        if e.button() == Qt.LeftButton and getattr(self, "panel", None) is not None:
            self.panel.rename_chip(self)

    def contextMenuEvent(self, e):
        if getattr(self, "panel", None) is not None:
            self.panel.chip_menu(self, e.globalPos())


class NewBrushChip(QWidget):
    """预设网格末尾的「＋ 新建画笔」格子：选择笔型，创建一支新笔。"""

    W, H = 96, 54

    def __init__(self, panel, parent=None):
        super().__init__(parent)
        self.panel = panel
        self.idx = -1               # 它不是某一支笔，选中状态永远不落到它身上
        self.setFixedSize(self.W, self.H)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("选择笔型创建新画笔（也可以点标题栏的「＋ 新建」）")

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(QColor(C.FIELD_BORDER), 1.2, Qt.DashLine))
        p.setBrush(QColor(C.FIELD))
        p.drawRoundedRect(QRectF(0.6, 0.6, self.width() - 1.2, self.H - 1.2), 4, 4)
        p.setPen(QColor(C.TEXT_DIM))
        f = QFont(self.font())
        f.setPointSizeF(13)
        p.setFont(f)
        p.drawText(QRectF(0, 6, self.width(), 26), Qt.AlignCenter, "＋")
        f.setPointSizeF(8.5)
        p.setFont(f)
        p.setPen(QColor(C.TEXT_FAINT))
        p.drawText(QRectF(0, 32, self.width(), 16), Qt.AlignCenter, "新建画笔")
        p.end()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.panel is not None:
            self.panel.new_preset()


class FlowLayout(QLayout):
    """自动换行的横向布局：分类标签多到放不下时自己折到下一行，不会被切掉。"""

    def __init__(self, parent=None, margin=0, spacing=4):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return s + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect, test):
        m = self.contentsMargins()
        eff = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        sp = self.spacing()
        x, y, line_h = eff.x(), eff.y(), 0
        for it in self._items:
            hint = it.sizeHint()
            w, h = hint.width(), hint.height()
            if x + w > eff.right() + 1 and line_h > 0:
                x = eff.x()
                y += line_h + sp
                line_h = 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), QSize(w, h)))
            x += w + sp
            line_h = max(line_h, h)
        return y + line_h - rect.y() + m.bottom()


class MiddleDragScroll(QObject):
    """按住鼠标中键上下拖动 = 滚动。

    笔刷格子铺满整个区域，靠右边的滚动条太细；中键拖动是建模/画图软件的老习惯，
    长列表里比去抓滚动条顺手得多。
    """

    def __init__(self, area: QScrollArea):
        super().__init__(area)
        self.area = area
        self._start = None
        area.viewport().installEventFilter(self)

    def _mine(self, obj) -> bool:
        vp = self.area.viewport()
        return obj is vp or (isinstance(obj, QWidget) and vp.isAncestorOf(obj))

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == QEvent.MouseButtonPress and ev.button() == Qt.MiddleButton:
            if not self._mine(obj):
                return False
            bar = self.area.verticalScrollBar()
            self._start = (ev.globalPosition().y(), bar.value())
            self.area.viewport().setCursor(Qt.ClosedHandCursor)
            return True
        if t == QEvent.MouseMove and self._start is not None:
            dy = ev.globalPosition().y() - self._start[0]
            self.area.verticalScrollBar().setValue(int(self._start[1] - dy))
            return True
        if t == QEvent.MouseButtonRelease and ev.button() == Qt.MiddleButton:
            if self._start is not None:
                self._start = None
                self.area.viewport().unsetCursor()
                return True
        return False


class PresetBar(Section):
    """画布下方的画笔库：分类 / 搜索 / 视图筛选，网格滚动和悬停试笔。"""

    CHIP_W = 96

    def __init__(self, panel, parent=None):
        super().__init__("画笔", parent)
        self.panel = panel
        self.chips = []
        self._cols = 0
        self._rebuilding = False
        self._stale = False          # 重建过程中又被 resize 了：结束后要再排一次
        self._pending_cols = False   # 已经排了一次「下一轮再量宽度」
        self._built_once = False
        self._restoring = True
        self.count_label = QLabel()
        self.count_label.setToolTip("当前筛选结果 / 全部笔刷；滚轮上下翻，参数在右侧调")
        self.count_label.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 9px;")
        self.head_extra.addWidget(self.count_label)

        b_library = QToolButton()
        b_library.setText("打开笔刷库")
        b_library.setCursor(Qt.PointingHandCursor)
        b_library.setToolTip("大窗口按分类浏览，查看真实笔触和持久保存的最近使用")
        b_library.clicked.connect(self.open_library)
        self.head_extra.addWidget(b_library)

        # 明确写出来的「＋ 新建画笔」：光靠一个 + 图标，很多人不知道笔是怎么加进来的
        b_new = QToolButton()
        b_new.setText("＋ 新建")
        b_new.setFixedHeight(18)
        b_new.setCursor(Qt.PointingHandCursor)
        b_new.setToolTip("选择笔型创建一支新画笔，保存到「我的」")
        b_new.setStyleSheet(
            f"QToolButton {{ border: 1px solid {C.FIELD_BORDER}; border-radius: 3px;"
            f" background: transparent; color: {C.TEXT_DIM}; font-size: 9px; padding: 0 6px; }}"
            f"QToolButton:hover {{ background: {C.HOVER}; color: {C.TEXT}; }}")
        b_new.clicked.connect(lambda: panel.new_preset())
        self.head_extra.addWidget(b_new)

        # 操作按钮放标题条上：不占预设区
        # （「新建画笔」已经在左边写成文字按钮了，这里不再放 + 图标，免得出现两个）
        for ic, tip, slot in (
                ("trash", "删除当前自建画笔", panel.delete_preset),
                ("up", "把当前画笔导出为 .pcbrush", panel.export_preset),
                ("down", "导入 .pcbrush / 预设包", panel.import_preset)):
            b = QToolButton()
            b.setFixedSize(18, 18)
            b.setIcon(icons.icon(ic, C.TEXT_DIM, 12))
            b.setToolTip(tip)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                "QToolButton { border: none; background: transparent; border-radius: 3px; }"
                f"QToolButton:hover {{ background: {C.HOVER}; }}")
            b.clicked.connect(lambda _c=False, sl=slot: sl())
            self.head_extra.addWidget(b)

        filters = QHBoxLayout()
        filters.setContentsMargins(0, 0, 0, 0)
        filters.setSpacing(4)
        self.category_combo = QComboBox()
        self.category_combo.setToolTip("按分类筛选；与搜索共同生效")
        self.category_combo.setMinimumWidth(66)
        self.category_combo.setMaximumWidth(170)
        self.category_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.category_combo.setMinimumContentsLength(3)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索笔刷")
        self.search_edit.setToolTip("搜索名字、英文笔型、中文笔型 / 分类或描述；空格分隔多个关键词")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMinimumWidth(40)
        for w in (self.category_combo, self.search_edit):
            w.setFixedHeight(24)
            w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        filters.addWidget(self.category_combo, 1)
        filters.addWidget(self.search_edit, 3)
        self.recent_button = QToolButton()
        self.recent_button.setFixedHeight(24)
        self.recent_button.setCursor(Qt.PointingHandCursor)
        self.recent_button.clicked.connect(self.show_recent)
        filters.addWidget(self.recent_button)
        self.body_layout.addLayout(filters)
        self.category_combo.currentIndexChanged.connect(self._filters_changed)
        self.search_edit.textChanged.connect(self._filters_changed)

        self.strip = QScrollArea()
        self.strip.setFrameShape(QFrame.NoFrame)
        self.strip.setWidgetResizable(True)
        self.strip.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)   # 常显，方便拖
        self.strip.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.strip.setStyleSheet(f"background: {C.CARD}; border: none;")
        self._mid_drag = MiddleDragScroll(self.strip)      # 中键拖动滚动
        self.strip_host = QWidget()
        self.strip_host.setStyleSheet(f"background: {C.CARD};")
        self.grid = QGridLayout(self.strip_host)
        self.grid.setContentsMargins(1, 1, 1, 1)
        self.grid.setSpacing(4)
        self.grid.setSizeConstraint(QLayout.SetNoConstraint)
        self.strip.setWidget(self.strip_host)

        # 试笔预览改成「悬停浮窗」：以前它常驻在右边，占掉 210px，
        # 笔多了一行就少看好几支 —— 现在把整条宽度都留给预设格子，
        # 鼠标停在某一支上才弹出大图预览。
        self.popup = BrushPreviewPopup()
        self._hover_chip = None
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(220)      # 扫过去不弹，停一下才弹
        self._hover_timer.timeout.connect(self._show_hover_preview)
        # 滚轮事件被滚动区吃掉了，滚的时候从滚动条这里把浮窗收掉
        self.strip.verticalScrollBar().valueChanged.connect(
            lambda _v: self.hide_preview())

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(self.strip, 1)
        self.body_layout.addLayout(row, 1)
        browse = panel.meta.get("browse", {})
        search = browse.get("search", "")
        self.search_edit.setText(search if isinstance(search, str) else "")
        self._sync_categories()
        category = browse.get("category")
        if category is None or isinstance(category, str):
            self.category_combo.setCurrentIndex(max(0, self.category_combo.findData(category)))
        self._sync_recent_button()
        self._restoring = False
        # 首次真正显示时才建格子：启动窗口先出来，不再被 134 个控件卡住。

    def open_library(self):
        from brush_library_view import BrushLibraryWindow
        if getattr(self, "_library_window", None) is None:
            self._library_window = BrushLibraryWindow(self.panel, self.window())
        else:
            self._library_window.group = self.category_combo.currentData()
            blocked = self._library_window.search.blockSignals(True)
            self._library_window.search.setText(self.search_edit.text())
            self._library_window.search.blockSignals(blocked)
            self._library_window.refresh()
        self._library_window.show()
        self._library_window.raise_()
        self._library_window.activateWindow()

    def browse_state(self):
        return {"category": self.category_combo.currentData(),
                "search": self.search_edit.text()}

    def _filters_changed(self, *_):
        if self._restoring or self._rebuilding:
            return
        self.rebuild()
        self._sync_recent_button()
        self.panel.meta["browse"] = self.browse_state()
        self.panel._save()

    def _sync_recent_button(self):
        """在最近使用时按钮变成「全部笔刷」，让新用户知道怎么切回去。"""
        in_recent = self.category_combo.currentData() == brushes.RECENT_GROUP
        self.recent_button.setText("全部笔刷" if in_recent else "最近使用")
        self.recent_button.setToolTip(
            "切回全部 133 支画笔" if in_recent
            else "按最近使用顺序显示；关闭软件后仍保留")
        self.recent_button.setStyleSheet(
            f"QToolButton {{ border: 1px solid {C.ACCENT if in_recent else C.FIELD_BORDER};"
            f" border-radius: 3px; background: {C.PRESSED if in_recent else 'transparent'};"
            f" color: {C.TEXT if in_recent else C.TEXT_DIM}; font-size: 9px; padding: 0 7px; }}"
            f"QToolButton:hover {{ background: {C.HOVER}; color: {C.TEXT}; }}")

    def show_recent(self):
        target = None if self.category_combo.currentData() == brushes.RECENT_GROUP \
            else brushes.RECENT_GROUP
        self.category_combo.setCurrentIndex(max(0, self.category_combo.findData(target)))

    def _matches(self, brush):
        words = self.search_edit.text().casefold().split()
        text = " ".join((brush.name, brush.kind, KIND_NAMES.get(brush.kind, brush.kind),
                         brush.group, brushes.brush_description(brush))).casefold()
        return all(word in text for word in words)

    def _sync_categories(self):
        groups = self.panel.groups()
        counts = {g: 0 for g in groups}
        total = 0
        for brush in self.panel.presets:
            if self._matches(brush):
                counts[brush.group] = counts.get(brush.group, 0) + 1
                total += 1
        recent_count = sum(self._matches(b) for _, b in self.panel.recent_presets())
        favorite_count = sum(self._matches(b) for _, b in self.panel.favorite_presets())
        entries = [(f"全部 ({total})", None),
                   (f"最近使用 ({recent_count})", brushes.RECENT_GROUP),
                   (f"常用 ({favorite_count})", brushes.FAVORITE_GROUP)]
        entries.extend((f"{g} ({counts.get(g, 0)})", g)
                       for g in groups if g != USER_GROUP)
        entries.append((f"我的 ({counts.get(USER_GROUP, 0)})", USER_GROUP))
        if [(self.category_combo.itemText(i), self.category_combo.itemData(i))
                for i in range(self.category_combo.count())] == entries:
            return
        selected = self.category_combo.currentData()
        blocked = self.category_combo.blockSignals(True)
        try:
            self.category_combo.clear()
            for text, group in entries:
                self.category_combo.addItem(text, group)
            idx = self.category_combo.findData(selected)
            self.category_combo.setCurrentIndex(max(0, idx))
        finally:
            self.category_combo.blockSignals(blocked)

    def refresh_cats(self):
        """分类增删后更新选项，保留仍然存在的筛选。"""
        self.rebuild()

    def filtered_presets(self):
        group = self.category_combo.currentData()
        if group == brushes.RECENT_GROUP:
            return [(idx, brush) for idx, brush in self.panel.recent_presets()
                    if self._matches(brush)]
        if group == brushes.FAVORITE_GROUP:
            return [(idx, brush) for idx, brush in self.panel.favorite_presets()
                    if self._matches(brush)]
        return [(idx, brush) for idx, brush in enumerate(self.panel.presets)
                if (group is None or brush.group == group) and self._matches(brush)]

    def show_added(self, indices):
        """新建 / 导入后清除旧搜索，显示新增笔所在分类；不替用户另选一支笔。"""
        groups = {self.panel.presets[i].group for i in indices}
        self._sync_categories()
        for w in (self.category_combo, self.search_edit):
            blocked = w.blockSignals(True)
            try:
                if w is self.category_combo:
                    group = next(iter(groups)) if len(groups) == 1 else None
                    w.setCurrentIndex(max(0, w.findData(group)))
                else:
                    w.clear()
            finally:
                w.blockSignals(blocked)
        self.rebuild()
        self._sync_recent_button()

    def _build_chip_menu(self, chip) -> QMenu:
        """右键菜单。单独拆出来，方便自检直接检查菜单项（不用真的弹出来）。"""
        b = chip.brush
        menu = QMenu(self)
        key = brushes.brush_key(b)
        is_favorite = key in set(self.panel.meta.get("favorites") or [])
        act = menu.addAction("从常用移除" if is_favorite else "添加到常用")
        act.triggered.connect(lambda: self.panel.toggle_favorite(chip.idx))
        # 只在这支笔确实在「最近使用」里时才给这一项
        recent = set(brushes.clean_recent(self.panel.presets,
                                          self.panel.meta.get("recent")))
        if key in recent:
            act = menu.addAction("从最近使用中移除")
            act.triggered.connect(lambda: self.panel.forget_recent(chip.idx))
        menu.addSeparator()
        act = menu.addAction("重命名…")
        act.triggered.connect(lambda: self.panel.rename_preset(chip.idx))
        menu.addSeparator()
        act = menu.addAction("导出这支笔…")
        act.triggered.connect(lambda: self.panel.export_preset(chip.idx))
        if builtin_origin(b) is None:
            act = menu.addAction("删除这支笔")
            act.triggered.connect(lambda: self.panel.delete_preset(chip.idx))
        return menu

    def chip_menu(self, chip, pos):
        self.hide_preview()
        self._build_chip_menu(chip).exec(pos)

    # ---- 悬停试笔 ----
    def hover_chip(self, chip):
        self._hover_chip = chip
        self._hover_timer.start()

    def unhover_chip(self, chip):
        if self._hover_chip is chip:
            self._hover_chip = None
            self._hover_timer.stop()
            self.popup.hide()

    def _show_hover_preview(self):
        chip = self._hover_chip
        if chip is None or not chip.isVisible():
            return
        self.popup.show_for(chip.brush, chip)

    def refresh_preview(self):
        """参数滑杆拖动时刷新浮窗（没显示就什么也不做）。"""
        if self.popup.isVisible():
            self.popup.update()

    def hide_preview(self):
        self._hover_chip = None
        self._hover_timer.stop()
        self.popup.hide()

    def wheelEvent(self, e):
        self.hide_preview()        # 一滚就收，别让浮窗挂在半空
        super().wheelEvent(e)

    # ---- 视图 ----
    def sizeHint(self):
        # 预设格子有 100 多支，网格的 sizeHint 会撑到几百像素高；分栏按 sizeHint
        # 分配高度时就会把画布挤扁。这里固定成「分类标签 + 两三排笔」的高度。
        return QSize(super().sizeHint().width(), 236)

    def minimumSizeHint(self):
        return QSize(200, 140)

    def _cols_for(self, width: int) -> int:
        return max(1, max(0, width + 2) // (self.CHIP_W + 4))

    def rebuild(self):
        if self._rebuilding:
            # 重建过程中布局会再触发一次 resize，这时不能重入（会递归），
            # 但也不能直接丢掉 —— 否则列数会停在窗口还没铺开时算出的值，
            # 结果画笔格子只占左边一半、右边空一大片。
            self._stale = True
            return
        self._rebuilding = True
        try:
            self._rebuild_grid()
            self._built_once = True
        finally:
            self._rebuilding = False
        if self._stale:
            self._stale = False
            QTimer.singleShot(0, self.rebuild)

    def _rebuild_grid(self):
        self.hide_preview()
        self._sync_categories()
        while self.grid.count():
            it = self.grid.takeAt(0)
            w = it.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self.chips = []
        cols = self._cols_for(self.strip.viewport().width())
        self._cols = cols
        # 清除旧拉伸，让少量结果仍靠左、靠上；按视口宽度换行。
        for c in range(self.grid.columnCount()):
            self.grid.setColumnStretch(c, 0)
        for r in range(self.grid.rowCount()):
            self.grid.setRowStretch(r, 0)
        self.grid.setColumnStretch(cols, 1)
        shown = self.filtered_presets()
        for n, (i, preset) in enumerate(shown):
            chip = PresetChip(preset)
            chip.panel = self
            chip.idx = i
            chip.selected = (i == self.panel.current)
            chip.setFixedWidth(self.CHIP_W)
            self.chips.append(chip)
            self.grid.addWidget(chip, n // cols, n % cols)
        # 末尾放一个「＋ 新建画笔」格子：不用记标题栏那个小图标，滚到底就能加笔
        new_chip = NewBrushChip(self.panel)
        new_chip.setFixedWidth(self.CHIP_W)
        self.chips.append(new_chip)
        n = len(shown)
        if not shown:
            category = self.category_combo.currentData()
            if category == brushes.RECENT_GROUP and not self.panel.recent_presets():
                message = "使用画笔后会自动记录，关闭软件也会保留。"
            elif category == brushes.FAVORITE_GROUP and not self.panel.favorite_presets():
                message = "右键任意画笔，选择「添加到常用」；关闭软件后仍会保留。"
            else:
                message = "没有符合条件的笔刷，请更换分类或清除搜索。"
            empty = QLabel(message)
            empty.setWordWrap(True)
            empty.setMinimumWidth(0)
            empty.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 10px;")
            self.grid.addWidget(empty, 0, 0, 1, cols)
            self.grid.addWidget(new_chip, 1, 0)
            rows = 2
        else:
            self.grid.addWidget(new_chip, n // cols, n % cols)
            rows = n // cols + 1
        self.grid.setRowStretch(rows, 1)
        self.strip_host.setMinimumHeight(rows * (PresetChip.H + 4) + 2)
        self.count_label.setText(f"{len(shown)}/{len(self.panel.presets)}")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # 不能在 resizeEvent 里直接量视口宽度：这时候布局还没算完，
        # viewport().width() 还是旧值，算出来的列数和原来一样 → 不重建，
        # 结果窗口拉宽后格子仍只占左边一半（用户反馈的「排列有问题」）。
        # 推到下一轮事件循环再量，宽度才是最终的。
        if self._pending_cols:
            return
        self._pending_cols = True
        QTimer.singleShot(0, self._check_cols)

    def _check_cols(self):
        self._pending_cols = False
        if self._cols_for(self.strip.viewport().width()) != self._cols:
            self.rebuild()

    def showEvent(self, e):
        # 首次显示：等布局算完再建卡片（宽度未知时建会排错列数）。
        # 列数变化由 resizeEvent 负责，这里不重复处理。
        super().showEvent(e)
        if not self._built_once:
            QTimer.singleShot(0, self.rebuild)

    def set_current(self, idx: int):
        for chip in self.chips:
            chip.selected = (chip.idx == idx)
            chip.update()
        for chip in self.chips:
            if chip.idx == idx:
                self.strip.ensureWidgetVisible(chip, 20, 20)
                break

    def refresh_current(self):
        shown = [idx for idx, _brush in self.filtered_presets()]
        if shown != [chip.idx for chip in self.chips if chip.idx >= 0]:
            self.rebuild()
        for chip in self.chips:
            if isinstance(chip, PresetChip):
                chip.refresh_tooltip()
        self.set_current(self.panel.current)

    def select_chip(self, chip):
        if chip in self.chips:
            self.panel.select_index(chip.idx)

    def rename_chip(self, chip):
        if chip in self.chips:
            self.panel.rename_preset(chip.idx)


# 参数滑杆的说明文字（放在模块级：懒建滑杆时按 attr 查）
_PARAM_TIPS = {
    "grain": "纸纹颗粒强度：铅笔 / 蜡笔的粗糙感就靠它",
    "grain_scale": "颗粒粗细：1 px 像铅笔纸纹，5~6 px 像蜡笔 / 炭笔的成块颗粒",
    "press_curve": (
        "轻压灵敏度：往右拖，轻轻落笔也能画出可见的线（默认 75%）。\n"
        "数位板送来的压力大多落在 0.05~0.4 这一段，线性映射下轻压只有\n"
        "1~2px，看着像「画不出来」。这条曲线把轻压抬起来，粗细变化仍然\n"
        "是从细到粗，不会变成等粗线。\n"
        "手重、觉得轻压太粗的话，往左拖到 40% 以下即可。"),
    "pattern_scale": "图案尺度（px），控制网点、排线等图案的疏密；默认 12 px",
    "color_cycle": "颜色循环长度（px），控制彩虹等变色笔刷沿笔画的循环速度；默认 240 px",
    "spacing": "笔点间距（占笔尖直径的比例）：调大能画出一个个笔点",
    "angle_follow": (
        "笔尖跟着运笔方向转：0% 固定角度，100% 永远顺着笔画走。\n"
        "扁头马克笔、油画笔、纤维笔都靠它，转弯时笔锋才不会「歪掉」。"),
    "size": "笔尖直径（px）。[ ] 快捷键、Ctrl+滚轮也能调",
    "opacity": "整笔浓度上限；关闭「逐笔叠色」时反复描画不超过此浓度。\n"
               "开启「逐笔叠色」后，多次落笔可继续加深。",
    "flow": "每笔出墨量；低流量更淡。「逐笔叠色」决定多次落笔能否继续加深。",
}


class BrushPanel(Section):
    changed = Signal()
    presetChanged = Signal()

    # 参数分组：照原版 PhotoCraft 的「画笔设置」分区（笔尖 / 形状动态 / 传递 / 纹理 / 颜色动态 / 笔锋）
    # (属性, 显示名, 最小, 最大, 后缀, 是百分比)
    GROUPS = [
        ("笔尖形状", [("size", "大小", 1, 600, " px", False),
                      ("roundness", "圆度", 5, 100, " %", True),
                      ("angle", "角度", -180, 180, "°", False),
                      ("hardness", "硬度", 0, 100, " %", True),
                      ("spacing", "间距", 1, 400, " %", True)]),
        ("形状动态", [("size_jitter", "大小抖动", 0, 100, " %", True),
                      ("roundness_jitter", "圆度抖动", 0, 100, " %", True),
                      ("angle_jitter", "角度抖动", 0, 100, " %", True),
                      ("angle_follow", "角度跟随笔画", 0, 100, " %", True),
                      ("scatter", "散布", 0, 100, " %", True),
                      ("scatter_count", "散布数量", 1, 8, "", False)]),
        ("传递", [("opacity", "不透明度", 1, 100, " %", True),
                  ("flow", "流量", 1, 100, " %", True),
                  ("flow_jitter", "流量抖动", 0, 100, " %", True),
                  ("press_curve", "轻压灵敏度", 0, 100, " %", True)]),
        ("纹理", [("grain", "颗粒", 0, 100, " %", True),
                  ("grain_scale", "颗粒粗细", 1, 8, " px", False),
                  ("pattern_scale", "图案尺度", 2, 256, " px", False),
                  ("wet", "湿边", 0, 100, " %", True)]),
        ("颜色动态", [("hue_jitter", "色相抖动", 0, 100, " %", True),
                      ("sat_jitter", "饱和度抖动", 0, 100, " %", True),
                      ("val_jitter", "明度抖动", 0, 100, " %", True),
                      ("color_cycle", "颜色循环长度", 8, 8192, " px", False)]),
        ("笔锋", [("taper", "起笔渐细", 0, 100, " %", True),
                  ("min_size", "最小直径", 0, 100, " %", True)]),
    ]

    def __init__(self, brush: Brush, parent=None):
        # 参数面板（放右栏）：预设条在画布下面，这里只管预览 + 参数
        super().__init__("画笔", parent, scroll=True)
        self.brush = brush
        # True = 这支笔是预设库里的画笔；False = 橡皮 / 涂抹自己的笔尖，
        # 改参数只写回它自己，绝不覆盖画笔预设
        self.presets_owned = True
        self.presets, self.meta = load_library()
        self.current = 0
        self.bar = None               # 底部预设条（由主窗口挂上）
        self.sliders = {}
        self._syncing = False
        self._dragging = False
        # 拖动滑杆时，重画试笔条 / 缩略图 / 画布要 20~30ms，逐帧做会让滑杆掉帧、看着有延迟。
        # 这里把重活合并成 33ms 一次（约 30fps），滑杆本身和数字始终保持即时响应。
        self._flush = QTimer(self)
        self._flush.setSingleShot(True)
        self._flush.setInterval(33)
        self._flush.timeout.connect(self._refresh_visuals)
        # 调参数后延迟存盘：滑杆一拖是几十次改动，不能每次都写文件
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(1200)
        self._save_timer.timeout.connect(self._save)

        # 「重置这支笔」放在参数面板上（新建/删除/导入导出在下面的预设条上）
        b_reset = QToolButton()
        b_reset.setText("重置")
        b_reset.setFixedHeight(17)
        b_reset.setToolTip("把当前这支笔恢复成内置默认参数")
        b_reset.setCursor(Qt.PointingHandCursor)
        b_reset.setStyleSheet(
            f"QToolButton {{ border: none; background: transparent; color: {C.TEXT_FAINT}; "
            "font-size: 9px; padding: 0 2px; }"
            f"QToolButton:hover {{ color: {C.TEXT}; }}")
        b_reset.clicked.connect(self.reset_preset)
        self.head_extra.addWidget(b_reset)

        self.preview = None          # 预览挪到底部预设条上了
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {C.SEPARATOR};")
        self.body_layout.addWidget(sep)

        kind_row = QHBoxLayout()
        kind_row.setContentsMargins(0, 0, 0, 0)
        kind_row.setSpacing(4)
        kind_row.addWidget(QLabel("笔型"))
        self.kind_combo = QComboBox()
        self.kind_combo.setMinimumWidth(0)
        self.kind_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.kind_combo.setMinimumContentsLength(5)
        self.kind_combo.setFixedHeight(24)
        for kind, name in KIND_NAMES.items():
            self.kind_combo.addItem(name, kind)
        self.kind_combo.setCurrentIndex(self.kind_combo.findData(brush.kind))
        self.kind_combo.setToolTip("改变当前笔刷的笔型，保留名字、分类及其余参数；新建可独立选择所有笔型")
        self.kind_combo.currentIndexChanged.connect(self._apply)
        kind_row.addWidget(self.kind_combo, 1)
        self.body_layout.addLayout(kind_row)

        # ---- 抖动修正（一根滑杆搞定「手抖」和「画不直」） ----
        self.s_stab = LabeledSlider("抖动修正", 0, 100, int(round(brush.stabilize * 100)), " %")
        self.s_stab.setToolTip(
            "往右拖：手抖被吃掉，线更直更顺。\n"
            "原理是「绳子牵引」——笔尖在几像素内乱抖时笔迹不动，只有拉出一定距离才跟上，\n"
            "所以画长直线特别明显。0% 完全跟手，100% 最稳（急转弯会略微迟钝）。\n"
            "60% 以上还会自动「拉直线」：本来就画得比较直的笔迹会被吸附成真正的直线，\n"
            "画弯的地方不受影响。画细节用小值，画长线 / 勾线用 60% 以上。")
        self.s_stab.valueChanged.connect(self._apply)
        self._track_drag(self.s_stab)
        self.sliders["stabilize"] = self.s_stab
        self.body_layout.addWidget(self.s_stab)

        # 大小与浓淡分别控制，不能在调整其他参数时互相覆盖。
        self.cb_psize = QCheckBox("压感控制大小")
        self.cb_popacity = QCheckBox("压感控制浓淡")
        self.cb_build_up = QCheckBox("逐笔叠色")
        self.cb_psize.setToolTip("只控制笔迹粗细，不改变浓淡压感；最小直径在「笔锋」中设置\n"
                                 "快捷键：Shift+P")
        self.cb_popacity.setToolTip("只控制笔迹浓淡，不改变大小压感\n"
                                    "快捷键：Shift+O")
        self.cb_build_up.setToolTip("开启后，同一处多次落笔可以继续叠色；关闭时保持整笔浓度上限")
        for cb, checked in ((self.cb_psize, brush.pressure_size),
                            (self.cb_popacity, brush.pressure_opacity),
                            (self.cb_build_up, brush.build_up)):
            blocked = cb.blockSignals(True)
            cb.setChecked(checked)
            cb.blockSignals(blocked)
            cb.setFixedHeight(22)
            cb.toggled.connect(self._apply)
        self.body_layout.addWidget(self.cb_psize)
        self.body_layout.addWidget(self.cb_popacity)
        # 压感两个开关上移到「笔型」下面：面板被分栏压矮时也能一眼看到，
        # 不会像之前那样藏在抖动修正后面，看起来像「压感功能不见了」。
        for offset, cb in enumerate((self.cb_psize, self.cb_popacity)):
            self.body_layout.removeWidget(cb)
            self.body_layout.insertWidget(2 + offset, cb)

        # ---- 参数（分组，可折叠；默认只展开笔尖形状） ----
        self.param_groups = {}
        # 折叠状态记住用户的选择；第一次打开只展开「笔尖形状」
        st = QSettings("PhotoCraftDraw", "PhotoCraftDraw")
        saved = st.value("brush/open_groups")
        if isinstance(saved, str):
            saved = [x for x in saved.split(",") if x]
        open_by_default = set(saved) if saved else {"笔尖形状"}
        def make_builder(title, items):
            """组内滑杆「第一次展开时才建」—— 收起状态下建了也看不见，白花 200ms。"""

            def build(layout):
                prev = self._syncing
                self._syncing = True       # 建滑杆时别触发 _apply
                try:
                    for attr, name, lo, hi, suffix, percent in items:
                        cur = getattr(self.brush, attr)
                        if attr == "scatter_count":
                            val = int(round(cur))
                        else:
                            val = int(round(cur * 100)) if percent else int(round(cur))
                        w = LabeledSlider(name, lo, hi, val, suffix)
                        w.valueChanged.connect(self._apply)
                        self._track_drag(w)
                        tip = _PARAM_TIPS.get(attr)
                        if tip:
                            w.setToolTip(tip)
                        self.sliders[attr] = w
                        layout.addWidget(w)
                    if title == "传递":
                        self.cb_build_up.setVisible(True)
                        layout.addWidget(self.cb_build_up)
                finally:
                    self._syncing = prev

            return build

        for title, items in self.GROUPS:
            grp = ParamGroup(title, expanded=(title in open_by_default),
                             builder=make_builder(title, items))
            # 「逐笔叠色」在「传递」组里：组收着的时候不能把它露在外面
            if title == "传递" and not grp._expanded:
                self.cb_build_up.setVisible(False)
            grp.toggled.connect(lambda _on: self._save_groups())
            self.param_groups[title] = grp
            self.body_layout.addWidget(grp)

        # 圆度 100% 时笔尖是正圆，转角度看不出变化；这里自动把圆度降下来
        self.sliders["angle"].valueChanged.connect(self._on_angle)

        # JSON 稳定标识优先，旧 QSettings 名字仅作兼容回退；启动绝不写历史。
        key = self.meta.get("current_key")
        idx = next((i for i, b in enumerate(self.presets) if brushes.brush_key(b) == key), None)
        if idx is None:
            last = st.value("brush/current")
            idx = next((i for i, b in enumerate(self.presets) if b.name == last), 0)
        self.select_index(idx, remember=False)
        if self.meta.get("_load_error"):
            QTimer.singleShot(0, lambda: self.hint(
                "笔刷库读取失败，已禁止覆盖原文件：" + self.meta["_load_error"]))

    def _save_groups(self):
        names = [t for t, g in self.param_groups.items() if g._expanded]
        st = QSettings("PhotoCraftDraw", "PhotoCraftDraw")
        st.setValue("brush/open_groups", ",".join(names))
        st.sync()

    def _on_angle(self, *_):
        if abs(self.brush.angle) < 0.5:
            return
        if self.brush.roundness > 0.97:
            self.sliders["roundness"].set_value(65)
            self._apply()
            self.hint("笔尖是正圆时角度不起作用，已把「圆度」调到 65%")

    def set_all_groups(self, expanded: bool):
        for grp in self.param_groups.values():
            grp.set_expanded(expanded)

    # ---- 预设 ----
    def _refresh_bar(self):
        if self.bar is not None:
            self.bar.rebuild()

    def recent_presets(self):
        """返回 [(原索引, Brush)]，顺序为最近使用在前。"""
        history = brushes.clean_recent(self.presets, self.meta.get("recent"))
        self.meta["recent"] = history
        by_key = {brushes.brush_key(b): (i, b) for i, b in enumerate(self.presets)}
        return [by_key[key] for key in history]

    def favorite_presets(self):
        """返回 [(原索引, Brush)]，顺序为用户添加收藏的顺序。"""
        favorites = brushes.clean_favorites(self.presets, self.meta.get("favorites"))
        self.meta["favorites"] = favorites
        by_key = {brushes.brush_key(b): (i, b) for i, b in enumerate(self.presets)}
        return [by_key[key] for key in favorites]

    def toggle_favorite(self, idx: int):
        """右键「添加到常用 / 从常用移除」，立即写盘，重启后保持。"""
        if not (0 <= idx < len(self.presets)):
            return False
        key = brushes.brush_key(self.presets[idx])
        favorites = brushes.clean_favorites(self.presets, self.meta.get("favorites"))
        if key in favorites:
            favorites.remove(key)
            message = f"已从常用移除「{self.presets[idx].name}」"
        else:
            favorites.insert(0, key)
            message = f"已添加「{self.presets[idx].name}」到常用"
        self.meta["favorites"] = favorites[:brushes.FAVORITE_LIMIT]
        saved = self._save()
        if self.bar is not None:
            # 右键菜单动作还没结束时不要销毁触发它的格子，延后一拍再刷新。
            QTimer.singleShot(0, self.bar.rebuild)
        self.hint(message if saved else "保存常用画笔失败：" +
                  self.meta.get("_save_error", "未知错误"))
        return saved

    def forget_recent(self, idx: int):
        """右键「从最近使用中移除」：只从历史里删掉，笔本身还在库里。"""
        if not (0 <= idx < len(self.presets)):
            return False
        key = brushes.brush_key(self.presets[idx])
        history = brushes.clean_recent(self.presets, self.meta.get("recent"))
        if key not in history:
            return False
        history.remove(key)
        self.meta["recent"] = history
        saved = self._save()
        if self.bar is not None:
            # 右键菜单动作还没结束时不要销毁触发它的格子，延后一拍再刷新
            QTimer.singleShot(0, self.bar.rebuild)
        self.hint(f"已从最近使用中移除「{self.presets[idx].name}」" if saved
                  else "保存最近使用失败：" + self.meta.get("_save_error", "未知错误"))
        return saved

    def record_recent(self):
        """选择 / 实际落笔均可调用；同笔连续使用不重排、不重复写盘。"""
        if not (0 <= self.current < len(self.presets)):
            return False
        key = brushes.brush_key(self.presets[self.current])
        history = brushes.clean_recent(self.presets, self.meta.get("recent"))
        updated = ([key] + [k for k in history if k != key])[:brushes.RECENT_LIMIT]
        changed = updated != self.meta.get("recent") or self.meta.get("current_key") != key
        self.meta["recent"] = updated
        self.meta["current_key"] = key
        if not changed and not self.meta.get("_save_error"):
            return False
        saved = self._save()
        if self.bar is not None:
            if self.bar.category_combo.currentData() == brushes.RECENT_GROUP:
                self.bar.rebuild()
            else:
                self.bar._sync_categories()
        return saved

    def select_index(self, idx, apply=True, remember=True):
        if not (0 <= idx < len(self.presets)):
            return
        self.current = idx
        preset = self.presets[idx]
        key = brushes.brush_key(preset)
        if apply:
            self.brush.apply_from(preset)
            self.brush.origin = builtin_origin(preset)
            self.brush._library_id = getattr(preset, "_library_id", None)
            self.sync_widgets()
        if remember:
            self.record_recent()
        else:
            self.meta["current_key"] = key
        if self.bar is not None:
            self.bar.set_current(idx)
        if apply:
            self.changed.emit()
            self.presetChanged.emit()

    def sync_widgets(self):
        b = self.brush
        syncing = self._syncing
        self._syncing = True
        try:
            for attr, w in self.sliders.items():
                cur = getattr(b, attr)
                w.set_value(cur * 100 if w.suffix == " %" else cur)
            for cb, checked in ((self.cb_psize, b.pressure_size),
                                (self.cb_popacity, b.pressure_opacity),
                                (self.cb_build_up, b.build_up)):
                blocked = cb.blockSignals(True)
                try:
                    cb.setChecked(checked)
                finally:
                    cb.blockSignals(blocked)
            blocked = self.kind_combo.blockSignals(True)
            try:
                self.kind_combo.setCurrentIndex(self.kind_combo.findData(b.kind))
                self._synced_kind = b.kind      # 下拉框现在显示的就是这个笔型
            finally:
                self.kind_combo.blockSignals(blocked)
        finally:
            self._syncing = syncing
        if self.bar is not None:
            self.bar.refresh_preview()

    def _apply(self, *_):
        if self._syncing:
            return
        b = self.brush
        kind = self.kind_combo.currentData()
        # 只有「下拉框真的被换过」才改笔型。
        # 以前这里无条件 b.kind = 下拉框的值：下拉框一旦和当前笔不同步（切换工具、
        # 刚绑定时），随便拖一下滑杆就会把笔型悄悄改掉 —— 连续彩虹就是这么变成
        # 「圆珠笔」、画出来没有颜色的。
        synced = getattr(self, "_synced_kind", None)
        kind_changed = kind is not None and synced is not None and kind != synced
        if kind_changed:
            b.kind = kind
        self._synced_kind = b.kind
        for attr, w in self.sliders.items():
            v = w.slider.value()
            if attr == "scatter_count":
                setattr(b, attr, int(round(v)))
            elif w.suffix == " %":
                setattr(b, attr, v / 100.0)
            else:
                setattr(b, attr, float(v))
        b.spacing = max(0.01, b.spacing)
        size_enabled = self.cb_psize.isChecked() and not b.pressure_size
        b.pressure_size = self.cb_psize.isChecked()
        b.pressure_opacity = self.cb_popacity.isChecked()
        b.build_up = self.cb_build_up.isChecked()
        # 仅主动开启大小压感时放开最小直径，不在普通滑杆操作中篡改预设。
        # 0.85 以上粗细变化只有 15%，肉眼几乎看不出来，会被当成「压感没反应」。
        if size_enabled and b.min_size >= 0.85 and "min_size" in self.sliders:
            b.min_size = 0.3
            self.sliders["min_size"].set_value(30)
            self.hint("「最小直径」太接近 100%，压感粗细变化不明显，已调到 30%（可在「笔锋」里改）")
        self._sync_to_preset()
        self._queue_visuals()
        if kind_changed:
            # 笔型换了，顶部栏要重新决定是否显示「密度 / 范围」。
            self.presetChanged.emit()

    def bind(self, brush: Brush, presets_owned: bool = True, title: str = "画笔"):
        """把面板切到另一支笔上（橡皮 / 涂抹各自独立时用）。

        presets_owned=False 表示这支笔不属于预设库：改了参数只写回它自己，
        不要同步进画笔预设 —— 否则调一次橡皮，画笔的参数就被橡皮盖掉了。
        """
        changed = brush is not self.brush
        self.brush = brush
        self.presets_owned = bool(presets_owned)
        if self.title_label.text() != title:
            self.title_label.setText(title)
        if changed:
            self.sync_widgets()
            self._queue_visuals()

    def _sync_to_preset(self):
        """把当前画笔的参数写回它对应的预设 —— 这样退出重进还是调好的样子。"""
        if not self.presets_owned:
            return                      # 橡皮 / 涂抹不属于预设库
        if not (0 <= self.current < len(self.presets)):
            return
        p = self.presets[self.current]
        for f in Brush.FIELDS:
            if f in ("name", "group"):
                continue
            setattr(p, f, getattr(self.brush, f))
        t = getattr(self, "_save_timer", None)
        if t is not None:
            t.start()

    def flush_save(self):
        """退出前把还没落盘的参数改动写掉。"""
        t = getattr(self, "_save_timer", None)
        if t is not None:
            t.stop()
        self._sync_to_preset()
        self._save()

    def _queue_visuals(self):
        """把「重画试笔条 / 缩略图 / 画布」合并到 33ms 一次。

        这三样每帧要 20~30ms（缩略图是 3 倍超采样真引擎画的），
        拖动时逐帧做会让滑杆明显掉帧、看着像有延迟。合并后滑杆
        （含上面的数字）始终即时跟手，画面最多慢 33ms。
        """
        if self._flush.isActive():
            return
        # 拖动时试笔条 / 缩略图重画一次要 10ms 以上，压到 9 帧/秒；
        # 松手立刻补一帧完整预览。滑杆和数字始终是逐帧跟手的。
        self._flush.start(110 if self._dragging else 33)

    def _track_drag(self, w: "LabeledSlider"):
        w.slider.pressed.connect(self._begin_drag)
        w.slider.released.connect(self._end_drag)

    def _begin_drag(self):
        self._dragging = True

    def _end_drag(self):
        self._dragging = False
        self._flush.stop()
        self._flush.start(0)

    def _refresh_visuals(self):
        if self.bar is not None:
            self.bar.refresh_current()
            self.bar.refresh_preview()
        self.changed.emit()

    def sync_size(self, size):
        if "size" in self.sliders:
            self.sliders["size"].set_value(size)
        self._apply()

    def set_param(self, attr: str, real: float):
        """按真实值设置某个参数（% 类的传 0..1），并立即生效。"""
        w = self.sliders.get(attr)
        if w is None:
            return
        w.set_value(real * 100.0 if w.suffix == " %" else real)
        self._apply()

    def set_field(self, attr: str, value):
        """设置没有右侧滑杆的字段（顶部栏的密度 / 范围），并写回预设。"""
        setattr(self.brush, attr, value)
        self._sync_to_preset()
        self._queue_visuals()

    # ---- 预设操作 ----
    def groups(self):
        """当前所有分类（内置 + 自建，按显示顺序）。"""
        return all_groups(self.presets, self.meta)

    def _save(self):
        self._save_timer.stop()
        if 0 <= self.current < len(self.presets):
            self.meta["current_key"] = brushes.brush_key(self.presets[self.current])
        if self.bar is not None:
            self.meta["browse"] = self.bar.browse_state()
        saved = save_library(self.presets, self.meta)
        if not saved:
            self.hint("保存画笔库失败：" + self.meta.get("_save_error", "未知错误"))
        return saved

    def new_preset(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("新建画笔")
        dlg.setMinimumWidth(260)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("画笔名字："))
        name_edit = QLineEdit(f"我的画笔 {len(self.presets) + 1}")
        name_edit.setMaxLength(24)
        name_edit.selectAll()
        layout.addWidget(name_edit)
        layout.addWidget(QLabel("笔型（新笔使用默认参数）："))
        kind_combo = QComboBox()
        for kind, label in KIND_NAMES.items():
            kind_combo.addItem(label, kind)
        kind_combo.setCurrentIndex(max(0, kind_combo.findData(self.brush.kind)))
        layout.addWidget(kind_combo)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("创建")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        name_edit.setFocus()
        accepted = dlg.exec() == QDialog.Accepted
        name = name_edit.text().strip()
        kind = kind_combo.currentData()
        dlg.deleteLater()
        if not accepted or not name:
            return
        if any(x.name == name for x in self.presets):
            dialogs.tell(self, "新建画笔", f"已经有叫「{name}」的画笔了，换个名字。")
            return
        b = Brush()
        b.kind = kind
        b.name = name
        b.group = USER_GROUP
        self.presets.append(b)
        idx = len(self.presets) - 1
        self.select_index(idx, remember=False)
        if self.bar is not None:
            self.bar.show_added([idx])
        if self._save():
            self.hint(f"已创建「{b.name}」")

    def rename_preset(self, idx: int):
        """改名。内置笔也能改 —— 原名记在 meta 里，「重置」照样找得到默认参数。"""
        if not (0 <= idx < len(self.presets)):
            return
        b = self.presets[idx]
        name, ok = dialogs.get_text(self, "重命名画笔", "新名字：", text=b.name)
        if not ok:
            return
        name = name.strip()[:24]
        if not name or name == b.name:
            return
        if any(x.name == name for x in self.presets):
            dialogs.tell(self, "重命名画笔", f"已经有叫「{name}」的画笔了，换个名字。")
            return
        brushes.brush_key(b)
        origin = builtin_origin(b)
        if origin:
            self.meta["renames"][origin] = name
        b.name = name
        self._refresh_bar()
        if idx == self.current:
            self.select_index(idx, remember=False)
        if self._save():
            self.hint(f"已改名为「{name}」")

    def delete_preset(self, idx=None):
        if not self.presets:
            return
        i = self.current if idx is None else idx
        if not (0 <= i < len(self.presets)):
            return
        b = self.presets[i]
        if builtin_origin(b):
            dialogs.tell(self, "删除画笔",
                         "内置画笔不能删除（可以改名、换分类，或者「新建」一支自己的）。")
            return
        if dialogs.ask(self, "删除画笔", f"删除画笔「{b.name}」？",
                       [("cancel", "取消", "primary"), ("del", "删除", "danger")],
                       default="cancel") != "del":
            return
        current = self.current
        self.presets.pop(i)
        self.meta["recent"] = brushes.clean_recent(self.presets, self.meta.get("recent"))
        idx = (min(i, len(self.presets) - 1) if current == i
               else current - int(i < current))
        self.select_index(idx, remember=False)
        self._refresh_bar()
        if self._save():
            self.hint("已删除")

    def reset_preset(self):
        if not self.presets:
            return
        cur = self.presets[self.current]
        name, group = cur.name, cur.group
        origin = builtin_origin(cur) or cur.name
        default = next((d for d in DEFAULTS if d.name == origin), None)
        if default is None:
            dialogs.tell(
                self, "重置画笔",
                f"「{cur.name}」是自建画笔，没有内置默认参数可以恢复。\n"
                "如果参数调乱了，可以删掉重新建一个。")
            return
        r = dialogs.ask(
            self, "重置画笔",
            f"把「{cur.name}」恢复成默认设置？\n（大小、硬度、间距、抖动等全部复位）",
            [("cancel", "取消", "primary"), ("reset", "恢复默认", "normal")],
            default="cancel")
        if r != "reset":
            return
        cur.apply_from(default)
        # 只复位参数：名字 / 分类是用户自己定的，别一起改回去
        cur.name = name
        cur.group = group
        self.select_index(self.current, remember=False)      # 复位参数，不重排历史
        if self._save():
            self.hint(f"「{cur.name}」已恢复默认设置")

    def export_preset(self, idx=None):
        from PySide6.QtWidgets import QFileDialog
        if not self.presets:
            return
        i = self.current if idx is None else idx
        if not (0 <= i < len(self.presets)):
            return
        b = self.presets[i]
        path, _ = QFileDialog.getSaveFileName(self, "导出画笔预设",
                                              f"{b.name}.pcbrush",
                                              "画笔预设 (*.pcbrush *.json)")
        if not path:
            return
        if not path.lower().endswith((".pcbrush", ".json")):
            path += ".pcbrush"
        ok = export_brush(b, path)
        self.hint("已导出画笔预设" if ok else "导出失败")

    def export_group(self, group: str):
        """把一个分类里的所有笔打包导出（换电脑 / 分享给别人用）。"""
        from PySide6.QtWidgets import QFileDialog
        items = [b for b in self.presets if b.group == group]
        if not items:
            dialogs.tell(self, "导出分类", f"「{group}」里还没有画笔。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, f"导出分类「{group}」", f"{group}.pcbrush",
            "画笔分类包 (*.pcbrush *.json)")
        if not path:
            return
        if not path.lower().endswith((".pcbrush", ".json")):
            path += ".pcbrush"
        ok = export_group_file(group, items, path)
        self.hint(f"已导出「{group}」（{len(items)} 支）" if ok else "导出失败")

    def import_preset(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "导入画笔 / 分类包", "",
            "画笔预设或分类包 (*.pcbrush *.json);;所有文件 (*)")
        if not path:
            return
        try:
            group, items = import_pack(path)
        except Exception as e:
            dialogs.tell(self, "导入失败", str(e), kind="warning")
            return
        if not items:
            dialogs.tell(self, "导入", "文件里没有可用的画笔。")
            return
        # 分类包的顶层分类优先；普通包保留每支笔自己的分类。
        # 只有没有分类的笔才归入「我的」，不能将分类包扁平化。
        group = group.strip() if isinstance(group, str) else ""
        known_groups = set(self.groups())
        custom_groups = self.meta.setdefault("groups", [])
        for b in items:
            b.group = group or (b.group.strip() if isinstance(b.group, str) else "") or USER_GROUP
            if b.group not in known_groups:
                custom_groups.append(b.group)
                known_groups.add(b.group)
        first = len(self.presets)
        exist = {b.name for b in self.presets}
        for b in items:
            base = b.name
            n = 2
            while b.name in exist:
                b.name = f"{base} {n}"
                n += 1
            exist.add(b.name)
            self.presets.append(b)
        self.select_index(first, remember=False)
        if self.bar is not None:
            self.bar.show_added(range(first, len(self.presets)))
        if self._save():
            self.hint(f"已导入 {len(items)} 支笔" + (f"，分类「{group}」" if group else ""))

    def hint(self, msg):
        target = getattr(self.window(), "hint", None)
        if hasattr(target, "setText"):
            target.setText(msg)


# ---------------------------------------------------------------- 图层
# ---------------------------------------------------------------- 对称
class SymmetryPanel(Section):
    """对称绘图：每一颗笔点都按轴镜像出去，而不是画完再复制一份。"""

    changed = Signal()
    pickRequested = Signal(bool)
    centerRequested = Signal()

    MODES = [("off", "关"), ("vertical", "垂直"), ("horizontal", "水平"),
             ("quad", "四象"), ("radial", "径向")]

    def __init__(self, sym: dict, parent=None):
        super().__init__("对称", parent, scroll=True)
        self.sym = sym
        self._syncing = False

        # 标题条左侧加个对称图标：一排面板里一眼就能认出这一栏
        self.head_icon = QLabel()
        self.head_icon.setPixmap(icons.pixmap("symmetry", C.TEXT_DIM, 13, 1.8))
        self.head_icon.setFixedWidth(15)
        self.head_layout.insertWidget(0, self.head_icon)

        self.state_label = QLabel("关闭")
        self.state_label.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 9px;")
        self.head_extra.addWidget(self.state_label)

        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(2)
        self.buttons = {}
        for key, name in self.MODES:
            b = QToolButton()
            b.setText(name)
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.setFixedHeight(22)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                f"QToolButton {{ border: 1px solid {C.FIELD_BORDER}; background: {C.FIELD}; "
                f"color: {C.TEXT_DIM}; border-radius: 3px; padding: 0 1px; font-size: 10px; }}"
                f"QToolButton:hover {{ background: {C.HOVER}; color: {C.TEXT}; }}"
                f"QToolButton:checked {{ background: {C.ACCENT}; color: #FFFFFF; "
                f"border-color: #2B7BD8; }}")
            b.clicked.connect(lambda _=False, k=key: self._set_mode(k))
            rl.addWidget(b, 1)
            self.buttons[key] = b
        self.body_layout.addWidget(row)

        self.s_count = LabeledSlider("份数", 2, 24, int(sym.get("count", 6)), " 份")
        self.s_count.setToolTip("径向对称绕轴心复制几份（6 份 = 雪花，12 份 = 曼陀罗）")
        self.s_count.valueChanged.connect(self._set_count)
        self.body_layout.addWidget(self.s_count)

        # 参考线不设开关：开了对称就一定显示轴线和轴心。
        # （以前误触关掉后，用户会一脸懵：明明开了对称却看不见那条线）
        bar = QWidget()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(4)
        self.b_center = QToolButton()
        self.b_center.setText("轴心居中")
        self.b_center.setToolTip("把对称轴心放回画布正中")
        self.b_center.setFixedHeight(22)
        self.b_center.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.b_center.clicked.connect(self.centerRequested.emit)
        self.b_pick = QToolButton()
        self.b_pick.setText("点选轴心")
        self.b_pick.setToolTip("点一下，然后在画布上点哪儿，对称轴心就落在哪儿\n"
                               "（也可以直接在画布上按住轴心圆点拖）")
        self.b_pick.setCheckable(True)
        self.b_pick.setFixedHeight(22)
        self.b_pick.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.b_pick.toggled.connect(self.pickRequested.emit)
        # 「固定」：锁住轴心，画布上拖不动它（画的时候手滑碰到轴心不会把对称挪走）
        self.b_lock = QToolButton()
        self.b_lock.setText("固定")
        self.b_lock.setToolTip("锁住轴心：画布上拖不动它，避免画的时候手滑把对称轴挪走\n"
                               "（「轴心居中 / 点选轴心」仍然可以改位置）")
        self.b_lock.setCheckable(True)
        self.b_lock.setFixedHeight(22)
        self.b_lock.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.b_lock.toggled.connect(self._set_locked)
        for b in (self.b_center, self.b_pick, self.b_lock):
            b.setStyleSheet(
                f"QToolButton {{ border: 1px solid {C.FIELD_BORDER}; background: {C.FIELD}; "
                f"color: {C.TEXT_DIM}; border-radius: 3px; padding: 0 4px; font-size: 10px; }}"
                f"QToolButton:hover {{ background: {C.HOVER}; color: {C.TEXT}; }}"
                f"QToolButton:checked {{ background: {C.ACCENT}; color: #FFFFFF; "
                f"border-color: #2B7BD8; }}")
            bl.addWidget(b, 1)
        self.body_layout.addWidget(bar)

        # 这里不再放说明文字：对称面板本来就不高，两行小字很占地方，
        # 去掉后把高度让给下面的图层列表。操作提示保留在按钮 tooltip 里。
        self.sync()
        self._cap_content_height()

    def _cap_content_height(self):
        """去掉说明文字后，别再把分栏给的空白留在面板里；多余高度让给图层。"""
        if self._collapsed:
            return
        cap = self.body.sizeHint().height() + 32
        from PySide6.QtWidgets import QSplitter
        sp = self.parentWidget()
        before = sp.sizes() if isinstance(sp, QSplitter) else None
        # 内容高度固定：分栏不能再给这块留空白，省下的高度自然落到图层。
        self.setMinimumHeight(cap)
        self.setMaximumHeight(cap)
        if not isinstance(sp, QSplitter) or before is None:
            return
        i = sp.indexOf(self)
        after = sp.sizes()
        if i < 0 or i >= len(after) or i == len(after) - 1:
            return
        excess = before[i] - after[i]
        if after[i] > cap:
            excess = max(excess, after[i] - cap)
            after[i] = cap
        if excess > 0:
            after[-1] += excess          # 最下面就是图层列表
            sp.setSizes(after)

    def set_collapsed(self, on: bool):
        super().set_collapsed(on)
        if not on:
            self._cap_content_height()
            QTimer.singleShot(0, self._cap_content_height)

    # ---------------------------------------------------------- 交互
    def _set_mode(self, key):
        if self._syncing:
            return
        self.sym["mode"] = key
        self._after_change()

    def _set_count(self, v):
        if self._syncing:
            return
        self.sym["count"] = max(2, min(24, int(round(v))))
        self._after_change()

    def _set_locked(self, on: bool):
        if self._syncing:
            return
        self.sym["locked"] = bool(on)
        self.changed.emit()

    def _after_change(self):
        self.sync()
        self.changed.emit()

    def set_picking(self, on: bool):
        self._syncing = True
        self.b_pick.setChecked(bool(on))
        self._syncing = False

    def sync(self):
        """把 dict 里的状态刷到控件上（切文档 / 外部改轴心时用）。"""
        self._syncing = True
        mode = self.sym.get("mode", "off")
        for key, b in self.buttons.items():
            b.setChecked(key == mode)
        self.s_count.set_value(float(self.sym.get("count", 6)))
        self.s_count.setEnabled(mode == "radial")
        self.sym["guides"] = mode != "off"      # 参考线跟对称同开同关，不给单独的开关
        self.b_center.setEnabled(mode != "off")
        self.b_pick.setEnabled(mode != "off")
        self.b_lock.setChecked(bool(self.sym.get("locked", False)))
        self.b_lock.setEnabled(mode != "off")
        self.state_label.setText(SYM_NAMES.get(mode, "关闭"))
        # 开着的时候标题条上的状态用强调色：面板折起来也能一眼看出「对称开着」
        on = mode != "off"
        self.state_label.setStyleSheet(
            f"color: {C.ACCENT if on else C.TEXT_FAINT}; font-size: 9px;"
            + (" font-weight: bold;" if on else ""))
        self.title_label.setStyleSheet(
            f"color: {C.TEXT if on else C.TEXT_DIM};")
        self.head_icon.setPixmap(
            icons.pixmap("symmetry", C.ACCENT if on else C.TEXT_DIM, 13, 1.8))
        self._syncing = False


class GroupRow(QWidget):
    """图层组的标题行：折叠 / 显示隐藏 / 整组锁定 / 组名。

    交互（和普通图层行保持一致）：
    · 单击 = 选中组里的所有图层（整组一起移动 / 调不透明度 / 删除）
    · 双击组名 = 就地改名
    · 左边的小三角 = 折叠 / 展开
    """

    ROW_H = 30

    def __init__(self, panel, doc, gid, group, count, indent=0):
        super().__init__()
        self.panel = panel
        self.doc = doc
        self.gid = gid
        self.group = group
        self.count = count
        self.selected = False
        self._hover = False
        self._renaming = False
        self.setFixedHeight(self.ROW_H)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("单击 = 选中整组的图层\n双击组名 = 改名\n"
                        "左边小三角 = 折叠 / 展开")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(4 + indent, 3, 6, 3)
        lay.setSpacing(4)

        self.chev = QToolButton()
        self.chev.setFixedSize(16, 16)
        self.chev.setText("▾" if group.expanded else "▸")
        self.chev.setStyleSheet(
            f"QToolButton {{ border: none; background: transparent; color: {C.TEXT_DIM}; "
            "font-size: 9px; padding: 0; }")
        self.chev.setToolTip("折叠 / 展开这个组")
        self.chev.clicked.connect(self._toggle_expand)
        lay.addWidget(self.chev)

        self.eye = QToolButton()
        self.eye.setFixedSize(18, 18)
        self.eye.setIcon(icons.icon("eye" if group.visible else "eye_off",
                                    C.TEXT if group.visible else C.TEXT_FAINT, 14))
        self.eye.setStyleSheet("QToolButton { border: none; background: transparent; }"
                               f"QToolButton:hover {{ background: {C.HOVER}; border-radius: 3px; }}")
        self.eye.setToolTip("显示 / 隐藏整个组")
        self.eye.clicked.connect(self._toggle_visible)
        lay.addWidget(self.eye)

        self.lock = QToolButton()
        self.lock.setFixedSize(18, 18)
        self.lock.setIcon(icons.icon("lock" if group.locked else "unlock",
                                     C.DANGER if group.locked else C.TEXT_FAINT, 14))
        self.lock.setStyleSheet("QToolButton { border: none; background: transparent; }"
                                f"QToolButton:hover {{ background: {C.HOVER}; border-radius: 3px; }}")
        self.lock.setToolTip("锁定整个组")
        self.lock.clicked.connect(self._toggle_lock)
        lay.addWidget(self.lock)

        self.icon = QLabel()
        self.icon.setPixmap(icons.pixmap("layers", C.TEXT_DIM, 14, 1.0))
        lay.addWidget(self.icon)

        self.name = QLabel(group.name)
        self.name.setStyleSheet(
            f"color: {C.TEXT if group.visible else C.TEXT_FAINT}; font-size: 11px; font-weight: bold;")
        lay.addWidget(self.name)

        self.meta = QLabel(f"{count} 层")
        self.meta.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 9px;")
        lay.addWidget(self.meta)
        lay.addStretch(1)

        self.name_edit = QLineEdit(group.name)
        self.name_edit.setFixedHeight(20)
        self.name_edit.setStyleSheet(
            f"QLineEdit {{ background: {C.FIELD}; color: {C.TEXT}; border: 1px solid "
            f"{C.ACCENT}; border-radius: 3px; font-size: 11px; padding: 0 4px; }}")
        self.name_edit.hide()
        self.name_edit.editingFinished.connect(self._finish_rename)
        lay.addWidget(self.name_edit, 1)

        for w in (self.icon, self.name, self.meta):
            w.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def _toggle_expand(self):
        self.group.expanded = not self.group.expanded
        self.panel.refresh()

    def _toggle_visible(self):
        self.group.visible = not self.group.visible
        self.doc.recompose()
        self.panel.refresh()
        self.panel.changed.emit()

    def _toggle_lock(self):
        self.group.locked = not self.group.locked
        self.panel.refresh()
        self.panel.changed.emit()
        self.panel.hintRequested.emit(
            f"组「{self.group.name}」已锁定" if self.group.locked
            else f"组「{self.group.name}」已解锁")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.panel.setFocus()
            self.panel.select_group(self.gid)

    def mouseDoubleClickEvent(self, e):
        self._start_rename()

    def _start_rename(self):
        self.name.hide()
        self.meta.hide()
        self.name_edit.setText(self.group.name)
        self.name_edit.show()
        self.name_edit.setFocus()
        self.name_edit.selectAll()
        self._renaming = True

    def _finish_rename(self):
        # 用显式标记而不是 isVisible()：控件被折叠 / 滚动到视野外时
        # isVisible() 会是 False，改名会被悄悄丢掉。
        if not getattr(self, "_renaming", False):
            return
        self._renaming = False
        txt = self.name_edit.text().strip()
        self.name_edit.hide()
        self.name.show()
        self.meta.show()
        if txt and txt != self.group.name:
            self.panel.rename_group(self.gid, txt)

    def contextMenuEvent(self, e):
        self.panel.show_group_menu(self, e.globalPos())

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        bg = QColor(C.TAB_STRIP)
        if self.selected:
            bg = QColor(C.ROW_SELECTED)
        elif self._hover:
            bg = QColor(C.HOVER)
        p.fillRect(self.rect(), bg)
        if self.selected:
            p.fillRect(QRect(0, 0, 2, self.height()), QColor(C.ACCENT))
        p.setPen(QPen(QColor(0, 0, 0, 110), 1))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        p.end()


class LayerRow(QWidget):
    ROW_H = 46

    def __init__(self, panel, doc, layer, index, active: bool, indent: int = 0):
        super().__init__()
        self.panel = panel
        self.doc = doc
        self.layer = layer
        self.index = index
        self.active = active
        self.selected = False
        self.is_bg = bool(getattr(layer, "is_bg", False))
        self.setFixedHeight(self.ROW_H)
        self.setCursor(Qt.ArrowCursor if self.is_bg else Qt.PointingHandCursor)
        self._editing = False
        if self.is_bg:
            self.setToolTip("背景层固定在最底层：不能拖动、不能上移 / 下移、不能删除\n"
                            "铺满画布的色块拖动时会自动吸附对齐")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(4 + indent, 4, 6, 4)
        lay.setSpacing(6)

        self.eye = QToolButton()
        self.eye.setFixedSize(20, 20)
        self.eye.setIcon(icons.icon("eye" if layer.visible else "eye_off",
                                    C.TEXT if layer.visible else C.TEXT_FAINT, 15))
        self.eye.setStyleSheet("QToolButton { border: none; background: transparent; }"
                               f"QToolButton:hover {{ background: {C.HOVER}; border-radius: 3px; }}")
        self.eye.setToolTip("显示 / 隐藏")
        self.eye.clicked.connect(self._toggle_visible)
        lay.addWidget(self.eye)

        self.lock = QToolButton()
        self.lock.setFixedSize(20, 20)
        self._update_lock_icon()
        self.lock.setStyleSheet("QToolButton { border: none; background: transparent; }"
                                f"QToolButton:hover {{ background: {C.HOVER}; border-radius: 3px; }}")
        self.lock.setToolTip("锁定图层：锁定后不能绘画 / 填充 / 移动")
        self.lock.clicked.connect(lambda: self.panel.toggle_lock(self.index))
        lay.addWidget(self.lock)

        self.thumb = QLabel()
        self.thumb.setFixedSize(44, 32)
        self.thumb.setStyleSheet(
            f"border: 1px solid #5A5A5A; background: {C.FIELD};")
        self.thumb.setPixmap(layer.thumb(42, 30))
        lay.addWidget(self.thumb)

        box = QVBoxLayout()
        box.setSpacing(1)
        box.setContentsMargins(0, 0, 0, 0)
        self.name = QLabel(layer.name)
        self.name.setStyleSheet(
            f"color: {C.TEXT if (active and not layer.locked) else C.TEXT_FAINT}; font-size: 11px;")
        self.meta = QLabel(self._meta_text())
        self.meta.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 10px;")
        box.addWidget(self.name)
        box.addWidget(self.meta)
        box.addStretch(1)
        lay.addLayout(box, 1)

        # 缩略图 / 文字都不吞鼠标事件，这样在行内任何位置按下都能拖动排序（眼睛按钮除外）
        for w in (self.thumb, self.name, self.meta):
            w.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self.name_edit = QLineEdit(layer.name)
        self.name_edit.setFixedHeight(20)
        self.name_edit.hide()
        self.name_edit.editingFinished.connect(self._finish_rename)
        box.addWidget(self.name_edit)

    def _meta_text(self):
        txt = f"{int(round(self.layer.opacity * 100))}%"
        if self.is_bg:
            # 文字比小图标直观：11px 的图钉在图层行里就是一道斜杠，看不出是「钉住」
            txt += "　固定底层"
        return txt

    def _update_lock_icon(self):
        locked = bool(self.layer.locked)
        self.lock.setIcon(icons.icon("lock" if locked else "unlock",
                                     C.DANGER if locked else C.TEXT_FAINT, 15))

    def _toggle_visible(self):
        self.panel.toggle_visible(self.index)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = e.position().toPoint()
            self._dragging = False
            self.panel.setFocus()          # 让 Backspace 能删掉这层
            self.panel.select(self.index, e.modifiers())

    def mouseMoveEvent(self, e):
        # 只要按下过就允许拖动：某些情况下 e.buttons() 不可靠，
        # 之前用它会偶发「拖了没反应」。没有按下时 Qt 不会发 move，所以是安全的。
        if getattr(self, "_press", None) is None:
            return
        if self.is_bg:
            # 背景层钉在底部，拖不动；提示一次就够，别刷屏
            if not getattr(self, "_bg_nagged", False):
                self._bg_nagged = True
                self.panel.hintRequested.emit(
                    "背景层固定在最底层，拖不动")
            return
        if not getattr(self, "_dragging", False):
            if (e.position().toPoint() - self._press).manhattanLength() < 4:
                return
            self._dragging = True
            self.setCursor(Qt.ClosedHandCursor)
            self.panel.begin_drag(self)
        self.panel.update_drag(e.globalPosition().toPoint())

    def mouseReleaseEvent(self, e):
        self._press = None
        if getattr(self, "_dragging", False):
            self._dragging = False
            self.unsetCursor()
            self.panel.finish_drag()

    def mouseDoubleClickEvent(self, e):
        self._start_rename()

    def contextMenuEvent(self, e):
        # 右键菜单：新人不用记快捷键也能找到「新建组 / 解散组」
        self.panel.select(self.index)
        self.panel.show_layer_menu(self, self.index, e.globalPos())

    def _start_rename(self):
        self.name.hide()
        self.meta.hide()
        self.name_edit.setText(self.layer.name)
        self.name_edit.show()
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def _finish_rename(self):
        if not self.name_edit.isVisible():
            return
        txt = self.name_edit.text().strip()
        if txt and txt != self.layer.name:
            self.panel.rename(self.index, txt)
        self.name_edit.hide()
        self.name.show()
        self.meta.show()

    def paintEvent(self, e):
        p = QPainter(self)
        bg = QColor(C.ROW_SELECTED) if self.active else QColor(C.CARD)
        if self.selected and not self.active:
            bg = QColor(C.PRESSED)
        if getattr(self, "dragging", False):
            bg = QColor(C.PRESSED)
        elif self.underMouse() and not self.active and not self.selected:
            bg = QColor(C.HOVER)
        p.fillRect(self.rect(), bg)
        if self.active:
            p.fillRect(QRect(0, 0, 2, self.height()), QColor(C.ACCENT))
        elif self.selected:
            p.fillRect(QRect(0, 0, 2, self.height()), QColor(C.ACCENT).lighter(150))
        p.setPen(QPen(QColor(0, 0, 0, 90), 1))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        p.end()

    def enterEvent(self, e):
        self.update()

    def leaveEvent(self, e):
        self.update()


class TextRow(QWidget):
    """图层面板里的「文字」行。

    文字不是像素图层：它浮在图层之上、不受锁定 / 不透明度影响，
    点这一行就回到文字工具继续改那段字（PS 里双击文字图层的效果）。
    它也能拖进 / 拖出图层组，和普通图层一样参与分组管理。
    """

    ROW_H = 34

    def __init__(self, panel, doc, item, index, parent=None, indent=0):
        super().__init__(parent)
        self.panel = panel
        self.doc = doc
        self.item = item
        self.index = index
        self.selected = False
        self.dragging = False
        self._press = None
        self._hover = False
        self.setFixedHeight(self.ROW_H)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("文字对象（可再编辑）：点一下选中它，双击回到文字工具继续改\n"
                        "选中后右下角垃圾桶删的就是这一段字\n"
                        "它不受图层锁定 / 不透明度影响，也不占用图层\n"
                        "可以按住拖进 / 拖出图层组")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6 + indent, 3, 6, 3)
        lay.setSpacing(6)

        self.eye = QToolButton()
        self.eye.setFixedSize(20, 20)
        self.eye.setIcon(icons.icon("eye" if item.visible else "eye_off",
                                    C.TEXT if item.visible else C.TEXT_FAINT, 15))
        self.eye.setStyleSheet("QToolButton { border: none; background: transparent; }"
                               f"QToolButton:hover {{ background: {C.HOVER}; border-radius: 3px; }}")
        self.eye.setToolTip("显示 / 隐藏这段文字")
        self.eye.clicked.connect(self._toggle_visible)
        lay.addWidget(self.eye)

        badge = QLabel("T")
        badge.setFixedSize(18, 18)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            f"background: {C.ACCENT}; color: #FFFFFF; border-radius: 3px;"
            " font-size: 11px; font-weight: bold;")
        badge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        lay.addWidget(badge)

        box = QVBoxLayout()
        box.setSpacing(1)
        box.setContentsMargins(0, 0, 0, 0)
        self.name = QLabel(item.name)
        self.name.setStyleSheet(
            f"color: {C.TEXT if item.visible else C.TEXT_FAINT}; font-size: 11px;")
        self.meta = QLabel(f"{int(round(item.px))} px　{len(item.text.splitlines()) or 1} 行")
        self.meta.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 10px;")
        box.addWidget(self.name)
        box.addWidget(self.meta)
        box.addStretch(1)
        lay.addLayout(box, 1)

        for w in (self.name, self.meta):
            w.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def paintEvent(self, e):
        p = QPainter(self)
        r = self.rect()
        base = QColor(C.CARD)
        if getattr(self, "dragging", False):
            base = QColor(C.PRESSED)
        elif self.selected:
            base = QColor(C.ROW_SELECTED)
        elif self._hover:
            base = QColor(C.HOVER)
        p.fillRect(r, base)
        # 左侧竖条：选中时更亮，告诉用户「右下角垃圾桶删的是这一段」
        p.fillRect(QRect(0, 0, 2, r.height()),
                   QColor(C.ACCENT if self.selected else C.ACCENT).lighter(
                       100 if self.selected else 160))
        p.setPen(QPen(QColor(C.SEPARATOR), 1))
        p.drawLine(0, r.height() - 1, r.width(), r.height() - 1)
        p.end()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = e.position().toPoint()
            self._dragging = False
            self.panel.setFocus()
            self.panel.select_text(self.index, e.modifiers())

    def mouseMoveEvent(self, e):
        if self._press is None:
            return
        if not getattr(self, "_dragging", False):
            if (e.position().toPoint() - self._press).manhattanLength() < 5:
                return
            self._dragging = True
            self.setCursor(Qt.ClosedHandCursor)
            self.panel.begin_drag(self)
        self.panel.update_drag(e.globalPosition().toPoint())

    def mouseReleaseEvent(self, e):
        self._press = None
        if getattr(self, "_dragging", False):
            self._dragging = False
            self.unsetCursor()
            self.panel.finish_drag()

    def mouseDoubleClickEvent(self, e):
        self.panel.textEditRequested.emit(self.index)

    def contextMenuEvent(self, e):
        m = QMenu(self)
        a_edit = m.addAction("编辑文字…")
        a_edit.triggered.connect(lambda: self.panel.textEditRequested.emit(self.index))
        a_vis = m.addAction("隐藏这段文字" if self.item.visible else "显示这段文字")
        a_vis.triggered.connect(self._toggle_visible)
        m.addSeparator()
        a_ungroup = m.addAction("移出图层组")
        a_ungroup.setEnabled(bool(getattr(self.item, "group", "")))
        a_ungroup.triggered.connect(lambda: self.panel.move_text_to_group(self.index, ""))
        m.addSeparator()
        a_del = m.addAction("删除这段文字")
        a_del.triggered.connect(self._delete)
        m.exec(e.globalPos())

    def _toggle_visible(self):
        self.item.visible = not self.item.visible
        self.doc.modified = True
        self.doc.recompose()
        self.panel.refresh()
        self.panel.changed.emit()

    def _delete(self):
        self.panel.delete_text(self.index)


class LayersPanel(QWidget):
    changed = Signal()
    added = Signal(int)
    hintRequested = Signal(str)
    activeChanged = Signal()
    selectionChanged = Signal()
    textEditRequested = Signal(int)      # 想编辑第 N 段文字

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {C.DOCK};")
        self.setFocusPolicy(Qt.ClickFocus)
        self.doc = None
        self.controller = None
        self.selected = set()            # 选中的图层下标
        self.selected_texts = set()      # 选中的文字对象下标（和图层平级）
        self.active_text = None          # 「正在编辑 / 主选」的那段文字
        self._empty_ok = False           # 用户主动取消选中时，refresh 不要自动选回当前层
        self._text_anchor = 0
        self._anchor = 0
        self._last_group_click = None   # 上一次点的是哪个组标题（用来做「再点取消」）
        self.drop_line = None
        self._drag_from = None
        self._drag_to = None
        # 拖不透明度滑杆时每帧都要整图重合成（1920×1080 一次十几毫秒），
        # 逐帧做滑杆会掉帧。合并到 33ms 一次，滑杆保持即时跟手。
        self._op_flush = QTimer(self)
        self._op_flush.setSingleShot(True)
        self._op_flush.setInterval(33)
        self._op_flush.timeout.connect(self._flush_opacity)
        # 当前层缩略图的防抖刷新（画完一笔用）
        self._thumb_timer = QTimer(self)
        self._thumb_timer.setSingleShot(True)
        self._thumb_timer.setInterval(150)
        self._thumb_timer.timeout.connect(self._refresh_active_thumb_now)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 顶部：只有不透明度（混合模式按需求已整体移除）
        top = Section("图层")
        self.active_label = QLabel("")
        self.active_label.setStyleSheet(f"color: {C.TEXT}; font-size: 12px;")
        top.head_extra.addWidget(self.active_label)
        # 层数放标题条上：底部工具条要留给 9 个按钮，不能被它挤掉
        self.count = QLabel("1 / 200")
        self.count.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 10px;")
        self.count.setToolTip(f"图层数 / 上限 {MAX_LAYERS}")
        top.head_extra.addWidget(self.count)

        op_row = QHBoxLayout()
        op_row.setSpacing(6)
        lbl = QLabel("不透明度")
        lbl.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 11px;")
        op_row.addWidget(lbl)
        self.opacity = NoWheelSlider(Qt.Horizontal)
        self.opacity.setRange(0, 100)
        self.opacity.setValue(100)
        self.opacity.setFixedHeight(16)
        self.opacity.valueChanged.connect(self._on_opacity)
        op_row.addWidget(self.opacity, 1)
        self.opacity_val = QLabel("100%")
        self.opacity_val.setFixedWidth(36)
        self.opacity_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.opacity_val.setStyleSheet(f"color: {C.TEXT}; font-size: 11px;")
        op_row.addWidget(self.opacity_val)
        top.body_layout.addLayout(op_row)
        outer.addWidget(top)

        # 图层列表
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(f"background: {C.CARD}; border: none;")
        self.list_host = QWidget()
        self.list_host.setStyleSheet(f"background: {C.CARD};")
        self.list_lay = QVBoxLayout(self.list_host)
        self.list_lay.setContentsMargins(0, 0, 0, 0)
        self.list_lay.setSpacing(0)
        self.list_lay.addStretch(1)
        self.scroll.setWidget(self.list_host)
        outer.addWidget(self.scroll, 1)

        # 底部工具条
        bar = QWidget()
        bar.setFixedHeight(30)
        bar.setStyleSheet(f"background: {C.TAB_STRIP}; border-top: 1px solid {C.SEPARATOR};")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(5, 3, 5, 3)
        bl.setSpacing(2)
        self.tb = {}
        for name, tip, slot in (
                ("plus", "新建图层　Ctrl+Shift+N", self.add_layer),
                ("copy", "复制图层　Ctrl+J", self.duplicate_layer),
                ("up", "上移图层　Ctrl+]", lambda: self.move_layer(1)),
                ("down", "下移图层　Ctrl+[", lambda: self.move_layer(-1)),
                ("merge", "合并图层　Ctrl+E", self.merge_down),
                ("group", "新建组　Ctrl+G\n把选中的图层装进一个新组", self.make_group),
                ("ungroup", "解散组　Ctrl+Shift+G\n把当前图层所在的组拆开，图层都留下",
                 self.ungroup_group),
                ("trash", "删除图层　Backspace（焦点在图层面板时）", self.remove_layer)):
            b = QToolButton()
            b.setFixedSize(24, 24)
            b.setIcon(icons.icon(name, C.ICON, 15))
            b.setToolTip(tip)
            b.setStyleSheet(
                "QToolButton { border: none; background: transparent; border-radius: 3px; }"
                f"QToolButton:hover {{ background: {C.HOVER}; }}"
                f"QToolButton:pressed {{ background: {C.PRESSED}; }}"
                f"QToolButton:disabled {{ background: transparent; }}")
            b.clicked.connect(slot)
            bl.addWidget(b)
            self.tb[name] = b
        outer.addWidget(bar)

    # -- 拖动排序（支持拖进组）
    def begin_drag(self, row):
        self._drag_row = row
        self._drag_target = None
        row.dragging = True
        row.update()
        if self.drop_line is None:
            self.drop_line = QFrame(self.list_host)
            self.drop_line.setStyleSheet(f"background: {C.ACCENT};")
        self.drop_line.show()
        self.drop_line.raise_()

    def _rows(self):
        rows = []
        for i in range(self.list_lay.count()):
            w = self.list_lay.itemAt(i).widget()
            if isinstance(w, (LayerRow, GroupRow, TextRow)):
                rows.append(w)
        return rows

    def _layer_rows(self):
        return [w for w in self._rows() if isinstance(w, LayerRow)]

    def update_active_thumb(self):
        """只刷新当前图层的缩略图 + 不透明度文字（画完一笔用）。

        整表 refresh() 会把每一行都销毁重建（40 层要 77ms），抬笔时就是「卡一下」。
        而且缩略图本身也不便宜：1600×1200 平滑缩到 42×30 要 20ms 左右。
        所以这里再加一层 150ms 防抖 —— 连笔快速画时只在停笔后更新一次，
        不会卡在运笔中间。
        """
        self._thumb_timer.start()

    def _refresh_active_thumb_now(self):
        if self.doc is None:
            return
        # 正在画的时候绝不重建缩略图（一次 2~20ms，正好卡在运笔中间）
        ctl = getattr(self, "controller", None)
        cv = getattr(ctl, "canvas", None)
        if cv is not None and (getattr(cv, "_stroke", None) is not None
                               or getattr(cv, "_smudge", None) is not None):
            self._thumb_timer.start()      # 等这一笔结束再说
            return
        idx = self.doc.active
        if not (0 <= idx < len(self.doc.layers)):
            return
        layer = self.doc.layers[idx]
        for row in self._layer_rows():
            if row.layer is layer:
                row.thumb.setPixmap(layer.thumb(42, 30))
                row.meta.setText(row._meta_text())
                return

    def update_drag(self, global_pos):
        if getattr(self, "_drag_row", None) is None:
            return
        y = self.list_host.mapFromGlobal(global_pos).y()
        target, side, ly = None, "above", 0
        for w in self._rows():
            top, h = w.y(), w.height()
            if y < top + h / 2:
                target, side, ly = w, "above", top
                break
            target, side, ly = w, "below", top + h
        self._drag_target = (target, side)
        self.drop_line.setGeometry(0, max(0, ly - 1), self.list_host.width(), 2)
        self.drop_line.show()
        self.drop_line.raise_()

    def finish_drag(self):
        if self.drop_line is not None:
            self.drop_line.hide()
        row = getattr(self, "_drag_row", None)
        target, side = getattr(self, "_drag_target", (None, "below"))
        self._drag_row = None
        self._drag_target = None
        self._drag_side = side
        if row is not None:
            row.dragging = False
            row.update()
        if row is None or self.doc is None:
            return
        if isinstance(row, TextRow):
            self._finish_text_drag(row, target)
            return
        dragged = row.layer
        if getattr(dragged, "is_bg", False):
            self.hintRequested.emit(
                "背景层固定在最底层，不能拖动")
            return
        layers = self.doc.layers
        new_group = dragged.group
        if isinstance(target, GroupRow):
            members = self.doc.group_members(target.gid)
            idx = (max(members) + 1) if members else len(layers)
            if target.gid == dragged.group and side == "above":
                # 拖到「自己所在组的标题上沿」= 从组里拿出来，放到组上面。
                # 没有这一条的话，往组标题上拖永远是「加入这个组」，
                # 拖出去就没有任何落点了（用户反馈的「拖不进却拖不出来」）。
                new_group = ""
            else:
                new_group = target.gid
        elif isinstance(target, TextRow):
            # 拖到某段文字上 = 跟着那段文字进同一个组，位置放到那组最上面
            new_group = getattr(target.item, "group", "") or ""
            members = self.doc.group_members(new_group) if new_group else []
            idx = (max(members) + 1) if members else len(layers)
        elif isinstance(target, LayerRow):
            ti = layers.index(target.layer)
            if getattr(target.layer, "is_bg", False):
                # 背景层上面没有别的位置可选：放到它上面那一格，别压到它下面
                idx = ti + 1
                new_group = ""
            else:
                idx = ti + (1 if side == "above" else 0)
                new_group = target.layer.group
        else:
            # 拖到列表下面的空白处 = 移出组，放到底部（背景层上面）
            idx = 0
            new_group = ""
        cur = layers.index(dragged)
        if idx > cur:
            idx -= 1
        if idx == cur and new_group == dragged.group:
            return

        def apply():
            layers.pop(cur)
            at = max(0, min(idx, len(layers)))
            if any(getattr(l, "is_bg", False) for l in layers):
                at = max(1, at)          # 任何图层都压不到背景层下面
            layers.insert(at, dragged)
            if new_group in self.doc.groups or new_group == "":
                dragged.group = new_group
            self.doc.active = self.doc.layers.index(dragged)
            self.doc.prune_groups()
            self.doc.recompose()
            return True

        if self.controller is not None:
            self.controller.run_struct("调整图层顺序", apply)
        else:
            apply()
            self.refresh()
            self.changed.emit()

    def _finish_text_drag(self, row, target):
        """文字对象拖到组标题上 = 进组；拖到组外 = 出组。"""
        doc = self.doc
        item = row.item
        new_group = getattr(item, "group", "") or ""
        if isinstance(target, GroupRow):
            # 拖到「自己所在组的标题上沿」= 移出组（和图层行同一套规则）
            if target.gid == item.group and getattr(self, "_drag_side", "") == "above":
                new_group = ""
            else:
                new_group = target.gid
        elif isinstance(target, LayerRow):
            new_group = target.layer.group or ""
        elif isinstance(target, TextRow):
            new_group = getattr(target.item, "group", "") or ""
        else:
            new_group = ""
        if new_group and new_group not in doc.groups:
            new_group = ""
        if new_group == (getattr(item, "group", "") or ""):
            return

        def apply():
            item.group = new_group
            doc.prune_groups()
            doc.recompose()
            return True

        label = "文字加入图层组" if new_group else "文字移出图层组"
        if self.controller is not None:
            self.controller.run_struct(label, apply)
        else:
            apply()
            self.refresh()
            self.changed.emit()
        g = doc.groups.get(new_group) if new_group else None
        self.hintRequested.emit(
            f"「{item.name}」已放进「{g.name}」" if g
            else f"「{item.name}」已移出图层组")

    # -- 绑定文档
    def set_document(self, doc):
        self.doc = doc
        self.refresh()

    def refresh(self):
        # 清空（先从布局摘掉再销毁，避免残留控件盖住新行）
        while self.list_lay.count():
            item = self.list_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                # 必须先把旧行藏起来：可见的子控件一旦 setParent(None) 就变成顶层窗口，
                # 在 deleteLater 生效前会在屏幕上闪一下（每次刷新图层都闪半个窗口）。
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self.list_lay.addStretch(1)
        if self.doc is None:
            return
        # 组装显示列表：文字（浮在最上层）→ 组标题 + （展开时）组内文字与成员，
        # 成员按 z 序自上而下
        doc = self.doc
        # 文字下标越界（删掉了 / 撤销了）就清掉，否则垃圾桶会去删别人的字
        if self.active_text is not None and not (0 <= self.active_text < len(doc.texts)):
            self.active_text = None
        members = {gid: sorted(doc.group_members(gid), reverse=True) for gid in doc.groups}
        gtexts = {gid: sorted(doc.group_texts(gid), reverse=True) for gid in doc.groups}
        emitted = set()
        skip = set()
        total_h = 0

        def add_text_row(k, indent=0):
            nonlocal total_h
            trow = TextRow(self, doc, doc.texts[k], k, indent=indent)
            trow.selected = (k in self.selected_texts)
            self.list_lay.insertWidget(self.list_lay.count() - 1, trow)
            total_h += TextRow.ROW_H
            return trow

        def add_group_row(gid):
            nonlocal total_h
            grp = doc.groups[gid]
            grows = GroupRow(self, doc, gid, grp,
                             len(members.get(gid, [])) + len(gtexts.get(gid, [])))
            grows.selected = self._group_selected(gid)
            self.list_lay.insertWidget(self.list_lay.count() - 1, grows)
            total_h += GroupRow.ROW_H
            if grp.expanded:
                for k in gtexts.get(gid, []):
                    add_text_row(k, indent=12)
            return grows

        # ① 只有文字、没有图层的组：组标题不会在下面的图层循环里出现，
        #    必须单独补上 —— 否则整组（连同里面的文字）在面板里凭空消失。
        with_layers = {l.group for l in doc.layers if l.group in doc.groups}
        for gid in list(doc.groups):
            if gid in with_layers or not gtexts.get(gid):
                continue
            emitted.add(gid)
            add_group_row(gid)
        # ② 不在组里的文字排在最上面
        for k in range(len(doc.texts) - 1, -1, -1):
            if (getattr(doc.texts[k], "group", "") or "") in doc.groups:
                continue
            add_text_row(k)
        # ③ 图层（组标题 + 展开时组内文字与成员）
        for i in range(len(doc.layers) - 1, -1, -1):
            if i in skip:
                continue
            layer = doc.layers[i]
            gid = layer.group
            if gid and gid in doc.groups:
                if gid in emitted:
                    continue
                emitted.add(gid)
                add_group_row(gid)
                if doc.groups[gid].expanded:
                    for j in members[gid]:
                        row = LayerRow(self, doc, doc.layers[j], j,
                                       self._row_active(j), indent=12)
                        row.selected = (j in self.selected)
                        self.list_lay.insertWidget(self.list_lay.count() - 1, row)
                        total_h += LayerRow.ROW_H
                        skip.add(j)
                continue
            row = LayerRow(self, doc, doc.layers[i], i, self._row_active(i))
            row.selected = (i in self.selected)
            self.list_lay.insertWidget(self.list_lay.count() - 1, row)
            total_h += LayerRow.ROW_H
        # 结构变了（新建/删除/合并）后，下标可能已经错位：只保留仍然有效的，
        # 并且不要自动替用户「补」一个选中（他可能刚点了取消）。
        self.selected = {i for i in getattr(self, "selected", set())
                         if 0 <= i < len(doc.layers)}
        self.selected_texts = {k for k in getattr(self, "selected_texts", set())
                               if 0 <= k < len(doc.texts)}
        if self.active_text is not None and self.active_text not in self.selected_texts:
            self.active_text = None
        if not self.selected and not self.selected_texts and not self._empty_ok:
            self.selected = {self.doc.active}
            self._anchor = self.doc.active
        for row in self._layer_rows():
            row.selected = (row.index in self.selected)
        self.count.setText(f"{len(self.doc.layers)} / {MAX_LAYERS}")
        n_txt = len(getattr(self.doc, "texts", []))
        self.count.setToolTip(f"图层数 / 上限 {MAX_LAYERS}"
                              + (f"\n另有 {n_txt} 段文字（不占图层）" if n_txt else ""))
        # 内容高度不足时 QVBoxLayout 会压缩行高，这里显式撑开，保证出现滚动条
        self.list_host.setMinimumHeight(max(1, total_h))
        self.selectionChanged.emit()
        self._sync_header()
        self._sync_toolbar()

    # -- 交互
    def select(self, index, mods=Qt.NoModifier):
        """单击 = 选中（再点同一行 = 取消）；Ctrl 加选 / 取消；Shift 区间选择。"""
        if self.doc is None or not (0 <= index < len(self.doc.layers)):
            return
        self.active_text = None          # 选了图层就不再「正在编辑哪段文字」
        self._last_group_click = None
        self._empty_ok = False
        if mods & Qt.ControlModifier:
            if index in self.selected:
                self.selected.discard(index)
                if not self.selected:
                    self._empty_ok = True
                elif self.doc.active == index:
                    self.doc.active = max(self.selected)
            else:
                self.selected.add(index)
                self.doc.active = index
        elif mods & Qt.ShiftModifier:
            anchor = getattr(self, "_anchor", self.doc.active)
            lo, hi = sorted((anchor, index))
            self.selected = set(range(lo, hi + 1))
            self.doc.active = index
        elif self.selected == {index} and not self.selected_texts:
            # 再点一下同一行 = 取消选中（用户要的「单击选中、再单击取消」）
            self.selected = set()
            self._empty_ok = True
        elif len(self.selected_texts) >= 2:
            # 已经在多选文字：点图层 = 把它加进来，别把文字全清掉
            self.selected.add(index)
            self.doc.active = index
        else:
            self.selected = {index}
            self.selected_texts = set()
            self.doc.active = index
        self._anchor = index
        self._sync_active()
        self.activeChanged.emit()
        self.selectionChanged.emit()

    def _sync_active(self):
        """只更新选中态，不重建行控件（重建会打断正在进行的拖动）。"""
        if self.doc is None:
            return
        for i in range(self.list_lay.count()):
            row = self.list_lay.itemAt(i).widget()
            if isinstance(row, LayerRow):
                row.active = self._row_active(row.index)
                row.selected = (row.index in getattr(self, "selected", set()))
                row.name.setStyleSheet(
                    f"color: {C.TEXT if row.active or row.selected else C.TEXT_DIM}; "
                    "font-size: 11px;")
                row.update()
            elif isinstance(row, TextRow):
                row.selected = (row.index in getattr(self, "selected_texts", set()))
                row.update()
            elif isinstance(row, GroupRow):
                row.selected = self._group_selected(row.gid)
                row.update()
        self._sync_header()
        self._sync_toolbar()

    # -- 文字对象 ---------------------------------------------------
    def _row_active(self, index):
        """图层行是否要画成「当前层」。

        选中文字的时候一律不画：否则文字行亮着、当前图层行也亮着，
        看着像「点一下文字就把下面的图层一起选中了」。
        """
        return index == self.doc.active and self.active_text is None

    def _group_selected(self, gid):
        """组里所有成员（图层 + 文字）都被选中了才算「整组选中」。"""
        if self.doc is None:
            return False
        mem = set(self.doc.group_members(gid)) | set(self.doc.group_texts(gid))
        return bool(mem) and mem.issubset(
            set(getattr(self, "selected", set()))
            | set(getattr(self, "selected_texts", set())))

    def select_text(self, index, mods=Qt.NoModifier):
        """选中一段文字 —— 和图层完全一样：单击选中 / 再单击取消 / Ctrl 加选。"""
        if self.doc is None or not (0 <= index < len(self.doc.texts)):
            return
        self.setFocus()              # 焦点留在面板：Backspace 才会走到「删文字」
        self._empty_ok = False
        self._last_group_click = None
        if mods & Qt.ControlModifier:
            if index in self.selected_texts:
                self.selected_texts.discard(index)
                if not self.selected_texts:
                    self.active_text = None
                    if not self.selected:
                        self._empty_ok = True
            else:
                self.selected_texts.add(index)
                self.active_text = index
        elif mods & Qt.ShiftModifier:
            anchor = getattr(self, "_text_anchor", index)
            lo, hi = sorted((anchor, index))
            self.selected_texts = set(range(lo, hi + 1))
            self.active_text = index
        elif self.selected_texts == {index} and not self.selected:
            # 再点一下同一行 = 取消选中
            self.selected_texts = set()
            self.active_text = None
            self._empty_ok = True
        elif len(self.selected) >= 2:
            # 已经在多选图层：把这段文字加进来（保留图层多选）
            self.selected_texts.add(index)
            self.active_text = index
        else:
            self.selected = set()
            self.selected_texts = {index}
            self.active_text = index
        self._text_anchor = index
        self._sync_active()
        it = self.doc.texts[index]
        g = self.doc.group_of_text(it)
        n_sel = len([i for i in self.selected if 0 <= i < len(self.doc.layers)])
        n_txt = len(self.selected_texts)
        if n_sel or n_txt > 1:
            tail = "已选中 " + " + ".join(
                [x for x in ((f"{n_sel} 个图层" if n_sel else ""),
                             (f"{n_txt} 段文字" if n_txt > 1 else "")) if x])
            tail += "（Ctrl+G 可以一起建组，垃圾桶一起删）"
        else:
            tail = "右下角垃圾桶 / Backspace 删的是它，双击可以接着改字"
        self.hintRequested.emit(
            f"已选中文字「{it.name}」" + (f"（在组「{g.name}」里）" if g else "")
            + "　" + tail)
        self.selectionChanged.emit()
        self.activeChanged.emit()

    def select_group(self, gid):
        """单击组标题 = 选中组里所有图层和文字；再点同一个组标题 = 取消。"""
        if self.doc is None or gid not in self.doc.groups:
            return
        mem = set(self.doc.group_members(gid))
        txs = set(self.doc.group_texts(gid))
        g = self.doc.groups[gid]
        if not mem and not txs:
            return
        # 只有「上一次点的就是这个组标题」才算「再点一下」。
        # 否则刚建完组（成员还选着）点一下组标题会直接变成取消，看着像没反应。
        all_sel = (mem | txs).issubset(
            set(self.selected) | set(self.selected_texts))
        if all_sel and self._last_group_click == gid:
            self.selected = set()
            self.selected_texts = set()
            self.active_text = None
            self._empty_ok = True
            self._last_group_click = None
            self._sync_active()
            self.activeChanged.emit()
            self.selectionChanged.emit()
            self.hintRequested.emit(f"已取消选中组「{g.name}」")
            return
        self.selected = set(mem)
        self.selected_texts = set(txs)
        self.active_text = (max(txs) if txs else None)
        self._last_group_click = gid
        if mem:
            self.doc.active = max(mem)
            self._anchor = max(mem)
        self._sync_active()
        self.activeChanged.emit()
        self.selectionChanged.emit()
        bits = []
        if mem:
            bits.append(f"{len(mem)} 个图层")
        if txs:
            bits.append(f"{len(txs)} 段文字")
        self.hintRequested.emit(
            f"已选中组「{g.name}」里的 " + " + ".join(bits)
            + "　再点一次组标题可以取消选中")

    def move_layer_out_of_group(self, index):
        """把某个图层移出它所在的组（图层留在原位，只是不再成组）。"""
        doc = self.doc
        if doc is None or not (0 <= index < len(doc.layers)):
            return
        layer = doc.layers[index]
        gid = layer.group
        if not gid or gid not in doc.groups:
            return
        g = doc.groups[gid]

        def apply():
            layer.group = ""
            doc.prune_groups()
            doc.recompose()
            return True

        if self.controller is not None:
            self.controller.run_struct("移出图层组", apply)
        else:
            apply()
            self.refresh()
            self.changed.emit()
        self.hintRequested.emit(f"「{layer.name}」已移出「{g.name}」")

    def move_text_to_group(self, index, gid):
        """把某段文字放进 / 移出图层组（gid 传空串 = 移出）。"""
        doc = self.doc
        if doc is None or not (0 <= index < len(doc.texts)):
            return
        if gid and gid not in doc.groups:
            return
        it = doc.texts[index]

        def apply():
            it.group = gid
            doc.prune_groups()
            doc.recompose()
            return True

        label = "文字加入图层组" if gid else "文字移出图层组"
        if self.controller is not None:
            self.controller.run_struct(label, apply)
        else:
            apply()
            self.refresh()
            self.changed.emit()
        g = doc.groups.get(gid) if gid else None
        self.hintRequested.emit(f"「{it.name}」已放进「{g.name}」" if g
                                else f"「{it.name}」已移出图层组")

    def delete_text(self, index):
        """删除一段文字（带撤销）。返回是否真的删掉了。"""
        doc = self.doc
        if doc is None or not (0 <= index < len(doc.texts)):
            return False
        name = doc.texts[index].name
        edit = TextEdit(doc, "删除文字")
        doc.remove_text(index)
        edit.capture(doc)
        doc.push(edit)
        self.active_text = None
        self.selected_texts = {k for k in self.selected_texts if k < index}
        self.refresh()
        self.changed.emit()
        self.hintRequested.emit(f"已删除文字「{name}」")
        return True

    def _deletable_layers(self):
        """当前选中、且真的能删的图层下标（背景层 / 删到只剩一层时排除）。"""
        doc = self.doc
        if doc is None:
            return []
        idx = sorted(i for i in getattr(self, "selected", set())
                     if 0 <= i < len(doc.layers)
                     and not getattr(doc.layers[i], "is_bg", False))
        # 至少要留一个图层
        keep = len(doc.layers) - len(idx)
        if keep < 1:
            idx = idx[:max(0, len(doc.layers) - 1)]
        return idx

    def _deletable_texts(self):
        doc = self.doc
        if doc is None:
            return []
        idx = {k for k in getattr(self, "selected_texts", set())
               if 0 <= k < len(doc.texts)}
        # 光标所在的那段也算（从画布点进来编辑时可能没有勾进多选）
        if self.active_text is not None and 0 <= self.active_text < len(doc.texts):
            idx.add(self.active_text)
        return sorted(idx)

    def remove_selection(self):
        """垃圾桶 / Backspace 的统一入口：删掉「选中的文字 + 选中的图层」。

        一步撤销。返回 False 表示这里没什么可删的，交给主窗口按老路子删当前图层。
        """
        doc = self.doc
        if doc is None:
            return False
        texts = self._deletable_texts()
        layers = self._deletable_layers()
        if not texts and len(layers) < 2:
            # 只选了一个图层 / 什么都没选：保持原来的行为（主窗口会处理
            # 背景层、只剩一层的提示）
            return False
        names = [doc.texts[k].name for k in texts]
        edit = StructEdit(doc, "删除" if (texts and layers) else
                          ("删除文字" if texts else "删除图层"))
        for k in reversed(texts):
            doc.texts.pop(k)
        for i in reversed(layers):
            doc.layers.pop(i)
        doc.prune_groups()
        doc.active = max(0, min(doc.active, len(doc.layers) - 1))
        doc.modified = True
        doc.recompose()
        edit.capture(doc)
        doc.push(edit)
        self.active_text = None
        self.selected_texts = set()
        self.selected = {doc.active}
        self._anchor = doc.active
        self.refresh()
        self.changed.emit()
        parts = []
        if texts:
            parts.append(f"{len(texts)} 段文字" if len(texts) > 1
                         else f"文字「{names[0]}」")
        if layers:
            parts.append(f"{len(layers)} 个图层")
        self.hintRequested.emit("已删除 " + " 和 ".join(parts) + "（Ctrl+Z 可撤销）")
        return True

    def remove_active(self):
        """兼容旧调用：选中文字时删文字。"""
        return self.remove_selection()

    def _sync_header(self):
        if self.doc is None:
            return
        if self.active_text is not None and 0 <= self.active_text < len(self.doc.texts):
            it = self.doc.texts[self.active_text]
            self.opacity.setEnabled(False)
            n_t = len(getattr(self, "selected_texts", set()))
            n_l = len(getattr(self, "selected", set()))
            if n_l or n_t > 1:
                bits = []
                if n_l:
                    bits.append(f"{n_l} 图层")
                if n_t:
                    bits.append(f"{n_t} 文字")
                self.active_label.setText("→ 已选 " + " + ".join(bits))
            else:
                self.active_label.setText(f"→ {it.name}（文字）")
            self.active_label.setToolTip(
                "不透明度只作用于像素图层；文字请改「文字颜色」或在组里调组不透明度")
            return
        if getattr(self, "selected_texts", None) and not self.selected:
            self.opacity.setEnabled(False)
            self.active_label.setText(f"→ 已选 {len(self.selected_texts)} 段文字")
            self.active_label.setToolTip("不透明度只作用于像素图层")
            return
        self.opacity.setEnabled(True)
        cur = self.doc.layer
        self.opacity.blockSignals(True)
        op = int(round((cur.opacity if cur else 1.0) * 100))
        self.opacity.setValue(op)
        self.opacity_val.setText(f"{op}%")
        self.opacity.blockSignals(False)
        self.active_label.setText(f"→ {cur.name}" if cur else "")
        self.active_label.setToolTip(
            f"不透明度作用于「{cur.name}」" if cur else "")

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Backspace, Qt.Key_Delete):
            if self.remove_selection():
                return
            self.added.emit(3)
            return
        super().keyPressEvent(e)

    def toggle_lock(self, index):
        if self.doc is None:
            return
        layer = self.doc.layers[index]
        layer.locked = not layer.locked
        self.refresh()
        self.changed.emit()
        self.hintRequested.emit(
            f"「{layer.name}」已锁定，无法绘画 / 填充 / 移动" if layer.locked
            else f"「{layer.name}」已解锁")

    def toggle_visible(self, index):
        if self.doc is None:
            return
        layer = self.doc.layers[index]
        layer.visible = not layer.visible
        self.doc.recompose()
        self.refresh()
        self.changed.emit()

    def rename(self, index, name):
        if self.doc is None:
            return
        self.doc.layers[index].name = name
        self.refresh()
        self.changed.emit()

    def _targets(self):
        """不透明度作用于所有选中的图层（单选时就是当前层）。"""
        if self.doc is None:
            return []
        sel = sorted(i for i in getattr(self, "selected", set())
                     if 0 <= i < len(self.doc.layers))
        if len(sel) >= 2:
            return [self.doc.layers[i] for i in sel]
        if not sel and getattr(self, "selected_texts", None):
            return []          # 只选了文字：没有图层可调
        return [self.doc.layer] if self.doc.layer is not None else []

    def _on_opacity(self, v):
        # 只改数值 + 数字，不立刻整图重合成（那是 10~20ms 的重活）
        self.opacity_val.setText(f"{v}%")
        targets = self._targets()
        if not targets:
            return
        for l in targets:
            l.opacity = v / 100.0
        if not self._op_flush.isActive():
            self._op_flush.start()

    def _flush_opacity(self):
        if self.doc is None:
            return
        self.doc.recompose()
        self.changed.emit()
        self._warn_if_empty()

    def _warn_if_empty(self):
        layer = self.doc.layer if self.doc else None
        if layer is not None and not getattr(layer, "has_content", True):
            self.hintRequested.emit(
                f"「{layer.name}」是空图层：调不透明度也看不出变化，请先选中有内容的图层")

    # -- 按钮（交给主窗口做撤销包装）
    def add_layer(self):
        if self.doc is None:
            return
        self.added.emit(1)

    def duplicate_layer(self):
        if self.doc is None:
            return
        self.added.emit(2)

    def remove_layer(self):
        if self.doc is None:
            return
        # 选中的是文字对象 / 多个图层 → 一起删（一步撤销），
        # 不然「多选三个图层按垃圾桶只掉一个」。
        if self.remove_selection():
            return
        self.added.emit(3)

    def merge_down(self):
        if self.doc is None:
            return
        self.added.emit(4)

    def make_group(self):
        if self.doc is None:
            return
        self.added.emit(7)

    def ungroup_group(self):
        if self.doc is None:
            return
        self.added.emit(8)

    def rename_group(self, gid, name):
        g = self.doc.groups.get(gid) if self.doc is not None else None
        if g is None:
            return
        name = (name or "").strip()
        if name and name != g.name:
            g.name = name
            self.refresh()
            self.changed.emit()

    # -- 右键菜单（新人不用记快捷键也能摸到这些操作）
    def show_layer_menu(self, row, index, gpos):
        if self.doc is None or not (0 <= index < len(self.doc.layers)):
            return
        layer = self.doc.layers[index]
        m = QMenu(self)
        a = m.addAction("新建组…\tCtrl+G")
        a.triggered.connect(lambda: self.added.emit(7))
        a_un = m.addAction("解散组\tCtrl+Shift+G")
        a_un.setEnabled(bool(layer.group))
        a_un.triggered.connect(lambda: self.added.emit(8))
        m.addSeparator()
        a_rn = m.addAction("重命名…")
        a_rn.triggered.connect(row._start_rename)
        a_out = m.addAction("移出图层组")
        a_out.setEnabled(bool(layer.group))
        a_out.triggered.connect(lambda: self.move_layer_out_of_group(index))
        a_dup = m.addAction("复制图层\tCtrl+J")
        a_dup.triggered.connect(lambda: self.added.emit(2))
        a_del = m.addAction("删除图层\tBackspace")
        a_del.setEnabled(not getattr(layer, "is_bg", False) and len(self.doc.layers) > 1)
        a_del.triggered.connect(lambda: self.added.emit(3))
        m.exec(gpos)

    def show_group_menu(self, row, gpos):
        if self.doc is None:
            return
        g = row.group
        m = QMenu(self)
        a_fold = m.addAction("折叠组" if g.expanded else "展开组")
        a_fold.triggered.connect(row._toggle_expand)
        a_rn = m.addAction("重命名组…")
        a_rn.triggered.connect(lambda: self._ask_rename_group(row.gid))
        m.addSeparator()
        a_vis = m.addAction("隐藏组" if g.visible else "显示组")
        a_vis.triggered.connect(row._toggle_visible)
        a_lock = m.addAction("解锁组" if g.locked else "锁定组")
        a_lock.triggered.connect(row._toggle_lock)
        m.addSeparator()
        a_un = m.addAction("解散组\tCtrl+Shift+G")
        a_un.triggered.connect(lambda: self.added.emit(8))
        m.exec(gpos)

    def _ask_rename_group(self, gid):
        g = self.doc.groups.get(gid) if self.doc is not None else None
        if g is None:
            return
        name, ok = dialogs.get_text(self, "重命名组", "组名：", text=g.name)
        if ok:
            self.rename_group(gid, name)

    def _sync_toolbar(self):
        """按钮的可用状态跟着「选中的图层 / 文字」走。"""
        if self.doc is None:
            return
        cur = self.doc.layer
        bg_cur = bool(cur is not None and getattr(cur, "is_bg", False))
        n_txt = len(self._deletable_texts())
        has_text = n_txt > 0
        sel = [self.doc.layers[i] for i in sorted(self.selected)
               if 0 <= i < len(self.doc.layers)]
        if not sel and not has_text and cur is not None:
            sel = [cur]
        n_del = len(self._deletable_layers())
        self.tb["group"].setEnabled(bool(sel) or has_text)
        self.tb["ungroup"].setEnabled(
            (has_text and any(getattr(self.doc.texts[k], "group", "")
                              for k in self._deletable_texts()))
            or any(l.group for l in sel))
        self.tb["up"].setEnabled(not has_text and cur is not None and not bg_cur
                                 and self.doc.active < len(self.doc.layers) - 1)
        self.tb["down"].setEnabled(not has_text and cur is not None and not bg_cur
                                   and self.doc.active > 0)
        self.tb["trash"].setEnabled(has_text or n_del >= 1)
        self.tb["merge"].setEnabled(not has_text and len(self.doc.layers) > 1)
        self.tb["copy"].setEnabled(not has_text)
        if has_text and n_del:
            self.tb["trash"].setToolTip(
                f"删除选中的 {n_txt} 段文字 + {n_del} 个图层")
        elif has_text:
            self.tb["trash"].setToolTip(f"删除选中的 {n_txt} 段文字")
        elif n_del >= 2:
            self.tb["trash"].setToolTip(f"删除选中的 {n_del} 个图层　Backspace")
        else:
            self.tb["trash"].setToolTip("删除图层　Backspace（焦点在图层面板时）")

    def move_layer(self, delta):
        if self.doc is None:
            return
        self.added.emit(5 if delta > 0 else 6)
