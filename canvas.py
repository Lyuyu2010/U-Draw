# -*- coding: utf-8 -*-
"""U Draw - 画布视图：绘画 / 压感 / 移动 / 缩放 / 选区"""

import math
import os
import time

from PySide6.QtCore import (QEvent, QPoint, QPointF, QRect, QRectF, Qt,
                            QTimer, Signal)
from PySide6.QtGui import (QBrush, QColor, QCursor, QImage, QImageReader,
                           QKeyEvent, QPainter, QPainterPath, QPen, QPixmap,
                           QPolygonF, QRegion, QTextCursor, QTransform)
from PySide6.QtWidgets import QApplication, QWidget

from core import (Brush, Document, GroupEdit, MoveOp, PixelEdit, SPRAY_KINDS,
                  SmudgeStroke, Stroke, TextEdit, TextItem, TransformOp,
                  flood_fill, new_symmetry, symmetry_targets)
import text_tool
import fonts as fontlib
from theme import C

MIN_ZOOM, MAX_ZOOM = 0.02, 32.0

# 拖进来就能当图层用的图片后缀
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff",
              ".ppm", ".pgm", ".jp2", ".ico")


def load_image_file(path: str) -> QImage:
    """读一张图片（自动按 EXIF 方向摆正）。读不出来返回空图。"""
    r = QImageReader(path)
    r.setAutoTransform(True)
    img = r.read()
    if img.isNull():
        img = QImage(path)          # 少数格式 QImageReader 不认，再兜一次
    return img



def _checker() -> QPixmap:
    pm = QPixmap(16, 16)
    pm.fill(QColor("#5E5E5E"))
    p = QPainter(pm)
    p.fillRect(0, 0, 8, 8, QColor("#767676"))
    p.fillRect(8, 8, 8, 8, QColor("#767676"))
    p.end()
    return pm


CHECKER = None


