# -*- coding: utf-8 -*-
"""2.15.33：中键拖动滚动 / 启动不再弹提示气泡 / 定时器不在运笔时捣乱。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtTest import QTest

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
win.resize(1400, 900)
win.show()
app.processEvents()

# ---- 1. 笔刷条中键拖动 ----
strip = win.preset_bar.strip
bar = strip.verticalScrollBar()
print("   笔刷条可滚动范围:", bar.minimum(), "-", bar.maximum())
if bar.maximum() > 0:
    bar.setValue(bar.minimum())
    vp = strip.viewport()
    start = QPoint(vp.width() // 2, vp.height() - 20)
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QPointF as PF

    def send(t, gp, btn=Qt.MiddleButton):
        ev = QMouseEvent(t, PF(start), PF(gp), btn,
                         btn if t != QEvent.MouseButtonRelease else Qt.NoButton,
                         Qt.NoModifier)
        QApplication.sendEvent(vp, ev)

    v0 = bar.value()
    send(QEvent.MouseButtonPress, vp.mapToGlobal(start))
    send(QEvent.MouseMove, vp.mapToGlobal(start) + QPoint(0, -120))
    v1 = bar.value()
    send(QEvent.MouseButtonRelease, vp.mapToGlobal(start) + QPoint(0, -120))
    check("中键往上拖 → 内容向下滚（滚动值变大）", v1 > v0, "%d → %d" % (v0, v1))
else:
    check("笔刷条内容不足一屏（跳过滚动测试）", True)

# ---- 2. 运笔过程中不重建图层缩略图 ----
c = win.canvas
c.tool = "brush"
import brushes
c.brush = {b.name: b for b in brushes.DEFAULTS}["G 笔"].copy()
c.brush.size = 20
doc = win.doc
doc.layers[0].image.fill(QColor(255, 255, 255, 255))
doc.recompose()
c.pointer_down(QPointF(80, 80), 0.9, Qt.LeftButton, Qt.NoModifier)
c.pointer_move(QPointF(200, 120), 0.9)
lp = win.layers_panel
lp._refresh_active_thumb_now()          # 画到一半强制触发
check("运笔中触发缩略图刷新 → 自动推迟（不执行重建）",
      lp._thumb_timer.isActive())
c.pointer_up()
app.processEvents()
lp._thumb_timer.stop()
lp._refresh_active_thumb_now()          # 抬笔后应该真的干活（不重启定时器）
check("抬笔后可以正常刷新", not lp._thumb_timer.isActive())

# ---- 3. 大脏区整块重绘（防掉帧残影）----
import time
calls = {"full": 0, "part": 0}
orig_update = c.update


def spy(rect=None, *a, **k):
    if rect is None or (hasattr(rect, "isNull") and rect.isNull()):
        calls["full"] += 1
    else:
        calls["part"] += 1
    return orig_update(rect, *a, **k) if rect is not None else orig_update()


c.update = spy
c._refresh(QRect(0, 0, doc.w, doc.h))          # 整块画布脏区
c.update = orig_update
check("整块脏区 → 走整块重绘", calls["full"] >= 1, calls)

print("\n结果:", "全部通过" if ok else "有失败项")
sys.exit(0 if ok else 1)
