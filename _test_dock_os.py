# -*- coding: utf-8 -*-
"""真实系统鼠标：拖「白色标题栏」靠近对方标签条 → 合并（两个方向都测）。

会短暂接管鼠标（约 4 秒），结束后把光标放回原处。
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


def move_to(p, wait=55):
    d = WIN.devicePixelRatioF() if WIN is not None else 1.0
    u32.SetCursorPos(int(round(p.x() * d)), int(round(p.y() * d)))
    QTest.qWait(wait)


def down():
    u32.mouse_event(0x0002, 0, 0, 0, 0)
    QTest.qWait(80)


def up():
    u32.mouse_event(0x0004, 0, 0, 0, 0)
    QTest.qWait(160)


def drag_titlebar(win_from, win_to):
    """按住 win_from 的白色标题栏，拖到 win_to 的标签条上松开。"""
    win_from.raise_()
    win_from.activateWindow()
    QTest.qWait(250)
    fg = win_from.frameGeometry()
    start = QPoint(fg.center().x(), fg.top() + 12)
    target = win_to.strip.mapToGlobal(QPoint(200, win_to.strip.height() // 2))
    move_to(start)
    down()
    for i in range(1, 7):
        move_to(QPoint(int(start.x() + (target.x() - start.x()) * i / 6),
                       int(start.y() + (target.y() - start.y()) * i / 6)))
    move_to(target, 140)          # 停在目标上多等一会，让最后一次 moveEvent 生效
    up()
    QTest.qWait(900)
    app.processEvents()


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


old = POINT()
u32.GetCursorPos(ctypes.byref(old))

win = MainWindow()
win.setGeometry(60, 80, 1150, 780)
win.show()
win.raise_()
win.activateWindow()
WIN = win
win._add_doc(win.make_blank_doc(640, 480, QColor(255, 255, 255, 255)))
QTest.qWait(500)
doc2 = win.docs[1]
win._tear_off_here(1)
QTest.qWait(700)
sub = next((w for w in QApplication.topLevelWidgets()
            if isinstance(w, MainWindow) and w is not win and doc2 in w.docs), None)
check("独立窗口已创建", sub is not None and len(win.docs) == 1,
      f"窗口 {sub is not None} 主窗口文档 {len(win.docs)}")

try:
    # ① 独立窗口 → 主窗口
    if sub is not None:
        drag_titlebar(sub, win)
        check("独立窗口标题栏拖到主窗口标签条 → 合并", doc2 in win.docs,
              f"主窗口 {len(win.docs)} 个文档")
        check("独立窗口已关闭", not sub.isVisible())

    # ② 主窗口 → 独立窗口
    doc3 = win.docs[1] if len(win.docs) > 1 else win.docs[0]
    win._tear_off_here(win.docs.index(doc3))
    QTest.qWait(700)
    sub2 = next((w for w in QApplication.topLevelWidgets()
                 if isinstance(w, MainWindow) and w is not win and doc3 in w.docs), None)
    check("准备：再拖出一个独立窗口", sub2 is not None)
    if sub2 is not None:
        n_sub = len(sub2.docs)
        drag_titlebar(win, sub2)
        check("主窗口标题栏拖到独立窗口标签条 → 主窗口合并进去",
              doc3 in sub2.docs and len(sub2.docs) >= n_sub,
              f"独立窗口 {len(sub2.docs)} 个文档")
        check("主窗口已关闭", not win.isVisible())
finally:
    u32.SetCursorPos(old.x, old.y)

print("\n结果:", "全部通过" if ok else "有失败项")
