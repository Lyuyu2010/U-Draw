# -*- coding: utf-8 -*-
"""画笔参数体检：逐个 UI 滑杆改动 → 真实笔迹渲染 → 像素比对，确认参数真的生效。

跑法： python _param_audit.py
输出： 每行一个参数，打印 低值/高值 的墨量和两图差异；结尾汇总「没生效」的项。

几个测量上的坑（踩过）：
* 图层本身是透明的，必须在白底上合成后再量，否则「透明」会被算成墨。
* 色相 / 饱和度抖动对灰墨无效——灰的饱和度是 0，色相转了也看不出来，
  所以这两项换饱和的红色来测。
* 起笔渐细只影响起笔前一小段，要限定区域比对，否则被整张图稀释成 0.17。
* 流量抖动早期是「逐笔点随机 alpha」，间距 5% 时二十个笔点叠下来一律到顶，
  根本量不出差别；现在改成整笔蒙一张按文档坐标平铺的噪声（见 core._flow_tile），
  流量 100% 也照样能看出浓淡。
"""

import math
import os
import random
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from core import Brush, Document, Stroke
from panels import BrushPanel

W, H = 720, 300
INK = QColor(25, 25, 25)
RED = QColor(210, 70, 55)


def stroke_points(jitter=0.0, seed=7):
    """一条带压力变化的 S 形笔迹。jitter>0 时模拟手抖。"""
    rnd = random.Random(seed)
    pts = []
    n = 90
    for i in range(n):
        t = i / (n - 1)
        x = 70 + t * (W - 140)
        y = 150 + math.sin(t * math.pi * 1.6) * 62
        if jitter:
            x += rnd.uniform(-jitter, jitter)
            y += rnd.uniform(-jitter, jitter)
        # 压力：中间重两头轻
        p = 0.25 + 0.75 * math.sin(t * math.pi) ** 0.7
        pts.append((QPointF(x, y), p))
    return pts


def render(brush: Brush, jitter=0.0, seed=7, color=None) -> QImage:
    # 引擎里的随机数（笔点抖动、色相偏移）也一起吃种子，这样换 seed 就是
    # 换一支「同参数的新笔」，多跑几个 seed 才能公平地量出抖动类参数的效果。
    random.seed(1000 + seed * 7919)
    doc = Document(W, H, QColor(255, 255, 255, 255))
    doc.add_layer("audit")
    layer = doc.layer
    s = Stroke(doc, layer, brush, color or INK)
    pts = stroke_points(jitter, seed)
    s.begin(pts[0][0], pts[0][1])
    for pos, pr in pts[1:]:
        s.move(pos, pr)
    s.end()
    # 合成到白底：图层本身是透明的，直接量会把透明像素当成墨
    flat = QImage(W, H, QImage.Format.Format_RGB32)
    flat.fill(Qt.white)
    p = QPainter(flat)
    p.drawImage(0, 0, layer.image)
    p.end()
    return flat


def ink(img: QImage, box=None) -> float:
    """墨量：所有像素「离白色有多远」的和。"""
    x0, y0, x1, y1 = box or (0, 0, W, H)
    total = 0
    for y in range(y0, y1, 2):
        for x in range(x0, x1, 2):
            c = img.pixelColor(x, y)
            total += (255 - c.red()) + (255 - c.green()) + (255 - c.blue())
    return total / 1000.0


def diff(a: QImage, b: QImage, box=None) -> float:
    """平均像素差（0~255）。box=(x0,y0,x1,y1) 时只比这一块。

    只统计「有墨的像素」（任一图明显不是白的地方）。笔迹只占画面几个百分点，
    拿整张图取平均会把颗粒、起笔渐细这类局部细节稀释掉一个数量级。
    """
    x0, y0, x1, y1 = box or (0, 0, W, H)
    tot = 0
    n = 0
    for y in range(y0, y1, 2):
        for x in range(x0, x1, 2):
            ca, cb = a.pixelColor(x, y), b.pixelColor(x, y)
            white_a = (255 - ca.red()) + (255 - ca.green()) + (255 - ca.blue())
            white_b = (255 - cb.red()) + (255 - cb.green()) + (255 - cb.blue())
            if white_a < 9 and white_b < 9:
                continue
            d = abs(ca.red() - cb.red()) + abs(ca.green() - cb.green()) + abs(ca.blue() - cb.blue())
            tot += d
            n += 1
    return tot / max(1, n) / 3.0


