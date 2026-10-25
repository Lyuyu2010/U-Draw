# -*- coding: utf-8 -*-
"""内置笔刷库体检：数量 / 分类 / 每支笔都能出墨 / 渲染全库样张

跑法：python _brushlib_audit.py
产出：_brushlib_sheet.png（按分类排版的全部笔刷样张）
"""

import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter
from PySide6.QtWidgets import QApplication

from core import Brush, Document, Stroke, KINDS, preview_image
import brushes as BL

FAIL = []


def ck(name, cond, extra=""):
    print(("[ OK ]" if cond else "[FAIL]"), name, extra)
    if not cond:
        FAIL.append(name)


def stroke_ink(brush: Brush, w=260, h=70) -> float:
    """用真引擎画一条横线，返回墨量（0 = 完全画不出来）。"""
    d = Document(w, h, QColor(255, 255, 255, 255))
    lay = d.add_layer("t")
    b = brush.copy()
    b.size = min(b.size, h * 0.6)
    b.taper = 0.0
    b.stabilize = 0.0
    s = Stroke(d, lay, b, QColor("#111111"))
    s.begin(QPointF(14, h / 2.0), 1.0)
    for x in range(18, w - 10, 3):
        s.move(QPointF(x, h / 2.0), 1.0)
    s.end()
    img = lay.image
    tot = 0
    for y in range(h):
        for x in range(w):
            tot += (img.pixel(x, y) >> 24) & 0xFF
    return tot / 255.0


def font() -> QFont:
    fams = QFontDatabase.families()
    for cand in ("微软雅黑", "Microsoft YaHei", "SimHei", "SimSun",
                 "BIZ UDPGothic", "BIZ UDGothic"):
        if cand in fams:
            f = QFont(cand)
            f.setPixelSize(12)
            return f
    f = QFont()
    f.setPixelSize(12)
    return f


def _load_fonts():
    """offscreen 下系统字体表是空的，把中文字体注册进来才画得出中文。"""
    cands = ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf",
             "C:/Windows/Fonts/simsun.ttc"]
    for path in cands:
        if os.path.isfile(path):
            QFontDatabase.addApplicationFont(path)
    import fonts
    d = fonts.asset_dir()
    for fname, _label, _note in fonts.BUNDLED_FILES:
        path = os.path.join(d, fname)
        if os.path.isfile(path):
            QFontDatabase.addApplicationFont(path)


def sheet(path: str):
    cell_w, cell_h = 252, 78
    cols = 6
    groups = [g for g in BL.GROUPS
              if any(b.group == g for b in BL.DEFAULTS)]
    rows = 0
    for g in groups:
        n = sum(1 for b in BL.DEFAULTS if b.group == g)
        rows += 22 + ((n + cols - 1) // cols) * cell_h + 6
    W = cols * cell_w + 40
    H = rows + 60
    img = QImage(W, H, QImage.Format_ARGB32)
    img.fill(QColor("#f6f4ef"))
    p = QPainter(img)
    f = font()
    f.setPixelSize(20)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#1a1a1a"))
    p.drawText(QRectF(20, 12, W - 40, 28), Qt.AlignLeft,
               f"U Draw 内置笔刷 {len(BL.DEFAULTS)} 支 · 共 {len(groups)} 个分类")
    y = 50
    for g in groups:
        items = [b for b in BL.DEFAULTS if b.group == g]
        f2 = font()
        f2.setPixelSize(13)
        f2.setBold(True)
        p.setFont(f2)
        p.setPen(QColor("#8a5a2b"))
        p.drawText(QRectF(20, y + 4, W - 40, 18), Qt.AlignLeft, f"{g}（{len(items)}）")
        y += 22
        for i, b in enumerate(items):
            cx = 20 + (i % cols) * cell_w
            cy = y + (i // cols) * cell_h
            p.setPen(QColor("#d8d3c8"))
            p.setBrush(QColor("#ffffff"))
            p.drawRoundedRect(QRectF(cx, cy, cell_w - 10, cell_h - 10), 4, 4)
            f3 = font()
            f3.setPixelSize(11)
            p.setFont(f3)
            p.setPen(QColor("#444444"))
            p.drawText(QRectF(cx + 8, cy + 4, cell_w - 26, 15), Qt.AlignLeft,
                       f"{b.name}  ·  {b.kind}  {int(round(b.size))}px")
            im = preview_image(b, cell_w - 26, cell_h - 34, QColor("#141414"), ss=2)
            p.drawImage(QRectF(cx + 8, cy + 22, cell_w - 26, cell_h - 34), im)
        y += ((len(items) + cols - 1) // cols) * cell_h + 6
    p.end()
    img.save(path)
    return img


def main():
    QApplication.instance() or QApplication(sys.argv)
    _load_fonts()
    print(f"[1] 数量：{len(BL.DEFAULTS)} 支 / {len(BL.GROUPS)} 个分类")
    ck("笔刷数量 ≥ 80", len(BL.DEFAULTS) >= 80)
    ck("分类都在 GROUPS 里",
       all(b.group in BL.GROUPS for b in BL.DEFAULTS))
    ck("笔型都合法", all(b.kind in KINDS for b in BL.DEFAULTS),
       f"{len(set(b.kind for b in BL.DEFAULTS))} 种笔型")
    names = [b.name for b in BL.DEFAULTS]
    ck("没有重名", len(set(names)) == len(names))

    print("[2] 每支笔都要画得出来")
    dead = []
    slow = []
    for b in BL.DEFAULTS:
        t0 = time.time()
        ink = stroke_ink(b)
        dt = (time.time() - t0) * 1000
        if ink < 3.0:
            dead.append((b.name, round(ink, 2)))
        if dt > 400:
            slow.append((b.name, round(dt)))
    ck("全部有笔迹", not dead, str(dead))
    ck("单笔渲染 < 400ms", not slow, str(slow))

    print("[3] 参数不能撞车（撞车说明只是换了个名字）")
    seen = {}
    dup = []
    for b in BL.DEFAULTS:
        sig = tuple(round(float(getattr(b, f)), 4) for f in Brush.FLOATS) + (b.kind,)
        if sig in seen:
            dup.append((seen[sig], b.name))
        seen[sig] = b.name
    ck("没有重复参数的笔", not dup, str(dup))

    print("[4] 新笔型确实长得不一样")
    base = None
    diffs = []
    for k in ("bristle", "noise", "cloud", "splatter", "star", "sparkle",
              "bubble", "ring", "block", "grass"):
        b = Brush()
        b.kind = k
        b.size = 26
        b.spacing = 0.10
        ink = stroke_ink(b)
        if base is None:
            base = ink
        diffs.append(ink)
    ck("新笔型墨量各不相同", len(set(round(v, 1) for v in diffs)) >= 8,
       str([round(v, 1) for v in diffs]))

    out = os.path.join(HERE, "_brushlib_sheet.png")
    im = sheet(out)
    print(f"[5] 样张：{out}  {im.width()}×{im.height()}")

    print()
    if FAIL:
        print("不通过（%d 项）：%s" % (len(FAIL), "、".join(FAIL)))
        return 1
    print("笔刷库自检全部通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
