# -*- coding: utf-8 -*-
"""笔迹质感检查：不同硬度/压感曲线下的笔触，输出 PNG 供目视确认"""

import math
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from canvas import Canvas
from core import Brush, Document

app = QApplication(sys.argv)
doc = Document(1400, 900, QColor(255, 255, 255, 255))
c = Canvas(doc)
c.resize(1400, 900)
c.zoom = 1.0
c.ox = 0.0
c.oy = 0.0
c.set_tool("brush")

rows = [
    ("soft  hardness 0.15", dict(size=46, hardness=0.15, opacity=1.0, flow=0.35)),
    ("mid   hardness 0.65", dict(size=46, hardness=0.65, opacity=1.0, flow=1.0)),
    ("hard  hardness 0.98", dict(size=46, hardness=0.98, opacity=1.0, flow=1.0)),
    ("thin  size 6 px", dict(size=6, hardness=0.7, opacity=1.0, flow=1.0)),
    ("big   size 120 px", dict(size=120, hardness=0.5, opacity=0.9, flow=1.0)),
]

y = 90
for label, kw in rows:
    c.brush = Brush(**kw)
    c.color = QColor(25, 25, 25)
    pts = []
    press = []
    for i in range(90):
        t = i / 89.0
        x = 320 + t * 1000
        yy = y + math.sin(t * 6.28) * 26
        pts.append(QPointF(x, yy))
        press.append(0.08 + 0.92 * abs(math.sin(t * 3.14)))
    c.pointer_down(pts[0], press[0])
    for p, pr in zip(pts[1:], press[1:]):
        c.pointer_move(p, pr)
    c.pointer_up()
    y += 165

out = os.path.join(os.path.dirname(HERE), "_research", "strokes.png")
doc.flatten().save(out, "PNG")
print("saved", out, os.path.getsize(out))