class Canvas(QWidget):
    zoomChanged = Signal(float)
    pressureChanged = Signal(float)
    cursorMoved = Signal(QPointF)
    docChanged = Signal()
    historyChanged = Signal()
    colorPicked = Signal(QColor)
    brushSizeChanged = Signal(float)
    brushOpacityChanged = Signal(float)
    brushUsed = Signal()              # 实际落笔后记录最近使用，而非移动 / 缩放等操作
    blocked = Signal(str)
    transformChanged = Signal(bool)
    layerPicked = Signal(int, int)      # (图层索引, 修饰键)
    symmetryChanged = Signal()
    textCommitted = Signal(str, int)    # 文字落定后带上它的名字和下标
    canvasTouched = Signal()            # 在画布上开始操作了（图层面板据此取消文字选中）
    filesDropped = Signal(list, QPointF)  # 从外面拖进来的图片（路径列表, 落点文档坐标）
    textEditing = Signal(int)           # 开始编辑第 N 段文字（选项栏要跟着刷新）

    def __init__(self, doc: Document, parent=None):
        super().__init__(parent)
        global CHECKER
        if CHECKER is None:
            CHECKER = _checker()
        self.doc = doc
        self.zoom = 1.0
        self.ox = 0.0
        self.oy = 0.0
        self.tool = "brush"
        self.brush = Brush()
        # 橡皮 / 涂抹各有自己的一套笔尖参数（大小、硬度、不透明度、流量…）。
        # 以前三把工具共用一个 Brush，换橡皮就把画笔的大小也改了；
        # 这里分开存，切回画笔时原来的大小还在（和 PS 一样）。
        self.eraser_brush = Brush(kind="round", size=40, hardness=0.9,
                                  opacity=1.0, flow=1.0, spacing=0.05,
                                  min_size=0.5, pressure_size=True)
        self.smudge_brush = Brush(kind="round", size=100, hardness=0.8,
                                  opacity=1.0, flow=1.0, spacing=0.06,
                                  min_size=0.6, pressure_size=True)
        self.color = QColor(20, 20, 20)
        self.secondary = QColor(255, 255, 255)
        self.simulate_pressure = False  # 鼠标默认等粗；需要时可手动开（数位板始终用真实压力）

        self._stroke = None
        self._panning = False
        self._pan_from = QPointF()
        self._pan_origin = (0.0, 0.0)
        self._space = False
        self._mouse = QPointF(-100, -100)
        self._inside = False
        self._pressure = 1.0
        self._last_pressure = 1.0
        self._tablet_last = None
        self._tablet_time = 0.0
        self._tablet_erase = False
        # 最近一次压力的来源："tablet" 数位板真实压力 / "mouse" 按速度模拟
        # 状态栏据此显示「笔压·笔」还是「笔压·模拟」，用户一眼能看出驱动有没有送压力
        self.pressure_source = "mouse"
        # 视图在「适应窗口」状态时会跟着窗口大小自动居中；
        # 用户一旦自己缩放 / 平移就不再干预。
        self._auto_fit = True

        self._move = None
        self._moves = None
        self.move_auto_select = False
        self._pick_skipped = None    # 自动选择时略过的锁定图层（只用于提示）
        self.layer_selection = []
        self._move_start = None
        self._shape_start = None
        self._shape_end = None
        self._shape_before = None
        self.shape_fill = False
        self.shape_width = 8.0
        self._tf = None
        self._tf_mode = None
        self._tf_handle = -1
        self._tf_start = None
        self._tf_saved = None

        self._sel_start = None
        self._sel_path = None
        self._sel_mode = "new"
        self._sel_points = []

        # ---- 对称 / 涂抹 / 文字 ----
        self.symmetry = new_symmetry(doc.w, doc.h)
        self.pick_symmetry = False        # 等待用户点一下设定对称轴心
        self._sym_drag = False            # 正在拖对称轴心
        self._sym_hot = False             # 光标停在轴心手柄上（换手形光标）
        self.smudge_strength = 0.35       # 涂抹力度（PS 的默认手感约 20%，这里给足一点）
        self._smudge = None
        self.text_family = fontlib.default_family()
        self.text_size = 48.0
        self.text_bold = False
        self.text_italic = False
        self.text_align = "left"
        # 文字有自己的一份颜色，不跟前景色走：改前景色不会把正在打的字染成别的颜色
        self.text_color = QColor(20, 20, 20)
        self.text_keep_parent = None      # 选项栏（改字体时不落字）
        self._text = None                 # text_tool.TextOverlay
        self._edit_index = None           # 正在改的是第几段文字（None = 新建）
        self._text_move = None            # [TextItem, 起点, 原 x, 原 y]
        self._prev_cursor = QRect()       # 上一次画笔光标圈的位置（局部刷新时要擦）
        self._range_preview_until = 0.0   # 调范围时在画布上临时显示光圈
        self._range_preview_pos = QPointF(-100, -100)
        self._text_edit = None            # 拖动文字时的撤销记录

        self._ants = 0
        self._ants_timer = QTimer(self)
        self._ants_timer.setInterval(110)
        self._ants_timer.timeout.connect(self._tick_ants)
        self._last_speed = 0.0
        # 笔触输入合并：喷点笔一帧要画不少东西，鼠标事件却可能上百 Hz。
        # 每 10ms 取「最新一个点」落一次，中间点由 Stroke 自己插值，
        # 这样不会越画越滞后（事件排队）。
        self._stroke_pending = None
        self._stroke_timer = QTimer(self)
        self._stroke_timer.setInterval(10)
        self._stroke_timer.timeout.connect(self._flush_stroke_move)
        # 悬停看门狗：数位板移出画布时 leaveEvent 不一定来，靠它兜底把笔尖圈擦掉
        self._hover_watch = QTimer(self)
        self._hover_watch.setInterval(200)
        self._hover_watch.timeout.connect(self._check_pointer_over)
        self._cursor_shape = None

        self.setMouseTracking(True)
        self.setTabletTracking(True)
        self.grabGesture(Qt.PinchGesture)      # 触摸板 / 触摸屏捏合缩放
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setCursor(Qt.CrossCursor)
        self.setMinimumSize(320, 240)
        # 从资源管理器拖图片进来 = 新建一个图层
        self.setAcceptDrops(True)
        self._drop_hot = False
        # 放大时是否平滑插值。默认关：100% 以上每个文档像素就是屏幕上的一块方块，
        # 硬笔描线的边缘才是它真正的样子（视图菜单里可以打开）。
        self.smooth_zoom = False

    # ------------------------------------------------------------ 状态
    def set_document(self, doc: Document, fit: bool = True):
        self.commit_text()               # 换文档前先把正在写的字落到旧文档上
        self.doc = doc
        self._stroke = None
        self._smudge = None
        self._tf = None
        self._edit_index = None
        # 对称轴心跟着画布走：换文档时回到新画布的中心，不然轴心会飘到画布外
        self.symmetry["cx"] = doc.w / 2.0
        self.symmetry["cy"] = doc.h / 2.0
        if fit:
            self.fit()
        self.update()

    # ------------------------------------------------------------ 文字
    def _open_overlay(self, anchor: QPointF, text: str, family: str, px: float,
                      bold: bool, italic: bool, color: QColor, index,
                      html: str = ""):
        """开编辑框：index=None 是新建，否则是在改第 index 段文字。"""
        self._edit_index = index
        ov = text_tool.TextOverlay(self, color)
        ov.setup(anchor, self.zoom, family, px, bold, italic, color, 1.0,
                 to_screen=self.doc_to_screen)
        ov.committed.connect(self._text_done)
        ov.cancelled.connect(self._text_cleared)
        ov.keep_parent = self.text_keep_parent
        if html:
            # 这段文字之前按选区改过样式：连样式一起放回编辑框
            ov.setHtml(html)
            ov.mark_per_char()
            ov.moveCursor(QTextCursor.MoveOperation.End)
            ov.reposition()
        elif text:
            ov.setPlainText(text)
            ov.moveCursor(QTextCursor.MoveOperation.End)
            ov.reposition()
        ov.show()
        ov.setFocus()
        self._text = ov

    def _begin_text(self, pos: QPointF):
        if self.doc.layer is None:
            return
        self.commit_text()
        anchor = self.screen_to_doc(pos)
        # 点在已有文字上 = 接着改那一段（PS 的用法），点空白处 = 新建
        idx, hit = self.doc.text_at(anchor.x(), anchor.y())
        if hit is not None:
            hit.editing = True            # 先藏起来，免得编辑框和本体重影
            self.doc.recompose()
            self.text_family = hit.family
            self.text_size = hit.px
            self.text_bold = hit.bold
            self.text_italic = hit.italic
            self.text_color = QColor(hit.color)
            self._open_overlay(QPointF(hit.x, hit.y), hit.text, hit.family, hit.px,
                               hit.bold, hit.italic, hit.color, idx, hit.html)
            self.textEditing.emit(idx)
            return
        self._open_overlay(anchor, "", self.text_family, self.text_size,
                           self.text_bold, self.text_italic, self.text_color, None)
        # 新建文字也要刷新选项栏：让顶部的 ✓ / ✕ 从禁用变成可点。
        self.textEditing.emit(-1)

    def begin_edit_text(self, index: int):
        """从图层面板点进来：选中某段文字，直接开始改。"""
        doc = self.doc
        if not (0 <= index < len(doc.texts)):
            return
        self.commit_text()
        it = doc.texts[index]
        it.editing = True
        self.text_family = it.family
        self.text_size = it.px
        self.text_bold = it.bold
        self.text_italic = it.italic
        self.text_color = QColor(it.color)
        doc.recompose()
        self._open_overlay(QPointF(it.x, it.y), it.text, it.family, it.px,
                           it.bold, it.italic, it.color, index, it.html)
        self.textEditing.emit(index)
        self.update()

    def _text_cleared(self):
        self._text = None
        idx = self._edit_index
        self._edit_index = None
        if idx is not None and 0 <= idx < len(self.doc.texts):
            self.doc.texts[idx].editing = False
            self.doc.recompose()
            self.update()

    def _text_done(self, text: str):
        ov = self._text
        self._text = None
        if ov is None:
            return
        html = ov.rich_html()
        idx = self._edit_index
        self._edit_index = None
        self._commit_text_object(str(text), ov.doc_anchor(), idx, html)

    def _commit_text_object(self, text: str, anchor: QPointF, idx, html: str = ""):
        doc = self.doc
        if not text.strip():
            # 内容被删光了：原来那段就删掉，新建的就当没发生
            if idx is not None and 0 <= idx < len(doc.texts):
                edit = TextEdit(doc, "删除文字")
                doc.remove_text(idx)
                edit.capture(doc)
                doc.push(edit)
                self.update()
                self.historyChanged.emit()
                self.docChanged.emit()
            return
        edit = TextEdit(doc, "编辑文字" if idx is not None else "新建文字")
        if idx is not None and 0 <= idx < len(doc.texts):
            it = doc.texts[idx]
            it.editing = False
            it.text = text
            it.family = self.text_family
            it.px = self.text_size
            it.bold = self.text_bold
            it.italic = self.text_italic
            it.color = QColor(self.text_color)
            it.html = html
            it.name = it.auto_name()
            doc.modified = True
            new_idx = idx
        else:
            it = TextItem(text, anchor.x(), anchor.y(), self.text_family,
                          self.text_size, self.text_bold, self.text_italic,
                          self.text_color, html=html)
            new_idx = doc.add_text(it)
        doc.recompose()
        edit.capture(doc)
        doc.push(edit)
        self.update()
        self.historyChanged.emit()
        self.docChanged.emit()
        self.textCommitted.emit(it.name, new_idx)

    def commit_text(self):
        if self._text is not None:
            self._text.commit()

    def cancel_text(self):
        if self._text is not None:
            self._text.cancel()

    def has_text(self) -> bool:
        return self._text is not None

    def text_overlay(self):
        return self._text

    def _text_follow(self):
        if self._text is not None:
            self._text.set_zoom(self.zoom)
            self._text.reposition()

    def set_tool(self, tool: str):
        if getattr(self, "_tf", None) is not None:
            self.commit_transform()      # 切工具时先把变换落地
        if tool != "text":
            self.commit_text()           # 切走文字工具 = 落字
        self.tool = tool
        self._sym_hot = False
        self._sym_drag = False
        self._prev_cursor = QRect()      # 换工具 = 换笔径，旧光标圈整块作废
        self._cursor_shape = None
        self._sync_cursor()
        if self.doc.has_selection() and tool not in ("marquee", "ellipse", "lasso"):
            self._ants_timer.start()
        else:
            if tool in ("marquee", "ellipse", "lasso"):
                self._ants_timer.start()
        self.update()

    # ------------------------------------------------------------ 坐标
    def active_brush(self):
        """当前工具用的那支「笔」：画笔 / 橡皮 / 涂抹各自独立。"""
        if self.tool == "eraser":
            return self.eraser_brush
        if self.tool == "smudge":
            return self.smudge_brush
        return self.brush

    def doc_to_screen(self, p: QPointF) -> QPointF:
        return QPointF(p.x() * self.zoom + self.ox, p.y() * self.zoom + self.oy)

    def screen_to_doc(self, p: QPointF) -> QPointF:
        return QPointF((p.x() - self.ox) / self.zoom, (p.y() - self.oy) / self.zoom)

    def doc_rect(self) -> QRectF:
        return QRectF(self.ox, self.oy, self.doc.w * self.zoom, self.doc.h * self.zoom)

    def fit(self):
        if not self.width() or not self.height():
            return
        self._auto_fit = True
        sx = (self.width() - 64) / self.doc.w
        sy = (self.height() - 64) / self.doc.h
        self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, min(sx, sy)))
        self.center()
        self.zoomChanged.emit(self.zoom)
        self._text_follow()
        self.update()

    def center(self):
        self.ox = (self.width() - self.doc.w * self.zoom) / 2.0
        self.oy = (self.height() - self.doc.h * self.zoom) / 2.0

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # 启动那一瞬间控件宽度还不是最终值（右侧面板的宽度要等布局算完），
        # 之前只在 timer 里 fit 一次，于是画布会偏在左边。
        # 只要还处在「适应窗口」状态，就跟着窗口尺寸重新算一次。
        if getattr(self, "_auto_fit", True):
            self.fit()
        else:
            self.update()

    def set_zoom(self, zoom: float, anchor: QPointF = None):
        zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        if abs(zoom - self.zoom) < 1e-9:
            return
        self._auto_fit = False
        anchor = QPointF(self.width() / 2, self.height() / 2) if anchor is None else anchor
        before = self.screen_to_doc(anchor)
        self.zoom = zoom
        after = self.doc_to_screen(before)
        self.ox += anchor.x() - after.x()
        self.oy += anchor.y() - after.y()
        self.zoomChanged.emit(self.zoom)
        self._text_follow()
        self.update()

    def zoom_step(self, up: bool, anchor: QPointF = None):
        # 没指定锚点就跟着鼠标走：缩放前后光标底下的那个像素不动，
        # 想放大哪块就把鼠标放哪块，不用放大完再拖回来。
        if anchor is None:
            anchor = self.pointer_anchor()
        self.set_zoom(self.zoom * (1.25 if up else 0.8), anchor)

    def pointer_anchor(self):
        """当前鼠标在画布上的位置（鼠标不在画布上就返回 None = 以中心缩放）。"""
        p = getattr(self, "_hover_pos", None)
        if p is not None and self.rect().contains(p.toPoint()):
            return QPointF(p)
        return None

    # ------------------------------------------------------------ 绘制
    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(C.CANVAS))
        dr = self.doc_rect()

        # 画布投影
        p.fillRect(dr.translated(0, 4).adjusted(-2, 0, 2, 6), QColor(0, 0, 0, 60))

        # 透明棋盘
        p.save()
        p.setClipRect(dr)
        p.fillRect(dr, QBrush(CHECKER))
        p.restore()

        # 画面合成：200% 以上默认**不平滑** —— 每个文档像素就是屏幕上的一块方块，
        # 硬笔描线的边缘才是它真正的样子。以前一律开平滑插值，380% 下那圈 1px 的
        # 抗锯齿被插值拉成 10 个屏幕像素的灰边（实测），看着就是「抗锯齿特别大」。
        # 200% 以下（缩小、适应窗口）必须平滑，否则细节会闪成噪点。
        # 想在放大时也柔一点：视图 → 放大时平滑显示。
        p.setRenderHint(QPainter.SmoothPixmapTransform,
                        self.zoom < 2.0 or self.smooth_zoom)
        # 只画屏幕可见的那一块源图：大画布 / 放大时不再把整张合成图缩放一遍，
        # 喷点笔这类需要每帧重绘的笔触才不会因为画布大而掉帧。
        visible = dr.intersected(QRectF(self.rect()))
        if not visible.isEmpty():
            sx = (visible.left() - self.ox) / self.zoom
            sy = (visible.top() - self.oy) / self.zoom
            sw = visible.width() / self.zoom
            sh = visible.height() / self.zoom
            p.drawImage(visible, self.doc.composite, QRectF(sx, sy, sw, sh))
        # 文字对象允许放到画布外：合成图只有画布大小，外面的部分在这里补画。
        self._draw_texts_outside(p)

        # 边线
        p.setRenderHint(QPainter.Antialiasing, False)
        p.setPen(QPen(QColor(0, 0, 0, 200), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(dr.adjusted(-0.5, -0.5, 0.5, 0.5))

        # 正拖着图片过来：画布亮一圈，松手就放到这里
        if self._drop_hot:
            pen = QPen(QColor(C.ACCENT), 2)
            pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(dr.adjusted(-2.5, -2.5, 2.5, 2.5))

        # 自由变换框
        self._draw_transform(p)
        # 对称参考线
        self._draw_symmetry(p)
        # 形状预览
        self._draw_shape_preview(p)
        # 选区蚂蚁线
        self._draw_selection(p)
        self._draw_cursor(p)
        p.end()

    def _draw_transform(self, p: QPainter):
        if self._tf is None:
            return
        tf = self._tf
        pts = tf.handles()
        corners = [self.doc_to_screen(pts[0]), self.doc_to_screen(pts[2]),
                   self.doc_to_screen(pts[4]), self.doc_to_screen(pts[6])]
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(QColor(C.ACCENT), 1.2)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPolygon(QPolygonF(corners))
        for hp in pts:
            sp = self.doc_to_screen(hp)
            p.setPen(QPen(QColor(0, 0, 0, 200), 1))
            p.setBrush(QColor(255, 255, 255))
            p.drawRect(QRectF(sp.x() - 4, sp.y() - 4, 8, 8))
        # 中心十字
        c = self.doc_to_screen(tf.center)
        p.setPen(QPen(QColor(C.ACCENT), 1.0))
        p.drawLine(QPointF(c.x() - 5, c.y()), QPointF(c.x() + 5, c.y()))
        p.drawLine(QPointF(c.x(), c.y() - 5), QPointF(c.x(), c.y() + 5))
        p.restore()

    def _draw_symmetry(self, p: QPainter):
        """对称参考线：虚线画轴，轴心一个小十字。"""
        sym = self.symmetry
        mode = sym.get("mode", "off")
        if mode == "off":            # 开了对称就一定画参考线，不给单独开关
            return
        # 只有真的会用到对称的工具才画参考线（以及「点选轴心」时，得看得见轴）
        if self.tool not in ("brush", "eraser", "smudge") and not self.pick_symmetry:
            return
        dr = self.doc_rect()
        c = self.doc_to_screen(QPointF(sym["cx"], sym["cy"]))
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setClipRect(dr)
        pen = QPen(QColor(84, 168, 255, 165), 1.0)
        pen.setCosmetic(True)
        pen.setStyle(Qt.CustomDashLine)
        pen.setDashPattern([6, 4])
        p.setPen(pen)
        if mode in ("vertical", "quad"):
            p.drawLine(QPointF(c.x(), dr.top()), QPointF(c.x(), dr.bottom()))
        if mode in ("horizontal", "quad"):
            p.drawLine(QPointF(dr.left(), c.y()), QPointF(dr.right(), c.y()))
        if mode == "radial":
            n = max(2, min(24, int(sym.get("count", 6))))
            rad = (dr.width() ** 2 + dr.height() ** 2) ** 0.5
            for k in range(n):
                a = math.pi * k / n
                dx, dy = math.cos(a) * rad, math.sin(a) * rad
                p.drawLine(QPointF(c.x() - dx, c.y() - dy),
                           QPointF(c.x() + dx, c.y() + dy))
        p.setPen(QPen(QColor(84, 168, 255, 235), 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(c.x() - 9, c.y()), QPointF(c.x() + 9, c.y()))
        p.drawLine(QPointF(c.x(), c.y() - 9), QPointF(c.x(), c.y() + 9))
        # 轴心画成实心圆点：它是可以按住拖的，空心的看不出「能抓」
        p.setPen(QPen(QColor(255, 255, 255, 235), 1.2))
        p.setBrush(QColor(84, 168, 255, 255 if self._sym_hot or self._sym_drag else 215))
        p.drawEllipse(c, 5.0, 5.0)
        p.restore()

    # ------------------------------------------------------------ 对称轴心拖动
    def _sym_handle_hit(self, pos: QPointF) -> bool:
        """光标是否落在对称轴心手柄上（半径 11 屏幕像素）。"""
        sym = self.symmetry
        if sym.get("mode", "off") == "off":
            return False
        if self.tool not in ("brush", "eraser", "smudge"):
            return False
        if sym.get("mode", "off") == "off":
            return False          # 参考线关掉时轴心也不画，别再留一个看不见的热区
        c = self.doc_to_screen(QPointF(sym["cx"], sym["cy"]))
        return math.hypot(pos.x() - c.x(), pos.y() - c.y()) <= 11.0

    def _tool_cursor(self):
        if self.tool in ("brush", "eraser", "smudge"):
            return Qt.BlankCursor
        if self.tool == "hand":
            return Qt.OpenHandCursor
        if self.tool == "move":
            return Qt.SizeAllCursor
        if self.tool == "text":
            return Qt.IBeamCursor
        return Qt.CrossCursor

    def _draw_shape_preview(self, p: QPainter):
        if self._shape_start is None or self._shape_end is None:
            return
        start, end = self._shape_start, self._shape_end
        r = self._shape_rect()
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setTransform(QTransform().translate(self.ox, self.oy).scale(self.zoom, self.zoom))

        path = QPainterPath()
        if self.tool == "rect":
            path.addRect(r)
        elif self.tool == "ellipse_shape":
            path.addEllipse(r)
        else:
            path.moveTo(start)
            path.lineTo(end)

        if self.tool == "line":
            # 直线直接按真实粗细预览
            pen = QPen(self.color, max(0.6, self.shape_width))
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
        else:
            if self.shape_fill:
                c = QColor(self.color)
                c.setAlpha(80)
                p.fillPath(path, QBrush(c))
            # 黑 + 白 双色虚线，白底 / 深色底都看得清
            for color, off in ((QColor(0, 0, 0, 210), 0.0),
                               (QColor(255, 255, 255, 245), 4.0)):
                pen = QPen(color)
                pen.setWidthF(1.3)
                pen.setCosmetic(True)
                pen.setStyle(Qt.CustomDashLine)
                pen.setDashPattern([4, 4])
                pen.setDashOffset(off)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawPath(path)
        p.restore()

        # 尺寸标注
        p.save()
        label = f"{int(abs(end.x() - start.x()))} × {int(abs(end.y() - start.y()))}"
        if self.tool == "line":
            dist = ((end.x() - start.x()) ** 2 + (end.y() - start.y()) ** 2) ** 0.5
            label = f"{int(dist)} px"
        sp = self.doc_to_screen(end) + QPointF(14, 16)
        fm = p.fontMetrics()
        w = fm.horizontalAdvance(label) + 10
        box = QRectF(sp.x(), sp.y(), w, 18)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 170))
        p.drawRoundedRect(box, 3, 3)
        p.setPen(QColor(255, 255, 255))
        p.drawText(box, Qt.AlignCenter, label)
        p.restore()

    def _draw_selection(self, p: QPainter):
        paths = []
        if self.doc.has_selection():
            paths.append(self.doc.selection)
        if self._sel_path is not None:
            paths.append(self._sel_path)
        if not paths:
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setTransform(QTransform().translate(self.ox, self.oy).scale(self.zoom, self.zoom))
        for path in paths:
            pen = QPen(QColor(0, 0, 0, 220))
            pen.setWidthF(0)
            pen.setCosmetic(True)
            pen.setStyle(Qt.CustomDashLine)
            pen.setDashPattern([4, 4])
            pen.setDashOffset(self._ants)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
            pen2 = QPen(QColor(255, 255, 255, 235))
            pen2.setWidthF(0)
            pen2.setCosmetic(True)
            pen2.setStyle(Qt.CustomDashLine)
            pen2.setDashPattern([4, 4])
            pen2.setDashOffset(self._ants + 4)
            p.setPen(pen2)
            p.drawPath(path)
        p.restore()

    def _draw_texts_outside(self, p: QPainter):
        """把落在画布外的文字补画到灰色工作区；画布内的部分仍由合成图负责。"""
        texts = getattr(self.doc, "texts", None)
        if not texts:
            return
        dr = self.doc_rect()
        outside = QRegion(self.rect()).subtracted(QRegion(dr.toAlignedRect()))
        if outside.isEmpty():
            return
        p.save()
        p.setClipRegion(outside)
        p.translate(self.ox, self.oy)
        p.scale(self.zoom, self.zoom)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        for it in texts:
            if it.editing or not it.text.strip():
                continue
            vis, op = self.doc.text_state(it)
            if not vis or op <= 0.0:
                continue
            p.setOpacity(op)
            it.draw(p)
        p.setOpacity(1.0)
        p.restore()

    # ------------------------------------------------------------ 拖入图片
    @staticmethod
    def _drop_files(mime) -> list:
        """从拖放数据里挑出能当图层用的图片文件。"""
        if not mime.hasUrls():
            return []
        out = []
        for u in mime.urls():
            if not u.isLocalFile():
                continue
            path = u.toLocalFile()
            if os.path.splitext(path)[1].lower() in IMAGE_EXTS and os.path.isfile(path):
                out.append(path)
        return out

    def dragEnterEvent(self, e):
        if self._drop_files(e.mimeData()):
            e.acceptProposedAction()
            if not self._drop_hot:
                self._drop_hot = True
                self.update()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if self._drop_files(e.mimeData()):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        if self._drop_hot:
            self._drop_hot = False
            self.update()

    def dropEvent(self, e):
        paths = self._drop_files(e.mimeData())
        self._drop_hot = False
        self.update()
        if not paths:
            e.ignore()
            return
        e.acceptProposedAction()
        p = self.screen_to_doc(QPointF(e.position()))
        self.filesDropped.emit(paths, p)

    def _draw_cursor(self, p: QPainter):
        preview = (not self._inside and
                   time.monotonic() < getattr(self, "_range_preview_until", 0.0))
        if not self._inside and not preview:
            return
        if self.tool not in ("brush", "eraser", "smudge"):
            return
        if self._inside and (self._sym_hot or self._sym_drag):
            return          # 光标在对称轴心上：这时是手形，别再画笔尖圈
        b = self.active_brush()
        d = b.diameter(self._pressure if self.tool != "eraser" else 1.0) * self.zoom
        if d < 2:
            d = 2
        range_d = 0.0
        if b.kind in SPRAY_KINDS:
            range_d = max(d, b.range_diameter() * self.zoom)
        # 开了对称就把镜像位置的笔尖一起画出来 —— 落笔前就知道会画到哪儿
        if preview:
            centers = [self._range_preview_pos]
        else:
            centers = [self._mouse]
            sym = self.symmetry
            if sym.get("mode", "off") != "off":
                m = self.screen_to_doc(self._mouse)
                for tx, ty, _a, _f in symmetry_targets(sym, m.x(), m.y()):
                    if abs(tx - m.x()) > 0.01 or abs(ty - m.y()) > 0.01:
                        centers.append(self.doc_to_screen(QPointF(tx, ty)))
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setBrush(Qt.NoBrush)
        for i, c in enumerate(centers):
            r = QRectF(c.x() - d / 2, c.y() - d / 2, d, d)
            if i == 0:
                if range_d > d + 1:
                    # 喷点外圈：范围直径。浅蓝色，和笔尖内圈区分开。
                    rr = QRectF(c.x() - range_d / 2, c.y() - range_d / 2,
                                range_d, range_d)
                    p.setPen(QPen(QColor(84, 168, 255, 205), 1.3))
                    p.drawEllipse(rr)
                p.setPen(QPen(QColor(0, 0, 0, 170), 1.6))
                p.drawEllipse(r.adjusted(-0.7, -0.7, 0.7, 0.7))
                p.setPen(QPen(QColor(255, 255, 255, 210), 1.0))
                p.drawEllipse(r)
            else:
                # 镜像笔尖画淡一点：看得见，但不抢主体
                p.setPen(QPen(QColor(84, 168, 255, 190), 1.0))
                p.drawEllipse(r)

    def _tick_ants(self):
        self._ants = (self._ants + 1) % 8
        if self.doc.has_selection() or self._sel_path is not None:
            self.update()

    # ------------------------------------------------------------ 刷新
    def _cursor_rect(self) -> QRect:
        """笔尖光标圈占的屏幕矩形（画的时候要一起擦掉，不然旧圈会留在画面上）。

        开了对称时必须把**镜像位置的光标圈也算进来**：
        只擦主光标那一块的话，镜像那边的圈既画不出来（更新区域被裁掉，
        看着就是「对称那边不显示光标」），画过之后又擦不掉
        （沿着轨迹留下一串残影）。
        """
        if not self._inside or self.tool not in ("brush", "eraser", "smudge"):
            return QRect()
        b = self.active_brush()
        d = b.diameter(1.0) * self.zoom
        if self.tool != "eraser":
            # 压感一变笔径就变，旧圈得按最大的那个擦，否则压力变大时会留边
            d = max(d, b.diameter(max(0.05, self._pressure)) * self.zoom)
        if b.kind in SPRAY_KINDS:
            d = max(d, b.range_diameter() * self.zoom)
        d += 8
        centers = [self._mouse]
        sym = self.symmetry
        if sym.get("mode", "off") != "off":
            m = self.screen_to_doc(self._mouse)
            for tx, ty, _a, _f in symmetry_targets(sym, m.x(), m.y()):
                c = self.doc_to_screen(QPointF(tx, ty))
                if abs(c.x() - self._mouse.x()) > 0.5 or \
                        abs(c.y() - self._mouse.y()) > 0.5:
                    centers.append(c)
        out = QRect()
        for c in centers:
            r = QRect(int(c.x() - d / 2), int(c.y() - d / 2), int(d) + 1, int(d) + 1)
            out = r if out.isNull() else out.united(r)
        return out

    def show_range_preview(self):
        """调范围 / 密度时在画布上亮一下光圈，让用户看到范围直径。"""
        self._range_preview_until = time.monotonic() + 1.2
        if self._inside:
            self._range_preview_pos = QPointF(self._mouse)
        else:
            self._range_preview_pos = self.doc_to_screen(
                QPointF(self.doc.w / 2.0, self.doc.h / 2.0))
        self.update()
        QTimer.singleShot(1250, self.update)

    def _refresh(self, doc_rect: QRect):
        # 关键：把「上一次」和「这一次」的光标圈都并进重绘区。
        # 只重绘笔迹那一小块的话，之前画在屏幕上的圆圈擦不掉，
        # 沿着笔迹就会留下一串淡淡的月牙弧线（用户反馈的那个 bug）。
        # 开了对称时 _cursor_rect() 已经把镜像位置的圈也算进去了，
        # 所以镜像那一边同样会被擦干净 —— 不会留残影。
        cur = self._cursor_rect()
        upd = cur.united(getattr(self, "_prev_cursor", QRect()))
        self._prev_cursor = cur
        if doc_rect is not None and not doc_rect.isEmpty():
            self.doc.recompose(doc_rect)
            tl = self.doc_to_screen(QPointF(doc_rect.left(), doc_rect.top()))
            br = self.doc_to_screen(QPointF(doc_rect.right() + 1,
                                            doc_rect.bottom() + 1))
            upd = upd.united(QRect(int(tl.x()) - 3, int(tl.y()) - 3,
                                   int(br.x() - tl.x()) + 7,
                                   int(br.y() - tl.y()) + 7))
        if not upd.isEmpty():
            # 掉帧（一次跳很远）时脏区会很大，局部刷新容易在边界留下上一帧的像素，
            # 看着就是一条条「显现边缘」。脏区超过可见面积的 35% 就整块重绘，
            # 代价差不多，但绝不会留残影。
            area = self.width() * self.height()
            if area <= 0 or upd.width() * upd.height() > area * 0.35:
                self.update()
            else:
                self.update(upd)

    # ------------------------------------------------------------ 指针
    def _pressure_for_mouse(self, pos: QPointF) -> float:
        """鼠标 / 驱动没送压力的数位板：按运笔速度模拟压力。

        数位板送 real pressure 时走 tabletEvent，不会到这里。
        这里必须也能给出粗细变化 —— 否则用户一张开手就是一条等粗的线，
        会以为「压感没了」。
        """
        # 只要开了「压感控制大小」或「压感控制浓淡」之一，鼠标就要送出
        # 模拟压力；否则只开浓淡时会被这里直接按成 1.0，看起来完全不生效。
        if not (self.active_brush().pressure_size or self.active_brush().pressure_opacity):
            return 1.0
        speed = self._last_speed
        # 越快越细，慢笔最粗（收窄范围，保证参数差异看得出来）
        return max(0.35, min(1.0, 1.0 - min(1.0, speed / 45.0) * 0.55))

    def _paint_tools(self):
        return ("brush", "eraser", "bucket", "eyedropper")

    def _sel_tools(self):
        return ("marquee", "ellipse", "lasso")

    def pointer_down(self, pos: QPointF, pressure: float, button=Qt.LeftButton,
                     mods=Qt.NoModifier):
        self.setFocus()
        # 在画布上动手了：图层面板里「选中的文字」要取消，
        # 否则之后按 Backspace 会去删上一次选的那段字，而不是当前图层。
        if self.tool != "text":
            self.canvasTouched.emit()
        if self._tf is not None:
            mode, idx = self._tf_hit(pos)
            if mode is None:
                return
            self._tf_mode = mode
            self._tf_handle = idx
            self._tf_start = self.screen_to_doc(pos)
            self._tf_saved = (QPointF(self._tf.center), self._tf.w, self._tf.h, self._tf.angle)
            return
        if button == Qt.MiddleButton or self._space or self.tool == "hand":
            self._panning = True
            self._auto_fit = False
            self._pan_from = pos
            self._pan_origin = (self.ox, self.oy)
            self.setCursor(Qt.ClosedHandCursor)
            return

        if button == Qt.RightButton:
            return

        # 「设置对称轴心」模式：下一次点击就落在哪儿算哪儿
        if self.pick_symmetry:
            d = self.screen_to_doc(pos)
            self.symmetry["cx"] = d.x()
            self.symmetry["cy"] = d.y()
            self.pick_symmetry = False
            self.symmetryChanged.emit()
            self.update()
            return

        if self.tool == "text":
            self._begin_text(pos)
            return

        # 按住对称轴心直接拖：轴心位置随时可调，不用再去面板点「点选轴心」
        # 面板上开了「固定」就不让拖 —— 画的时候手滑碰到轴心不会把对称挪走。
        if self._sym_handle_hit(pos) and not self.symmetry.get("locked", False):
            self._sym_drag = True
            self.setCursor(Qt.ClosedHandCursor)
            self.update()
            return

        if self.tool == "zoom":
            self.zoom_step(not (mods & Qt.AltModifier), pos)
            return

        if self.tool == "eyedropper":
            d = self.screen_to_doc(pos)
            c = self.doc.sample(int(d.x()), int(d.y()))
            if c.alpha() > 0:
                self.color = QColor(c)
                self.colorPicked.emit(self.color)
            return

        if self.tool == "bucket":
            d = self.screen_to_doc(pos)
            layer = self.doc.layer
            if layer is None:
                return
            if self.doc.is_locked(layer):
                self.blocked.emit(f"「{layer.name}」已锁定，先解锁再填充")
                return
            edit = flood_fill(self.doc, int(d.x()), int(d.y()), self.color)
            if edit:
                self.doc.push(edit)
                self._refresh(edit.rect)      # 立刻重绘，不用等切换图层
                self.historyChanged.emit()
                self.docChanged.emit()
            return

        if self.tool in ("brush", "eraser"):
            layer = self.doc.layer
            if layer is None:
                return
            if self.doc.is_locked(layer):
                self.blocked.emit(f"「{layer.name}」已锁定，先解锁再画")
                return
            self._stroke_pending = None
            self._stroke_timer.stop()
            self._stroke = Stroke(self.doc, layer, self.active_brush(), self.color,
                                  erase=(self.tool == "eraser" or self._tablet_erase),
                                  sym=self.symmetry)
            r = self._stroke.begin(self.screen_to_doc(pos), pressure)
            if not r.isEmpty():
                self.brushUsed.emit()
            self._refresh(r)
            return

        if self.tool == "smudge":
            layer = self.doc.layer
            if layer is None:
                return
            if self.doc.is_locked(layer):
                self.blocked.emit(f"「{layer.name}」已锁定，先解锁再涂抹")
                return
            self._smudge = SmudgeStroke(self.doc, layer, self.active_brush(),
                                        self.smudge_strength, self.symmetry)
            r = self._smudge.begin(self.screen_to_doc(pos), pressure)
            self._refresh(r)
            return

        if self.tool == "move":
            # 点在文字对象上 = 挪这段文字（它不在图层里，所以优先于图层移动）
            d0 = self.screen_to_doc(pos)
            _ti, _hit = self.doc.text_at(d0.x(), d0.y())
            if _hit is not None:
                self._text_edit = TextEdit(self.doc, "移动文字")
                self._text_move = [_hit, d0, _hit.x, _hit.y]
                self.setCursor(Qt.ClosedHandCursor)
                return
            if self.move_auto_select:
                picked = self.pick_layer_at(self.screen_to_doc(pos))
                if picked is None and self._pick_skipped is not None:
                    self.blocked.emit(
                        f"「{self._pick_skipped.name}」已锁定，自动选择已跳过")
                if picked is not None:
                    # Ctrl / Shift 跟图层面板一致：加选、区间选。
                    # 所以这里把修饰键一起发出去，由面板决定是替换还是追加。
                    self.doc.active = picked
                    self.layerPicked.emit(picked, int(getattr(mods, "value", mods)))
            layer = self.doc.layer
            if layer is None:
                return
            targets = []
            sel = [i for i in self.layer_selection
                   if 0 <= i < len(self.doc.layers) and self.doc.layers[i].visible]
            if len(sel) >= 2:
                targets = [self.doc.layers[i] for i in sel]
            else:
                targets = [layer]
            if self.doc.is_locked(layer) and len(targets) == 1:
                self.blocked.emit(f"「{layer.name}」已锁定，先解锁再移动")
                return
            targets = [l for l in targets if not self.doc.is_locked(l)]
            if not targets:
                self.blocked.emit("选中的图层都被锁定了")
                return
            self._moves = [MoveOp(self.doc, l) for l in targets]
            self._move = self._moves[0]
            self._move_start = self.screen_to_doc(pos)
            self.setCursor(Qt.ClosedHandCursor)
            return

        if self.tool in ("rect", "ellipse_shape", "line"):
            layer = self.doc.layer
            if layer is None:
                return
            if self.doc.is_locked(layer):
                self.blocked.emit(f"「{layer.name}」已锁定，先解锁再画形状")
                return
            self._shape_start = self.screen_to_doc(pos)
            self._shape_end = QPointF(self._shape_start)
            self._shape_before = layer.image.copy()
            self.update()
            return

        if self.tool in self._sel_tools():
            self._sel_start = self.screen_to_doc(pos)
            if mods & Qt.ShiftModifier:
                self._sel_mode = "add"
            elif mods & Qt.AltModifier:
                self._sel_mode = "sub"
            else:
                self._sel_mode = "new"
            self._sel_points = [self._sel_start]
            self._sel_path = QPainterPath()
            self._ants_timer.start()

    def pointer_move(self, pos: QPointF, pressure: float):
        dt = QPointF(pos.x() - self._mouse.x(), pos.y() - self._mouse.y())
        self._last_speed = (dt.x() ** 2 + dt.y() ** 2) ** 0.5
        self._mouse = QPointF(pos)
        self._pressure = pressure
        self._last_ptr = time.monotonic()
        # 这里不能无条件写 True：笔从画布边缘拖出去时仍会收到 move 事件，
        # 一旦把 _inside 设成 True，松手后光标圈就再也没人擦掉，
        # 会一直留在画布边缘（用户反馈的「光标卡在边缘」）。
        self._inside = self.rect().contains(QPoint(int(pos.x()), int(pos.y())))

        if self._panning:
            self.ox = self._pan_origin[0] + (pos.x() - self._pan_from.x())
            self.oy = self._pan_origin[1] + (pos.y() - self._pan_from.y())
            self._text_follow()
            self.update()
            return

        if self._sym_drag:
            d = self.screen_to_doc(pos)
            self.symmetry["cx"] = max(0.0, min(float(self.doc.w), d.x()))
            self.symmetry["cy"] = max(0.0, min(float(self.doc.h), d.y()))
            self.cursorMoved.emit(d)
            self.update()
            return

        if self._tf is not None and self._tf_mode is not None:
            self._tf_drag(pos)
            return

        if self._text_move is not None:
            it, start, ox, oy = self._text_move
            d = self.screen_to_doc(pos)
            it.x = ox + (d.x() - start.x())
            it.y = oy + (d.y() - start.y())
            self.doc.recompose()
            self.update()
            self.cursorMoved.emit(d)
            return

        if self._move is not None:
            d = self.screen_to_doc(pos)
            dx = d.x() - self._move_start.x()
            dy = d.y() - self._move_start.y()
            for op in (self._moves or [self._move]):
                op.render(dx, dy)
            self.doc.recompose()
            self.update()
            self.cursorMoved.emit(d)
            return

        if self._shape_start is not None:
            d = self.screen_to_doc(pos)
            self._shape_end = self._constrain_shape(d)
            self.update()
            self.cursorMoved.emit(d)
            return

        if self._stroke is not None:
            self._stroke_pending = (QPointF(pos), pressure)
            if not self._stroke_timer.isActive():
                self._stroke_timer.start()
            return

        if self._smudge is not None:
            r = self._smudge.move(self.screen_to_doc(pos), pressure)
            self._refresh(r if r is not None else QRect())
            self.pressureChanged.emit(pressure)
            return

        if self._sel_start is not None:
            self._build_sel_preview(self.screen_to_doc(pos))
            self.update()

        d = self.screen_to_doc(pos)
        self.cursorMoved.emit(d)
        # 悬停到对称轴心上就换成手形，告诉用户「这个点可以拖」
        hot = self._sym_handle_hit(pos)
        if hot != self._sym_hot:
            self._sym_hot = hot
            self._sync_cursor()
            self.update()
        if self.tool in ("brush", "eraser", "smudge"):
            # 只重画笔尖圈那一小块。整块画布重绘（合成图 + 棋盘 + 所有叠加层）
            # 在 200px 大笔刷下要十几毫秒，鼠标一动就是满帧重画 —— 看起来就是
            # 「圆圈跟不上手、卡卡的」。擦掉旧圈 + 画新圈，两个小方块就够。
            cur = self._cursor_rect()
            upd = cur.united(getattr(self, "_prev_cursor", QRect()))
            if not upd.isEmpty():
                self.update(upd)
            self._prev_cursor = cur

    def _flush_stroke_move(self):
        """把合并后的最新笔触点真正落到 Stroke，避免鼠标事件排队。"""
        if self._stroke is None or self._stroke_pending is None:
            self._stroke_timer.stop()
            return
        pos, pressure = self._stroke_pending
        self._stroke_pending = None
        r = self._stroke.move(self.screen_to_doc(pos), pressure)
        self._refresh(r if r is not None else QRect())
        self.pressureChanged.emit(pressure)
        if self._stroke_pending is None:
            self._stroke_timer.stop()

    def pointer_up(self):
        if self._text_move is not None:
            it, start, ox, oy = self._text_move
            moved = abs(it.x - ox) > 0.01 or abs(it.y - oy) > 0.01
            self._text_move = None
            self.setCursor(Qt.SizeAllCursor)
            edit = self._text_edit
            self._text_edit = None
            if moved and edit is not None:
                self.doc.modified = True
                edit.capture(self.doc)
                self.doc.push(edit)
                self.historyChanged.emit()
                self.docChanged.emit()
            self.doc.recompose()
            self.update()
            return
        if self._sym_drag:
            self._sym_drag = False
            self._sym_hot = False
            self.setCursor(self._tool_cursor())
            self.symmetryChanged.emit()      # 让状态栏报一下新轴心坐标
            self.update()
            return
        if self._panning:
            self._panning = False
            self.setCursor(Qt.OpenHandCursor if self.tool == "hand" else
                           (Qt.BlankCursor if self.tool in ("brush", "eraser", "smudge")
                           else Qt.CrossCursor))
            return
        if self._stroke is not None:
            self._flush_stroke_move()
            self._stroke_timer.stop()
            edit = self._stroke.end()
            self._stroke = None
            if edit is not None:
                self.doc.push(edit)
                self.historyChanged.emit()
                self.docChanged.emit()
            return

        if self._smudge is not None:
            edit = self._smudge.end()
            self._smudge = None
            if edit is not None:
                self.doc.push(edit)
                self.historyChanged.emit()
                self.docChanged.emit()
            return

        if self._tf is not None:
            self._tf_mode = None
            self._tf_handle = -1
            return

        if self._move is not None:
            d = self.screen_to_doc(self._mouse)
            dx = d.x() - self._move_start.x()
            dy = d.y() - self._move_start.y()
            ops = self._moves or [self._move]
            self._move = None
            self._moves = None
            self.setCursor(Qt.SizeAllCursor)
            if abs(dx) > 0.01 or abs(dy) > 0.01:
                edits = [op.finish(dx, dy) for op in ops]
                edit = edits[0] if len(edits) == 1 else GroupEdit(edits, "移动图层")
                self.doc.push(edit)
                self.historyChanged.emit()
                self.docChanged.emit()
                if any(getattr(op, "snapped", False) for op in ops):
                    self.blocked.emit("已吸附：色块正好对齐画布")
                elif any(getattr(op, "lost", False) for op in ops):
                    self.blocked.emit(
                        "有内容被推到画布外面了　再拖回来会自动恢复（导出只含画布内）")
            else:
                for op in ops:
                    op.render(0.0, 0.0)
            self.doc.recompose()
            self.update()
            return

        if self._shape_start is not None:
            self._commit_shape()
            return
        if self._sel_start is not None:
            self._commit_selection()
            self._sel_start = None
            self._sel_path = None
            self.update()

    def pick_layer_at(self, point: QPointF):
        """移动工具的「自动选择」：返回光标下最上层有像素、且没被锁住的图层。

        锁住的图层直接跳过：自动选择是为了「点哪儿移哪儿」，点到一个锁住的
        图层只会弹一句「已锁定」，还不如让给下面那层能动的。
        """
        x, y = int(point.x()), int(point.y())
        self._pick_skipped = None
        for i in range(len(self.doc.layers) - 1, -1, -1):
            layer = self.doc.layers[i]
            if self.doc.is_locked(layer):
                if self._pick_skipped is None:
                    self._pick_skipped = layer
                continue
            vis, op = self.doc.layer_state(layer)
            if not vis or op <= 0.01:
                continue
            if not (0 <= x < layer.image.width() and 0 <= y < layer.image.height()):
                continue
            if layer.image.pixelColor(x, y).alpha() > 8:
                return i
        return None

    # ------------------------------------------------------------ 自由变换
    def begin_transform(self) -> bool:
        layer = self.doc.layer
        if layer is None:
            return False
        if self.doc.is_locked(layer):
            self.blocked.emit(f"「{layer.name}」已锁定，先解锁再变换")
            return False
        if self._tf is not None:
            return True
        self._tf = TransformOp(self.doc, layer)
        self._tf.render()
        self.doc.recompose()
        self.setCursor(Qt.SizeAllCursor)
        self.update()
        self.transformChanged.emit(True)
        return True

    def has_transform(self) -> bool:
        return self._tf is not None

    def tf_base_size(self):
        tf = self._tf
        if tf is None:
            return (1.0, 1.0)
        return (max(1.0, tf.src_rect.width()), max(1.0, tf.src_rect.height()))

    def tf_scale_pct(self) -> float:
        bw, _ = self.tf_base_size()
        return 100.0 * (self._tf.w / bw if self._tf is not None else 1.0)

    def tf_set_angle(self, deg: float):
        if self._tf is None:
            return
        self._tf.angle = float(deg)
        self._tf.render()
        self.doc.recompose()
        self.update()

    def tf_set_scale(self, pct: float):
        if self._tf is None:
            return
        bw, bh = self.tf_base_size()
        k = max(0.02, float(pct) / 100.0)
        self._tf.w = bw * k
        self._tf.h = bh * k
        self._tf.render()
        self.doc.recompose()
        self.update()

    def tf_flip(self, horizontal: bool):
        if self._tf is None:
            return
        if horizontal:
            self._tf.flip_h = not self._tf.flip_h
        else:
            self._tf.flip_v = not self._tf.flip_v
        self._tf.render()
        self.doc.recompose()
        self.update()

    def commit_transform(self):
        if self._tf is None:
            return
        op = self._tf
        self._tf = None
        self._tf_mode = None
        edit = op.finish()
        self.doc.push(edit)
        self.doc.recompose()
        self.update()
        self.historyChanged.emit()
        self.docChanged.emit()
        self.setCursor(Qt.BlankCursor if self.tool in ("brush", "eraser", "smudge")
                       else Qt.CrossCursor)
        self.transformChanged.emit(False)

    def cancel_transform(self):
        if self._tf is None:
            return
        op = self._tf
        self._tf = None
        self._tf_mode = None
        op.layer.image = op.before.copy()
        op.layer.off = op.off_before          # 画布外那部分也要还原
        op.layer.off_pos = op.pos_before
        op.layer.touch()
        self.doc.recompose()
        self.update()
        self.transformChanged.emit(False)

    def _tf_hit(self, pos: QPointF):
        """返回 ('scale', idx) / ('move', -1) / ('rotate', -1) / (None, -1)。"""
        tf = self._tf
        if tf is None:
            return (None, -1)
        for i, hp in enumerate(tf.handles()):
            d = self.doc_to_screen(hp) - pos
            if abs(d.x()) + abs(d.y()) <= 9:
                return ("scale", i)
        # 转成局部坐标判断是否在框内
        d = QPointF(pos.x() - self.ox, pos.y() - self.oy)
        d = QPointF(d.x() / self.zoom, d.y() / self.zoom)
        rel = d - tf.center
        rad = math.radians(-tf.angle)
        lx = rel.x() * math.cos(rad) - rel.y() * math.sin(rad)
        ly = rel.x() * math.sin(rad) + rel.y() * math.cos(rad)
        if abs(lx) <= tf.w / 2 and abs(ly) <= tf.h / 2:
            return ("move", -1)
        pad = 42 / max(0.05, self.zoom)
        if abs(lx) <= tf.w / 2 + pad and abs(ly) <= tf.h / 2 + pad:
            return ("rotate", -1)
        return (None, -1)

    def _tf_drag(self, pos: QPointF):
        tf = self._tf
        if tf is None or self._tf_saved is None:
            return
        c0, w0, h0, a0 = self._tf_saved
        cur = self.screen_to_doc(pos)
        if self._tf_mode == "move":
            tf.center = QPointF(c0.x() + (cur.x() - self._tf_start.x()),
                                c0.y() + (cur.y() - self._tf_start.y()))
        elif self._tf_mode == "rotate":
            ang0 = math.atan2(self._tf_start.y() - c0.y(), self._tf_start.x() - c0.x())
            ang1 = math.atan2(cur.y() - c0.y(), cur.x() - c0.x())
            deg = a0 + math.degrees(ang1 - ang0)
            if QApplication.keyboardModifiers() & Qt.ShiftModifier:
                deg = round(deg / 15.0) * 15.0
            tf.angle = deg
        else:
            rel = QPointF(cur.x() - c0.x(), cur.y() - c0.y())
            rad = math.radians(-a0)
            lx = rel.x() * math.cos(rad) - rel.y() * math.sin(rad)
            ly = rel.x() * math.sin(rad) + rel.y() * math.cos(rad)
            idx = self._tf_handle
            hx = 0 if idx in (1, 5) else (-1 if idx in (0, 6, 7) else 1)
            hy = 0 if idx in (3, 7) else (-1 if idx in (0, 1, 2) else 1)
            nw = max(4.0, abs(lx) * 2) if hx else w0
            nh = max(4.0, abs(ly) * 2) if hy else h0
            if QApplication.keyboardModifiers() & Qt.ShiftModifier and hx and hy:
                k = max(nw / max(1.0, w0), nh / max(1.0, h0))
                nw, nh = w0 * k, h0 * k
            tf.w, tf.h = nw, nh
        tf.render()
        self.doc.recompose()
        self.update()

    # ------------------------------------------------------------ 形状
    def _constrain_shape(self, cur: QPointF) -> QPointF:
        """按住 Shift：矩形/椭圆约束为正方形、圆；直线约束到 45°。"""
        if not (QApplication.keyboardModifiers() & Qt.ShiftModifier):
            return cur
        sx, sy = self._shape_start.x(), self._shape_start.y()
        dx, dy = cur.x() - sx, cur.y() - sy
        if self.tool == "line":
            ang = math.atan2(dy, dx)
            step = math.pi / 4
            ang = round(ang / step) * step
            r = (dx * dx + dy * dy) ** 0.5
            return QPointF(sx + math.cos(ang) * r, sy + math.sin(ang) * r)
        m = max(abs(dx), abs(dy))
        return QPointF(sx + math.copysign(m, dx or 1), sy + math.copysign(m, dy or 1))

    def _shape_rect(self) -> QRectF:
        return QRectF(self._shape_start, self._shape_end).normalized()

    def _commit_shape(self):
        layer = self.doc.layer
        start, end = self._shape_start, self._shape_end
        self._shape_start = None
        self._shape_end = None
        before = self._shape_before
        self._shape_before = None
        self.update()
        if layer is None or before is None:
            return
        w = max(1.0, self.shape_width)
        p = QPainter(layer.image)
        p.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(self.color, w)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(QBrush(self.color) if self.shape_fill else Qt.NoBrush)
        if self.doc.has_selection():
            p.setClipPath(self.doc.selection)
        r = QRectF(start, end).normalized()
        if self.tool == "rect":
            p.drawRect(r)
        elif self.tool == "ellipse_shape":
            p.drawEllipse(r)
        elif self.tool == "line":
            p.setBrush(Qt.NoBrush)
            p.drawLine(start, end)
        p.end()
        pad = int(w / 2) + 2
        # r 已经是 start/end 归一化后的外接矩形，直线也一样用这个 ——
        # 以前直线单独算了一遍，把「高」写成了 ys[1]-ys[1]（恒为 0），
        # 结果脏矩形只有一条横带，斜线大部分没重绘：画完看不见，
        # 得等下一次别的操作把那一块重画出来才显示。
        box = r.toAlignedRect().adjusted(-pad, -pad, pad, pad)
        box = box.intersected(QRect(0, 0, layer.image.width(), layer.image.height()))
        layer.touch()
        layer.has_content = True
        self.doc.recompose(box)
        self.update()
        edit = PixelEdit(layer, box, before.copy(box), layer.image.copy(box))
        self.doc.push(edit)
        self.historyChanged.emit()
        self.docChanged.emit()

    # ------------------------------------------------------------ 选区
    def _build_sel_preview(self, cur: QPointF):
        path = QPainterPath()
        if self.tool == "lasso":
            self._sel_points.append(cur)
            poly = QPainterPath(QPointF(self._sel_points[0]))
            for pt in self._sel_points[1:]:
                poly.lineTo(pt)
            path = poly
        else:
            r = QRectF(self._sel_start, cur).normalized()
            if self.tool == "ellipse":
                path.addEllipse(r)
            else:
                path.addRect(r)
        self._sel_path = path

    def _commit_selection(self):
        path = self._sel_path
        if path is None:
            self.doc.clear_selection()
            return
        if self.tool == "lasso" and len(self._sel_points) > 2:
            path.closeSubpath()
        if path.isEmpty():
            if self._sel_mode in ("new",):
                self.doc.clear_selection()
            return
        if self._sel_mode == "add" and self.doc.has_selection():
            self.doc.set_selection(self.doc.selection.united(path))
        elif self._sel_mode == "sub" and self.doc.has_selection():
            self.doc.set_selection(self.doc.selection.subtracted(path))
        else:
            self.doc.set_selection(path)

    # ------------------------------------------------------------ 事件
    def warm_brush_cache(self):
        """提前生成喷点笔的随机贴图，避免第一笔要等贴图缓存。"""
        b = self.active_brush()
        if b.kind in ("spray", "splatter"):
            from core import STAMPS
            STAMPS.get(b.size, b.hardness, self.color, b.grain,
                       b.grain_scale, b.kind)

    def sync_selection_ants(self):
        """选区变了（含撤销/重做）之后，让蚂蚁线跟着动起来或者停下来。"""
        if self.doc.has_selection():
            if not self._ants_timer.isActive():
                self._ants_timer.start()
        else:
            self._ants_timer.stop()
        self.update()

    def refresh_brush_cursor(self):
        """笔刷参数变了：只有光标落在画布上时才需要重画（画的是笔尖圆圈）。

        调参数时光标在右侧面板上，整块画布重绘纯属浪费 —— 拖动滑杆时每帧
        省下十几毫秒，手感就是从「发涩」变成「跟手」。
        """
        if self._inside and self.tool in ("brush", "eraser", "smudge"):
            self._prev_cursor = QRect()      # 圈的大小变了，旧位置整块重画
            self.update()

    def _mark_inside(self, v: bool):
        if self._inside != v:
            self._inside = v
            self._prev_cursor = QRect()      # 进出画布时光标圈整块重画，旧位置作废
            if self.tool in ("brush", "eraser", "smudge"):
                self.update()

    def _sync_cursor(self):
        """把系统光标同步成当前该有的样子。

        数位板（TabletMove 被 accept 之后不会再合成鼠标事件）不会触发
        enterEvent / mouseMoveEvent，光标就会一直停在「上一个工作区」的样子 ——
        用户反馈的「回到画布没切回画笔光标」就是这个。
        """
        if self._panning or self._sym_drag:
            want = Qt.ClosedHandCursor
        elif self._sym_hot:
            want = Qt.OpenHandCursor
        else:
            want = self._tool_cursor()
        if getattr(self, "_cursor_shape", None) != want:
            self._cursor_shape = want
            self.setCursor(want)

    def _check_pointer_over(self):
        """看门狗：确认系统光标真的还在画布上。

        leaveEvent 在数位板上不一定来（笔悬停移出画布时常常没有），
        于是笔尖圈会一直留在最后那个位置，人已经去点下面的笔刷了 ——
        用户反馈的「光标卡在工作区边缘」。这里每 200ms 用 widgetAt 复核一次。
        """
        if not self._inside or self._stroke is not None or self._smudge is not None:
            return
        # 只处理「笔已经停住」的情况：运笔过程中每 200ms 判一次会白白触发整块重绘，
        # 反而制造卡顿。指针事件刚过去 0.4 秒内一律不管。
        if time.monotonic() - getattr(self, "_last_ptr", 0.0) < 0.4:
            return
        try:
            w = QApplication.widgetAt(QCursor.pos())
        except Exception:
            return
        if w is self or (w is not None and self.isAncestorOf(w)):
            return
        self._mark_inside(False)
        self._prev_cursor = QRect()
        self.update()

    def enterEvent(self, e):
        self._mark_inside(True)
        self._sync_cursor()
        if not self._hover_watch.isActive():
            self._hover_watch.start()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover_watch.stop()
        self._mark_inside(False)
        # 无条件重绘一次：贴着边缘出去时，最后一次局部刷新只擦了光标圈那一小块，
        # 圈正好压在边界上就会留半圈在那儿。整块重画一次最省心（只在离开时发生）。
        self._prev_cursor = QRect()
        self.update()
        super().leaveEvent(e)

    def _mouse_shadowed(self) -> bool:
        """数位板工作时，部分驱动会同时补发鼠标事件，这里屏蔽，避免双重描边。"""
        return (time.monotonic() - self._tablet_time) < 0.35

    def mousePressEvent(self, e):
        if self._mouse_shadowed() and e.button() == Qt.LeftButton:
            return
        self.pressure_source = "mouse"
        self.pointer_down(QPointF(e.position()), self._pressure_for_mouse(QPointF(e.position())),
                          e.button(), e.modifiers())

    def mouseMoveEvent(self, e):
        self._hover_pos = QPointF(e.position())     # 缩放时以它为锚点
        if self._mouse_shadowed() and self._stroke is None:
            return
        if not self._mouse_shadowed():
            self.pressure_source = "mouse"
        self.pointer_move(QPointF(e.position()), self._pressure_for_mouse(QPointF(e.position())))

    def mouseDoubleClickEvent(self, e):
        if self._tf is not None:
            self.commit_transform()
            e.accept()
            return
        super().mouseDoubleClickEvent(e)

    def mouseReleaseEvent(self, e):
        self.pointer_up()

    def tabletEvent(self, e):
        t = e.type()
        self._tablet_time = time.monotonic()
        self.pressure_source = "tablet"
        pos = QPointF(e.position())
        # 数位板不走 enterEvent：这里手动补上「在画布内」和光标形状
        self._sync_cursor()
        self._last_ptr = time.monotonic()
        if not self._hover_watch.isActive():
            self._hover_watch.start()
        self._inside = self.rect().contains(QPoint(int(pos.x()), int(pos.y())))
        # 压力：抬笔前驱动会连续报 0，之前遇到 0 就当成「没压感」按 1.0 画，
        # 结果笔迹末端会突然冒出一个满径的墨团。这里保留上一帧的真实压力。
        raw = float(e.pressure())
        if raw > 0.0005:
            self._last_pressure = raw
        self._pressure = raw if raw > 0.0005 else self._last_pressure
        if t == QEvent.TabletPress:
            self._tablet_erase = self._eraser_tip(e)
            if self._tablet_erase and self.tool not in ("brush", "eraser", "smudge"):
                self.set_tool("eraser")
            self.pointer_down(pos, self._pressure, Qt.LeftButton, e.modifiers())
        elif t == QEvent.TabletMove:
            self.pointer_move(pos, self._pressure)
        elif t == QEvent.TabletRelease:
            self.pointer_up()
            self._tablet_erase = False
        e.accept()

    @staticmethod
    def _eraser_tip(e) -> bool:
        """笔尾橡皮（Wacom / XPPen 都有）；拿不到就当作普通笔尖。"""
        try:
            from PySide6.QtGui import QPointingDevice
            return e.pointerType() == QPointingDevice.PointerType.Eraser
        except Exception:
            return False

    def event(self, e):
        # 触摸板双指捏合：Windows / macOS 走 NativeGesture 这条通道，
        # 不接的话触摸板用户根本放不大画布（滚轮事件在触摸板上不是「捏合」）。
        if e.type() == QEvent.NativeGesture:
            gt = e.gestureType()
            if gt in (Qt.ZoomNativeGesture, Qt.SmartZoomNativeGesture):
                pos = QPointF(e.position())
                factor = 1.0 + float(e.value())
                factor = max(0.2, min(5.0, factor))
                self.set_zoom(self.zoom * factor, pos)
                return True
        # 触摸屏 / 部分驱动把捏合送成 QPinchGesture
        if e.type() == QEvent.Gesture:
            for g in e.gestures():
                if g.gestureType() != Qt.PinchGesture:
                    continue
                if g.state() == Qt.GestureUpdated:
                    last = float(g.lastScaleFactor()) or 1.0
                    f = float(g.scaleFactor()) / last
                    if 0.2 < f < 5.0:
                        self.set_zoom(self.zoom * f, QPointF(g.centerPoint()))
                return True
        return super().event(e)

    def wheelEvent(self, e):
        pos = QPointF(e.position())
        mods = e.modifiers()
        delta = e.angleDelta()
        pd = e.pixelDelta()
        # 触摸板 vs 鼠标：触摸板带滚动相位（Begin/Update/End），鼠标滚轮没有。
        # 触摸板上两指滑 = 平移画布，捏合（驱动一般发 Ctrl+滚轮）= 缩放；
        # 鼠标仍然是「滚轮缩放、Ctrl+滚轮调笔刷大小」。
        touchpad = e.phase() != Qt.NoScrollPhase
        if touchpad:
            self._auto_fit = False
            if mods & Qt.ControlModifier:
                step = pd.y() if not pd.isNull() else delta.y() * 0.5
                factor = max(0.5, min(2.0, 1.0 + step / 240.0))
                self.set_zoom(self.zoom * factor, pos)
                return
            step = pd.y() if not pd.isNull() else delta.y() * 0.5
            if mods & Qt.AltModifier:
                # 触摸板：Alt + 双指上下 = 调当前工具的笔径（画笔 / 橡皮 / 涂抹各调各的）
                if abs(step) > 0.01:
                    b = self.active_brush()
                    size = max(1.0, min(400.0, b.size * (1.0 + step / 300.0)))
                    if b.kind in SPRAY_KINDS and b.spread > 0.001:
                        size = min(size, b.spread)
                    b.size = size
                    self.brushSizeChanged.emit(size)
                    self.update()
                return
            if mods & Qt.ShiftModifier:
                # 触摸板：Shift + 双指上下 = 调不透明度
                if abs(step) > 0.01:
                    b = self.active_brush()
                    v = max(0.01, min(1.0, b.opacity + step / 600.0))
                    b.opacity = v
                    self.brushOpacityChanged.emit(v)
                    self.update()
                return
            dx = pd.x() if not pd.isNull() else delta.x() * 0.5
            dy = pd.y() if not pd.isNull() else delta.y() * 0.5
            self.ox += dx
            self.oy += dy
            self._text_follow()
            self.update()
            return
        if not pd.isNull():
            # 极少数鼠标也会给 pixelDelta：按平移处理，别当成缩放
            self._auto_fit = False
            self.ox += pd.x()
            self.oy += pd.y()
            self._text_follow()
            self.update()
            return
        if mods & Qt.ControlModifier:
            step = 1.0 + (0.06 if delta.y() > 0 else -0.06)
            b = self.active_brush()
            size = max(1.0, min(2000.0, b.size * step))
            b.size = size
            self.brushSizeChanged.emit(size)
            self.update()
            return
        if mods & Qt.ShiftModifier:
            self._auto_fit = False
            self.ox += delta.y() * 0.6
            self._text_follow()
            self.update()
            return
        if mods & Qt.AltModifier:
            self._auto_fit = False
            self.oy += delta.y() * 0.6
            self._text_follow()
            self.update()
            return
        factor = 1.0 + (delta.y() / 1200.0 if delta.y() else 0)
        if abs(factor - 1.0) < 1e-6:
            factor = 1.25 if delta.y() > 0 else 0.8
        self.set_zoom(self.zoom * factor, pos)

    def keyPressEvent(self, e: QKeyEvent):
        if self._tf is not None:
            if e.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.commit_transform()
                e.accept()
                return
            if e.key() == Qt.Key_Escape:
                self.cancel_transform()
                e.accept()
                return
        if e.key() == Qt.Key_Space and not e.isAutoRepeat():
            self._space = True
            if not self._panning:
                self.setCursor(Qt.OpenHandCursor)
            e.accept()
            return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e: QKeyEvent):
        if e.key() == Qt.Key_Space and not e.isAutoRepeat():
            self._space = False
            if self.tool in ("brush", "eraser", "smudge"):
                self.setCursor(Qt.BlankCursor)
            elif self.tool == "hand":
                self.setCursor(Qt.OpenHandCursor)
            else:
                self.setCursor(Qt.CrossCursor)
            e.accept()
            return
        super().keyReleaseEvent(e)
