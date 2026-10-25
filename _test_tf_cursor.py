# -*- coding: utf-8 -*-
"""自由变换光标：框内 / 边 / 角 / 框外 应该各是各的形状。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QCursor
from PySide6.QtCore import QPointF, QRectF, Qt

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
doc.layers[0].image.fill(QColor(255, 255, 255, 255))
doc.recompose()
app.processEvents()

win.free_transform()
app.processEvents()
check("进入自由变换", c.has_transform() is True)

tf = c._tf
c.set_zoom(1.0)
c.ox, c.oy = 40.0, 40.0     # 固定一下原点，方便算屏幕坐标

# 变换框中心 / 上边中点 / 左上角 / 框外远处
center = c.doc_to_screen(tf.center)
hs = [c.doc_to_screen(p) for p in tf.handles()]
top = hs[1]
tl = hs[0]
tr = hs[2]
left = hs[7]
outside = QPointF(center.x(), center.y() - tf.h * c.zoom / 2 - 30)


def shape_at(p):
    c._cursor_key = None
    c._tf_apply_cursor(p)
    cur = c.cursor()
    return cur.shape()


s_center = shape_at(center)
s_top = shape_at(top)
s_tl = shape_at(tl)
s_tr = shape_at(tr)
s_left = shape_at(left)
s_out = shape_at(outside)

print("   形状：框内=%s 上边=%s 左上=%s 右上=%s 左边=%s 框外=%s"
      % (s_center, s_top, s_tl, s_tr, s_left, s_out))

check("框内 → 移动（十字箭头）", s_center == Qt.SizeAllCursor, s_center)
check("上边中点 → 上下缩放", s_top == Qt.SizeVerCursor, s_top)
check("左边中点 → 左右缩放", s_left == Qt.SizeHorCursor, s_left)
check("左上角 → 斜向缩放（↖↘）", s_tl == Qt.SizeFDiagCursor, s_tl)
check("右上角 → 斜向缩放（↗↙）", s_tr == Qt.SizeBDiagCursor, s_tr)
check("框外一圈 → 旋转（自定义光标）", c.cursor().pixmap().width() > 0, "位图光标")
check("框内/框外光标不同", s_center != s_out, "%s vs %s" % (s_center, s_out))

# 旋转 90° 之后，角上的光标方向要跟着换
tf.angle = 90.0
tf.render()
doc.recompose()
app.processEvents()
hs2 = [c.doc_to_screen(p) for p in tf.handles()]
s_tl2 = shape_at(hs2[0])
check("框转 90° 后左上角光标跟着变（不再是斜向）", s_tl2 != Qt.SizeFDiagCursor, s_tl2)

# 结束变换后回到工具光标
c.set_tool("brush")
app.processEvents()
check("退出变换后光标回到画笔（隐藏系统光标）", c.cursor().shape() == Qt.BlankCursor,
      c.cursor().shape())

print("\n结果:", "全部通过" if ok else "有失败项")
sys.exit(0 if ok else 1)
