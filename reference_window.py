# -*- coding: utf-8 -*-
"""U Draw - 参考图窗口

一个能浮在画布上方的独立小窗：载入一张参考图，缩放 / 翻转 / 调透明度，
方便临摹。

两个设计取舍：

* **窗口本体不透明，只有图片半透明**。
  以前用 setWindowOpacity 调透明度，连标题栏、按钮一起变淡，看着和主界面
  完全不是一个东西（用户反馈「参考 UI 不一致」）。现在标题栏用和应用一致的
  配色与控件，透明度只作用在图片上 —— 框子是清楚的，图是透的。
* **窗口背景整体透明（WA_TranslucentBackground）**，图片之外的地方能直接
  看到下面的画布，这才是「叠着临摹」该有的样子。
"""

import os

from PySide6.QtCore import (QEvent, QPoint, QPointF, QRect, QRectF, QSettings,
                            QSize, Qt, QTimer, Signal)
from PySide6.QtGui import (QAction, QColor, QFont, QImage, QKeySequence, QPainter,
                           QPen, QTransform)
from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QLabel,
                               QSizeGrip, QSizePolicy, QToolButton, QVBoxLayout,
                               QWidget)

import icons
from canvas import load_image_file
from panels import NoWheelSlider
from theme import C

TITLE_H = 28
BAR_H = 30
MIN_W, MIN_H = 280, 220
BTN = 22
IMG_FILTER = ("图片 (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff "
              "*.psd *.pdn *.tga);;所有文件 (*)")

BTN_TIPS = {
    "load": "载入参考图（也可以直接把图片拖进来）",
    "clear": "清空参考图（图片移出窗口，窗口设置保留）",
    "fit": "适配窗口（双击标题栏 / Alt+0 同效）",
    "flip": "水平翻转",
    "lock": "锁定位置：锁定后不能拖动 / 缩放 / 滚轮缩放，防止临摹时误碰",
    "close": "关闭参考图窗口（视图菜单可再打开）",
}

# 键盘 / 数位板快捷键：临摹的人是「一边画一边调参考图」，
# 所以用 ApplicationShortcut —— 画布有焦点时也要生效，
# 不然每调一次都得先用笔点一下参考图窗口，完全没法用。
KEY_ACTIONS = (
    ("Alt+=", "zoom_in"), ("Alt++", "zoom_in"),
    ("Alt+-", "zoom_out"),
    ("Alt+0", "fit"),
    ("Alt+Left", "pan_left"), ("Alt+Right", "pan_right"),
    ("Alt+Up", "pan_up"), ("Alt+Down", "pan_down"),
)


class _TitleBar(QWidget):
    """标题栏：按住空白处拖动整窗，双击 = 适配窗口。"""

    def __init__(self, win: "ReferenceWindow"):
        super().__init__(win)
        self.win = win
        self.setFixedHeight(TITLE_H)
        self.setCursor(Qt.ArrowCursor)
        self._press = None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = (e.globalPosition().toPoint(), self.win.pos())

    def mouseMoveEvent(self, e):
        if self._press is None or self.win.locked:
            return
        g = e.globalPosition().toPoint()
        self.win.move(self._press[1] + (g - self._press[0]))

    def mouseReleaseEvent(self, e):
        self._press = None

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.win.fit_window()


