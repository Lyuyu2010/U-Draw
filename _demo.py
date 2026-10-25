# -*- coding: utf-8 -*-
"""生成一张演示截图（画几笔 + 建立选区 + 多图层），用于展示界面"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtCore import QPointF, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

import theme
from main_window import MainWindow

app = QApplication(sys.argv)
theme.apply_theme(app)
win = MainWindow()
win.resize(1440, 900)
win.show()
app.processEvents()

c = win.canvas
c.fit()
c.simulate_pressure = False


def sp(x, y):
    return c.doc_to_screen(QPointF(x, y))


def stroke(points, pressures, color, size, hardness=0.7, flow=1.0):
    c.brush.size = size
    c.brush.hardness = hardness
    c.brush.flow = flow
    c.color = QColor(color)
    c.pointer_down(sp(*points[0][0:2]) if isinstance(points[0], tuple) else sp(*points[0]),
                   pressures[0])
    for p, pr in zip(points[1:], pressures[1:]):
        c.pointer_move(sp(*p), pr)
    c.pointer_up()


def arc(x0, y0, w, amp, color, size, hard=0.7, flow=1.0, n=110):
    pts = []
    press = []
    for i in range(n):
        t = i / (n - 1)
        pts.append((x0 + t * w, y0 + math.sin(t * 3.4) * amp))
        press.append(0.12 + 0.88 * math.sin(t * 3.14) ** 0.7)
    stroke(pts, press, color, size, hard, flow)


# 图1：底色
win.layer_action(1)
arc(220, 420, 1480, 120, "#2F6FED", 70, 0.55, 1.0)
# 图2：暖色叠一层
win.layer_action(1)
arc(260, 560, 1420, 90, "#F2994A", 52, 0.35, 0.85)
# 图3：细节线
win.layer_action(1)
arc(300, 340, 1360, 60, "#1A1A1A", 9, 0.9, 1.0)
arc(320, 700, 1320, 40, "#111111", 5, 0.9, 1.0)

# 选区
win.rail.select("ellipse")
c.pointer_down(sp(760, 300), 1.0)
c.pointer_move(sp(1260, 700), 1.0)
c.pointer_up()

win.rail.select("brush")
c.brush.size = 24
c.brush.hardness = 0.8
win._on_color(QColor("#C2410C"))
c.pointer_down(sp(800, 640), 0.4)
for i in range(1, 40):
    t = i / 39
    c.pointer_move(sp(800 + t * 420, 640 - math.sin(t * 3.14) * 90), 0.35 + 0.6 * math.sin(t * 3.14))
c.pointer_up()

app.processEvents()
out = os.path.join(os.path.dirname(HERE), "_research", "demo.png")
win.grab().save(out)
print("saved", out)
