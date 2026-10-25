# -*- coding: utf-8 -*-
"""彩色笔回归：彩虹 / 彩色抖动笔不能被「取最大浓度」混成发白。"""
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
NAMED = {b.name: b for b in brushes.DEFAULTS}


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("  OK  " if cond else " FAIL ") + name + ("  " + str(extra) if extra else ""))


def stroke_stats(name, size, color=QColor(120, 200, 240)):
    br = NAMED[name].copy()
    br.size = size
    doc = Document(900, 260, QColor(255, 255, 255, 255))
    st = Stroke(doc, doc.layers[0], br, color)
    st.begin(QPointF(60, 130), 0.9)
    for i in range(1, 40):
        st.move(QPointF(60 + i * 20, 130 + (i % 5) * 3), 0.9)
    st.end()
    doc.recompose()
    img = doc.composite
    washed = 0      # 「发白」的像素：又亮又没颜色
    inked = 0
    for y in range(60, 200):
        for x in range(80, 840):
            c = img.pixelColor(x, y)
            if c.red() > 250 and c.green() > 250 and c.blue() > 250:
                continue          # 纯白背景，不算
            inked += 1
            mx = max(c.red(), c.green(), c.blue())
            mn = min(c.red(), c.green(), c.blue())
            if mx > 200 and (mx - mn) < 30:
                washed += 1       # 亮且几乎无色 → 被混白了
    return washed, max(1, inked)


for nm, sz in (("连续彩虹", 26), ("连续彩虹", 111)):
    washed, inked = stroke_stats(nm, sz)
    ratio = 100.0 * washed / inked
    check("%s %dpx 没有被混成发白（发白像素 %.2f%%）" % (nm, sz, ratio), ratio < 1.0,
          "%d / %d" % (washed, inked))

# 带色相/明度抖动的笔不能走「取最大浓度」
fire = NAMED["火星笔"]
check("火星笔（带色相抖动）不走取最大浓度",
      not (fire.kind != "rainbow" and fire.hue_jitter < 0.001
           and fire.sat_jitter < 0.001 and fire.val_jitter < 0.001))

# 排齿笔仍然走「取最大浓度」（线条交叉处不变深）
br = NAMED["多线排齿笔"].copy()
br.size = 38
check("排齿笔仍然满足取最大浓度的条件",
      br.kind not in ("rainbow",) and br.hue_jitter < 0.001
      and br.sat_jitter < 0.001 and br.val_jitter < 0.001
      and br.flow >= 0.98 and br.opacity >= 0.98 and not br.build_up)

print("\n结果:", "全部通过" if ok else "有失败项")
sys.exit(0 if ok else 1)