class _View(QWidget):
    """图片区：滚轮缩放、Ctrl+滚轮调透明度、拖动平移。"""

    def __init__(self, win: "ReferenceWindow"):
        super().__init__(win)
        self.win = win
        self.setMouseTracking(True)
        self._press = None

    def paintEvent(self, e):
        img = self.win.shown_image()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        if img.isNull():
            # 空状态：垫一层半透明底，否则文字会直接糊在画布上看不清
            box = QRectF(self.rect()).adjusted(10, 10, -10, -10)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(24, 24, 24, 165))
            p.drawRoundedRect(box, 6, 6)
            p.setPen(QColor(C.TEXT_DIM))
            p.setFont(QFont("Microsoft YaHei UI", 9))
            p.drawText(box, Qt.AlignCenter, "把图片拖进来\n或点标题栏的图片按钮载入")
            p.end()
            return
        p.setRenderHint(QPainter.SmoothPixmapTransform, self.win.zoom < 2.0)
        p.setOpacity(self.win.alpha)
        w = img.width() * self.win.zoom
        h = img.height() * self.win.zoom
        p.drawImage(QRectF(self.win.ox, self.win.oy, w, h), img)
        p.end()

    def mousePressEvent(self, e):
        self.win._view_pos = e.position()
        if e.button() == Qt.LeftButton and not self.win.shown_image().isNull():
            if self.win.locked:
                return
            self._press = (e.position(), self.win.ox, self.win.oy)
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        self.win._view_pos = e.position()      # 键盘缩放以它为锚点
        if self._press is None:
            return
        pos, ox, oy = self._press
        self.win.ox = ox + (e.position().x() - pos.x())
        self.win.oy = oy + (e.position().y() - pos.y())
        self.win.fit = False
        self.win.update()

    def mouseReleaseEvent(self, e):
        self._press = None
        self.setCursor(Qt.ArrowCursor)

    def wheelEvent(self, e):
        dy = e.angleDelta().y()
        if dy == 0:
            return
        if e.modifiers() & Qt.ControlModifier:
            self.win.set_alpha(self.win.alpha + (0.02 if dy > 0 else -0.02))
        else:
            self.win.zoom_at(e.position(), 1.12 if dy > 0 else 1 / 1.12)
        e.accept()

    def enterEvent(self, e):
        if not self.win.locked and not self.win.shown_image().isNull():
            self.setCursor(Qt.OpenHandCursor)

    def leaveEvent(self, e):
        self.setCursor(Qt.ArrowCursor)


