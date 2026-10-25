# -*- coding: utf-8 -*-
"""验证：印章类笔刷起笔处不再「两个粘在一起」（第一个 move 里不该有重合笔点）。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor
from PySide6.QtCore import QPointF

app = QApplication([])
import brushes
from core import Document, Stroke

ok = True
NAMES = ("星星印章", "心形印章", "六边形印章", "圆环笔", "六角雪晶", "气泡笔", "雪花笔")


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("  OK  " if cond else " FAIL ") + name + ("  " + str(extra) if extra else ""))


def dab_positions(brush, moves):
    """画一小段，记录所有笔点位置。"""
    doc = Document(300, 200, QColor(255, 255, 255, 255))
    layer = doc.layers[0]
    st = Stroke(doc, layer, brush, QColor(200, 30, 30))
    pts = []
    orig = st._dab

    def spy(p, pos, pressure):
        pts.append((round(pos.x(), 2), round(pos.y(), 2)))
        return orig(p, pos, pressure)

    st._dab = spy
    st.begin(QPointF(60, 100), 0.9)
    for dx in moves:
        st.move(QPointF(60 + dx, 100), 0.9)
    st.end()
    return pts


found = [b for b in brushes.DEFAULTS if b.name in NAMES]
print("参与测试的印章笔刷:", [b.name for b in found])

for b in found:
    br = b.copy()
    br.size = 44
    pts = dab_positions(br, [5, 10, 16, 22, 30, 40])
    # 起笔点附近（前 2px 内）有几个笔点
    near = [p for p in pts if (p[0] - 60) ** 2 + (p[1] - 100) ** 2 < 6.0]
    check("%s 起笔处只有 1 颗笔点" % b.name, len(near) <= 1,
          "起笔附近 %d 颗，全部笔点 %d 颗" % (len(near), len(pts)))

print("\n结果:", "全部通过" if ok else "有失败项")
sys.exit(0 if ok else 1)
