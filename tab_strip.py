# -*- coding: utf-8 -*-
"""U Draw - 文档标签条（DocStrip）与拖动预览（_TabGhost）。

从 main_window.py 里拆出来的：标签条自成一个交互单元（切换 / 关闭 / 新建 /
拖出成独立窗口），跟主窗口的面板、工具栏没关系。拆开后主窗口只留一个
`self.strip = DocStrip()` 和几根信号线。

约定：
  · 拖标签只负责「拖出成独立窗口」，合并不在这里（合并走拖系统标题栏）
  · 拖动时跟一张 Qt.Tool 顶层小卡片做实时预览，WindowTransparentForInput
    保证它不抢鼠标
"""

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QMenu, QWidget

from theme import C


class _TabGhost(QWidget):
    """拖动标签时跟着鼠标走的小预览：文档缩略图 + 名字。

    做成 Qt.Tool 顶层窗口，鼠标拖到窗口外面也一直跟着（这是「实时预览」的关键）。
    WindowTransparentForInput 保证它不抢鼠标，不会打断拖动。
    """

    W, H = 132, 92

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint
                         | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(self.W, self.H)
        self.title = ""
        self.thumb = None

    def set_content(self, title: str, thumb=None):
        self.title = title
        self.thumb = thumb
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        p.setPen(QPen(QColor(C.ACCENT), 1.4))
        p.setBrush(QColor(32, 34, 38, 235))
        p.drawRoundedRect(r, 6, 6)
        # 缩略图
        tr = QRectF(8, 8, self.W - 16, self.H - 32)
        if self.thumb is not None and not self.thumb.isNull():
            p.setBrush(QColor(255, 255, 255, 255))
            p.setPen(QPen(QColor(0, 0, 0, 110), 1))
            p.drawRoundedRect(tr, 3, 3)
            p.drawPixmap(tr.adjusted(1, 1, -1, -1), self.thumb,
                         QRectF(self.thumb.rect()))
        f = QFont(self.font())
        f.setPointSizeF(8.4)
        p.setFont(f)
        p.setPen(QColor(C.TEXT))
        fm = p.fontMetrics()
        p.drawText(QRectF(8, self.H - 22, self.W - 16, 18),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(self.title or "文档", Qt.ElideRight, self.W - 16))
        p.end()


