# -*- coding: utf-8 -*-
"""彩虹笔不再被改成别的笔型 + 细软笔不再出现「一点一点」。"""
import json
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor
from PySide6.QtCore import QPointF

app = QApplication([])
import theme
theme.apply_theme(app)
from main_window import MainWindow
import brushes
from core import Document, Stroke

ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("  OK  " if cond else " FAIL ") + name + ("  " + str(extra) if extra else ""))


win = MainWindow()
win.show()
app.processEvents()
bp = win.brush_panel
c = win.canvas
rain = [i for i, b in enumerate(bp.presets) if b.name == "连续彩虹"][0]

# ① 选彩虹笔 → 笔型必须是彩虹
bp.select_index(rain)
app.processEvents()
check("选中连续彩虹后笔型是 rainbow", c.brush.kind == "rainbow", c.brush.kind)

# ② 拖滑杆（会走 _apply）不能把笔型改掉
for v in (40, 70, 100):
    win._set_opacity(v)
    win._set_hardness(v)
    win._set_size(v)
    app.processEvents()
check("拖滑杆后笔型仍是 rainbow", c.brush.kind == "rainbow", c.brush.kind)
check("下拉框显示也还是 rainbow", bp.kind_combo.currentData() == "rainbow",
      bp.kind_combo.currentData())

# ④ 彩虹笔画出来的颜色要真的有变化
doc = win.doc
img = doc.layer.image
img.fill(QColor(0, 0, 0, 0))
doc.recompose()
c.set_tool("brush")
c.brush.apply_from(bp.presets[rain])
c.brush.size = 24
c.set_zoom(1.0)
c.ox, c.oy = 0.0, 0.0
c.pointer_down(c.doc_to_screen(QPointF(60, 120)), 0.9, 0, 0)
for i in range(1, 40):
    c.pointer_move(c.doc_to_screen(QPointF(60 + i * 16, 120)), 0.9)
c.pointer_up()
app.processEvents()
hues = set()
for x in range(80, 600, 12):
    col = doc.layer.image.pixelColor(x, 120)
    if col.alpha() > 40:
        hues.add(round(col.hsvHueF(), 1))
check("彩虹笔画出的颜色确实在变（色相不唯一）", len(hues) >= 4, "色相 %d 种" % len(hues))

# ⑤ 细软笔的笔迹要均匀，不能一串珠子
def evenness(name, size):
    br = {b.name: b for b in brushes.DEFAULTS}[name].copy()
    br.size = size
    d = Document(300, 40, QColor(255, 255, 255, 255))
    st = Stroke(d, d.layers[0], br, QColor(30, 30, 30))
    st.begin(QPointF(10, 20), 0.9)
    for i in range(1, 12):
        st.move(QPointF(10 + i * 18, 20), 0.9)
    st.end()
    d.recompose()
    row = [d.composite.pixelColor(x, 20).red() for x in range(40, 180)]
    return max(row) - min(row)


for nm, sz in (("软圆笔", 12), ("素描铅笔", 10), ("HB 铅笔", 8)):
    spread = evenness(nm, sz)
    check("%s %dpx 笔迹均匀（中线亮度起伏 %d < 12）" % (nm, sz, spread), spread < 12, spread)

# ⑥ 手动换笔型仍然有效（功能不能丢）—— 放最后，免得污染上面的绘制测试
idx = bp.kind_combo.findData("ballpoint")
if idx >= 0:
    bp.kind_combo.setCurrentIndex(idx)
    app.processEvents()
    check("手动换笔型仍然有效（改成圆珠笔）", c.brush.kind == "ballpoint", c.brush.kind)

# ⑦ 存档里彩虹笔被改成别的笔型时，读档要能修回来
d = {"kind": "ballpoint", "size": 30}
tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
json.dump({"edits": {"连续彩虹": d}}, tmp, ensure_ascii=False)
tmp.close()
os.unlink(tmp.name)

print("\n结果:", "全部通过" if ok else "有失败项")
sys.exit(0 if ok else 1)
