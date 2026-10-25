# -*- coding: utf-8 -*-
"""程序笔尖与画布坐标纹理；不依赖 core，也不创建界面或读写设置。"""
import math
import random

from lazynp import np          # 惰性 numpy：启动时不需要它
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen, QRadialGradient

KINDS = ("chisel", "rake", "graphite", "pastel", "wax", "dry_ink",
         "sponge", "salt", "bloom", "impasto", "knife", "fur", "grass_blade",
         "fern", "petal", "blossom", "rose", "snowflake", "rain", "feather",
         "heart", "hexagon", "chain", "lace", "stitch", "hatch", "crosshatch",
         "stipple", "brick", "scales", "neon", "rainbow")
KIND_NAMES = dict(zip(KINDS, (
    "凿头", "排齿", "石墨", "色粉", "蜡质", "枯墨", "海绵", "盐粒", "水渍晕花",
    "堆色", "刮刀", "弧形毛发", "尖草束", "蕨叶", "花瓣", "五瓣花", "卷层玫瑰",
    "六枝雪晶", "雨丝", "羽毛", "心形", "六边形", "链环", "蕾丝", "缝线",
    "排线", "交叉排线", "点描", "砖纹", "鳞片", "霓虹", "彩虹")))
RANDOM_TEXTURES = ("graphite", "pastel", "wax", "dry_ink", "sponge", "salt",
                   "bloom", "impasto", "knife", "fur", "grass_blade", "rain")
PATTERN_KINDS = ("hatch", "crosshatch", "stipple", "brick", "scales")
MEDIA_MASKS = ("graphite", "pastel", "wax", "dry_ink", "sponge", "salt", "bloom",
               "impasto", "knife")
MASK_KINDS = PATTERN_KINDS + MEDIA_MASKS
FORMAT = QImage.Format_ARGB32_Premultiplied


def _col(color, alpha=1.0, light=100):
    c = QColor(color)
    if light != 100:
        c = c.lighter(light) if light > 100 else c.darker(200 - light)
    c.setAlphaF(max(0.0, min(1.0, alpha * color.alphaF())))
    return c


def _polygon(p, points, color):
    path = QPainterPath()
    path.moveTo(*points[0])
    for xy in points[1:]:
        path.lineTo(*xy)
    path.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawPath(path)


def _line(p, color, width, *coords):
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawLine(QPointF(*coords[:2]), QPointF(*coords[2:]))


def _petal_path(tip_x=0.0, tip_y=-0.9, root_y=0.18, breadth=0.42):
    path = QPainterPath()
    path.moveTo(0.0, root_y)
    path.cubicTo(-breadth, root_y - 0.2, tip_x - breadth, tip_y, tip_x, tip_y)
    path.cubicTo(tip_x + breadth, tip_y, breadth, root_y - 0.2, 0.0, root_y)
    return path


def _soft_disc(p, x, y, radius, color, hard=0.0):
    g = QRadialGradient(QPointF(x, y), radius)
    g.setColorAt(0.0, color)
    g.setColorAt(max(0.01, min(0.94, hard)), color)
    clear = QColor(color)
    clear.setAlpha(0)
    g.setColorAt(1.0, clear)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(x, y), radius, radius)


def paint_color_tip(p, d, color, kind, hardness=0.85):
    """动态颜色直接画，避免彩虹每个 HSV 值都生成一套缓存。"""
    r = max(0.3, d / 2.0)
    if kind == "neon":
        _soft_disc(p, 0.0, 0.0, r, _col(color, 0.55))
        _soft_disc(p, 0.0, 0.0, r * 0.42, color, 0.3)
        _soft_disc(p, 0.0, 0.0, r * 0.13, QColor(255, 255, 255, color.alpha()), 0.8)
    else:
        _soft_disc(p, 0.0, 0.0, r, color, hardness)