class DocStrip(QWidget):
    """文档标签条：多文档切换 + 关闭 + 新建 + 拖出成独立窗口。"""

    tabActivated = Signal(int)
    tabClosed = Signal(int)
    newRequested = Signal()
    tabDragEnded = Signal(int, QPoint, bool)   # (下标, 松手的全局坐标, 是否还在标签条里)
    tabTearRequested = Signal(int)             # 右键菜单：拖出成独立窗口

    TAB_H = 27

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.TAB_H)
        self.tabs = []
        self.active = 0
        self._hover_close = -1
        self._press_index = None
        self._press_pos = None
        self._dragging = False
        self._ghost = None
        self.drop_hint = False          # 别的窗口靠过来时：这一条画个框，表示能合并
        self.thumb_provider = None      # 主窗口塞进来：index -> QPixmap 缩略图
        self.setMouseTracking(True)
        self.setStyleSheet(f"background: {C.TAB_STRIP};")

    def set_tabs(self, items, active: int):
        self.tabs = items
        self.active = max(0, min(active, len(items) - 1))
        self.update()

    # -- 几何 --
    def _tab_rects(self):
        rects = []
        x = 0
        for it in self.tabs:
            text = ("• " if it.get("modified") else "") + it.get("title", "未命名")
            w = max(132, min(236, 9 * len(text) + 84))
            rects.append(QRect(x, 0, w, self.height()))
            x += w
        return rects

    def _close_rect(self, i):
        r = self._tab_rects()[i]
        return QRect(r.right() - 21, r.top() + (r.height() - 15) // 2, 15, 15)

    def _plus_rect(self):
        rects = self._tab_rects()
        x = rects[-1].right() + 1 if rects else 0
        return QRect(x + 2, 4, 22, self.height() - 8)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(C.TAB_STRIP))
        rects = self._tab_rects()
        for i, (it, r) in enumerate(zip(self.tabs, rects)):
            active = (i == self.active)
            p.fillRect(r, QColor(C.CARD if active else C.TAB_STRIP))
            if active:
                p.setPen(QPen(QColor(C.ACCENT), 2))
                p.drawLine(r.left(), r.top(), r.right(), r.top())
            p.setPen(QPen(QColor(C.SEPARATOR), 1))
            p.drawLine(r.right(), r.top() + 2, r.right(), r.bottom() - 2)

            text = ("• " if it.get("modified") else "") + it.get("title", "未命名")
            f = QFont(self.font())
            f.setPointSizeF(8.6)
            p.setFont(f)
            fm = p.fontMetrics()
            right_pad = 56
            text = fm.elidedText(text, Qt.ElideMiddle, r.width() - right_pad)
            p.setPen(QColor(C.TEXT if active else C.TEXT_DIM))
            p.drawText(r.adjusted(10, 0, -right_pad, 0), Qt.AlignVCenter | Qt.AlignLeft, text)

            p.setPen(QColor(C.TEXT_FAINT))
            p.drawText(r.adjusted(0, 0, -24, 0), Qt.AlignVCenter | Qt.AlignRight,
                       f"{int(round(it.get('zoom', 1.0) * 100))}%")

            cr = QRect(r.right() - 21, r.top() + (r.height() - 15) // 2, 15, 15)
            hover = (self._hover_close == i)
            if hover:
                p.setBrush(QColor(C.HOVER))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(cr, 3, 3)
            pen = QPen(QColor(C.TEXT if hover else C.TEXT_FAINT), 1.2)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(cr.left() + 4, cr.top() + 4, cr.right() - 4, cr.bottom() - 4)
            p.drawLine(cr.right() - 4, cr.top() + 4, cr.left() + 4, cr.bottom() - 4)

        pr = self._plus_rect()
        pen = QPen(QColor(C.TEXT_FAINT), 1.4)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(pr.center().x() - 4, pr.center().y(), pr.center().x() + 4, pr.center().y())
        p.drawLine(pr.center().x(), pr.center().y() - 4, pr.center().x(), pr.center().y() + 4)

        # 有窗口拖到附近：整条画个框，表示「松手会合并到这里」
        if self.drop_hint:
            p.fillRect(self.rect(), QColor(255, 255, 255, 14))
            p.setPen(QPen(QColor(C.ACCENT), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRect(self.rect().adjusted(1, 1, -2, -2))
        p.end()

    def set_drop_hint(self, on: bool):
        on = bool(on)
        if on != self.drop_hint:
            self.drop_hint = on
            self.update()

    # -- 交互 --
    def _begin_press(self, index: int, pos: QPoint):
        """按下就记住「可能要拖这个文档」。"""
        self._press_index = index
        self._press_pos = pos
        self._dragging = False

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        pos = e.position().toPoint()
        if self._plus_rect().contains(pos):
            self.newRequested.emit()
            return
        for i, r in enumerate(self._tab_rects()):
            if r.contains(pos):
                if self._close_rect(i).contains(pos):
                    self.tabClosed.emit(i)
                else:
                    self.tabActivated.emit(i)
                    # 记下来：按住标签拖出去 = 变成独立窗口
                    self._begin_press(i, pos)
                return
        # 标签条上的**空白区域**也能拖 —— 整条顶栏都是抓手，
        # 拖的是当前文档（用户习惯抓这块空白处拖，以前这里按下去毫无反应）
        if self.tabs:
            self._begin_press(self.active, pos)

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        hover = -1
        for i in range(len(self.tabs)):
            if self._close_rect(i).contains(pos):
                hover = i
                break
        if hover != self._hover_close:
            self._hover_close = hover
            self.update()
        if self._press_index is not None:
            if not self._dragging:
                if (pos - self._press_pos).manhattanLength() < 8:
                    return
                self._dragging = True
                self.setCursor(Qt.ClosedHandCursor)
                self._show_ghost(self._press_index)
            self._move_ghost(e.globalPosition().toPoint())
            return
        # 没在拖：光标提示这一整条顶栏都能抓手拖动
        on_tab = any(r.contains(pos) for r in self._tab_rects())
        want = (Qt.ArrowCursor if (on_tab or self._plus_rect().contains(pos))
                else Qt.OpenHandCursor)
        if self.tabs and self.cursor().shape() != want:
            self.setCursor(want)

    # -- 拖动预览 --
    def _show_ghost(self, index: int):
        if self._ghost is None:
            self._ghost = _TabGhost()
        it = self.tabs[index] if 0 <= index < len(self.tabs) else {}
        thumb = None
        if callable(self.thumb_provider):
            try:
                thumb = self.thumb_provider(index)
            except Exception:
                thumb = None
        self._ghost.set_content(it.get("title", "文档"), thumb)
        self._ghost.show()

    def _move_ghost(self, gpos):
        if self._ghost is not None:
            self._ghost.move(gpos.x() + 16, gpos.y() + 14)

    def mouseReleaseEvent(self, e):
        idx, dragging = self._press_index, self._dragging
        self._press_index = None
        self._dragging = False
        if self._ghost is not None:
            self._ghost.hide()
        if self.cursor().shape() == Qt.ClosedHandCursor:
            self.unsetCursor()
        if dragging and idx is not None and e.button() == Qt.LeftButton:
            gpos = e.globalPosition().toPoint()
            inside = self.rect().contains(e.position().toPoint())
            self.tabDragEnded.emit(idx, gpos, inside)

    def leaveEvent(self, e):
        if self._hover_close != -1:
            self._hover_close = -1
            self.update()
        if not self._dragging:
            self.unsetCursor()

    def contextMenuEvent(self, e):
        """标签右键：拖出为独立窗口 / 关闭这个文档。"""
        pos = e.pos()
        for i, r in enumerate(self._tab_rects()):
            if not r.contains(pos):
                continue
            m = QMenu(self)
            a_out = m.addAction("拖出为独立窗口")
            a_out.triggered.connect(lambda _=False, k=i: self.tabTearRequested.emit(k))
            m.addSeparator()
            a_close = m.addAction("关闭这个文档")
            a_close.triggered.connect(lambda _=False, k=i: self.tabClosed.emit(k))
            m.exec(e.globalPos())
            return
