# -*- coding: utf-8 -*-
"""选区移动回归：蚂蚁线跟随偏移 + 局部重绘（拖动不整屏合成）。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtCore import QRectF, Qt

app = QApplication([])
import theme

theme.apply_theme(app)

import numpy as np
from core import Document, MoveOp, _qimage_to_np

ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("  OK  " if cond else " FAIL ") + name + ("  " + str(extra) if extra else ""))


def build():
    d = Document(400, 300)
    l = d.add_layer(name="c", above=True, select=True)
    l.image.fill(Qt.transparent)
    p = QPainter(l.image)
    p.fillRect(100, 100, 60, 60, QColor(220, 40, 40))
    p.end()
    d.recompose()
    sel = QPainterPath()
    sel.addRect(QRectF(100, 100, 60, 60))
    d.set_selection(sel, record=False)
    return d, l


doc, layer = build()
op = MoveOp(doc, layer)
op.render(0, 0)
op.render(20, 20)
d3 = op.render(40, 10)

check("脏矩形比整画布小", d3.width() < doc.w or d3.height() < doc.h, (d3.width(), d3.height()))
check("当前偏移记录正确（给蚂蚁线用）",
      abs(op.off[0] - 40) < 0.01 and abs(op.off[1] - 10) < 0.01, op.off)
check("新位置有像素", QColor(layer.image.pixelColor(100 + 40 + 30, 100 + 10 + 30)).alpha() > 200)
check("旧位置已清空", QColor(layer.image.pixelColor(130, 130)).alpha() == 0,
      QColor(layer.image.pixelColor(130, 130)).alpha())

# 局部重绘累积结果应与「一次整层重绘到同一位置」完全一致
doc2, layer2 = build()
op2 = MoveOp(doc2, layer2)
op2.render(40, 10, full=True)
a1 = _qimage_to_np(layer.image, np)
a2 = _qimage_to_np(layer2.image, np)
check("局部重绘结果 == 整层重绘", a1.shape == a2.shape and bool(np.array_equal(a1, a2)))

# 松手后选区真正跟着走
doc3, layer3 = build()
op3 = MoveOp(doc3, layer3)
op3.render(25, 0)
op3.finish(25, 0)
check("松手后选区平移到位", abs(doc3.selection.boundingRect().left() - 125) < 1,
      doc3.selection.boundingRect().left())

print("\n结果:", "全部通过" if ok else "有失败项")
sys.exit(0 if ok else 1)
