# -*- coding: utf-8 -*-
"""2.15.14 回归：多选 / 删除 / 建组 / 拖出组。"""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, r"C:\Users\20688\Desktop\U Draw Project files\app")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt

app = QApplication([])
import panels
from core import Document, TextItem

ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("  OK  " if cond else " FAIL ") + name + ("  " + extra if extra else ""))


def make():
    d = Document(400, 300, QColor("#ffffff"))
    d.add_layer("图层 1")
    d.add_layer("图层 2")
    d.add_layer("图层 3")
    d.add_text(TextItem("我的", 40, 40, "SimSun", 48))
    p = panels.LayersPanel()
    p.set_document(d)
    return d, p


def rows(p, kind=None):
    out = []
    for i in range(p.list_lay.count()):
        w = p.list_lay.itemAt(i).widget()
        if w is None:
            continue
        if kind is None or w.__class__.__name__ == kind:
            out.append(w)
    return out


# 1. 没有多选时点文字：只有文字亮着
d, p = make()
p.select(3)
p.select_text(0)
check("单选图层后点文字：图层高亮全灭",
      not any(r.active or r.selected for r in rows(p, "LayerRow")))
check("单选图层后点文字：文字行亮着",
      [r for r in rows(p, "TextRow")][0].selected)

# 2. 多选两个图层后点文字：多选保留
d, p = make()
p.select(1)
p.select(2, Qt.ControlModifier)
p.select_text(0)
check("多选 2 层后点文字：多选保留", p.selected == {1, 2}, f"{sorted(p.selected)}")
check("多选后点文字：没有图层被画成当前层",
      not any(r.active for r in rows(p, "LayerRow")))

# 3. 多选删除
d, p = make()
n0 = len(d.layers)
p.select(1)
p.select(2, Qt.ControlModifier)
p.remove_layer()
check("多选 2 层一起删", len(d.layers) == n0 - 2, f"{n0} -> {len(d.layers)}")
check("多选删除可撤销", d.can_undo())
d.undo()
p.refresh()
check("撤销后图层回来", len(d.layers) == n0)

# 4. 文字 + 多选图层一起删
d, p = make()
n0, t0 = len(d.layers), len(d.texts)
p.select(1)
p.select(2, Qt.ControlModifier)
p.select_text(0)
p.remove_layer()
check("文字和图层一起删", len(d.texts) == t0 - 1 and len(d.layers) == n0 - 2,
      f"texts={len(d.texts)} layers={len(d.layers)}")
d.undo()
p.refresh()
check("一起删也能一步撤销", len(d.texts) == t0 and len(d.layers) == n0)

# 5. 只有文字的组要在面板里看得见
d, p = make()
gid = d.add_group("组1", [], [0])
p.refresh()
check("只有文字的组：组标题出现", len(rows(p, "GroupRow")) == 1)
check("只有文字的组：文字行还在", len(rows(p, "TextRow")) == 1)
check("只有文字的组：画布上文字仍然可见", d.text_state(d.texts[0])[0])

# 6. 多选图层 + 文字建组
d, p = make()
p.select(1)
p.select(2, Qt.ControlModifier)
p.select_text(0)
gid = d.add_group("组2", sorted(p.selected), [p.active_text])
p.refresh()
check("多选+文字一起进组",
      d.layers[1].group == gid and d.layers[2].group == gid and d.texts[0].group == gid)
check("建组后组标题只有一个", len(rows(p, "GroupRow")) == 1)
check("建组后文字行还在", len(rows(p, "TextRow")) == 1)

# 7. 图层拖出组：拖到自己组的标题上沿
d, p = make()
gid = d.add_group("组3", [1, 2])
p.refresh()
layer = d.layers[1]
grow = rows(p, "GroupRow")[0]
p._drag_row = [r for r in rows(p, "LayerRow") if r.layer is layer][0]
p._drag_target = (grow, "above")
p.finish_drag()
check("拖到组标题上沿 = 移出组", layer.group == "", repr(layer.group))

# 8. 拖回组里：拖到组标题下沿
p.refresh()
grow = rows(p, "GroupRow")[0]
p._drag_row = [r for r in rows(p, "LayerRow") if r.layer is layer][0]
p._drag_target = (grow, "below")
p.finish_drag()
check("拖到组标题下沿 = 进组", layer.group == gid, repr(layer.group))

# 9. 右键「移出图层组」
p.move_layer_out_of_group(d.layers.index(layer))
check("右键移出图层组", layer.group == "")
check("移出后组还在（还有别的成员）", gid in d.groups)

# 10. 文字拖出组
d, p = make()
gid = d.add_group("组4", [1], [0])
p.refresh()
trow = rows(p, "TextRow")[0]
grow = rows(p, "GroupRow")[0]
p._drag_row = trow
p._drag_target = (grow, "above")
p.finish_drag()
check("文字拖到自己组的标题上沿 = 移出组", d.texts[0].group == "",
      repr(d.texts[0].group))

print("\n结果:", "全部通过" if ok else "有失败项")
