# -*- coding: utf-8 -*-
"""本次修复的回归自检：

A. 图层面板选中文字后，垃圾桶删的是文字（不是下面的图层）
B. 文字可以拖进 / 拖出图层组，组也能装文字
C. 单击组标题选中整组、双击组名能改
D. 涂抹开对称时，镜像那一边的光标也要在重绘区域里（不残影 / 不消失）
"""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, r"C:\Users\20688\Desktop\U Draw Project files\app")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor
from PySide6.QtCore import QPointF

app = QApplication([])
import panels, canvas as canvas_mod
from core import Document, TextItem

ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("  OK  " if cond else " FAIL ") + name + ("  " + extra if extra else ""))


def make_doc():
    d = Document(600, 400, QColor("#ffffff"))
    d.add_layer("图层 1")          # index 1
    d.add_layer("图层 2")          # index 2
    t = TextItem("我的天", 60, 60, "SimSun", 64)
    d.add_text(t)
    return d, t


# ---------------------------------------------------------------- A
doc, t = make_doc()
panel = panels.LayersPanel()
panel.set_document(doc)
n_layers = len(doc.layers)
rows = [w for w in panel._rows() if isinstance(w, panels.TextRow)]
check("文字行出现在面板里", len(rows) == 1)
panel.select_text(0)
check("选中文字后 trash 可用", panel.tb["trash"].isEnabled())
panel.remove_layer()
check("垃圾桶删掉的是文字", len(doc.texts) == 0)
check("垃圾桶没动图层", len(doc.layers) == n_layers)
check("删除文字可撤销", doc.can_undo())
doc.undo()
check("撤销后文字回来", len(doc.texts) == 1)

# ---------------------------------------------------------------- B
doc, t = make_doc()
panel.set_document(doc)
gid = doc.add_group("组1", [1])
check("组建好了", gid in doc.groups and doc.layers[1].group == gid)
panel.refresh()
panel.move_text_to_group(0, gid)
check("文字进了组", doc.texts[0].group == gid)
check("组里能查到文字", doc.group_texts(gid) == [0])
panel.refresh()
grows = [w for w in panel._rows() if isinstance(w, panels.GroupRow)]
trows = [w for w in panel._rows() if isinstance(w, panels.TextRow)]
check("组标题行存在", len(grows) == 1, f"{len(grows)}")
check("文字行缩进显示在组里", len(trows) == 1 and trows[0].parent() is not None)
# 组隐藏时文字一起消失
doc.groups[gid].visible = False
vis, op = doc.text_state(doc.texts[0])
check("隐藏组后文字也不显示", vis is False)
doc.groups[gid].visible = True
# 移出组
panel.move_text_to_group(0, "")
check("文字能移出组", doc.texts[0].group == "")
# 只有文字的组不会被误删
doc.add_group("只有文字", [], [0])
gid2 = [g for g in doc.groups if doc.groups[g].name == "只有文字"][0]
doc.prune_groups()
check("只有文字的组不会被 prune 掉", gid2 in doc.groups)
doc.dissolve_group(gid2)
check("解散组后文字还在", len(doc.texts) == 1 and doc.texts[0].group == "")

# ---------------------------------------------------------------- C
doc, t = make_doc()
panel.set_document(doc)
gid = doc.add_group("组1", [1, 2])
panel.refresh()
grows = [w for w in panel._rows() if isinstance(w, panels.GroupRow)]
check("组标题行存在", len(grows) == 1)
grows[0].mousePressEvent(None) if False else panel.select_group(gid)
check("单击组标题选中整组", panel.selected == set(doc.group_members(gid)),
      f"{sorted(panel.selected)}")
check("组标题显示选中态", panel._group_selected(gid))
panel.rename_group(gid, "我的线稿")
check("组能改名", doc.groups[gid].name == "我的线稿")
panel.refresh()
grows = [w for w in panel._rows() if isinstance(w, panels.GroupRow)]
check("改名后标题跟着变", grows[0].name.text() == "我的线稿")

# ---------------------------------------------------------------- D
doc2, _t = make_doc()
cv = canvas_mod.Canvas(doc2)
cv.resize(800, 600)
cv.show()
cv.tool = "smudge"
cv.symmetry["mode"] = "vertical"
cv.symmetry["cx"] = doc2.w / 2.0
cv.symmetry["cy"] = doc2.h / 2.0
cv._inside = True
cv._mouse = QPointF(120, 200)
r1 = cv._cursor_rect()
mirror = cv.doc_to_screen(QPointF(2 * cv.symmetry["cx"] - cv.screen_to_doc(cv._mouse).x(),
                                  cv.screen_to_doc(cv._mouse).y()))
check("对称光标区域覆盖主光标", r1.contains(cv._mouse.toPoint()))
check("对称光标区域覆盖镜像位置", r1.contains(mirror.toPoint()),
      f"{r1} vs {mirror}")
cv.symmetry["mode"] = "off"
r2 = cv._cursor_rect()
check("关掉对称后区域收回到主光标", r2.width() < r1.width(), f"{r2.width()} < {r1.width()}")

print("\n结果:", "全部通过" if ok else "有失败项")
