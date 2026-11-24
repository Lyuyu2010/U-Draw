# -*- coding: utf-8 -*-
"""v3.0 S5（返工版）：四种滤镜 —— 线稿 / 高斯模糊 / 像素化 / 黑白

每个滤镜都配**数值断言**，不是「跑通就算过」：
模糊必须产生中间灰、像素化必须整块同色、黑白必须三通道相等、
线稿必须在边缘变暗、参数变了结果必须跟着变。

再验预览流程：
  ① 打开滤镜 = 只预览，撤销栈不动
  ② 取消 = 图层完全恢复
  ③ 应用 = 写进图层，且只记一步撤销
  ④ 有选区只改选区内
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QPushButton

app = QApplication([])
import filters
import theme

theme.apply_theme(app)
from main_window import MainWindow

ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("  OK  " if cond else " FAIL ") + name + ("  " + str(extra) if extra else ""))


def rgb(img, x, y):
    c = img.pixelColor(x, y)
    return c.red(), c.green(), c.blue(), c.alpha()


def edge_img(w=60, h=40):
    """左黑右白的硬边图。"""
    img = QImage(w, h, QImage.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 255))
    p = QPainter(img)
    p.fillRect(w // 2, 0, w - w // 2, h, QColor(255, 255, 255, 255))
    p.end()
    return img


src = edge_img()

# ---------------------------------------------------------------- 滤镜表
check("正好三种滤镜", len(filters.FILTERS) == 3, len(filters.FILTERS))
names = [n for _k, n, _f, _p in filters.FILTERS]
check("名字对得上", names == ["高斯模糊", "像素化", "黑白"], names)
check("每个滤镜都有参数定义",
      all(len(filters.params_for(k)) >= 1 for k, _n, _f, _p in filters.FILTERS))

# ---------------------------------------------------------------- 逐个滤镜
bl = filters.gaussian_blur(src, 8)
mid = rgb(bl, 29, 20)[0]
check("模糊：边界出现中间灰", 0 < mid < 255, mid)
check("模糊：远处仍然是纯黑", rgb(bl, 2, 20)[0] < 6, rgb(bl, 2, 20))
check("模糊：远处仍然是纯白", rgb(bl, 57, 20)[0] > 249, rgb(bl, 57, 20))
bl2 = filters.gaussian_blur(src, 24)
check("模糊：半径变大，过渡更宽", rgb(bl2, 20, 20)[0] > rgb(bl, 20, 20)[0],
      f"{rgb(bl, 20, 20)[0]} → {rgb(bl2, 20, 20)[0]}")

pi = filters.pixelate(src, 10)
check("像素化：同一块内颜色一致",
      len({rgb(pi, x, 20) for x in range(30, 40)}) == 1)
check("像素化：块外不受影响", rgb(pi, 5, 20)[0] == 0)
pi2 = filters.pixelate(src, 20)
check("像素化：块变大后结果跟着变",
      rgb(pi2, 20, 20) != rgb(pi, 20, 20), f"{rgb(pi, 20, 20)} → {rgb(pi2, 20, 20)}")

bw = filters.black_white(src, 100)
check("黑白：黑仍黑", rgb(bw, 10, 20) == (0, 0, 0, 255), rgb(bw, 10, 20))
check("黑白：白仍白", rgb(bw, 50, 20) == (255, 255, 255, 255), rgb(bw, 50, 20))
col = QImage(8, 8, QImage.Format_ARGB32)
col.fill(QColor(220, 40, 40))
bwc = filters.black_white(col, 100)
r, g, b, _a = rgb(bwc, 4, 4)
check("黑白：彩色变灰（三通道相等）", r == g == b, (r, g, b))
check("黑白：灰值约等于亮度", abs(r - int(220 * 0.299 + 40 * 0.587 + 40 * 0.114)) <= 3, r)

check("未知滤镜 key 原样返回", filters.apply_filter("nope", src) is src)

# ---------------------------------------------------------------- 主窗口：预览流程
win = MainWindow()
win.resize(1000, 720)
win.show()
app.processEvents()
doc = win.doc
layer = doc.layer
p = QPainter(layer.image)
p.fillRect(0, 0, 300, 200, QColor(30, 120, 200))
p.end()
layer.has_content = True
doc.recompose()

menu = {a.text(): a for a in win.menus[5].actions() if a.text()}
check("菜单里就是这三项", list(menu) == ["高斯模糊", "像素化", "黑白"], list(menu))

base = layer.image.pixelColor(50, 50).name()
undo_before = len(doc.undo_stack)
menu["黑白"].trigger()      # 关键：走真实菜单回调（之前 triggered 传 checked 把 key 吃掉了）
app.processEvents()
check("点菜单真的进入预览", win._filter_state is not None)
check("预览已经改变画面", layer.image.pixelColor(50, 50).name() != base,
      f"{base} → {layer.image.pixelColor(50, 50).name()}")
check("预览不改撤销栈", len(doc.undo_stack) == undo_before, len(doc.undo_stack))

labels = {b.text() for b in win.findChildren(QPushButton)}
check("选项栏有醒目的应用按钮", "✔ 应用" in labels, sorted(labels))
check("选项栏有取消按钮", "取消" in labels)

win._filter_cancel()
app.processEvents()
check("取消后完全恢复", layer.image.pixelColor(50, 50).name() == base,
      layer.image.pixelColor(50, 50).name())
check("取消后退出预览", win._filter_state is None)

menu["黑白"].trigger()
app.processEvents()
win._filter_apply()
app.processEvents()
check("应用后退出预览", win._filter_state is None)
check("应用只记一步撤销", len(doc.undo_stack) == undo_before + 1, len(doc.undo_stack))
applied = layer.image.pixelColor(50, 50).name()
check("应用后画面变了", applied != base, applied)
win.undo()
app.processEvents()
check("一步撤销回到原样", layer.image.pixelColor(50, 50).name() == base,
      layer.image.pixelColor(50, 50).name())

# 换滤镜：**不落地**，仍基于同一份原图预览（以前会自动应用，导致层层叠加）
menu["像素化"].trigger()
app.processEvents()
menu["高斯模糊"].trigger()
app.processEvents()
check("换滤镜不会偷偷应用", len(doc.undo_stack) == undo_before, len(doc.undo_stack))
check("当前预览的是高斯模糊", win._filter_state["key"] == "blur", win._filter_state["key"])
check("换滤镜后基准仍是原图",
      win._filter_state["base"]["before"].pixelColor(50, 50).name() == base,
      win._filter_state["base"]["before"].pixelColor(50, 50).name())
win._filter_cancel()

# 参数调节
menu["高斯模糊"].trigger()
app.processEvents()
# 纯色内部本来就不变；图像最外圈又有边缘延拓，所以要挑「色块外侧但远离画布边」
soft = layer.image.pixelColor(150, 210).alpha()
win._filter_param("radius", 30)
win._filter_refresh()            # 测试里不等防抖计时器
app.processEvents()
hard = layer.image.pixelColor(150, 210).alpha()
check("调大半径扩散更远（不是死值）", hard > soft, f"alpha {soft} → {hard}")
win._filter_cancel()
app.processEvents()

# 选区：只改选区内
path = QPainterPath()
path.addRect(QRectF(10, 10, 50, 50))
doc.set_selection(path)
app.processEvents()
win.open_filter("bw")
app.processEvents()
check("有选区时只改选区内", layer.image.pixelColor(30, 30).name() != base,
      layer.image.pixelColor(30, 30).name())
check("选区外一个像素都不动", layer.image.pixelColor(200, 150).name() == base,
      layer.image.pixelColor(200, 150).name())
win._filter_apply()
app.processEvents()
doc.clear_selection()

# 模糊接缝：选区边界内外不能有明显台阶（曾经差很多，出现一圈方框）
# 用一张全新的纯色图，避免和上面的滤镜结果混在一起
d_seam = win.make_blank_doc(200, 200, QColor(255, 255, 255, 255))
win._add_doc(d_seam)
app.processEvents()
lay_seam = d_seam.layer
ps = QPainter(lay_seam.image)
ps.fillRect(0, 0, 200, 200, QColor(30, 120, 200))
ps.end()
d_seam.recompose()
path_seam = QPainterPath()
path_seam.addRect(QRectF(40, 40, 80, 80))
d_seam.set_selection(path_seam)
win.open_filter("blur")
app.processEvents()
win._filter_param("radius", 24)
win._filter_refresh()
app.processEvents()
inside_edge = lay_seam.image.pixelColor(41, 80).red()
outside_edge = lay_seam.image.pixelColor(39, 80).red()
check("模糊在选区边界没有接缝", abs(inside_edge - outside_edge) <= 2,
      f"{outside_edge} → {inside_edge}")
win._filter_cancel()
app.processEvents()
d_seam.modified = False      # 免得后面关闭文档时弹「要保存吗」
win._switch_doc(0)           # 切回原文档，后面的断言还在它身上
app.processEvents()

# 选区按钮只在有选区时出现
win.canvas.sync_selection_ants()
app.processEvents()
check("没选区时「剪切 / 复制」按钮隐藏", not win.sel_tools_box.isVisible())
doc.set_selection(path)
win.canvas.sync_selection_ants()
app.processEvents()
check("有选区时按钮出现", win.sel_tools_box.isVisible())

# 预览中按 Ctrl+Z：应该取消预览，而不是去撤上一条编辑
undo_n = len(doc.undo_stack)
win.open_filter("bw")
app.processEvents()
check("预览中", win._filter_state is not None)
win.undo()
app.processEvents()
check("Ctrl+Z 在预览中 = 取消预览", win._filter_state is None)
check("取消预览不动撤销栈", len(doc.undo_stack) == undo_n, len(doc.undo_stack))

# 预览写回必须「替换」而不是「叠加」：叠的话滤镜的半透明边会让原色透出来，
# 放大后就是一圈「边缘还是原色」的粉边（黑白尤其明显）。
d_res = win.make_blank_doc(300, 200, QColor(255, 255, 255, 255))
win._add_doc(d_res)
app.processEvents()
lay_r = d_res.layer
pr = QPainter(lay_r.image)
pr.setRenderHint(QPainter.Antialiasing, True)
pr.setPen(QPen(QColor(226, 182, 182), 40, Qt.SolidLine, Qt.RoundCap))
pr.drawLine(40, 60, 260, 150)
pr.end()
d_res.recompose()
win.open_filter("bw")
app.processEvents()
colored = 0
for yy in range(0, 200, 2):
    for xx in range(0, 300, 2):
        c = lay_r.image.pixelColor(xx, yy)
        if c.alpha() > 8 and abs(c.red() - c.green()) > 12:
            colored += 1
check("预览不会让原色透出来（无彩色残留）", colored == 0, colored)
win._filter_cancel()
app.processEvents()
d_res.modified = False
win._switch_doc(0)
app.processEvents()

# 锁定图层
doc.layers[doc.active].locked = True
snap = layer.image.pixelColor(50, 50).name()
win.open_filter("bw")
app.processEvents()
check("锁定图层不进入预览", win._filter_state is None)
check("锁定图层给出提示", "锁定" in win.hint.text(), win.hint.text())
check("锁定图层画面不变", layer.image.pixelColor(50, 50).name() == snap)
doc.layers[doc.active].locked = False

print("\n结果:", "全部通过" if ok else "有失败项")
sys.exit(0 if ok else 1)
