# -*- coding: utf-8 -*-
"""标签拖出 / 标题栏停靠 的回归。

行为约定（2.15.24 起）：
  · 拖标签 = 只负责「拖出成独立窗口」，不再负责合并
  · 合并统一走「拖白色系统标题栏靠近对方标签条」，主窗口 ↔ 独立窗口双向都行
"""
import os, sys, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, r"C:\Users\20688\Desktop\U Draw Project files\app")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtCore import QPoint, QPointF, QEvent, Qt

app = QApplication([])
from main_window import MainWindow, DocStrip
import main_window as mw

ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("  OK  " if cond else " FAIL ") + name + ("  " + extra if extra else ""))


def find_win(doc, exclude=None):
    for w in QApplication.topLevelWidgets():
        if isinstance(w, MainWindow) and w is not exclude and doc in w.docs:
            return w
    return None


win = MainWindow()
win.resize(1200, 800)
win.show()
win._add_doc(win.make_blank_doc(640, 480, QColor(255, 255, 255, 255)))
app.processEvents()
check("两个文档", len(win.docs) == 2, f"{len(win.docs)}")

# 1. 标签条会发出 tabDragEnded
strip = DocStrip()
strip.resize(700, DocStrip.TAB_H)
strip.set_tabs([{"title": "A"}, {"title": "B"}], 0)
got = {}
strip.tabDragEnded.connect(lambda i, p, ins: got.update(i=i, p=p, ins=ins))
strip._press_index = 1
strip._press_pos = QPoint(10, 10)
strip._dragging = True
strip.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, QPointF(10, 40),
                                    QPointF(900, 900), Qt.LeftButton,
                                    Qt.NoButton, Qt.NoModifier))
check("拖动松手会发出 tabDragEnded", got.get("i") == 1 and got.get("ins") is False, f"{got}")

# 2. 标签条空白处也能抓（用户习惯抓顶栏空白）
bs = DocStrip()
bs.resize(700, DocStrip.TAB_H)
bs.set_tabs([{"title": "A"}, {"title": "B"}, {"title": "C"}], 1)
bs.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, QPointF(690, 12),
                               QPointF(900, 300), Qt.LeftButton, Qt.NoButton,
                               Qt.NoModifier))
check("按空白处 = 抓住当前文档", bs._press_index == 1, f"{bs._press_index}")

# 3. 拖出成独立窗口
doc2 = win.docs[1]
win._tear_off_here(1)
app.processEvents()
sub = find_win(doc2, exclude=win)
check("拖出后新建了一个窗口", sub is not None)
check("新窗口里是那个文档", sub is not None and sub.doc is doc2)
check("新窗口只有一个文档", sub is not None and len(sub.docs) == 1)
check("新窗口标记成 secondary", sub is not None and sub._secondary)
check("源窗口只剩一个文档", len(win.docs) == 1, f"{len(win.docs)}")

# 4. 拖标签不再负责合并：落在别的窗口上也只会「拖出」
if sub is not None:
    n_other = len(win.docs)
    n_self = len(sub.docs)
    pt = QPoint(20, 720)
    sub._on_tab_drag_ended(0, pt, False)
    app.processEvents()
    check("拖标签落在别的窗口上不会合并（只做拖出）",
          len(win.docs) == n_other, f"主窗口 {len(win.docs)} 个文档")

# 5. 独立窗口内部松手：不动作
if sub is not None:
    n_self = len(sub.docs)
    sub._on_tab_drag_ended(0, sub.frameGeometry().center(), True)
    check("独立窗口内部松手不动作", len(sub.docs) == n_self, f"{len(sub.docs)}")

# 6. 拖动时有实时预览（缩略图 + 名字）
win.strip.set_tabs([{"title": "甲"}, {"title": "乙"}], 0)
win.strip._show_ghost(0)
check("拖动时有预览浮窗", win.strip._ghost is not None
      and win.strip._ghost.title == "甲", getattr(win.strip._ghost, "title", "-"))
check("预览带缩略图", win.strip._ghost.thumb is not None
      and not win.strip._ghost.thumb.isNull())
win.strip._ghost.hide()

