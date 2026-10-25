# -*- coding: utf-8 -*-
"""真实系统鼠标：拖标签拖出成独立窗口（合并已改由标题栏负责，这里只验证拖出）。

注意：会短暂接管鼠标（约 2 秒），结束后把光标放回原处。
"""
import os, sys, ctypes
sys.path.insert(0, r"C:\Users\20688\Desktop\U Draw Project files\app")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor
from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest

app = QApplication([])
from main_window import MainWindow

u32 = ctypes.windll.user32
ok = True
WIN = None


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("  OK  " if cond else " FAIL ") + name + ("  " + extra if extra else ""))


def move(x, y):
    d = WIN.devicePixelRatioF() if WIN is not None else 1.0
    u32.SetCursorPos(int(round(x * d)), int(round(y * d)))
    QTest.qWait(45)


def down():
    u32.mouse_event(0x0002, 0, 0, 0, 0)
    QTest.qWait(70)


def up():
    u32.mouse_event(0x0004, 0, 0, 0, 0)
    QTest.qWait(150)


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


old = POINT()
u32.GetCursorPos(ctypes.byref(old))

win = MainWindow()
if os.environ.get("UDRAW_MAX") == "1":
    win.showMaximized()
else:
    win.setGeometry(80, 60, 1180, 800)
    win.show()
win.raise_()
win.activateWindow()
WIN = win
print("   dpr =", win.devicePixelRatioF(), " maximized =", win.isMaximized())
win._add_doc(win.make_blank_doc(640, 480, QColor(255, 255, 255, 255)))
win.docs[1].title = "第二张"
QTest.qWait(600)

try:
    r = win.strip._tab_rects()[1]
    g = win.strip.mapToGlobal(QPoint(r.center().x(), r.center().y()))
    print("   标签全局坐标 =", g.x(), g.y())
    move(g.x(), g.y())
    down()
    for dy in (30, 80, 150, 220):
        move(g.x(), g.y() + dy)
    up()
    QTest.qWait(600)
    subs = [w for w in QApplication.topLevelWidgets()
            if isinstance(w, MainWindow) and w is not win and w.isVisible()]
    check("真实鼠标：拖标签拖出成独立窗口", len(subs) == 1 and len(win.docs) == 1,
          f"窗口 {len(subs)} / 主窗口文档 {len(win.docs)}")
finally:
    u32.SetCursorPos(old.x, old.y)

print("\n结果:", "全部通过" if ok else "有失败项")
