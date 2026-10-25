# -*- coding: utf-8 -*-
"""v2.1 新功能自测：对称 / 涂抹 / 文字 / 油漆桶消白边

不打开主窗口，直接把结果画进 QImage 存成 PNG，肉眼可查。
用法：  python _v21_test.py  [输出目录]
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "_v21_out")

from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication

import fonts as fontlib
import text_tool
from core import (Brush, Document, SmudgeStroke, Stroke, flood_fill,
                  new_symmetry)


def save(img, name, scale=1):
    os.makedirs(OUT, exist_ok=True)
    if scale != 1:
        img = img.scaled(img.width() * scale, img.height() * scale,
                         Qt.IgnoreAspectRatio, Qt.FastTransformation)
    p = os.path.join(OUT, name)
    img.save(p)
    print("  ->", p, img.width(), "x", img.height())
    return p


def t_fill():
    """在白底上画一个闭合形状，再用油漆桶填充 —— 看边缘还有没有白边。"""
    doc = Document(320, 320, QColor(255, 255, 255, 255))
    layer = doc.layer
    b = Brush(size=14, hardness=0.9, spacing=0.05, stabilize=0.5,
              pressure_size=False)
    st = Stroke(doc, layer, b, QColor(0, 0, 0))
    pts = []
    import math
    for i in range(160):
        a = math.tau * i / 160
        r = 100 + 22 * math.sin(3 * a)
        pts.append(QPointF(160 + math.cos(a) * r, 160 + math.sin(a) * r))
    st.begin(pts[0], 1.0)
    for p in pts[1:]:
        st.move(p, 1.0)
    st.end()
    edit = flood_fill(doc, 160, 160, QColor(210, 60, 40), 32)
    doc.recompose()
    print("  fill:", bool(edit), edit.rect if edit else None)
    save(doc.composite, "1_fill.png", 2)
    crop = doc.composite.copy(QRect(30, 40, 90, 90))
    save(crop, "1_fill_zoom.png", 6)


def t_symmetry():
    """径向 8 份对称画一圈花瓣。"""
    doc = Document(360, 360, QColor(255, 255, 255, 255))
    sym = new_symmetry(doc.w, doc.h)
    sym["mode"] = "radial"
    sym["count"] = 8
    b = Brush(size=10, hardness=0.75, spacing=0.04, stabilize=0.4,
              pressure_size=False)
    st = Stroke(doc, doc.layer, b, QColor(30, 90, 200), sym=sym)
    import math
    st.begin(QPointF(180, 180), 1.0)
    for i in range(80):
        t = i / 79.0
        a = math.pi * 0.9 * t
        r = 20 + 120 * t
        st.move(QPointF(180 + math.cos(a - 1.2) * r,
                        180 + math.sin(a - 1.2) * r), 1.0)
    st.end()
    doc.recompose()
    save(doc.composite, "2_symmetry.png")


def t_smudge():
    """画一块色带，再从中间涂抹到空白处。"""
    doc = Document(400, 200, QColor(255, 255, 255, 255))
    img = doc.layer.image
    p = QPainter(img)
    for i, c in enumerate((QColor(230, 60, 60), QColor(240, 180, 40),
                           QColor(60, 160, 90), QColor(60, 90, 220))):
        p.fillRect(QRect(40 + i * 40, 60, 40, 80), c)
    p.end()
    doc.recompose()
    b = Brush(size=40, hardness=0.6, spacing=0.05, pressure_size=False)
    sm = SmudgeStroke(doc, doc.layer, b, 0.6, None)
    sm.begin(QPointF(200, 100), 1.0)
    for i in range(60):
        t = i / 59.0
        sm.move(QPointF(200 + 170 * t, 100 + 50 * t), 1.0)
    edit = sm.end()
    print("  smudge:", bool(edit))
    doc.recompose()
    save(doc.composite, "3_smudge.png")


def t_text():
    """用内置字体写字，确认文字库真的注册上了。"""
    ents = fontlib.entries()
    print("  文字库:", len(ents), "个字体，内置",
          sum(1 for e in ents if e["bundled"]), "个")
    doc = Document(560, 320, QColor(250, 250, 248, 255))
    y = 20
    for e in [x for x in ents if x["bundled"]][:4]:
        text_tool.draw_text(doc.layer.image, e["label"].split("（")[0],
                            QPointF(24, y), e["family"], 30, False, False,
                            QColor(25, 25, 25), "left")
        text_tool.draw_text(doc.layer.image, "永和九年 U Draw 0123",
                            QPointF(24, y + 34), e["family"], 30, False, False,
                            QColor(25, 25, 25), "left")
        y += 76
    doc.recompose()
    save(doc.composite, "4_text.png")


def t_text_overlay():
    """画布上的就地编辑框能不能建出来、能不能落字。"""
    from PySide6.QtWidgets import QWidget
    import canvas as canvas_mod
    from PySide6.QtGui import QImage

    doc = Document(300, 200, QColor(255, 255, 255, 255))
    c = canvas_mod.Canvas(doc)
    c.resize(300, 200)
    c.set_tool("text")
    c.text_family = fontlib.default_family()
    c.text_size = 40
    c._begin_text(QPointF(60, 40))
    ov = c.text_overlay()
    print("  overlay:", ov is not None, ov.geometry() if ov else None)
    ov.setPlainText("Hello 文字")
    c.commit_text()
    print("  after commit:", c.text_overlay() is None,
          doc.layer.image.pixelColor(70, 60).alpha())
    save(doc.composite, "5_text_overlay.png")


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    print("PySide6 OK; 输出目录", OUT)
    for fn in (t_fill, t_symmetry, t_smudge, t_text, t_text_overlay):
        print(fn.__name__)
        try:
            fn()
        except Exception:
            import traceback
            traceback.print_exc()
    print("done")


if __name__ == "__main__":
    main()
