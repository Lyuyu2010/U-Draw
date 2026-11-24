# -*- coding: utf-8 -*-
"""选区撤销 + 变换撤销的交互"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

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
win.resize(1000, 700)
win.show()
app.processEvents()
doc = win.doc
p = QPainter(doc.layer.image)
p.fillRect(0, 0, 300, 200, QColor(30, 120, 200))
p.end()
doc.recompose()

path = QPainterPath()
path.addRect(QRectF(10, 10, 50, 50))

doc.set_selection(path)
app.processEvents()
check("框选后选区存在", doc.has_selection())
check("选区变化进了撤销栈", len(doc.undo_stack) == 1, len(doc.undo_stack))

win.canvas.setFocus()
app.processEvents()
QTest.keyClick(win.canvas, Qt.Key_Z, Qt.ControlModifier)
app.processEvents()
check("Ctrl+Z 撤销选区", not doc.has_selection())

QTest.keyClick(win.canvas, Qt.Key_Z, Qt.ControlModifier | Qt.ShiftModifier)
app.processEvents()
check("Ctrl+Shift+Z 重做选区", doc.has_selection())

QTest.keyClick(win.canvas, Qt.Key_Y, Qt.ControlModifier)
app.processEvents()
check("Ctrl+Y 也是重做", doc.has_selection())

# 取消选择本身也可撤销
doc.clear_selection()
app.processEvents()
check("取消选择后没有选区", not doc.has_selection())
win.undo()
app.processEvents()
check("撤销「取消选择」能恢复选区", doc.has_selection())

# 反选
doc.set_selection(path)
doc.invert_selection()
app.processEvents()
inner = doc.selection.contains(QRectF(30, 30, 5, 5).center())
check("反选后原来的选区内部被排除", not inner)
win.undo()
app.processEvents()
check("撤销反选回到原选区", doc.selection.contains(QRectF(30, 30, 5, 5).center()))

print("\n结果:", "全部通过" if ok else "有失败项")
sys.exit(0 if ok else 1)