class ReferenceWindow(QWidget):
    """可悬浮的参考图窗口（每个主窗口一个实例）。"""

    closed = Signal()
    activated = Signal()      # 窗口里任何一处被按下：主窗口据此把缩放快捷键切过来

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window | Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(MIN_W, MIN_H)
        self.setWindowTitle("参考图")

        self._img = QImage()
        self._shown = QImage()
        self.zoom = 1.0
        self.ox = 0.0                 # 图片左上角在图片区里的位置
        self.oy = 0.0
        self.alpha = 1.0              # 只作用在图片上
        self.flip = False
        self.fit = True               # 自动适配：改窗口大小时重新算缩放
        self.locked = False
        self.buttons = {}
        self._view_pos = None     # 鼠标在图片区里的最后位置（键盘缩放跟着它走）
        self._notice = ""
        self._notice_timer = QTimer(self)
        self._notice_timer.setSingleShot(True)
        self._notice_timer.setInterval(2600)
        self._notice_timer.timeout.connect(self._clear_notice)

        self._build()
        # 标题栏 / 底栏各自带不透明底色。
        # 以前是靠父窗口 paintEvent 画，依赖透明窗口的合成 —— 有些机器上那层
        # 合成没生效，标题栏就变成「白底浅字」（用户反馈的「颜色有问题」）。
        self.setStyleSheet(
            f"QWidget#refTop {{ background: {C.CHROME};"
            " border-bottom: 1px solid #101010; }"
            f"QWidget#refBottom {{ background: {C.CHROME};"
            " border-top: 1px solid #101010; }")
        self._install_shortcuts()
        # 点窗口里的任何地方（按钮 / 标题栏 / 图片区）都算「切到参考图」。
        # 只靠窗口自己的 mousePressEvent 收不到按钮上的点击，所以挂应用级过滤器。
        QApplication.instance().installEventFilter(self)
        self._restore()
        self._sync_buttons()
        self._sync_labels()

    # ------------------------------------------------------------ UI
    def _mk_btn(self, key: str, icon_name: str = None, text: str = "") -> QToolButton:
        b = QToolButton(self)
        b.setFixedSize(BTN, BTN)
        b.setIconSize(QSize(14, 14))
        if icon_name:
            b.setIcon(icons.icon(icon_name, C.ICON, 14))
        if text:
            b.setText(text)
            b.setStyleSheet(
                "QToolButton { border: none; background: transparent; border-radius: 3px;"
                f" color: {C.TEXT_DIM}; font-size: 15px; }}"
                f"QToolButton:hover {{ background: {C.HOVER}; color: {C.TEXT}; }}"
                f"QToolButton:pressed {{ background: {C.PRESSED}; }}")
        else:
            b.setStyleSheet(
                "QToolButton { border: none; background: transparent; border-radius: 3px; }"
                f"QToolButton:hover {{ background: {C.HOVER}; }}"
                f"QToolButton:pressed {{ background: {C.PRESSED}; }}"
                f"QToolButton:checked {{ background: {C.ACCENT}; }}")
        b.setToolTip(BTN_TIPS.get(key, ""))
        b.setCursor(Qt.PointingHandCursor)
        self.buttons[key] = b
        return b

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 标题栏：只有标题 + 按钮。文件名 / 状态一律不往这儿塞 ——
        # 窗口一窄就会被按钮挤掉半个字（实测「参考图」的「图」被截断）。
        self.title_bar = _TitleBar(self)
        self.title_bar.setObjectName("refTop")
        tl = QHBoxLayout(self.title_bar)
        tl.setContentsMargins(9, 0, 5, 0)
        tl.setSpacing(2)
        self.title_label = QLabel("参考图", self.title_bar)
        self.title_label.setStyleSheet(
            f"color: {C.TEXT_DIM}; font-size: 11px; background: transparent;")
        tl.addWidget(self.title_label)
        tl.addStretch(1)

        b_load = self._mk_btn("load", "image")
        b_load.clicked.connect(self.load_dialog)
        b_clear = self._mk_btn("clear", "trash")
        b_clear.clicked.connect(self.clear)
        b_fit = self._mk_btn("fit", "reset")
        b_fit.clicked.connect(self.fit_window)
        self.b_flip = self._mk_btn("flip", "flip_h")
        self.b_flip.clicked.connect(self.toggle_flip)
        self.b_lock = self._mk_btn("lock", "unlock")
        self.b_lock.clicked.connect(self.toggle_lock)
        # 锁定按钮不铺蓝色选中底：状态靠图标本身表达（红色上锁 / 灰色开锁），
        # 和左侧图层面板里那个锁保持一致的读法
        self.b_lock.setStyleSheet(
            "QToolButton { border: none; background: transparent; border-radius: 3px; }"
            f"QToolButton:hover {{ background: {C.HOVER}; }}"
            f"QToolButton:pressed {{ background: {C.PRESSED}; }}")
        b_close = self._mk_btn("close", None, "×")
        b_close.clicked.connect(self.close)
        for b in (b_load, b_clear, b_fit, self.b_flip, self.b_lock, b_close):
            tl.addWidget(b)
        outer.addWidget(self.title_bar)

        # 图片区
        self.view = _View(self)
        outer.addWidget(self.view, 1)

        # 底部：透明度滑杆（自由调节）+ 缩放读数 + 缩放角
        self.bottom = QWidget(self)
        self.bottom.setObjectName("refBottom")
        self.bottom.setFixedHeight(BAR_H)
        bl = QHBoxLayout(self.bottom)
        bl.setContentsMargins(9, 0, 4, 0)
        bl.setSpacing(6)
        lbl = QLabel("透明度", self.bottom)
        lbl.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 11px; background: transparent;")
        bl.addWidget(lbl)
        self.alpha_slider = NoWheelSlider(Qt.Horizontal, self.bottom)
        self.alpha_slider.setRange(5, 100)
        self.alpha_slider.setValue(100)
        self.alpha_slider.setFixedHeight(16)
        self.alpha_slider.setMinimumWidth(56)
        self.alpha_slider.setMaximumWidth(160)
        self.alpha_slider.setToolTip("参考图的不透明度：往左拖更透，能看到下面的画布")
        self.alpha_slider.valueChanged.connect(self._on_alpha_slider)
        # 滑杆吃掉多余宽度：窗口变窄时先压滑杆，不要把文字挤掉
        bl.addWidget(self.alpha_slider, 1)
        self.alpha_label = QLabel("100%", self.bottom)
        self.alpha_label.setFixedWidth(34)
        self.alpha_label.setStyleSheet(
            f"color: {C.TEXT}; font-size: 11px; background: transparent;")
        bl.addWidget(self.alpha_label)
        self.zoom_label = QLabel("", self.bottom)
        self.zoom_label.setStyleSheet(
            f"color: {C.TEXT_FAINT}; font-size: 10px; background: transparent;")
        # 读数再长也不许把右下角的缩放手柄挤出去
        self.zoom_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.zoom_label.setToolTip(
            "点一下本窗口，Ctrl+= / Ctrl+- / Ctrl+0 就作用在这里\n"
            "（Alt+= / Alt+- / Alt+0 任何时候都能用）")
        bl.addWidget(self.zoom_label)
        grip = QSizeGrip(self.bottom)
        grip.setFixedSize(14, 14)
        bl.addWidget(grip, 0, Qt.AlignBottom | Qt.AlignRight)
        outer.addWidget(self.bottom)

    # ------------------------------------------------------------ 快捷键
    def _install_shortcuts(self):
        """键盘 / 数位板快捷键：Alt+= / Alt+- 缩放、Alt+0 适配、Alt+方向键平移。

        用 ApplicationShortcut 是为了「画布有焦点时也生效」—— 临摹的时候人是在
        画布上画，参考图窗口没有焦点，普通窗口快捷键根本收不到。
        """
        slots = {
            "zoom_in": lambda: self._key_zoom(True),
            "zoom_out": lambda: self._key_zoom(False),
            "fit": self.fit_window,
            "pan_left": lambda: self._key_pan(-1, 0),
            "pan_right": lambda: self._key_pan(1, 0),
            "pan_up": lambda: self._key_pan(0, -1),
            "pan_down": lambda: self._key_pan(0, 1),
        }
        self._key_actions = []
        for keys, name in KEY_ACTIONS:
            a = QAction(self)
            a.setShortcut(QKeySequence(keys))
            a.setShortcutContext(Qt.ApplicationShortcut)
            a.triggered.connect(slots[name])
            self.addAction(a)
            self._key_actions.append(a)

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.MouseButtonPress and isinstance(obj, QWidget):
            if obj.window() is self:
                self.activated.emit()
        return False

    def zoom_step(self, up: bool):
        """键盘 / 菜单缩放：和画布一样，**跟着鼠标位置**缩放。

        鼠标不在图片区里（或还没进过窗口）才退回中心缩放。
        """
        if not self.isVisible() or self._img.isNull():
            return
        anchor = self._view_pos
        if anchor is None or not self.view.rect().contains(anchor.toPoint()):
            anchor = QPointF(self.view.width() / 2.0, self.view.height() / 2.0)
        self.zoom_at(anchor, 1.25 if up else 0.8, force=True)

    def zoom_100(self):
        """实际像素（Ctrl+1）。"""
        if not self.isVisible() or self._img.isNull():
            return
        c = QPointF(self.view.width() / 2.0, self.view.height() / 2.0)
        self.zoom_at(c, 1.0 / max(1e-6, self.zoom), force=True)
        self._say("100%")

    def _key_zoom(self, up: bool):
        self.zoom_step(up)

    def _key_pan(self, dx: int, dy: int):
        if not self.isVisible() or self.locked:
            return
        step = 40
        self.ox += dx * step
        self.oy += dy * step
        self.fit = False
        self.view.update()

    def keyPressEvent(self, e):
        """窗口有焦点时的普通按键（不用 Alt 也行）。"""
        k = e.key()
        if k in (Qt.Key_Plus, Qt.Key_Equal):
            self._key_zoom(True)
        elif k == Qt.Key_Minus:
            self._key_zoom(False)
        elif k == Qt.Key_0:
            self.fit_window()
        elif k == Qt.Key_Left:
            self._key_pan(-1, 0)
        elif k == Qt.Key_Right:
            self._key_pan(1, 0)
        elif k == Qt.Key_Up:
            self._key_pan(0, -1)
        elif k == Qt.Key_Down:
            self._key_pan(0, 1)
        else:
            super().keyPressEvent(e)

    # ------------------------------------------------------------ 设置
    @staticmethod
    def _settings():
        return QSettings("PhotoCraftDraw", "PhotoCraftDraw")

    def _restore(self):
        st = self._settings()
        geo = st.value("refwin/geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        else:
            self.resize(420, 480)
            par = self.parentWidget()
            if par is not None:
                g = par.geometry()
                self.move(max(0, g.right() - self.width() - 60), g.top() + 90)
        try:
            # 老版本存的是 windowOpacity，读回来当图片透明度用
            self.alpha = max(0.05, min(1.0, float(st.value("refwin/alpha",
                                                          st.value("refwin/opacity", 1.0)))))
        except (TypeError, ValueError):
            self.alpha = 1.0
        self.locked = str(st.value("refwin/lock", "false")).lower() in ("true", "1")

    def _save(self):
        st = self._settings()
        st.setValue("refwin/geometry", self.saveGeometry())
        st.setValue("refwin/alpha", float(self.alpha))
        st.setValue("refwin/lock", bool(self.locked))
        st.sync()

    # ------------------------------------------------------------ 内容
    def has_image(self) -> bool:
        return not self._img.isNull()

    def image(self) -> QImage:
        return self._img

    def shown_image(self) -> QImage:
        return self._shown

    def load(self, path: str) -> bool:
        if not path or not os.path.isfile(path):
            return False
        img = load_image_file(path)
        if img is None or img.isNull():
            self._say("这张图片读不出来")
            return False
        self._img = img
        self._rebuild_shown()
        self.fit = True
        self._apply_fit()
        # 只报尺寸，不报文件名 —— 长文件名会把底栏撑宽
        self._say(f"{img.width()}×{img.height()}")
        self.update()
        return True

    def load_dialog(self):
        start = self._settings().value("refwin/last_dir", "") or ""
        path, _ = QFileDialog.getOpenFileName(self, "载入参考图", start, IMG_FILTER)
        if path and self.load(path):
            self._settings().setValue("refwin/last_dir", os.path.dirname(path))

    def clear(self):
        """清空参考图：图片、缩放、平移一起复位，窗口本身不动。"""
        self._img = QImage()
        self._shown = QImage()
        self.zoom, self.ox, self.oy = 1.0, 0.0, 0.0
        self.fit = True
        self._sync_labels()
        self.view.update()
        self.update()
        self._say("已清空参考图")

    def _rebuild_shown(self):
        if self._img.isNull():
            self._shown = QImage()
        else:
            # 翻转结果缓存下来：每帧 mirrored 一遍 4K 图会明显掉帧
            self._shown = (self._img.transformed(QTransform().scale(-1, 1))
                           if self.flip else self._img)

    # ------------------------------------------------------------ 几何
    def _apply_fit(self):
        vw, vh = max(1, self.view.width()), max(1, self.view.height())
        if self._img.isNull():
            self.zoom, self.ox, self.oy = 1.0, 0.0, 0.0
            self._sync_labels()
            return
        iw, ih = self._img.width(), self._img.height()
        s = min(vw / max(1, iw), vh / max(1, ih))
        self.zoom = max(0.02, min(16.0, s))
        self.ox = (vw - iw * self.zoom) / 2.0
        self.oy = (vh - ih * self.zoom) / 2.0
        self._sync_labels()

    def zoom_at(self, pos: QPointF, factor: float, force: bool = False):
        """以光标为中心缩放（光标下的那个像素原地不动）。

        force=True 用于键盘 / 菜单缩放：锁定位置只挡「误碰」（拖动、缩放角、
        滚轮），不该把明确的缩放操作也一起挡掉。
        """
        if self._img.isNull() or (self.locked and not force):
            return
        old = self.zoom
        new = max(0.02, min(16.0, old * factor))
        if abs(new - old) < 1e-9:
            return
        self.ox = pos.x() - (pos.x() - self.ox) * (new / old)
        self.oy = pos.y() - (pos.y() - self.oy) * (new / old)
        self.zoom = new
        self.fit = False
        self._sync_labels()
        self.view.update()

    def set_alpha(self, v: float):
        self.alpha = max(0.05, min(1.0, float(v)))
        self._sync_labels()
        self.view.update()

    def _on_alpha_slider(self, val: int):
        self.set_alpha(val / 100.0)

    def toggle_flip(self):
        self.flip = not self.flip
        self._rebuild_shown()
        self._sync_buttons()
        self._say("已翻转" if self.flip else "已还原")
        self.view.update()

    def toggle_lock(self):
        self.locked = not self.locked
        self._sync_buttons()
        self._say("已锁定" if self.locked else "已解锁")

    def fit_window(self):
        self.fit = True
        self._apply_fit()
        self._say("已适配")
        self.view.update()

    def _say(self, text: str):
        """状态提示：临时占用底栏右侧，2.6 秒后回到缩放读数。"""
        self._notice = text
        self._notice_timer.start()
        self._sync_labels()

    def _clear_notice(self):
        self._notice = ""
        self._sync_labels()

    def _sync_buttons(self):
        self.b_flip.setChecked(bool(self.flip))
        self.b_lock.setChecked(bool(self.locked))
        self.b_lock.setIcon(icons.icon("lock" if self.locked else "unlock",
                                       C.DANGER if self.locked else C.TEXT_FAINT, 14))

    def _sync_labels(self):
        self.alpha_label.setText(f"{round(self.alpha * 100)}%")
        pct = round(self.alpha * 100)
        if self.alpha_slider.value() != pct:
            blocked = self.alpha_slider.blockSignals(True)
            self.alpha_slider.setValue(pct)
            self.alpha_slider.blockSignals(blocked)
        if self._notice:
            self.zoom_label.setText(self._notice)
        elif not self._img.isNull():
            self.zoom_label.setText(f"缩放 {round(self.zoom * 100)}%")
        else:
            self.zoom_label.setText("")

    # ------------------------------------------------------------ 绘制
    def paintEvent(self, ev):
        """只画「框」：标题栏、底栏、1px 边线。图片区留空 = 透出下面的画布。"""
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(QRect(0, 0, w, TITLE_H), QColor(C.CHROME))
        p.fillRect(QRect(0, h - BAR_H, w, BAR_H), QColor(C.CHROME))
        p.setPen(QPen(QColor(0, 0, 0, 110), 1))
        p.drawLine(0, TITLE_H - 1, w, TITLE_H - 1)
        p.drawLine(0, h - BAR_H, w, h - BAR_H)
        p.setPen(QPen(QColor(0, 0, 0, 150), 1))
        p.drawRect(QRect(0, 0, w - 1, h - 1))
        p.end()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.fit:
            self._apply_fit()
        else:
            self._sync_labels()

    # ------------------------------------------------------------ 其它
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            path = url.toLocalFile()
            if path and self.load(path):
                e.acceptProposedAction()
                return

    def closeEvent(self, e):
        self._save()
        self.closed.emit()
        super().closeEvent(e)
