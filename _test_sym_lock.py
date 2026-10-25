# -*- coding: utf-8 -*-
"""对称「固定」后不该再出现抓手（热区 / 手形光标 / 可拖的圆点）。"""
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
c.set_tool("brush")
c.set_zoom(1.0)
c.ox, c.oy = 60.0, 60.0
app.processEvents()

c.symmetry["mode"] = "quad"
c.symmetry["cx"] = c.doc.w / 2
c.symmetry["cy"] = c.doc.h / 2
center = c.doc_to_screen(QPointF(c.symmetry["cx"], c.symmetry["cy"]))


def hover(p):
    ev = QMouseEvent(QEvent.MouseMove, QPointF(p), QPointF(p), Qt.NoButton,
                     Qt.NoButton, Qt.NoModifier)
    QApplication.sendEvent(c, ev)
    app.processEvents()
    return c.cursor().shape()


# 未固定：轴心可拖，光标变手
c.symmetry["locked"] = False
c._cursor_shape = None
check("未固定时轴心是热区", c._sym_handle_hit(center) is True)
s_open = hover(center)
check("未固定时悬停轴心 → 手形光标", s_open == Qt.OpenHandCursor, s_open)

# 固定：不该再是热区，光标也不该是手
c.symmetry["locked"] = True
c._cursor_shape = None
check("固定后轴心不再是热区", c._sym_handle_hit(center) is False)
s_fixed = hover(center)
check("固定后悬停轴心不再是手形", s_fixed != Qt.OpenHandCursor, s_fixed)
check("固定后光标是画笔（隐藏系统光标）", s_fixed == Qt.BlankCursor, s_fixed)

# 固定时按下去也不能拖动对称
before = (c.symmetry["cx"], c.symmetry["cy"])
c.pointer_down(center, 0.9, Qt.LeftButton, Qt.NoModifier)
check("固定后按下轴心不会进入拖动", c._sym_drag is False)
c.pointer_move(QPointF(center.x() + 40, center.y() + 30), 0.9)
c.pointer_up()
app.processEvents()
after = (c.symmetry["cx"], c.symmetry["cy"])
check("固定后轴心位置没被拖走", before == after, "%s → %s" % (before, after))

# 取消固定后又能拖了
c.symmetry["locked"] = False
c._sym_hot = False
c._cursor_shape = None
c.pointer_down(center, 0.9, Qt.LeftButton, Qt.NoModifier)
check("取消固定后又能拖动轴心", c._sym_drag is True)
c.pointer_up()

print("\n结果:", "全部通过" if ok else "有失败项")
sys.exit(0 if ok else 1)
