# -*- coding: utf-8 -*-
"""v3.0 S4：选区全家桶（按用户定的语义）

  ① extract_selection_pixels 只抠选区内、保留抗锯齿
  ② **剪切 Ctrl+X**：内容从原层拿走，放进新图层，可马上拖动
  ③ **复制 Ctrl+C**：保留原内容，直接生成新图层（不再是剪贴板两步）
  ④ **复制为新图层 Ctrl+Shift+J**：同上但不切工具
  ⑤ 没有选区时三个动作都作用于**整层**，不能「点了没反应」
  ⑥ 选项栏要有可视化按钮（不是只藏在菜单里）
  ⑦ 图层锁定时给提示，不动数据
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication, QToolButton

app = QApplication([])
import core
import theme

theme.apply_theme(app)
import main_window
from main_window import MainWindow

ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("  OK  " if cond else " FAIL ") + name + ("  " + str(extra) if extra else ""))


RED = QColor(220, 40, 40)
BLUE = QColor(40, 60, 220)

win = MainWindow()
win.resize(1000, 720)
win.show()
app.processEvents()
doc = win.doc

doc.layers[0].image.fill(QColor(255, 255, 255))
src = doc.layer                       # 「图层 1」，当前层
p = QPainter(src.image)
p.fillRect(50, 40, 60, 50, RED)       # 选区内的红块
p.fillRect(150, 100, 30, 30, BLUE)    # 选区外的蓝块
p.end()
doc.recompose()


def select_rect(x, y, w, h):
    path = QPainterPath()
    path.addRect(QRectF(x, y, w, h))
    doc.set_selection(path)


def key(k, mods=Qt.NoModifier):
    win.keyPressEvent(QKeyEvent(QEvent.KeyPress, k, mods))
    app.processEvents()


# ---------------------------------------------------------------- 可视化按钮
labels = {b.text() for b in win.findChildren(QToolButton) if b.text()}
check("选项栏有「剪切」按钮", "剪切" in labels, sorted(labels))
check("选项栏有「复制」按钮", "复制" in labels)
check("选项栏有「复制为新层」按钮", "复制为新层" in labels)
menu_items = [a.text() for a in win.menus[1].actions() if a.text()]
check("菜单里不再有「剪切选区为新图层」",
      not any("剪切选区为新图层" in t for t in menu_items), menu_items)

# ---------------------------------------------------------------- 抠像素
doc.clear_selection()
check("没有选区时返回 None", doc.extract_selection_pixels(src) is None)

select_rect(40, 30, 80, 70)
got = doc.extract_selection_pixels(src)
check("有选区时能抠出内容", got is not None)
img, pos = got
check("抠出的尺寸 = 选区外接矩形", img.width() == 80 and img.height() == 70,
      f"{img.width()}×{img.height()}")
check("左上角位置正确", pos == QPoint(40, 30), pos)
check("选区内的像素还在", img.pixelColor(20, 20) == RED, img.pixelColor(20, 20).name())
check("矩形内、色块外的区域是透明的", img.pixelColor(75, 65).alpha() == 0,
      img.pixelColor(75, 65).alpha())

# ---------------------------------------------------------------- Ctrl+X 剪切
before_red = src.image.pixelColor(70, 60)
n0 = len(doc.layers)
key(Qt.Key_X, Qt.ControlModifier)
check("剪切生成新图层", len(doc.layers) == n0 + 1, f"{n0}->{len(doc.layers)}")
nl = doc.layers[doc.active]
check("新图层名字是「剪切 N」", nl.name.startswith("剪切"), nl.name)
check("新图层拿到那块像素", nl.image.pixelColor(70, 60) == RED,
      nl.image.pixelColor(70, 60).name())
check("源图层的选区被清空", src.image.pixelColor(70, 60).alpha() == 0,
      src.image.pixelColor(70, 60).alpha())
check("源图层选区外没被动", src.image.pixelColor(160, 110) == BLUE)
check("剪切后切到移动工具（可以直接拖）", win.current_tool == "move", win.current_tool)

win.undo()
app.processEvents()
check("一次撤销把图层收回", len(doc.layers) == n0, len(doc.layers))
check("一次撤销把像素也还原", src.image.pixelColor(70, 60) == before_red,
      src.image.pixelColor(70, 60).name())

# ---------------------------------------------------------------- Ctrl+C 复制
# 复制「跟着当前图层」：在原图层上复制一份、直接拖着走，不新建图层
win.rail.select("brush")
app.processEvents()
n0 = len(doc.layers)
key(Qt.Key_C, Qt.ControlModifier)
check("复制不新建图层", len(doc.layers) == n0, f"{n0}->{len(doc.layers)}")
check("复制进入浮动状态（可以拖）", win.canvas.has_float())
check("浮动副本内容正确", win.canvas._float["img"].pixelColor(10, 10) == RED,
      win.canvas._float["img"].pixelColor(10, 10).name())
check("复制不改原图层内容", src.image.pixelColor(70, 60) == before_red,
      src.image.pixelColor(70, 60).name())
check("复制写进剪贴板（跨文档仍可用）", main_window.PASTE_BUF.get("image") is not None)

# 拖动浮动副本
c = win.canvas
p0 = c.doc_to_screen(QPointF(70, 60))
c.pointer_down(p0, 0.5, Qt.LeftButton, Qt.NoModifier)
c.pointer_move(QPointF(p0.x() + 40, p0.y() + 30), 0.5)
c.pointer_up()
app.processEvents()
moved = c._float["pos"]
check("拖动改变了浮动位置", abs(moved.x() - 40) > 1 or abs(moved.y() - 30) > 1,
      f"({moved.x():.0f},{moved.y():.0f})")
# 选区必须跟着内容一起走，否则看着像「只复制了选区框、内容没动」
sel_center = doc.selection.boundingRect().center()
check("选区跟着内容一起平移",
      abs(sel_center.x() - (moved.x() + 40)) < 2 and abs(sel_center.y() - (moved.y() + 35)) < 2,
      f"选区中心 ({sel_center.x():.0f},{sel_center.y():.0f})　浮动 ({moved.x():.0f},{moved.y():.0f})")

c.commit_float()
app.processEvents()
check("落地不新建图层", len(doc.layers) == n0, len(doc.layers))
check("新位置出现了副本",
      src.image.pixelColor(int(moved.x()) + 10, int(moved.y()) + 10) == RED,
      src.image.pixelColor(int(moved.x()) + 10, int(moved.y()) + 10).name())
check("原位置像素还在（复制不是剪切）", src.image.pixelColor(70, 60) == before_red)
win.undo()
app.processEvents()
check("撤销一次把副本收回",
      src.image.pixelColor(int(moved.x()) + 10, int(moved.y()) + 10).alpha() == 0)
check("撤销后原内容还在", src.image.pixelColor(70, 60) == before_red)

# Esc 取消浮动：什么都不该写进图层，选区也要回到这次复制之前的位置
sel_before = doc.selection.boundingRect().center()
key(Qt.Key_C, Qt.ControlModifier)
check("再次复制进入浮动", c.has_float())
win.canvas.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
app.processEvents()
check("Esc 取消浮动", not c.has_float())
check("Esc 之后图层没被改", src.image.pixelColor(70, 60) == before_red)
check("Esc 之后选区回到复制前的位置",
      abs(doc.selection.boundingRect().center().x() - sel_before.x()) < 2,
      f"{doc.selection.boundingRect().center()} vs {sel_before}")

# ---------------------------------------------------------------- 切图层后取新图层的内容
doc.clear_selection()
sel = QPainterPath()
sel.addRect(QRectF(40, 30, 80, 70))
doc.set_selection(sel)
other = doc.add_layer(name="另一层")
p2 = QPainter(other.image)
p2.fillRect(50, 40, 60, 50, BLUE)
p2.end()
doc.recompose()
win.layers_panel.refresh()
app.processEvents()
win.layers_panel.select(doc.layers.index(src))      # 切回原来那层
app.processEvents()
check("切图层后活动层确实变了", doc.layer is src, doc.layer.name)
check("切图层后选区还在", doc.has_selection())
key(Qt.Key_C, Qt.ControlModifier)
check("切图层后复制取的是当前层的内容",
      c._float is not None and c._float["img"].pixelColor(10, 10) == RED,
      None if c._float is None else c._float["img"].pixelColor(10, 10).name())
c.cancel_float()
app.processEvents()

# ---------------------------------------------------------------- 复制为新图层
win.rail.select("brush")          # 换回画笔，验证这个动作**不切工具**
app.processEvents()
n0 = len(doc.layers)
key(Qt.Key_J, Qt.ControlModifier | Qt.ShiftModifier)
check("Ctrl+Shift+J 生成新图层", len(doc.layers) == n0 + 1, f"{n0}->{len(doc.layers)}")
check("新图层有内容", doc.layers[doc.active].image.pixelColor(70, 60) == RED)
check("原层不受影响", src.image.pixelColor(70, 60) == before_red)
check("复制为新图层不切工具", win.current_tool == "brush", win.current_tool)
win.undo()
app.processEvents()

# ---------------------------------------------------------------- 没有选区 → 整层
doc.clear_selection()
n0 = len(doc.layers)
main_window.PASTE_BUF.clear()
key(Qt.Key_C, Qt.ControlModifier)
check("没选区时复制整层（不再空转）", main_window.PASTE_BUF.get("image") is not None)
check("整层复制的内容对得上",
      main_window.PASTE_BUF["image"].pixelColor(160, 110) == BLUE)
check("整层复制同样不动图层", len(doc.layers) == n0, len(doc.layers))

n0 = len(doc.layers)
key(Qt.Key_X, Qt.ControlModifier)
check("没选区时剪切整层", len(doc.layers) == n0 + 1, f"{n0}->{len(doc.layers)}")
check("整层剪切后源层空了", src.image.pixelColor(70, 60).alpha() == 0)
win.undo()
app.processEvents()
check("整层剪切一次撤销就回来", src.image.pixelColor(70, 60) == before_red)

# ---------------------------------------------------------------- 锁定图层
select_rect(40, 30, 80, 70)
doc.layers[doc.active].locked = True
win.hint.setText("")
n0 = len(doc.layers)
win.cut_selection()
app.processEvents()
check("锁定图层不执行剪切", len(doc.layers) == n0, len(doc.layers))
check("锁定图层给出提示", "锁定" in win.hint.text(), win.hint.text())
doc.layers[doc.active].locked = False

# ---------------------------------------------------------------- 空白选区
blank = QPainterPath()
blank.addRect(QRectF(2, 2, 10, 10))
doc.set_selection(blank)
got = doc.extract_selection_pixels(src)
check("空白处也能抠出（全透明，但不是 None）",
      got is not None and got[0].width() == 10 and got[0].pixelColor(2, 2).alpha() == 0,
      None if got is None else f"{got[0].width()}×{got[0].height()}")

# ---------------------------------------------------------------- 取消选择 / Esc
doc.set_selection(sel)
win.copy_selection()
app.processEvents()
check("复制后有浮动副本", c.has_float())
win.deselect()                       # 选项栏 / 菜单里的「取消选择」
app.processEvents()
check("取消选择会把浮动副本一起取消", not c.has_float())
check("取消选择清掉了选区", not doc.has_selection())

doc.set_selection(sel)
c.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
app.processEvents()
check("Esc 能取消选择", not doc.has_selection())

# 文字工具下 Esc 不能抢走（那边 Esc 是结束文字编辑）
win.rail.select("text")
app.processEvents()
doc.set_selection(sel)
c.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
app.processEvents()
check("文字工具下 Esc 不清选区", doc.has_selection())
win.rail.select("marquee")
app.processEvents()
win.deselect()

# ---------------------------------------------------------------- 把选区内容搬到当前图层
doc.clear_selection()
base = doc.add_layer(name="搬运源")
p3 = QPainter(base.image)
p3.fillRect(50, 40, 60, 50, RED)
p3.end()
dst = doc.add_layer(name="搬运目标")
doc.recompose()
win.layers_panel.refresh()
app.processEvents()

win.layers_panel.select(doc.layers.index(base))
app.processEvents()
win.rail.select("marquee")
app.processEvents()
c._sel_path = QPainterPath()
c._sel_path.addRect(QRectF(40, 30, 80, 70))
c._commit_selection()
app.processEvents()
check("圈选区时记住了来源层", win._sel_layer is base,
      None if win._sel_layer is None else win._sel_layer.name)

win.layers_panel.select(doc.layers.index(dst))
app.processEvents()
check("切到了目标层", doc.layer is dst, doc.layer.name)
win.move_selection_to_layer()
app.processEvents()
check("源层的选区被清空", base.image.pixelColor(70, 60).alpha() == 0,
      base.image.pixelColor(70, 60).alpha())
check("目标层拿到了内容", dst.image.pixelColor(70, 60) == RED,
      dst.image.pixelColor(70, 60).name())
check("搬完选区还在", doc.has_selection())

win.undo()
app.processEvents()
check("一次撤销把源层还原", base.image.pixelColor(70, 60) == RED,
      base.image.pixelColor(70, 60).name())
check("一次撤销把目标层也还原", dst.image.pixelColor(70, 60).alpha() == 0,
      dst.image.pixelColor(70, 60).alpha())

# ---------------------------------------------------------------- 无选区移动整层
# 这条是打包自检抓出来的：删第三方 Warp 代码时把 SNAP_PX / _fills_canvas 一起切掉了，
# 结果「无选区拖动整层」直接 NameError。补一条守住它。
doc.clear_selection()
op = core.MoveOp(doc, doc.layer)
check("无选区也能构造移动操作", op is not None)
col = doc.layer.image.pixelColor(70, 60)
op.render(6, 6)
doc.recompose()
check("整层移动后像素确实挪了", doc.layer.image.pixelColor(76, 66) == col,
      doc.layer.image.pixelColor(76, 66).name())

print("\n结果:", "全部通过" if ok else "有失败项")
sys.exit(0 if ok else 1)
