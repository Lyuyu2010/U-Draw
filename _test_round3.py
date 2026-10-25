# -*- coding: utf-8 -*-
"""2.15.15 回归：单击选中/再单击取消、文字参与多选、文字建组、组选中含文字。"""
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
    d.add_text(TextItem("我的", 40, 40, "SimSun", 48))
    d.add_text(TextItem("标题", 40, 140, "SimSun", 48))
    p = panels.LayersPanel()
    p.set_document(d)
    return d, p


def rows(p, kind=None):
    out = []
    for i in range(p.list_lay.count()):
        w = p.list_lay.itemAt(i).widget()
        if w is not None and (kind is None or w.__class__.__name__ == kind):
            out.append(w)
    return out


# 1. 图层：单击选中，再单击取消（先点一个「不是当前选中」的层）
d, p = make()
p.select(1)
check("单击图层 = 选中", p.selected == {1}, f"{sorted(p.selected)}")
p.select(1)
check("再单击同一图层 = 取消", p.selected == set(), f"{sorted(p.selected)}")
p.select(1)
check("第三次单击又选中", p.selected == {1})

# 2. 背景层也能点选 / 取消
p.select(0)
check("背景层也能单击选中", p.selected == {0})
p.select(0)
check("背景层再单击取消", p.selected == set())

# 3. Ctrl 多选仍然正常
p.select(1)
p.select(2, Qt.ControlModifier)
check("Ctrl 加选两个图层", p.selected == {1, 2})

# 4. 文字：单击选中 / 再单击取消
d, p = make()
p.select_text(0)
check("单击文字 = 选中", p.selected_texts == {0} and p.active_text == 0)
p.select_text(0)
check("再单击同一文字 = 取消",
      p.selected_texts == set() and p.active_text is None)

# 5. 文字 Ctrl 加选（和图层一样的待遇）
p.select_text(0)
p.select_text(1, Qt.ControlModifier)
check("Ctrl 加选两段文字", p.selected_texts == {0, 1},
      f"{sorted(p.selected_texts)}")
p.select_text(1, Qt.ControlModifier)
check("Ctrl 再点取消其中一段", p.selected_texts == {0})

# 6. 图层 + 文字混合多选
d, p = make()
p.select(1)
p.select_text(0, Qt.ControlModifier)
check("图层 + 文字混合多选",
      p.selected == {1} and p.selected_texts == {0},
      f"layers={sorted(p.selected)} texts={sorted(p.selected_texts)}")

# 7. 混合多选一起删（一步撤销）
n0, t0 = len(d.layers), len(d.texts)
p.select(2, Qt.ControlModifier)
p.remove_selection()
check("混合多选一起删", len(d.layers) == n0 - 2 and len(d.texts) == t0 - 1,
      f"layers={len(d.layers)} texts={len(d.texts)}")
d.undo()
p.refresh()
check("一起删可一步撤销", len(d.layers) == n0 and len(d.texts) == t0)

# 8. 文字单独建组：组里要有它
d, p = make()
p.select_text(0)
gid = d.add_group("文字组", [], sorted(p.selected_texts))
p.refresh()
check("文字单独建组：文字进组了", d.texts[0].group == gid, repr(d.texts[0].group))
grows = rows(p, "GroupRow")
allrows = rows(p)
check("文字单独建组：面板里有组标题", len(grows) == 1)
# 组标题的下一行必须是组里那段文字
gi = allrows.index(grows[0])
check("文字单独建组：文字行紧跟在组标题下面",
      gi + 1 < len(allrows) and allrows[gi + 1].__class__.__name__ == "TextRow"
      and allrows[gi + 1].item is d.texts[0])
check("文字单独建组：组内文字仍可见", d.text_state(d.texts[0])[0])

# 9. 组单击 = 选中组内图层和文字；再单击 = 取消
d, p = make()
gid = d.add_group("混合组", [1], [0])
p.refresh()
p.select(2)                     # 先选别的东西
p.select_group(gid)
check("组单击：图层和文字都被选中",
      p.selected == {1} and p.selected_texts == {0},
      f"layers={sorted(p.selected)} texts={sorted(p.selected_texts)}")
check("组标题显示整组选中", p._group_selected(gid))
p.select_group(gid)
check("组再单击：整组取消选中",
      not p.selected and not p.selected_texts)
p.select_group(gid)
check("组第三次单击：又整组选中", p.selected == {1} and p.selected_texts == {0})

# 10. 取消选中后按删除，不应该删掉当前图层
d, p = make()
n0 = len(d.layers)
p.select(1)
p.select(1)                     # 取消
check("取消选中后 selected 为空", not p.selected)
check("取消选中时删除入口返回 False（交给上层提示，不删）",
      p.remove_selection() is False and len(d.layers) == n0)

print("\n结果:", "全部通过" if ok else "有失败项")
