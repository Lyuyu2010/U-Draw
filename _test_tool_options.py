# -*- coding: utf-8 -*-
"""橡皮 / 涂抹的选项栏和 [ ] 快捷键：必须改「当前工具的笔」，且真的生效。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QPainter
from PySide6.QtCore import QPointF, Qt

app = QApplication([])
import theme
theme.apply_theme(app)
from main_window import MainWindow

ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("  OK  " if cond else " FAIL ") + name + ("  " + str(extra) if extra else ""))


win = MainWindow()
win.resize(1200, 800)
win.show()
app.processEvents()
c = win.canvas
doc = win.doc
paint = win.brush                      # 画笔（和 BrushPanel 共用同一个对象）

# ---------- 橡皮 ----------
c.set_tool("eraser")
app.processEvents()
eb = c.eraser_brush
paint_size0 = paint.size

win._nudge_size(True)
check("[ 或 ] 改的是橡皮的笔径", eb.size > 0 and abs(eb.size - paint_size0) > 0.01,
      "橡皮 %.1f / 画笔 %.1f" % (eb.size, paint_size0))
check("画笔笔径没被顺手改掉", abs(paint.size - paint_size0) < 0.01, paint.size)

win._set_opacity(35)
win._set_flow(45)
win._set_hardness(20)
check("不透明度写进了橡皮", abs(eb.opacity - 0.35) < 0.01, eb.opacity)
check("流量写进了橡皮", abs(eb.flow - 0.45) < 0.01, eb.flow)
check("硬度写进了橡皮", abs(eb.hardness - 0.20) < 0.01, eb.hardness)
check("画笔参数没被污染", abs(paint.opacity - 1.0) < 0.01 and abs(paint.hardness - 1.0) < 0.01,
      "%.2f / %.2f" % (paint.opacity, paint.hardness))

# ---------- 涂抹 ----------
c.set_tool("smudge")
app.processEvents()
sb = c.smudge_brush
size_before = sb.size
win._nudge_size(False)
check("[ ] 改的是涂抹的笔径", abs(sb.size - size_before) > 0.01, "%.1f → %.1f" % (size_before, sb.size))
win._set_hardness(70)
check("硬度写进了涂抹", abs(sb.hardness - 0.70) < 0.01, sb.hardness)
check("画笔硬度仍是 1.0", abs(paint.hardness - 1.0) < 0.01, paint.hardness)

# ---------- 橡皮的「不透明度」要真的影响擦除效果 ----------
def erase_alpha(op: float) -> int:
    img = doc.layer.image
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    p.fillRect(0, 0, 400, 300, QColor(220, 60, 60, 255))
    p.end()
    doc.recompose()
    c.set_tool("eraser")
    eb.size = 60
    eb.hardness = 1.0
    eb.flow = 1.0
    eb.opacity = op
    # pointer_* 收的是**屏幕坐标**，采样用**文档坐标** —— 别混
    c.set_zoom(1.0)
    c.ox, c.oy = 0.0, 0.0
    c.pointer_down(c.doc_to_screen(QPointF(80, 120)), 0.9, Qt.LeftButton, Qt.NoModifier)
    c.pointer_move(c.doc_to_screen(QPointF(240, 120)), 0.9)
    c.pointer_up()
    app.processEvents()
    return doc.layer.image.pixelColor(180, 120).alpha()


a_full = erase_alpha(1.0)
a_half = erase_alpha(0.35)
print("   擦除后残留 alpha：不透明度 100%% → %d，35%% → %d" % (a_full, a_half))
check("不透明度 100% 擦干净", a_full == 0, a_full)
check("不透明度 35% 只擦掉一部分（参数真的起作用）", 0 < a_half < 200, a_half)

print("\n结果:", "全部通过" if ok else "有失败项")
sys.exit(0 if ok else 1)
