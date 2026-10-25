# -*- coding: utf-8 -*-
"""自由变换里逐次撤回：按一次退一步，退到头才取消整个变换。"""
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
img = doc.layer.image
img.fill(QColor(0, 0, 0, 0))
p = QPainter(img)
p.fillRect(300, 200, 400, 260, QColor(220, 60, 60))
p.end()
doc.recompose()
app.processEvents()

win.free_transform()
app.processEvents()
c.set_zoom(1.0)
tf = c._tf
c0 = QPointF(tf.center)

# ① 拖动移动一步
start = c.doc_to_screen(tf.center)
c.pointer_down(start, 0.9, Qt.LeftButton, Qt.NoModifier)
c.pointer_move(QPointF(start.x() + 60, start.y() + 40), 0.9)
c.pointer_up()
app.processEvents()
moved = QPointF(tf.center)
check("拖动移动生效", abs(moved.x() - c0.x()) > 20, "%.0f → %.0f" % (c0.x(), moved.x()))
check("记下了 1 步", len(tf.steps) == 1, len(tf.steps))

# ② 再转个角度（滑杆）
c.tf_set_angle(25.0)
app.processEvents()
check("旋转生效", abs(tf.angle - 25.0) < 0.01, tf.angle)
check("又记了 1 步", len(tf.steps) == 2, len(tf.steps))

# ③ 撤销一次：只退掉旋转，位置还在
win.undo()
app.processEvents()
check("第 1 次撤销：角度回到 0", abs(tf.angle) < 0.01, tf.angle)
check("第 1 次撤销：位置没被一起撤掉", abs(tf.center.x() - moved.x()) < 0.5, tf.center.x())
check("变换还在（没退出）", c.has_transform() is True)

# ④ 再撤一次：位置也退回去
win.undo()
app.processEvents()
check("第 2 次撤销：位置回到最初", abs(tf.center.x() - c0.x()) < 0.5, tf.center.x())
check("变换还在", c.has_transform() is True)

# ⑤ 再撤一次：退到头，整个变换取消
win.undo()
app.processEvents()
check("第 3 次撤销：退到头 → 变换取消", c.has_transform() is False)

print("\n结果:", "全部通过" if ok else "有失败项")
sys.exit(0 if ok else 1)