def make_stamp(kind, d, hard, color, variant):
    """在单位圆附近画独立形状；所有随机循环均有常数粒子上限。"""
    img = QImage(d, d, FORMAT)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.translate(d / 2.0, d / 2.0)
    if kind in ("neon", "rainbow"):
        paint_color_tip(p, max(0.6, d - 2), color, kind, hard)
        p.end()
        return img
    # 留抗锯齿和描边余量，不在贴图边缘画出界图形。
    radius = max(0.3, d / 2.0 - 1.0)
    p.scale(radius, radius)
    rng = random.Random(7351 + variant * 1193 + sum(map(ord, kind)) * 53)
    w = min(0.14, max(0.018, 0.8 / radius))
    if kind == "chisel":
        _polygon(p, [(-0.91, -0.42), (0.65, -0.42), (0.93, 0.38), (-0.65, 0.38)], color)
        _line(p, _col(color, 0.65, 130), w * 2, -0.76, -0.2, 0.70, -0.2)
    elif kind == "rake":
        for i in range(7):
            x = -0.78 + i * 0.26
            _polygon(p, [(x - 0.05, 0.60), (x - 0.04, -0.72), (x + 0.04, -0.84),
                         (x + 0.07, 0.60)], _col(color, 0.6 + 0.4 * (i % 3) / 2))
    elif kind == "graphite":
        for _ in range(130):
            x, y = rng.uniform(-0.84, 0.84), rng.uniform(-0.82, 0.82)
            if x * x + y * y > 0.80:
                continue
            ln = rng.uniform(0.018, 0.17)
            _line(p, _col(color, rng.uniform(0.3, 0.8)), w * rng.uniform(0.6, 1.4),
                  x, y, min(0.9, x + ln), y - ln * 0.28)
    elif kind == "pastel":
        for _ in range(85):
            x, y = rng.uniform(-0.8, 0.8), rng.uniform(-0.8, 0.8)
            if x * x + y * y > 0.6:
                continue
            rr = rng.choice((0.025, 0.06, 0.12))
            pts = [(x + math.cos(a * math.tau / 5) * rr,
                    y + math.sin(a * math.tau / 5) * rr) for a in range(5)]
            _polygon(p, pts, _col(color, rng.uniform(0.3, 0.95)))
    elif kind == "wax":
        for _ in range(36):
            x, y = rng.uniform(-0.65, 0.65), rng.uniform(-0.65, 0.65)
            rr = rng.uniform(0.035, 0.20)
            _polygon(p, [(x - rr, y - rr * 0.4), (x + rr * 0.7, y - rr),
                         (x + rr, y + rr * 0.65), (x - rr * 0.4, y + rr)],
                     _col(color, rng.uniform(0.55, 1.0)))
    elif kind == "dry_ink":
        for i in range(15):
            x = -0.82 + i * 0.115 + rng.uniform(-0.018, 0.018)
            for lo, hi in ((-0.8, -0.12), (0.06, 0.78)):
                _polygon(p, [(x - 0.022, lo + rng.uniform(0, 0.15)), (x + 0.036, lo),
                             (x + 0.020, hi - rng.uniform(0, 0.19)), (x - 0.036, hi)],
                         _col(color, rng.uniform(0.6, 1.0)))
    elif kind == "sponge":
        for _ in range(30):
            x, y = rng.uniform(-0.65, 0.65), rng.uniform(-0.65, 0.65)
            _soft_disc(p, x, y, rng.uniform(0.07, 0.22), _col(color, rng.uniform(0.25, 0.75)), 0.45)
        p.setCompositionMode(QPainter.CompositionMode_DestinationOut)
        for _ in range(20):
            _soft_disc(p, rng.uniform(-0.7, 0.7), rng.uniform(-0.7, 0.7),
                       rng.uniform(0.025, 0.09), QColor(255, 255, 255), 0.8)
    elif kind == "salt":
        for _ in range(48):
            x, y = rng.uniform(-0.8, 0.8), rng.uniform(-0.8, 0.8)
            if x * x + y * y > 0.65:
                continue
            rr = rng.choice((0.022, 0.045, 0.10))
            _polygon(p, [(x, y - rr), (x + rr * 0.7, y), (x, y + rr), (x - rr, y)],
                     _col(color, rng.uniform(0.4, 1.0)))
    elif kind == "bloom":
        for _ in range(7):
            x, y = rng.uniform(-0.28, 0.28), rng.uniform(-0.28, 0.28)
            _soft_disc(p, x, y, rng.uniform(0.3, 0.56), _col(color, 0.35))
        path = QPainterPath()
        for i in range(65):
            a = i * math.tau / 64
            rr = 0.64 + 0.055 * math.sin(a * 7) + 0.035 * math.sin(a * 13 + variant)
            xy = (math.cos(a) * rr, math.sin(a) * rr)
            path.moveTo(*xy) if i == 0 else path.lineTo(*xy)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(_col(color, 0.8, 85), w * 2))
        p.drawPath(path)
    elif kind == "impasto":
        _polygon(p, [(-0.82, -0.6), (-0.25, -0.8), (0.83, -0.48),
                     (0.72, 0.66), (-0.54, 0.78), (-0.88, 0.10)], color)
        for i in range(8):
            x = -0.65 + i * 0.18 + rng.uniform(-0.025, 0.025)
            path = QPainterPath(QPointF(x, rng.uniform(0.45, 0.62)))
            path.cubicTo(x - rng.uniform(0.04, 0.17), 0.1,
                         x + rng.uniform(0.04, 0.17), -0.15, x, rng.uniform(-0.65, -0.45))
            p.setPen(QPen(_col(color, rng.uniform(0.6, 0.9), 135 if i % 2 else 75), w * 2.5))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
    elif kind == "knife":
        _polygon(p, [(-0.9, 0.1), (0.74, -0.43), (0.9, 0.02), (-0.74, 0.43)], color)
        for j in range(7):
            offset = j * 0.026 + rng.uniform(-0.012, 0.012)
            _line(p, _col(color, rng.uniform(0.45, 0.9), 140 if j % 2 else 70), w,
                  rng.uniform(-0.72, -0.44), 0.16 + offset,
                  rng.uniform(0.38, 0.68), -0.26 + offset)
    elif kind == "fur":
        for _ in range(18):
            root = rng.uniform(-0.5, 0.5)
            tip = root + rng.uniform(-0.32, 0.32)
            path = QPainterPath(QPointF(root, 0.78))
            path.cubicTo(root - 0.32, 0.25, tip - 0.32, -0.4, tip, rng.uniform(-0.82, -0.55))
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(_col(color, rng.uniform(0.4, 0.9)), w))
            p.drawPath(path)
    elif kind == "grass_blade":
        for i in range(9):
            x = -0.32 + i * 0.08
            tip = -0.78 + i * 0.18 + rng.uniform(-0.05, 0.05)
            path = QPainterPath(QPointF(x - 0.055, 0.83))
            ty = rng.uniform(-0.86, -0.30)
            path.quadTo(x - 0.03, -0.14, tip, ty)
            path.quadTo(x + 0.14, 0.14, x + 0.055, 0.83)
            p.setPen(Qt.NoPen)
            p.setBrush(_col(color, rng.uniform(0.6, 1.0)))
            p.drawPath(path)
    elif kind == "fern":
        _line(p, color, w * 1.7, 0.0, 0.88, 0.0, -0.9)
        for i in range(9):
            y = 0.64 - i * 0.17
            ln = 0.70 * (1.0 - i / 10.0)
            for side in (-1, 1):
                path = QPainterPath(QPointF(0, y))
                path.quadTo(side * ln * 0.25, y - 0.26, side * ln, y - 0.20)
                path.quadTo(side * ln * 0.60, y + 0.06, 0, y)
                p.setPen(Qt.NoPen)
                p.setBrush(color)
                p.drawPath(path)
    elif kind in ("petal", "blossom"):
        n = 1 if kind == "petal" else 5
        for i in range(n):
            p.save()
            p.rotate(i * 72)
            p.setPen(Qt.NoPen)
            p.setBrush(_col(color, 0.95, 100 + i * 4))
            p.drawPath(_petal_path(breadth=0.45 if n == 1 else 0.34))
            _line(p, _col(color, 0.5, 145), w, 0, 0.02, 0, -0.58)
            p.restore()
        if n == 5:
            p.setPen(Qt.NoPen)
            p.setBrush(_col(color, 1.0, 65))
            p.drawEllipse(QPointF(0, 0), 0.14, 0.14)
    elif kind == "rose":
        # 各层花瓣之间保留透明缝隙，密集轮廓也能读出卷层。
        for layer, (rad, n) in enumerate(((0.88, 7), (0.61, 5), (0.34, 4))):
            for i in range(n):
                p.save()
                p.rotate(i * 360 / n + layer * 29)
                path = QPainterPath(QPointF(-rad * 0.42, -rad * 0.35))
                path.cubicTo(-rad, -rad * 0.65, -rad * 0.2, -rad * 1.02, rad * 0.45, -rad * 0.79)
                path.quadTo(rad * 0.75, -rad * 0.35, rad * 0.1, -rad * 0.24)
                path.quadTo(-rad * 0.04, -rad * 0.62, -rad * 0.42, -rad * 0.35)
                p.setPen(Qt.NoPen)
                p.setBrush(_col(color, 1.0, 100 + layer * 15))
                p.drawPath(path)
                p.restore()
        path = QPainterPath()
        for i in range(45):
            a = i * math.pi / 14
            rr = 0.02 + i * 0.0036
            xy = (math.cos(a) * rr, math.sin(a) * rr)
            path.moveTo(*xy) if i == 0 else path.lineTo(*xy)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(color, w * 1.5))
        p.drawPath(path)
    elif kind == "snowflake":
        for i in range(6):
            p.save()
            p.rotate(i * 60)
            _line(p, color, w * 1.6, 0, 0, 0, -0.88)
            for y, ln in ((-0.35, 0.21), (-0.57, 0.18), (-0.73, 0.12)):
                for side in (-1, 1):
                    _line(p, color, w, 0, y, side * ln, y - ln * 0.6)
            p.restore()
    elif kind == "rain":
        for _ in range(8):
            x, y = rng.uniform(-0.72, 0.65), rng.uniform(-0.5, 0.05)
            ln = rng.uniform(0.22, 0.72)
            _line(p, _col(color, rng.uniform(0.25, 0.85)), w * 1.5, x, y, x - ln * 0.24, y + ln)
    elif kind == "feather":
        path = QPainterPath(QPointF(-0.1, 0.88))
        path.quadTo(0.12, 0.10, 0.20, -0.86)
        p.setPen(QPen(color, w * 1.8))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        for i in range(15):
            y = 0.65 - i * 0.095
            x = 0.04 + (0.65 - y) * 0.11
            ln = 0.60 * math.sin((i + 1) * math.pi / 17)
            for side in (-1, 1):
                path = QPainterPath(QPointF(x, y))
                path.quadTo(x + side * ln * 0.7, y - 0.06, x + side * ln, y - 0.29)
                p.setPen(QPen(_col(color, 0.85), w))
                p.drawPath(path)
    elif kind == "heart":
        path = QPainterPath(QPointF(0, 0.84))
        path.cubicTo(-0.18, 0.60, -0.90, 0.0, -0.84, -0.38)
        path.cubicTo(-0.79, -0.90, -0.22, -0.88, 0, -0.38)
        path.cubicTo(0.22, -0.88, 0.79, -0.90, 0.84, -0.38)
        path.cubicTo(0.90, 0.0, 0.18, 0.60, 0, 0.84)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawPath(path)
    elif kind == "hexagon":
        path = QPainterPath()
        for i in range(6):
            xy = (0.84 * math.cos(i * math.pi / 3), 0.84 * math.sin(i * math.pi / 3))
            path.moveTo(*xy) if i == 0 else path.lineTo(*xy)
        path.closeSubpath()
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(color, max(w, 0.085)))
        p.drawPath(path)
    elif kind == "chain":
        for x, a in ((-0.32, -26), (0.32, 26)):
            p.save()
            p.translate(x, 0)
            p.rotate(a)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(color, max(w, 0.11)))
            p.drawEllipse(QRectF(-0.36, -0.54, 0.72, 1.08))
            p.restore()
        _line(p, _col(color, 0.8, 145), w, -0.13, -0.19, 0.16, 0.10)
    elif kind == "lace":
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(color, w * 1.5))
        p.drawEllipse(QPointF(0, 0), 0.31, 0.31)
        for i in range(10):
            p.save()
            p.rotate(i * 36)
            p.drawEllipse(QRectF(-0.14, -0.83, 0.28, 0.48))
            p.restore()
        _line(p, color, w, -0.21, -0.21, 0.21, 0.21)
        _line(p, color, w, -0.21, 0.21, 0.21, -0.21)
    elif kind == "stitch":
        for x in (-0.61, 0.0, 0.61):
            _line(p, color, w * 2.8, x - 0.17, -0.24, x + 0.17, 0.24)
        _line(p, _col(color, 0.55), w, -0.83, 0.32, 0.83, 0.32)
    elif kind in PATTERN_KINDS:
        _soft_disc(p, 0, 0, 0.96, color, hard)
    p.end()
    return img


