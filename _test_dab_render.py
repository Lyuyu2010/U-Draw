# -*- coding: utf-8 -*-
"""验证：改缓存之后，笔尖渲染和原来逐像素一致（不能为了快把笔迹画歪）。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtGui import QColor, QImage, QPainter, QRadialGradient, QBrush, QPen
from PySide6.QtCore import QPointF, QRectF, Qt

import core

W, H = 400, 260


def old_paint_disc(p, cx, cy, rad, hard, color, edge=1.7):
    """改动之前的实现（原样抄一份做对照）。"""
    if rad <= 0.25:
        return
    hard = core._clamp(hard)
    g = QRadialGradient(QPointF(cx, cy), rad)
    c0 = QColor(color)
    c0.setAlpha(255)
    c1 = QColor(color)
    c1.setAlpha(0)
    if hard >= 0.97:
        g.setColorAt(0.0, c0)
        g.setColorAt(min(0.999, 1.0 - edge / max(1.0, rad)), c0)
        g.setColorAt(1.0, c1)
    else:
        inner = max(0.02, min(hard * 0.94, 1.0 - edge / max(1.0, rad)))
        g.setColorAt(0.0, c0)
        g.setColorAt(inner, c0)
        steps = 12
        for k in range(1, steps + 1):
            u = k / steps
            t = inner + (1.0 - inner) * u
            a = int(round(255 * (1.0 - u) ** 1.55))
            col = QColor(color)
            col.setAlpha(max(0, min(255, a)))
            g.setColorAt(min(0.999, t), col)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QRectF(cx - rad, cy - rad, rad * 2, rad * 2))


def render(fn, color, hard):
    img = QImage(W, H, QImage.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    y = 20.0
    for rad in (1.0, 2.0, 3.5, 6.0, 10.0, 18.0):
        p.save()
        p.setOpacity(0.72)
        fn(p, 40 + rad, y + rad, rad, hard, color)
        fn(p, 120 + rad, y + rad, rad * 0.77, hard, color)
        p.restore()
        y += rad * 2 + 6
    p.end()
    return img


def diff(a, b):
    worst = 0
    total = 0
    n = 0
    for y in range(0, H, 2):
        for x in range(0, W, 2):
            ca, cb = a.pixelColor(x, y), b.pixelColor(x, y)
            d = max(abs(ca.red() - cb.red()), abs(ca.green() - cb.green()),
                    abs(ca.blue() - cb.blue()), abs(ca.alpha() - cb.alpha()))
            worst = max(worst, d)
            total += d
            n += 1
    return worst, total / max(1, n)


ok = True
for hard in (1.0, 0.6, 0.25):
    for color in (QColor(20, 20, 20), QColor(220, 40, 40, 128)):
        a = render(old_paint_disc, color, hard)
        b = render(core._paint_disc, color, hard)
        worst, mean = diff(a, b)
        good = worst <= 2 and mean < 0.2
        ok = ok and good
        print(("  OK  " if good else " FAIL ") +
              "hard=%.2f color=%s  最大差 %d 平均差 %.3f" % (hard, color.name(), worst, mean))

print("\n结果:", "笔尖渲染与改动前一致" if ok else "有像素差异")
sys.exit(0 if ok else 1)
