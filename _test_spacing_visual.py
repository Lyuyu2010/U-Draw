# -*- coding: utf-8 -*-
"""验证：硬笔的笔点间距从 0.4px 放宽到 0.9px 之后，笔迹有没有肉眼可见的差别。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtCore import QPointF

import core
from core import Brush, Document, Stroke
import brushes

_OLD_SPACING = Brush.stamp_spacing


def old_spacing(self, pressure):
    """改动之前：一律 max(0.4, s * diameter)。"""
    s = self.spacing
    if self.kind in core.STAMP_KINDS:
        s *= 2.0 ** ((0.5 - core._clamp(self.density)) * 2.0)
    return max(0.4, s * self.diameter(pressure))


def draw(brush, path, spacing_fn):
    Brush.stamp_spacing = spacing_fn
    doc = Document(420, 160, QColor(255, 255, 255, 255))
    layer = doc.layers[0]
    st = Stroke(doc, layer, brush, QColor(25, 25, 25))
    st.begin(QPointF(*path[0]), 0.9)
    for x, y in path[1:]:
        st.move(QPointF(x, y), 0.9)
    st.end()
    Brush.stamp_spacing = _OLD_SPACING
    return doc.composite


def diff(a, b, w, h):
    worst = 0
    total = 0
    for y in range(h):
        for x in range(w):
            ca, cb = a.pixelColor(x, y), b.pixelColor(x, y)
            d = max(abs(ca.red() - cb.red()), abs(ca.green() - cb.green()),
                    abs(ca.blue() - cb.blue()))
            worst = max(worst, d)
            total += d
    return worst, total / (w * h)


NAMED = {b.name: b for b in brushes.DEFAULTS}
# 一条快笔：横向拉长 + 轻微起伏（模拟快速运笔）
path = [(20 + i * 12, 70 + (i % 4) * 3) for i in range(31)]

ok = True
for name in ("G 笔", "针管笔", "中性笔", "圆珠笔", "钢笔"):
    for size in (4, 8, 24):
        br = NAMED[name].copy()
        br.size = size
        a = draw(br, path, _OLD_SPACING)
        b = draw(br, path, Brush.stamp_spacing)
        worst, mean = diff(a, b, 420, 160)
        # 硬笔是实心圆叠加，间距放宽后重叠率仍有 85%+，差异应该极小
        good = worst <= 12 and mean < 1.2
        ok = ok and good
        print(("  OK  " if good else " FAIL ") +
              "%-6s %2dpx  最大差 %3d 平均差 %.2f" % (name, size, worst, mean))

print("\n结果:", "笔迹看不出差别" if ok else "有可见差异，需要调回")
sys.exit(0 if ok else 1)
