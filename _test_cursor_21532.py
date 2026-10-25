# -*- coding: utf-8 -*-
"""2.15.32 验证：光标卡边 / 数位板切不回画笔光标 / 轻压画不出来。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QCursor
from PySide6.QtCore import QPoint, QPointF, Qt

app = QApplication([])
import theme
theme.apply_theme(app)
from main_window import MainWindow
from core import Document, Stroke
import brushes

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

# ---- 1. 光标形状跟着工具走（数位板不触发 enterEvent 时靠它兜底）----
c.tool = "brush"
c._cursor_shape = None
c._sync_cursor()
check("画笔工具 → 隐藏系统光标（自己画笔尖圈）", c.cursor().shape() == Qt.BlankCursor,
      c.cursor().shape())
c.tool = "hand"
c._cursor_shape = None
c._sync_cursor()
check("抓手工具 → 手形光标", c.cursor().shape() == Qt.OpenHandCursor, c.cursor().shape())
c.tool = "brush"
c._cursor_shape = None
c._sync_cursor()

# ---- 2. 看门狗：光标不在画布上就把笔尖圈擦掉 ----
c._inside = True
c._stroke = None
c._smudge = None
# 把系统光标放到窗口外面，再手动跑一次看门狗
QCursor.setPos(QPoint(5, 5))
c._check_pointer_over()
check("光标不在画布上 → _inside 变回 False（圈会被擦掉）", c._inside is False, c._inside)

# 画布内则保持不变（offscreen 下 widgetAt 可能返回 None，这里只验证不误杀的逻辑）
c._inside = True
c._stroke = object()          # 假装正在画：看门狗不该动
c._check_pointer_over()
check("正在画的时候看门狗不插手", c._inside is True)
c._stroke = None

# ---- 3. 笔拖出画布：不再留下贴边的圈 ----
c._inside = True
c.pointer_move(QPointF(200, c.height() + 80), 0.8)
check("拖出画布后 _inside=False", c._inside is False, c._inside)
check("光标圈矩形为空", c._cursor_rect().isEmpty())

# ---- 4. 轻压能画出看得见的线 ----
named = {b.name: b for b in brushes.DEFAULTS}


def darkest(name, pressure):
    br = named[name].copy()
    br.size = 10
    doc = Document(120, 60, QColor(255, 255, 255, 255))
    st = Stroke(doc, doc.layers[0], br, QColor(0, 0, 0))
    st.begin(QPointF(10, 30), pressure)
    for i in range(10):
        st.move(QPointF(10 + i * 10, 30), pressure)
    st.end()
    doc.recompose()
    img = doc.composite
    return min(img.pixelColor(x, 30).red() for x in range(10, 100))


for name in ("素描铅笔", "2B 铅笔"):
    v01 = darkest(name, 0.01)
    v10 = darkest(name, 1.0)
    # 阈值 242：白纸 255，轻压到 242 已有约 5% 的墨，屏幕上是能看见的淡线。
    # （笔点间距修正成真正均匀后，细笔墨量比之前少了约一成，所以从 235 放宽到 242。）
    check("%s 轻压(0.01)能看见：R=%d（<242 才算看得见）" % (name, v01), v01 < 242, v01)
    check("%s 满压明显更深：R=%d" % (name, v10), v10 < v01 - 25, "%d vs %d" % (v10, v01))

print("\n结果:", "全部通过" if ok else "有失败项")
sys.exit(0 if ok else 1)