def main():
    app = QApplication.instance() or QApplication([])  # noqa: F841
    brush = Brush()
    brush.kind = "round"
    brush.name = "audit"
    panel = BrushPanel(brush)

    def set_slider(key, value, apply_now=True):
        w = panel.sliders.get(key)
        if w is None:
            raise KeyError(key)
        w.set_value(value)
        if apply_now:
            panel._apply()

    def set_check(on):
        panel.cb_psize.setChecked(on)
        panel._apply()

    def snapshot(color=None, seed=7):
        app.processEvents()
        return render(brush, seed=seed, color=color)

    # 抖动类参数是随机量，单次抽样可能刚好抽到接近 0 的值，要多跑几支笔取平均
    STOCHASTIC = {"size_jitter", "roundness_jitter", "angle_jitter", "scatter",
                  "scatter_count", "flow_jitter", "grain", "grain_scale",
                  "hue_jitter", "sat_jitter", "val_jitter", "stabilize"}
    SEEDS = (11, 29, 47, 71)

    # 前置参数（需要先满足才有意义的项）；box 限定比对区域
    CASES = [
        # key,            低值, 高值, 前置,                压感, 手抖, 墨色, 区域
        ("size",            10,   56, {},                     True,  0, None, None),
        ("roundness",      100,   35, {},                     True,  0, None, None),
        ("angle",            0,   70, {"roundness": 40},      True,  0, None, None),
        ("hardness",       100,    0, {},                     True,  0, None, None),
        ("spacing",          5,  120, {},                     True,  0, None, None),
        ("size_jitter",      0,   70, {},                     True,  0, None, None),
        ("roundness_jitter", 0,   70, {"roundness": 55},      True,  0, None, None),
        ("angle_jitter",     0,   90, {"roundness": 40},      True,  0, None, None),
        ("scatter",          0,   80, {},                     True,  0, None, None),
        ("scatter_count",    1,    6, {"scatter": 30},        True,  0, None, None),
        ("opacity",        100,   35, {},                     True,  0, None, None),
        ("flow",           100,   25, {},                     True,  0, None, None),
        ("flow_jitter",      0,   80, {},                     True,  0, None, None),
        ("grain",            0,   80, {"spacing": 75},        True,  0, None, None),
        ("grain_scale",      2,    8, {"grain": 80, "spacing": 75},
                                                              True,  0, None, None),
        ("wet",              0,   85, {},                     True,  0, None, None),
        ("hue_jitter",       0,   80, {},                     True,  0, RED,  None),
        ("sat_jitter",       0,   80, {},                     True,  0, RED,  None),
        ("val_jitter",       0,   80, {},                     True,  0, None, None),
        ("taper",            0,   70, {},                    False,  0, None, (60, 60, 170, 240)),
        ("min_size",        10,   90, {},                     True,  0, None, None),
        ("stabilize",        0,   70, {},                     True,  6, None, None),
    ]

    print(f"{'参数':<18}{'低值':>6}{'高值':>6}{'墨量(低)':>11}{'墨量(高)':>11}{'差异':>8}  判定")
    print("-" * 80)
    bad = []
    for key, lo, hi, pre, pressure_on, jitter, color, box in CASES:
        # 复位到一组中性参数，避免上一项影响
        set_slider("size", 26)
        set_slider("opacity", 100)
        set_slider("flow", 100)
        set_slider("hardness", 85)
        set_slider("spacing", 8)
        set_slider("roundness", 100)
        set_slider("angle", 0)
        set_slider("min_size", 15)
        set_slider("stabilize", 15)
        for k in ("size_jitter", "roundness_jitter", "angle_jitter", "scatter",
                  "flow_jitter", "grain", "wet", "hue_jitter", "sat_jitter",
                  "val_jitter", "taper"):
            set_slider(k, 0)
        set_slider("scatter_count", 1)
        set_slider("grain_scale", 2)
        for k, v in pre.items():
            set_slider(k, v)
        set_check(pressure_on)

        seeds = SEEDS if key in STOCHASTIC else (7,)
        set_slider(key, lo)
        a = [snapshot(color, sd) for sd in seeds]
        set_slider(key, hi)
        b = [snapshot(color, sd) for sd in seeds]
        ia = sum(ink(i, box) for i in a) / len(a)
        ib = sum(ink(i, box) for i in b) / len(b)
        d = sum(diff(x, y, box) for x, y in zip(a, b)) / len(b)
        # 判定：差异 ≥ 1.0（约 0.4% 满量程）就算肉眼可辨
        ok = d >= 3.0
        if not ok:
            bad.append((key, d, ia, ib))
        print(f"{key:<18}{lo:>6}{hi:>6}{ia:>11.1f}{ib:>11.1f}{d:>8.2f}"
              f"  {'OK' if ok else '⚠ 无反应'}")

    # 压感开关单独测（关 vs 开）
    set_slider("size", 26)
    set_slider("min_size", 15)
    set_check(False)
    a = snapshot()
    set_check(True)
    b = snapshot()
    d = diff(a, b)
    print(f"{'压感开关':<18}{'关':>6}{'开':>6}{ink(a):>11.1f}{ink(b):>11.1f}{d:>8.2f}"
          f"  {'OK' if d >= 3.0 else '⚠ 无反应'}")
    if d < 3.0:
        bad.append(("pressure", d, ink(a), ink(b)))

    print("-" * 80)
    if bad:
        print("没生效：", [x[0] for x in bad])
    else:
        print("全部参数均生效 ✅")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