def _hash(x, y, seed=0):
    """整型坐标哈希，不消费全局随机数，也不随合成矩形改变。"""
    a = np.asarray(x, dtype=np.int64) * 374761393 + np.asarray(y, dtype=np.int64) * 668265263 + seed * 144269
    a = (a ^ (a >> 13)) * 1274126177
    return ((a ^ (a >> 16)) & 65535).astype(np.float32) / 65535.0


def _sstep(x, lo, hi):
    """平滑阈值：以前用 `x > 0.22` 这种硬比较，遮罩就是「有 / 没有」两种状态，
    放大后是一粒一粒的硬边像素（马赛克感）。改成一段渐变，边缘才是过渡。"""
    t = np.clip((x - lo) / max(1e-6, hi - lo), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _texture(x, y, cell, seed):
    xx, yy = x / cell, y / cell
    ix, iy = np.floor(xx), np.floor(yy)
    fx, fy = xx - ix, yy - iy
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    return ((_hash(ix, iy, seed) * (1 - fx) + _hash(ix + 1, iy, seed) * fx) * (1 - fy)
            + (_hash(ix, iy + 1, seed) * (1 - fx) + _hash(ix + 1, iy + 1, seed) * fx) * fy)


def pattern_alpha(kind, x, y, scale, samples=1):
    """返回广播后的 alpha；图案空隙是真透明，密集盖章也无法填满。

    samples>1 时在像素内做 2x2 子采样再平均。斜线/砖缝只有 1px 宽，
    不采样的话放大后会是一格一格的硬锯齿。
    """
    if samples > 1:
        acc = None
        for sy in range(samples):
            for sx in range(samples):
                xx = x + (sx + 0.5) / samples
                yy = y + (sy + 0.5) / samples
                a = _pattern_alpha_raw(kind, xx, yy, scale).astype(np.float32)
                acc = a if acc is None else acc + a
        return (acc / float(samples * samples)).astype(np.uint8)
    return _pattern_alpha_raw(kind, x, y, scale)


def _pattern_alpha_raw(kind, x, y, scale):
    s = max(2.0, min(256.0, float(scale)))
    u, v = x / s, y / s
    width = max(0.055, min(0.22, 0.9 / s))
    diag = np.abs((u + v + 0.5) % 1.0 - 0.5) / math.sqrt(2)
    if kind in ("hatch", "crosshatch"):
        dist = diag
        if kind == "crosshatch":
            dist = np.minimum(dist, np.abs((u - v + 0.5) % 1.0 - 0.5) / math.sqrt(2))
        a = np.clip((width - dist) * s + 0.5, 0, 1)
    elif kind == "stipple":
        ix, iy = np.floor(u), np.floor(v)
        cx = 0.25 + 0.5 * _hash(ix, iy, 71)
        cy = 0.25 + 0.5 * _hash(ix, iy, 97)
        rr = 0.065 + 0.11 * _hash(ix, iy, 103)
        dist = np.hypot(u - ix - cx, v - iy - cy)
        a = np.clip((rr - dist) * s + 0.5, 0, 1)
    elif kind == "brick":
        row = np.floor(v)
        dx = np.abs(((u + (row % 2)) / 2 + 0.5) % 1 - 0.5) * 2
        dy = np.abs((v + 0.5) % 1 - 0.5)
        a = np.clip((width - np.minimum(dx, dy)) * s + 0.5, 0, 1)
    elif kind == "scales":
        a = np.zeros(np.broadcast_shapes(x.shape, y.shape), dtype=np.float32)
        for offset in (0, -1):
            row = np.floor(v / 0.55) + offset
            xx = (u + (row % 2) * 0.5 + 0.5) % 1 - 0.5
            yy = v - row * 0.55
            dist = np.abs(np.hypot(xx, yy) - 0.62)
            arc = np.clip((width - dist) * s + 0.5, 0, 1) * (yy >= 0) * (yy < 0.68)
            a = np.maximum(a, arc)
    else:
        fine = _hash(np.floor(x / max(0.7, s / 12)), np.floor(y / max(0.7, s / 12)), 19)
        mid = _texture(x, y, s * 0.30, 43)
        coarse = _texture(x, y, s, 67)
        if kind == "graphite":
            a = (0.2 + 0.7 * fine) * _sstep(fine, 0.10, 0.34) * (0.45 + 0.55 * mid)
        elif kind == "pastel":
            a = (0.4 + 0.6 * fine) * _sstep(mid, 0.16, 0.40) * _sstep(fine, 0.06, 0.28)
        elif kind == "wax":
            cracks = np.abs(np.sin(u * 13 + mid * 3))
            a = (0.65 + 0.35 * coarse) * _sstep(cracks, 0.08, 0.38) * _sstep(fine, 0.04, 0.22)
        elif kind == "dry_ink":
            streak = _hash(np.floor(x / max(1.0, s / 8)), np.floor(y / (s * 2)), 79)
            a = _sstep(streak, 0.18, 0.44) * _sstep(mid, 0.10, 0.34) * (0.6 + 0.4 * fine)
        elif kind == "sponge":
            a = np.clip((mid - 0.32) * 3.2, 0, 0.9) * (0.6 + 0.4 * coarse)
        elif kind == "salt":
            a = _sstep(fine, 0.62, 0.86) * (0.5 + 0.5 * mid) + 0.12 * _sstep(coarse, 0.52, 0.72)
        elif kind == "bloom":
            a = (0.15 + 0.55 * coarse + 0.30 * np.exp(-((mid - 0.42) / 0.085) ** 2)) * _sstep(mid, 0.12, 0.30)
        elif kind == "impasto":
            ridge = np.sin(u * math.tau * 3 + coarse * 2)
            a = 0.64 + 0.36 * np.clip(ridge, 0, 1)
        elif kind == "knife":
            a = (0.68 + 0.32 * np.cos((v + u * 0.3) * math.tau * 5)) * _sstep(fine, 0.03, 0.18)
        else:
            raise ValueError("未知纹理笔型: " + kind)
    return (np.clip(a, 0, 1) * 255).astype(np.uint8)


def apply_pattern(patch, rect, kind, scale):
    """分条生成 DestinationIn 遮罩，临时数组受 256 行预算约束。"""
    q = QPainter(patch)
    q.setCompositionMode(QPainter.CompositionMode_DestinationIn)
    for top in range(0, patch.height(), 256):
        h = min(256, patch.height() - top)
        y = np.arange(rect.top() + top, rect.top() + top + h, dtype=np.float32)[:, None]
        for left in range(0, patch.width(), 512):
            w = min(512, patch.width() - left)
            x = np.arange(rect.left() + left, rect.left() + left + w, dtype=np.float32)[None, :]
            # 斜线、砖缝、鱼鳞这类 1px 边缘图案做 2x2 子采样；
            # 颗粒/纹理类保持单采样，避免拖慢大笔触。
            samples = 2 if kind in ("hatch", "crosshatch", "brick", "scales", "stipple") else 1
            a = pattern_alpha(kind, x, y, scale, samples)
            buf = np.empty((h, w, 4), dtype=np.uint8)
            buf[:] = a[..., None]
            mask = QImage(buf.data, w, h, w * 4, FORMAT)
            q.drawImage(left, top, mask)
    q.end()
