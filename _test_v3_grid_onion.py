# -*- coding: utf-8 -*-
"""v3.0 S1（缩减版）：洋葱皮（聚焦当前图层）

网格 / 参考线已按用户要求整体移除，这里保留一条「确实没了」的守卫断言。

重点验：
  ① 洋葱皮只改「画布看到的东西」，composite / flatten / 导出一点都不能动
  ② 背景层（纸）不压暗
  ③ 切图层 / 多选图层都要立刻重绘（曾经的 bug：切层不重绘）
  ④ 网格 / 参考线相关接口已经清干净
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication

app = QApplication([])
import core
import theme

theme.apply_theme(app)
from main_window import MainWindow

ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("  OK  " if cond else " FAIL ") + name + ("  " + str(extra) if extra else ""))


# ---------------------------------------------------------------- 网格/参考线已移除
d0 = core.Document(80, 60)
check("文档没有 grid 字段了", not hasattr(d0, "grid"))
check("文档没有 guides 字段了", not hasattr(d0, "guides"))
check("core 里没有 GuidesEdit 了", not hasattr(core, "GuidesEdit"))

# ---------------------------------------------------------------- 洋葱皮
d2 = core.Document(200, 150, QColor(0, 0, 0, 0))
d2.layers[0].image.fill(QColor(0, 0, 0, 0))
p = QPainter(d2.layers[0].image)
p.fillRect(0, 0, 50, 50, QColor(220, 40, 40))       # 底层：红块
p.end()
lay = d2.add_layer(name="蓝层")
p = QPainter(lay.image)
p.fillRect(100, 0, 50, 50, QColor(40, 60, 220))     # 上层：蓝块（不与红块重叠）
p.end()
d2.recompose()

check("新文档默认不开洋葱皮", d2.onion is False)
d2.onion = True
d2.onion_dim = 0.35
d2.active = 0                                        # 当前层 = 红层
view = d2.view_image(0, 0.35)
check("当前层颜色不变", view.pixelColor(10, 10) == QColor(220, 40, 40),
      view.pixelColor(10, 10).name())
a = view.pixelColor(110, 10).alpha()
check("其余图层被压暗", 80 <= a <= 100, f"alpha={a}（期望≈89）")
check("其余图层颜色仍是原来的", view.pixelColor(110, 10).blue() > 180,
      view.pixelColor(110, 10).name())

# 背景层是「纸」，不能被压暗
d3 = core.Document(100, 100, QColor(250, 248, 240))
p = QPainter(d3.add_layer(name="上").image)
p.fillRect(10, 10, 30, 30, QColor(10, 120, 60))
p.end()
d3.recompose()
d3.active = 1
v3i = d3.view_image(1, 0.35)
check("背景层不压暗（纸仍然是纸）", v3i.pixelColor(80, 80).alpha() == 255,
      f"alpha={v3i.pixelColor(80, 80).alpha()}")

check("composite 里其余图层仍是全不透明",
      d2.composite.pixelColor(110, 10).alpha() == 255,
      d2.composite.pixelColor(110, 10).alpha())
flat_before = d2.flatten()
d2.onion = False
d2.recompose()
flat_after = d2.flatten()
check("开关洋葱皮不影响 flatten / 导出", flat_before == flat_after)

d2.onion = True
v1 = d2.view_image(0, 0.35)
v2 = d2.view_image(0, 0.35)
check("视图缓存命中（同一个对象）", v1 is v2)
d2.recompose()
v3 = d2.view_image(0, 0.35)
check("recompose 之后缓存失效", v3 is not v1)

# ---------------------------------------------------------------- 主窗口
win = MainWindow()
win.resize(1100, 760)
win.show()
app.processEvents()

menu_texts = [a.text() for a in win.menus[4].actions() if a.text()]
check("视图菜单里没有网格 / 参考线了",
      not any(("网格" in t or "参考线" in t or "九宫格" in t) for t in menu_texts),
      menu_texts)
check("选项栏没有网格按钮了", not hasattr(win, "vb_grid"))
check("视图菜单里洋葱皮还在", any("洋葱皮" in t for t in menu_texts), menu_texts)

win.toggle_onion(True)
app.processEvents()
check("菜单开洋葱皮 → 文档标记生效", win.doc.onion is True)
check("面板按钮跟着亮", win.layers_panel.onion_btn.isChecked())
win.layers_panel.onion_btn.setChecked(False)
app.processEvents()
check("面板按钮关 → 文档标记也关", win.doc.onion is False)
check("菜单项跟着取消勾选", win.a_onion.isChecked() is False)

doc_b = win.make_blank_doc(300, 200, QColor(255, 255, 255, 255))
win._add_doc(doc_b)
app.processEvents()
win.toggle_onion(True)
app.processEvents()
check("新开的文档也继承洋葱皮", doc_b.onion is True)
win._switch_doc(0)
app.processEvents()
check("切回旧文档仍然是开的", win.doc.onion is True)

# ---------------------------------------------------------------- 切层必须重绘
d4 = core.Document(120, 90)
d4.layers[0].image.fill(QColor(255, 255, 255))
_la = d4.add_layer(name="A")
_p = QPainter(_la.image)
_p.fillRect(0, 0, 40, 40, QColor(220, 40, 40))
_p.end()
_lb = d4.add_layer(name="B")
_p = QPainter(_lb.image)
_p.fillRect(60, 40, 40, 40, QColor(40, 60, 220))
_p.end()
d4.recompose()
win._add_doc(d4)
app.processEvents()
win.toggle_onion(True)
app.processEvents()

calls = {"n": 0}
_orig_update = win.canvas.update


def _spy_update(*a, **k):
    calls["n"] += 1
    return _orig_update(*a, **k)


win.canvas.update = _spy_update

win.layers_panel.select(2)          # 当前层 = B
app.processEvents()
calls["n"] = 0
win.layers_panel.select(1)          # 切到 A
app.processEvents()
check("切图层会重绘画布（洋葱皮）", calls["n"] > 0, f"update 调用 {calls['n']} 次")

calls["n"] = 0
win.layers_panel.select(2, Qt.ControlModifier)      # Ctrl 加选 B → 多选
app.processEvents()
check("多选图层也会重绘画布", calls["n"] > 0, f"update 调用 {calls['n']} 次")
check("多选状态正确", win.canvas.layer_selection == [1, 2], win.canvas.layer_selection)

v_multi = d4.view_image(2, 0.35, keep={1, 2})
v_single = d4.view_image(2, 0.35, keep={2})
check("多选时选中的图层不压暗", v_multi.pixelColor(10, 10).green() < 60,
      f"A 的绿通道={v_multi.pixelColor(10, 10).green()}（红色原值 40）")
check("不在选中里的图层仍被压暗", v_single.pixelColor(10, 10).green() > 120,
      f"A 的绿通道={v_single.pixelColor(10, 10).green()}（压暗后≈180）")
check("当前层始终正常", v_multi.pixelColor(80, 60) == QColor(40, 60, 220),
      v_multi.pixelColor(80, 60).name())

print("\n结果:", "全部通过" if ok else "有失败项")
sys.exit(0 if ok else 1)
