# -*- coding: utf-8 -*-
"""内部自测：图层数量 / 压感笔迹 / 选区限制 / 撤销 / 填充 / 缩放 / 存取"""

import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

import theme
import main_window as mw
from core import load_project, save_project

app = QApplication(sys.argv)
theme.apply_theme(app)
w = mw.MainWindow()
w.resize(1200, 800)
w.show()
app.processEvents()

c = w.canvas
c.fit()
doc = w.doc
# 自检要可复现：固定用「硬圆笔」，别被「记住上次用的笔」影响
from brushes import DEFAULTS as _DEF
c.brush.apply_from(next(b for b in _DEF if b.name == "硬圆笔"))
ok = []


def check(name, cond, extra=""):
    ok.append(bool(cond))
    print(("[ OK ]" if cond else "[FAIL]"), name, extra)


def sp(x, y):
    return c.doc_to_screen(QPointF(x, y))


def stroke(points, pressures):
    c.pointer_down(sp(*points[0]), pressures[0])
    for p, pr in zip(points[1:], pressures[1:]):
        c.pointer_move(sp(*p), pr)
    c.pointer_up()


# 1. 图层：再建 60 个，确认远超 50
for _ in range(60):
    w.layer_action(1)
check("图层数量 ≥ 50", len(doc.layers) >= 51, f"{len(doc.layers)} 层")

# 2. 压感笔迹（粗细随压力变化）
w.layer_action(1)
c.set_tool("brush")
c.brush.size = 40
c.color = QColor(20, 20, 20)
t0 = time.time()
pts = [(300 + i * 10, 700 + (i % 9) * 8) for i in range(45)]
stroke(pts, [0.15 + 0.85 * i / 44 for i in range(45)])
dt = time.time() - t0
check("笔迹已绘制", doc.composite.pixelColor(310, 705).alpha() > 0)
check("绘制耗时", dt < 1.5, f"{dt*1000:.0f} ms / 45 个采样")

# 压力越大线越粗
thin = 0
thick = 0
for y in range(690, 740):
    if doc.composite.pixelColor(302, y).alpha() > 40:
        thin += 1
for y in range(700, 760):
    if doc.composite.pixelColor(720, y).alpha() > 40:
        thick += 1
check("压感影响粗细", thick > thin, f"细端 {thin}px / 粗端 {thick}px")

# 3. 选区限制
doc.clear_selection()
c.set_tool("marquee")
c.pointer_down(sp(900, 300), 1.0)
c.pointer_move(sp(1300, 600), 1.0)
c.pointer_up()
check("选区已建立", doc.has_selection())
before_out = doc.composite.pixelColor(850, 400).name()
before_in = doc.composite.pixelColor(1000, 400).name()
c.set_tool("brush")
c.brush.size = 80
stroke([(950, 350), (1250, 550)], [1.0, 1.0])
check("选区内被画到", doc.composite.pixelColor(1000, 400).name() != before_in)
check("选区外未受影响", doc.composite.pixelColor(850, 400).name() == before_out)

# 4. 撤销 / 重做
n = len(doc.undo_stack)
w.undo()
check("撤销堆栈减少", len(doc.undo_stack) == n - 1 and len(doc.redo_stack) == 1)
check("撤销后内容恢复", doc.composite.pixelColor(1000, 400).name() == before_in)
w.redo()
check("重做恢复笔迹", doc.composite.pixelColor(1000, 400).name() != before_in)

# 5. 图层结构撤销
cnt = len(doc.layers)
w.layer_action(2)
check("复制图层", len(doc.layers) == cnt + 1)
w.undo()
check("撤销复制图层", len(doc.layers) == cnt)

# 6. 油漆桶填充（在选区内）
doc.clear_selection()
w.layer_action(1)
c.set_tool("bucket")
c.color = QColor(220, 60, 60)
c.pointer_down(sp(1000, 900), 1.0)
c.pointer_up()
check("填充改变像素", doc.composite.pixelColor(1000, 900).red() > 180, doc.composite.pixelColor(1000, 900).name())

# 7. 缩放 / 移动画布
c.set_zoom(2.5)
p = QPointF(400, 300)
back = c.screen_to_doc(c.doc_to_screen(p))
check("缩放坐标往返", abs(back.x() - p.x()) < 1e-6 and abs(back.y() - p.y()) < 1e-6)
z0 = c.zoom
c.wheelEvent  # noqa
c.set_zoom(1.0)
check("缩放切换", abs(c.zoom - 1.0) < 1e-9, f"{z0:.2f} → {c.zoom:.2f}")

# 8. 工程保存 / 读取
tmp = os.path.join(HERE, "_test.pcdraw")
save_project(doc, tmp)
d2 = load_project(tmp)
check("保存并重载", len(d2.layers) == len(doc.layers) and d2.w == doc.w,
      f"{len(d2.layers)} 层 / {d2.w}×{d2.h}")
check("重载像素一致", d2.composite.pixelColor(1000, 900) == doc.composite.pixelColor(1000, 900))
os.remove(tmp)

# 9. 导出
out = os.path.join(HERE, "_test.png")
from core import export_image
check("导出 PNG", export_image(doc, out) and os.path.getsize(out) > 1000)
os.remove(out)

print("\n结果: %d/%d 通过" % (sum(ok), len(ok)))
w.close()