# 7. 松手时「只要离开标签条」就建窗口（不用拖到窗口外）
win._add_doc(win.make_blank_doc(400, 300, QColor(255, 255, 255, 255)))
app.processEvents()
strip_bottom = win.strip.mapTo(win, QPoint(0, win.strip.height())).y()
just_below = win.mapToGlobal(QPoint(300, strip_bottom + 6))
n0 = len(win.docs)
doc_j = win.docs[0]
win._on_tab_drag_ended(0, just_below, False)
app.processEvents()
check("松手点刚离开标签条就建窗口", len(win.docs) == n0 - 1, f"{len(win.docs)}")
sub_j = find_win(doc_j, exclude=win)
if sub_j is not None:
    sub_j._dock_into(win)          # 收回来，后面的用例继续用主窗口
    app.processEvents()
check("主窗口还在（没被关掉）", win.isVisible())

# 8. 不做预加载
check("没有预加载的备用窗口池", not hasattr(mw, "_WIN_POOL"))
check("分栏样式窗口级一次下发", "QSplitter::handle" in (win.styleSheet() or ""))

# 7. 标题栏停靠：独立窗口 → 主窗口
if sub is not None:
    strip_g = win.strip.mapToGlobal(QPoint(0, 0))
    sub.move(strip_g.x() + 60, strip_g.y() - 8)
    app.processEvents()
    check("靠近时目标标签条会框起来（drop_hint）", win.strip.drop_hint is True)
    check("标题栏压到主窗口标签条上能识别目标", sub._dock_candidate() is win,
          f"{sub._titlebar_rect().getRect()}")
    msg = mw._WinMSG()
    msg.message = 0x0232
    parsed = mw.ctypes.cast(mw.ctypes.addressof(msg),
                            mw.ctypes.POINTER(mw._WinMSG)).contents
    check("MSG 结构能解析出消息号", parsed.message == 0x0232, f"{parsed.message}")
    sub._on_native_message(0x0232)
    app.processEvents()
    check("松开标题栏后合并回主窗口", doc2 in win.docs, f"主窗口 {len(win.docs)} 个文档")
    check("合并后框消失", win.strip.drop_hint is False)
    check("独立窗口已关闭", not sub.isVisible())

# 8. 标题栏停靠：主窗口 → 独立窗口（双向）
win._switch_doc(0)
win.canvas.zoom = 2.5
win.canvas.ox, win.canvas.oy = -300.0, -220.0
win._save_view()
z0 = win.canvas.zoom
c0 = ((win.canvas.width() / 2 - win.canvas.ox) / z0,
      (win.canvas.height() / 2 - win.canvas.oy) / z0)
m3 = win.docs[0]
win._tear_off_here(0)
app.processEvents()
sub3 = find_win(m3, exclude=win)
check("准备：拖出一个独立窗口", sub3 is not None)
if sub3 is not None:
    check("拖出后缩放不变", abs(sub3.canvas.zoom - z0) < 0.01, f"{sub3.canvas.zoom}")
    c3 = ((sub3.canvas.width() / 2 - sub3.canvas.ox) / sub3.canvas.zoom,
          (sub3.canvas.height() / 2 - sub3.canvas.oy) / sub3.canvas.zoom)
    check("拖出后看的还是同一块", abs(c3[0] - c0[0]) < 2 and abs(c3[1] - c0[1]) < 2,
          f"{c0} -> {c3}")
    # 主窗口的标题栏压到独立窗口的标签条上
    sub_g = sub3.strip.mapToGlobal(QPoint(0, 0))
    win.move(sub_g.x() + 40, sub_g.y() - 6)
    app.processEvents()
    check("主窗口标题栏压到独立窗口标签条上也能识别",
          win._dock_candidate() is sub3,
          f"{win._titlebar_rect().getRect()} vs {sub_g.x()},{sub_g.y()}")
    win._on_native_message(0x0232)
    app.processEvents()
    check("主窗口也能合并进独立窗口", m3 in sub3.docs, f"独立窗口 {len(sub3.docs)} 个文档")

print("\n结果:", "全部通过" if ok else "有失败项")
