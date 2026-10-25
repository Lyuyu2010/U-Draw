# -*- coding: utf-8 -*-
"""2.15.28 的三处改动验证：
  1. 关于对话框笔刷数量与实际一致（133 支 / 17 类）
  2. 笔从画布边缘拖出去后，笔尖圈不会卡在边上（_inside 不再被无条件置 True）
  3. Shift+P / Shift+O 能切压感两个开关
"""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, r"C:\Users\20688\Desktop\U Draw Project files\app")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtTest import QTest

app = QApplication([])
import brushes
from about_dialogs import AboutDialog, _brush_counts
from main_window import MainWindow, APP_NAME, APP_VERSION

ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("  OK  " if cond else " FAIL ") + name + ("  " + extra if extra else ""))


# 1. 笔刷数量
n, g = _brush_counts()
check("关于里的笔刷数与实际一致", n == len(brushes.DEFAULTS) and g == len({b.group for b in brushes.DEFAULTS}),
      f"{n} 支 / {g} 类（实际 {len(brushes.DEFAULTS)} / {len({b.group for b in brushes.DEFAULTS})}）")
check("不再是 102", n != 102, f"{n}")
dlg = AboutDialog(APP_NAME, APP_VERSION)
from PySide6.QtWidgets import QLabel
joined = " ".join(w.text() for w in dlg.findChildren(QLabel) if w.text())
check("关于正文写的是 133 支 / 17 类", "133 支" in joined and "17 类" in joined,
      "命中" if ("133 支" in joined and "17 类" in joined) else joined[:60])
dlg.deleteLater()

# 2. 光标不再卡在边缘
win = MainWindow()
win.resize(1200, 800)
win.show()
app.processEvents()
c = win.canvas
c.tool = "brush"
check("初始不在画布内", c._inside is False)
# 模拟笔在画布内移动
c.pointer_move(QPointF(300, 300), 0.8)
check("画布内移动后 _inside = True", c._inside is True)
# 关键：拖到画布外面（笔拖出边界时仍会收到 move）
c.pointer_move(QPointF(300, c.height() + 60), 0.8)
check("拖出画布后 _inside 变回 False（以前这里一直是 True，圈就卡住了）",
      c._inside is False, f"{c._inside}")
check("此时光标圈矩形为空（重绘会把旧圈擦掉）", c._cursor_rect().isEmpty())
# 再模拟一次 leaveEvent，确认不会残留
c.leaveEvent(QEvent(QEvent.Leave))
check("leave 之后仍然不在画布内", c._inside is False)

# 3. 压感快捷键
bp = win.brush_panel
s0, o0 = bp.cb_psize.isChecked(), bp.cb_popacity.isChecked()
check("两个开关的快捷键已注册",
      win.a_psize.shortcut().toString() == "Shift+P"
      and win.a_popacity.shortcut().toString() == "Shift+O",
      f"{win.a_psize.shortcut().toString()} / {win.a_popacity.shortcut().toString()}")
win.a_psize.trigger()
check("Shift+P 切换了「压感控制大小」", bp.cb_psize.isChecked() != s0,
      f"{s0} -> {bp.cb_psize.isChecked()}")
win.a_popacity.trigger()
check("Shift+O 切换了「压感控制浓淡」", bp.cb_popacity.isChecked() != o0,
      f"{o0} -> {bp.cb_popacity.isChecked()}")
check("状态栏有提示", "压感" in win.hint.text(), win.hint.text()[:30])

print("\n结果:", "全部通过" if ok else "有失败项")
