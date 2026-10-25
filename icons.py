# -*- coding: utf-8 -*-
"""U Draw - 纯代码绘制的矢量图标

所有图标都画在 20×20 的网格里，1.7px 描边、圆头圆角，形状尽量写实可辨。
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QIcon, QPainter, QPainterPath, QPen,
                           QPixmap, QPolygonF)

from theme import C

_G = 20.0


def _fg(p: QPainter) -> QColor:
    return QColor(p.pen().color())


def _dashed(pen: QPen, on=2.2, off=2.0):
    pen.setDashPattern([on, off])
    return pen


def _draw(p: QPainter, name: str):
    col = _fg(p)
    pen = QPen(col, 1.7)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    if name == "brush":
        # 笔头朝右上的画笔：笔杆 + 金属箍 + 鼓起的笔毛（实心剪影）
        p.save()
        p.translate(10.2, 10.0)
        p.rotate(-45)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        p.drawRoundedRect(QRectF(-9.8, -1.55, 7.9, 3.1), 1.55, 1.55)   # 笔杆
        p.drawRoundedRect(QRectF(-2.2, -2.05, 2.8, 4.1), 0.8, 0.8)     # 金属箍
        tip = QPainterPath(QPointF(0.5, -2.05))                         # 笔毛
        tip.cubicTo(QPointF(2.2, -3.0), QPointF(4.4, -2.6), QPointF(7.2, 0.0))
        tip.cubicTo(QPointF(4.4, 2.6), QPointF(2.2, 3.0), QPointF(0.5, 2.05))
        tip.closeSubpath()
        p.drawPath(tip)
        p.setBrush(Qt.NoBrush)
        p.restore()

    elif name == "eraser":
        p.save()
        p.translate(9.9, 10.0)
        p.rotate(-38)
        body = QPainterPath()
        body.addRoundedRect(QRectF(-6.2, -4.3, 12.4, 8.6), 1.5, 1.5)
        p.save()
        p.setClipPath(body)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        p.drawRect(QRectF(-6.4, 0.0, 12.8, 4.8))        # 下端橡皮实心
        p.restore()
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(col, 1.55))
        p.drawPath(body)
        p.drawLine(QPointF(-5.8, 0.0), QPointF(5.8, 0.0))
        p.restore()

    elif name == "bucket":
        p.save()
        p.translate(9.0, 10.8)
        p.rotate(-26)
        p.setPen(QPen(col, 1.5))                         # 提手
        p.setBrush(Qt.NoBrush)
        h = QPainterPath(QPointF(-4.2, -4.8))
        h.quadTo(QPointF(0.0, -9.4), QPointF(4.2, -4.8))
        p.drawPath(h)
        body = QPainterPath(QPointF(-3.8, 4.4))          # 桶身（上口是弧，像敞口的桶）
        body.lineTo(QPointF(-5.2, -4.3))
        body.quadTo(QPointF(0.0, -2.8), QPointF(5.2, -4.3))
        body.lineTo(QPointF(3.8, 4.4))
        body.closeSubpath()
        p.drawPath(body)
        p.restore()
        p.setPen(Qt.NoPen)                               # 溅出的颜料
        p.setBrush(QBrush(col))
        drop = QPainterPath(QPointF(16.4, 12.8))
        drop.cubicTo(QPointF(19.0, 15.6), QPointF(18.0, 17.4), QPointF(16.4, 17.4))
        drop.cubicTo(QPointF(14.8, 17.4), QPointF(13.8, 15.6), QPointF(16.4, 12.8))
        p.drawPath(drop)
        p.setBrush(Qt.NoBrush)

    elif name == "eyedropper":
        p.save()
        p.translate(10.0, 9.8)
        p.rotate(-45)
        p.setPen(Qt.NoPen)                               # 针尖
        p.setBrush(QBrush(col))
        p.drawPolygon(QPolygonF([QPointF(-3.0, -1.05), QPointF(-7.8, -0.3),
                                 QPointF(-7.8, 0.3), QPointF(-3.0, 1.05)]))
        p.drawRoundedRect(QRectF(-3.2, -1.85, 6.2, 3.7), 1.85, 1.85)   # 管身
        p.drawRoundedRect(QRectF(3.9, -3.0, 5.8, 6.0), 3.0, 3.0)       # 橡皮头
        p.setBrush(Qt.NoBrush)
        p.restore()

    elif name == "marquee":
        p.setPen(_dashed(QPen(col, 1.5), 2.6, 2.2))
        p.drawRect(QRectF(3.8, 4.8, 12.4, 10.4))

    elif name == "ellipse":
        p.setPen(_dashed(QPen(col, 1.5), 2.4, 2.1))
        p.drawEllipse(QRectF(3.6, 5.2, 12.8, 9.6))

    elif name == "ellipse_shape":
        p.setPen(QPen(col, 1.6))
        p.drawEllipse(QRectF(3.6, 5.0, 12.8, 10.0))

    elif name == "lasso":
        path = QPainterPath(QPointF(8.2, 16.0))
        path.cubicTo(QPointF(2.4, 12.2), QPointF(2.6, 4.4), QPointF(9.4, 3.7))
        path.cubicTo(QPointF(16.2, 3.0), QPointF(18.4, 9.4), QPointF(13.4, 13.2))
        path.cubicTo(QPointF(11.6, 14.5), QPointF(9.6, 15.5), QPointF(8.2, 16.0))
        p.setPen(QPen(col, 1.6))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        tail = QPainterPath(QPointF(8.2, 16.0))          # 交叉垂下的绳尾
        tail.cubicTo(QPointF(9.6, 17.0), QPointF(10.4, 18.0), QPointF(10.8, 18.9))
        p.drawPath(tail)

    elif name == "hand":
        # 张开的手：四指 + 拇指 + 掌心
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        p.drawRoundedRect(QRectF(4.7, 9.2, 10.3, 7.6), 3.3, 3.3)
        pen = QPen(col, 2.0)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        for x, y0, y1 in ((6.8, 10.6, 5.6), (9.1, 10.6, 4.3),
                          (11.4, 10.6, 4.9), (13.6, 10.6, 6.6)):
            p.drawLine(QPointF(x, y1 + 0.9), QPointF(x + 0.35, y0))
        p.drawLine(QPointF(5.8, 12.6), QPointF(3.5, 10.1))    # 拇指
        p.setBrush(Qt.NoBrush)

    elif name in ("zoom", "zoom_in", "zoom_out"):
        p.drawEllipse(QRectF(3.4, 3.4, 10.4, 10.4))
        p.setPen(QPen(col, 2.2))
        p.drawLine(QPointF(12.8, 12.8), QPointF(17.2, 17.2))
        p.setPen(QPen(col, 1.7))
        p.drawLine(QPointF(6.2, 8.6), QPointF(11.0, 8.6))     # 横杠（缩小就只留这条）
        if name != "zoom_out":
            p.drawLine(QPointF(8.6, 6.2), QPointF(8.6, 11.0))  # 竖杠 → 加号

    elif name == "eye":
        path = QPainterPath(QPointF(2.6, 10.0))
        path.quadTo(QPointF(10.0, 3.2), QPointF(17.4, 10.0))
        path.quadTo(QPointF(10.0, 16.8), QPointF(2.6, 10.0))
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        p.drawEllipse(QRectF(7.9, 7.9, 4.2, 4.2))
        p.setBrush(Qt.NoBrush)

    elif name == "eye_off":
        path = QPainterPath(QPointF(2.6, 10.0))
        path.quadTo(QPointF(10.0, 3.2), QPointF(17.4, 10.0))
        path.quadTo(QPointF(10.0, 16.8), QPointF(2.6, 10.0))
        p.drawPath(path)
        p.setPen(QPen(col, 1.9))
        p.drawLine(QPointF(3.8, 16.8), QPointF(16.2, 3.2))

    elif name in ("undo", "redo"):
        p.save()
        if name == "redo":
            p.translate(20.0, 0.0)
            p.scale(-1.0, 1.0)
        path = QPainterPath(QPointF(16.2, 16.2))
        path.cubicTo(QPointF(16.2, 7.4), QPointF(9.6, 4.8), QPointF(5.0, 8.6))
        p.setPen(QPen(col, 1.9))
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        p.drawPolygon(QPolygonF([QPointF(8.6, 4.9), QPointF(3.2, 8.9),
                                 QPointF(8.9, 12.0)]))
        p.setBrush(Qt.NoBrush)
        p.restore()

    elif name == "plus":
        p.drawRoundedRect(QRectF(3.6, 3.6, 12.8, 12.8), 2.2, 2.2)
        p.setPen(QPen(col, 2.0))
        p.drawLine(QPointF(10.0, 6.6), QPointF(10.0, 13.4))
        p.drawLine(QPointF(6.6, 10.0), QPointF(13.4, 10.0))

    elif name == "copy":
        p.drawRoundedRect(QRectF(3.4, 3.4, 8.6, 8.6), 1.6, 1.6)
        p.drawRoundedRect(QRectF(8.0, 8.0, 8.6, 8.6), 1.6, 1.6)

    elif name == "up":
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        p.drawPolygon(QPolygonF([QPointF(4.4, 13.2), QPointF(10.0, 7.2),
                                 QPointF(15.6, 13.2)]))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(col, 1.8))
        p.drawLine(QPointF(5.0, 16.4), QPointF(15.0, 16.4))

    elif name == "down":
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        p.drawPolygon(QPolygonF([QPointF(4.4, 6.8), QPointF(10.0, 12.8),
                                 QPointF(15.6, 6.8)]))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(col, 1.8))
        p.drawLine(QPointF(5.0, 3.6), QPointF(15.0, 3.6))

    elif name == "merge":
        p.setPen(QPen(col, 1.8))
        p.drawLine(QPointF(10.0, 3.2), QPointF(10.0, 8.4))
        p.drawLine(QPointF(4.6, 16.4), QPointF(15.4, 16.4))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        p.drawPolygon(QPolygonF([QPointF(5.8, 9.0), QPointF(14.2, 9.0),
                                 QPointF(10.0, 14.4)]))
        p.setBrush(Qt.NoBrush)

    elif name == "trash":
        p.setPen(QPen(col, 1.8))
        p.drawLine(QPointF(3.6, 6.4), QPointF(16.4, 6.4))
        p.drawLine(QPointF(7.6, 3.6), QPointF(12.4, 3.6))
        p.setPen(QPen(col, 1.7))
        p.drawPolyline(QPolygonF([QPointF(5.2, 7.0), QPointF(14.8, 7.0),
                                  QPointF(13.8, 17.2), QPointF(6.2, 17.2),
                                  QPointF(5.2, 7.0)]))
        p.drawLine(QPointF(8.6, 9.6), QPointF(8.8, 14.6))
        p.drawLine(QPointF(11.4, 9.6), QPointF(11.2, 14.6))

    elif name == "layers":
        p.drawPolygon(QPolygonF([QPointF(10.0, 3.2), QPointF(17.2, 6.8),
                                 QPointF(10.0, 10.4), QPointF(2.8, 6.8)]))
        p.drawPolyline(QPolygonF([QPointF(2.8, 11.4), QPointF(10.0, 15.0),
                                  QPointF(17.2, 11.4)]))

    elif name == "move":
        # 四向箭头：十字 + 四个实心箭头
        pen = QPen(col, 1.6)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(10, 5.6), QPointF(10, 14.4))
        p.drawLine(QPointF(5.6, 10), QPointF(14.4, 10))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        for pts in (
                [(10, 2.4), (7.6, 6.2), (12.4, 6.2)],
                [(10, 17.6), (7.6, 13.8), (12.4, 13.8)],
                [(2.4, 10), (6.2, 7.6), (6.2, 12.4)],
                [(17.6, 10), (13.8, 7.6), (13.8, 12.4)]):
            p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
        p.setBrush(Qt.NoBrush)

    elif name == "rect":
        p.setPen(QPen(col, 1.6))
        p.drawRect(QRectF(3.8, 5.2, 12.4, 9.6))

    elif name == "line":
        p.setPen(QPen(col, 1.9))
        p.drawLine(QPointF(4.6, 15.4), QPointF(15.4, 4.6))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        p.drawEllipse(QPointF(4.6, 15.4), 1.5, 1.5)
        p.drawEllipse(QPointF(15.4, 4.6), 1.5, 1.5)
        p.setBrush(Qt.NoBrush)

    elif name == "smudge":
        # 一根手指 + 两道拖痕：一眼看出是「抹开」
        p.save()
        p.translate(8.6, 11.4)
        p.rotate(-24)
        p.setPen(QPen(col, 1.55))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(-1.6, -9.6, 3.2, 9.6), 1.6, 1.6)     # 手指
        p.drawRoundedRect(QRectF(-3.4, -1.2, 6.8, 6.6), 2.4, 2.4)     # 手背
        p.restore()
        pen = QPen(col, 1.3)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(QRectF(12.4, 4.2, 5.6, 5.6), -55 * 16, 110 * 16)
        p.drawArc(QRectF(12.4, 9.8, 5.6, 5.6), -55 * 16, 110 * 16)

    elif name == "text":
        # 衬线 T
        pen = QPen(col, 1.9)
        pen.setCapStyle(Qt.FlatCap)
        p.setPen(pen)
        p.drawLine(QPointF(4.2, 5.2), QPointF(15.8, 5.2))
        p.drawLine(QPointF(10.0, 5.2), QPointF(10.0, 16.2))
        pen2 = QPen(col, 1.4)
        pen2.setCapStyle(Qt.FlatCap)
        p.setPen(pen2)
        p.drawLine(QPointF(4.2, 5.2), QPointF(4.2, 7.8))
        p.drawLine(QPointF(15.8, 5.2), QPointF(15.8, 7.8))
        p.drawLine(QPointF(7.4, 16.2), QPointF(12.6, 16.2))

    elif name == "group":
        # 文件夹 + 右下角加号：把选中图层装进新组
        folder = QPainterPath(QPointF(2.6, 7.0))
        folder.lineTo(7.2, 7.0)
        folder.lineTo(8.8, 9.0)
        folder.lineTo(11.6, 9.0)
        folder.lineTo(11.6, 15.2)
        folder.lineTo(2.6, 15.2)
        folder.closeSubpath()
        p.setPen(QPen(col, 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawPath(folder)
        p.setPen(QPen(col, 1.6))
        p.drawEllipse(QPointF(14.8, 13.8), 3.5, 3.5)          # 加号徽标
        p.setPen(QPen(col, 1.5))
        p.drawLine(QPointF(14.8, 11.8), QPointF(14.8, 15.8))
        p.drawLine(QPointF(12.8, 13.8), QPointF(16.8, 13.8))

    elif name == "ungroup":
        # 虚线框（组）+ 一支飞出去的箭头：把成员从组里放出来
        p.setPen(_dashed(QPen(col, 1.4), 2.3, 1.9))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(3.0, 6.6, 9.2, 9.2))
        p.setPen(QPen(col, 1.6))
        p.drawLine(QPointF(9.4, 12.4), QPointF(15.6, 6.2))     # 箭头杆
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        p.drawPolygon(QPolygonF([QPointF(17.6, 4.2), QPointF(11.4, 5.4),
                                 QPointF(16.4, 10.4)]))
        p.setBrush(Qt.NoBrush)

    elif name == "pin":
        # 图钉：背景层固定在最底层
        p.save()
        p.translate(10.0, 9.4)
        p.rotate(38)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        p.drawRoundedRect(QRectF(-4.6, -5.2, 9.2, 2.6), 0.9, 0.9)   # 钉帽
        p.drawPolygon(QPolygonF([QPointF(-1.7, -2.6), QPointF(1.7, -2.6),
                                 QPointF(0.9, 2.4), QPointF(-0.9, 2.4)]))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(col, 1.3))
        p.drawLine(QPointF(0.0, 2.4), QPointF(0.0, 7.4))            # 钉尖
        p.restore()

    elif name == "symmetry":
        # 竖轴 + 两侧镜像的笔尖
        pen = QPen(col, 1.2)
        pen.setStyle(Qt.CustomDashLine)
        pen.setDashPattern([2.6, 2.2])
        p.setPen(pen)
        p.drawLine(QPointF(10.0, 2.4), QPointF(10.0, 17.6))
        p.setPen(QPen(col, 1.6))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(5.4, 8.0), 2.6, 2.6)
        p.drawEllipse(QPointF(14.6, 8.0), 2.6, 2.6)
        p.setPen(QPen(col, 1.3))
        p.drawLine(QPointF(3.2, 14.4), QPointF(7.4, 12.4))
        p.drawLine(QPointF(16.8, 14.4), QPointF(12.6, 12.4))

    elif name == "lock":
        p.setPen(QPen(col, 1.7))
        p.drawArc(QRectF(6.2, 2.8, 7.6, 8.0), 0, 180 * 16)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        p.drawRoundedRect(QRectF(4.4, 8.6, 11.2, 8.4), 1.8, 1.8)
        p.setBrush(QColor("#323232"))
        p.drawEllipse(QPointF(10.0, 12.2), 1.15, 1.15)
        p.drawRect(QRectF(9.3, 12.2, 1.4, 2.6))
        p.setBrush(Qt.NoBrush)

    elif name == "unlock":
        p.setPen(QPen(col, 1.7))
        p.drawArc(QRectF(8.6, 2.6, 7.6, 8.0), 20 * 16, 150 * 16)
        p.setPen(Qt.NoPen)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(col, 1.6))
        p.drawRoundedRect(QRectF(4.4, 8.6, 11.2, 8.4), 1.8, 1.8)
        p.drawEllipse(QPointF(10.0, 12.2), 1.15, 1.15)

    elif name == "reset":
        # 环形箭头
        pen = QPen(col, 1.8)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(4.0, 4.0, 12.0, 12.0), 40 * 16, 280 * 16)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        p.drawPolygon(QPolygonF([QPointF(13.6, 2.4), QPointF(18.2, 5.0), QPointF(13.2, 6.8)]))
        p.setBrush(Qt.NoBrush)

    elif name == "transform":
        # 虚线框 + 四角手柄
        p.setPen(_dashed(QPen(col, 1.5), 2.4, 2.0))
        p.drawRect(QRectF(4.4, 4.4, 11.2, 11.2))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        for cx in (4.4, 15.6):
            for cy in (4.4, 15.6):
                p.drawRect(QRectF(cx - 1.5, cy - 1.5, 3.0, 3.0))
        p.setBrush(Qt.NoBrush)

    elif name == "caret":
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        p.drawPolygon(QPolygonF([QPointF(3.6, 7.6), QPointF(8.4, 7.6),
                                 QPointF(6.0, 11.2)]))

    elif name == "opacity":
        p.drawEllipse(QRectF(3.4, 3.4, 13.2, 13.2))
        path = QPainterPath(QPointF(10.0, 3.4))
        path.arcTo(QRectF(3.4, 3.4, 13.2, 13.2), 90, -180)
        path.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        p.drawPath(path)
        p.setBrush(Qt.NoBrush)


_cache = {}


def icon(name: str, color: str = C.ICON, size: int = 18, dpr: float = 3.0) -> QIcon:
    key = (name, color, size, dpr)
    if key in _cache:
        return _cache[key]
    px = max(8, int(round(size * dpr)))
    pm = QPixmap(px, px)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    # 注意：pixmap 已设置 devicePixelRatio，QPainter 使用的是逻辑坐标，
    # 这里只能按逻辑尺寸缩放，再乘 dpr 会把图标缩到左上角四分之一。
    p.scale(size / _G, size / _G)
    p.setPen(QPen(QColor(color), 1.7))
    _draw(p, name)
    p.end()
    ic = QIcon(pm)
    _cache[key] = ic
    return ic


def pixmap(name: str, color: str = C.ICON, size: int = 18, dpr: float = 3.0) -> QPixmap:
    return icon(name, color, size, dpr).pixmap(int(size * dpr), int(size * dpr))
