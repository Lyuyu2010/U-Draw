# -*- coding: utf-8 -*-
"""走真实的鼠标事件路径，验证自由变换光标真的会变（不只是直接调函数）。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtCore import QEvent, QPointF, Qt

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
c.set_zoom(1.0)
c.ox, c.oy = 60.0, 60.0
app.processEvents()

tf = c._tf
hs = [c.doc_to_screen(p) for p in tf.handles()]
center = c.doc_to_screen(tf.center)


def hover(p):
    """发一个真实的 MouseMove 给画布（和用户移动鼠标走同一条路）。"""
    ev = QMouseEvent(QEvent.MouseMove, QPointF(p), QPointF(p), Qt.NoButton,
                     Qt.NoButton, Qt.NoModifier)
    QApplication.sendEvent(c, ev)
    app.processEvents()
    return c.cursor().shape()


s_in = hover(center)
s_top = hover(hs[1])
s_left = hover(hs[7])
s_tl = hover(hs[0])
s_out = hover(QPointF(center.x(), hs[1].y() - 40))

print("   悬停结果：框内=%s 上边=%s 左边=%s 左上=%s 框外=%s"
      % (s_in, s_top, s_left, s_tl, s_out))

check("鼠标移到框内 → 十字箭头", s_in == Qt.SizeAllCursor, s_in)
check("鼠标移到上边中点 → 上下箭头", s_top == Qt.SizeVerCursor, s_top)
check("鼠标移到左边中点 → 左右箭头", s_left == Qt.SizeHorCursor, s_left)
check("鼠标移到左上角 → 斜向箭头", s_tl == Qt.SizeFDiagCursor, s_tl)
check("鼠标移到框外 → 旋转光标（位图）", c.cursor().pixmap().width() > 0, s_out)
check("框内与框外光标不同", s_in != s_out, "%s vs %s" % (s_in, s_out))

print("\n结果:", "全部通过" if ok else "有失败项")
sys.exit(0 if ok else 1)
