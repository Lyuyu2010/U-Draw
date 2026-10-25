# -*- coding: utf-8 -*-
"""画笔参数体检 2.0：逐项验证「调了到底有没有该有的效果」。

和旧版 _param_audit 的区别：这里每一项都用**针对该参数语义**的指标
（比如颗粒看 alpha 起伏、湿边看边缘比中间深多少、间距看断点数量），
而不是只看「像素数变没变」。

跑法：python _brush_audit.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from core import Brush, Document, Stroke

W, H = 220, 140


def render(**kw):
    """在画布上画一条横线，返回图层和文档。"""
    d = Document(W, H, QColor(255, 255, 255, 255))
    lay = d.add_layer("t")
    b = Brush()
    b.size = 24
    b.hardness = 0.9
    b.spacing = 0.1
    for k, v in kw.items():
        setattr(b, k, v)
    s = Stroke(d, lay, b, QColor("#000000"))
    s.begin(QPointF(30, H / 2), 1.0)
    for x in range(34, 190, 3):
        s.move(QPointF(x, H / 2), kw.get("_pressure", 1.0))
    s.end()
    return lay.image


def alphas(img, x0=40, x1=180, y0=None, y1=None):
    y0 = 0 if y0 is None else y0
    y1 = img.height() if y1 is None else y1
    out = []
    for y in range(y0, y1):
        for x in range(x0, x1):
            out.append((img.pixel(x, y) >> 24) & 0xFF)
    return out


def stats(img):
    a = alphas(img)
    n = len(a)
    solid = sum(1 for v in a if v > 200)
    soft = sum(1 for v in a if 20 < v <= 200)
    mean = sum(a) / n
    var = (sum((v - mean) ** 2 for v in a) / n) ** 0.5
    ys = [y for y in range(img.height()) for x in range(40, 180)
          if ((img.pixel(x, y) >> 24) & 0xFF) > 20]
    spread = (max(ys) - min(ys) + 1) if ys else 0
    return {"solid": solid, "soft": soft, "mean": mean, "var": var,
            "spread": spread}


def gaps(img):
    """沿中线数「有墨 / 没墨」的切换次数。"""
    y = img.height() // 2
    row = [((img.pixel(x, y) >> 24) & 0xFF) > 20 for x in range(20, 200)]
    return sum(1 for i in range(1, len(row)) if row[i] != row[i - 1])


def edge_vs_center(img):
    """湿边：笔画「边沿内侧」比中间深多少（0~1，正数=边缘更深）。"""
    y0 = img.height() // 2
    xs = [x for x in range(20, 200) if ((img.pixel(x, y0) >> 24) & 0xFF) > 20]
    if not xs:
        return 0.0
    col = xs[len(xs) // 2]
    col_a = [((img.pixel(col, y) >> 24) & 0xFF) for y in range(img.height())]
    ys = [y for y, v in enumerate(col_a) if v > 20]
    if len(ys) < 8:
        return 0.0
    top, bot = ys[0], ys[-1]
    mid = (top + bot) // 2
    # 边沿内侧 2px（跳过抗锯齿的那一圈）
    edge = max(col_a[min(top + 2, mid - 1)], col_a[max(bot - 2, mid + 1)])
    return (edge - col_a[mid]) / 255.0


def center_var(img):
    """只沿笔画中线取 alpha 的起伏（排除边缘，才能看出颗粒 / 流量抖动）。"""
    y = img.height() // 2
    vals = [((img.pixel(x, y) >> 24) & 0xFF) for x in range(40, 180)]
    m = sum(vals) / len(vals)
    return (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5


def ink(img):
    return sum((img.pixel(x, y) >> 24) & 0xFF
               for y in range(img.height()) for x in range(40, 180)) / 255.0


def width_at(img, x):
    ys = [y for y in range(img.height()) if ((img.pixel(x, y) >> 24) & 0xFF) > 20]
    return (max(ys) - min(ys) + 1) if ys else 0


FAIL = []


def ck(name, base, got, kind="differ", note=""):
    """kind: differ=必须不同；up=必须更大；down=必须更小"""
    ok = {"differ": abs(got - base) > 1e-6,
          "up": got > base * 1.05 + 0.02,
          "down": got < base * 0.95 - 0.02}[kind]
    print(("  OK   " if ok else "  FAIL ") + f"{name}: {base:.3f} → {got:.3f} {note}")
    if not ok:
        FAIL.append(name)


def main():
    QApplication.instance() or QApplication(sys.argv)
    base = stats(render())

    print("[1] 大小 / 硬度 / 不透明度 / 流量")
    ck("大小", base["spread"], stats(render(size=40))["spread"], "up")
    ck("硬度", base["soft"], stats(render(hardness=0.0))["soft"], "up")
    ck("不透明度", base["mean"], stats(render(opacity=0.4))["mean"], "down")
    ck("流量", base["mean"], stats(render(flow=0.25))["mean"], "down")

    print("[2] 间距 / 散布 / 散布数量")
    g0 = gaps(render())
    ck("间距 300%", g0, gaps(render(spacing=3.0)), "up", "断点变多")
    ck("散布", base["spread"], stats(render(scatter=0.8))["spread"], "up")
    d1 = stats(render(scatter=0.6))
    d3 = stats(render(scatter=0.6, scatter_count=4))
    ck("散布数量", d1["mean"], d3["mean"], "differ", "墨量变化")

    print("[3] 圆度 / 角度")
    ck("圆度", base["spread"], stats(render(roundness=0.3))["spread"], "down")
    b2 = stats(render(roundness=0.3))
    b3 = stats(render(roundness=0.3, angle=90))
    ck("角度", b2["spread"], b3["spread"], "up", "90° 后变宽")

    print("[4] 颗粒 / 颗粒粗细 / 湿边")
    ck("颗粒", center_var(render()), center_var(render(grain=0.85)), "up", "中线 alpha 起伏")
    g1 = center_var(render(grain=0.85, grain_scale=1.5))
    g6 = center_var(render(grain=0.85, grain_scale=6))
    ck("颗粒粗细", g1, g6, "differ", "颗粒尺度变了")
    # 湿边要配半透明的笔身才看得出来（alpha 已经到顶时没地方再深）
    ck("湿边", edge_vs_center(render(flow=0.55)),
       edge_vs_center(render(flow=0.55, wet=0.9)), "up", "边缘更深")

    print("[5] 抖动")
    ck("大小抖动", ink(render()), ink(render(size_jitter=0.8)), "down", "笔尖忽大忽小，总墨量降")
    ck("流量抖动", center_var(render()), center_var(render(flow_jitter=0.9)), "up")
    ck("角度抖动", stats(render(roundness=0.3))["spread"],
       stats(render(roundness=0.3, angle_jitter=1.0))["spread"], "up")
    ck("圆度抖动", stats(render(roundness=0.6))["spread"],
       stats(render(roundness=0.6, roundness_jitter=0.9))["spread"], "differ")

    print("[6] 笔锋 / 压感")
    taper = render(taper=1.0)
    ck("起笔渐细", width_at(taper, 190), width_at(taper, 31), "down", "起笔比中段细")
    low = render(min_size=0.2, pressure_size=True, _pressure=0.2)
    full = render(pressure_size=False, _pressure=1.0)
    ck("最小直径+压感", width_at(full, 120), width_at(low, 120), "down", "轻压更细")
    ck("压感关闭时等粗", width_at(full, 120), width_at(low, 120), "differ")

    print()
    if FAIL:
        print("有问题的参数（%d 项）：" % len(FAIL))
        for m in FAIL:
            print("  -", m)
        return 1
    print("全部参数都有效果 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
