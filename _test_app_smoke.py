# -*- coding: utf-8 -*-
"""整机冒烟：真把主窗口建起来，走一遍用户报的几个操作，确认没有异常。"""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, r"C:\Users\20688\Desktop\U Draw Project files\app")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor
from PySide6.QtCore import QPointF, Qt

app = QApplication([])
import traceback
from main_window import MainWindow
from core import TextItem

ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("  OK  " if cond else " FAIL ") + name + ("  " + extra if extra else ""))


try:
    win = MainWindow()
    win.resize(1400, 900)
    win.show()
    doc = win.doc
    panel = win.layers_panel

    # 造两个图层 + 一段文字
    doc.add_layer("图层 1")
    doc.add_layer("图层 2")
    doc.add_text(TextItem("我的天", 120, 120, "SimSun", 96))
    panel.refresh()

    # --- 选中文字 -> 垃圾桶
    panel.select_text(0)
    n_layers = len(doc.layers)
    panel.tb["trash"].click()
    check("垃圾桶删文字、不动图层", len(doc.texts) == 0 and len(doc.layers) == n_layers)
    win.doc.undo()
    panel.refresh()
    check("撤销恢复文字", len(win.doc.texts) == 1)

    # --- 全局 Backspace 路径
    panel.select_text(0)
    win.layer_action(3)
    check("Backspace 路径也删文字", len(win.doc.texts) == 0)
    win.doc.undo()
    panel.refresh()

    # --- 建组：多选两个图层 + 文字，走真正的 Ctrl+G（layer_action(7)）
    win.doc.active = 1
    panel.select(1)
    panel.select(2, Qt.ControlModifier)
    panel.select_text(0)
    n_layers = len(win.doc.layers)
    import dialogs as _dlg
    _orig_get_text = _dlg.get_text
    _dlg.get_text = lambda *a, **k: ("线稿组", True)
    try:
        win.layer_action(7)
    finally:
        _dlg.get_text = _orig_get_text
    gid = win.doc.texts[0].group
    check("Ctrl+G：图层和文字都进了同一个组",
          bool(gid) and win.doc.layers[1].group == gid
          and win.doc.layers[2].group == gid, f"gid={gid}")
    check("Ctrl+G：图层一个都没少", len(win.doc.layers) == n_layers,
          f"{n_layers} -> {len(win.doc.layers)}")
    grows = [w for w in panel._rows() if w.__class__.__name__ == "GroupRow"]
    trows = [w for w in panel._rows() if w.__class__.__name__ == "TextRow"]
    check("Ctrl+G：面板里组标题和文字行都还在",
          len(grows) == 1 and len(trows) == 1,
          f"group={len(grows)} text={len(trows)}")
    check("Ctrl+G：组里的文字仍然可见", win.doc.text_state(win.doc.texts[0])[0])

    # --- 组标题：单击选中整组（含文字），再单击取消
    mem = set(win.doc.group_members(gid))
    panel.select_group(gid)
    check("单击组标题 = 选中整组（图层 + 文字）",
          panel.selected == mem and panel.selected_texts == {0},
          f"layers={sorted(panel.selected)} texts={sorted(panel.selected_texts)}")
    check("组标题显示选中态", panel._group_selected(gid))
    panel.select_group(gid)
    check("再点组标题 = 取消整组选中",
          not panel.selected and not panel.selected_texts,
          f"{sorted(panel.selected)} / {sorted(panel.selected_texts)}")
    panel.select_group(gid)
    check("第三次点 = 又整组选中", panel.selected == mem and panel.selected_texts == {0})

    # --- 只选一段文字建组（Ctrl+G）：组里必须真的有这段文字
    panel.selected = set()
    panel.selected_texts = set()
    panel.select_text(0)
    _dlg.get_text = lambda *a, **k: ("文字组", True)
    try:
        win.layer_action(7)
    finally:
        _dlg.get_text = _orig_get_text
    g2 = win.doc.texts[0].group
    check("只选文字建组：文字真的进组了", bool(g2) and g2 != gid, f"gid={g2}")
    grows2 = [w for w in panel._rows() if w.__class__.__name__ == "GroupRow"]
    check("只选文字建组：面板里有组标题", len(grows2) >= 2,
          f"{len(grows2)}")
    panel.select_group(g2)
    check("只选文字建组：点组标题能选中这段文字",
          panel.selected_texts == {0}, f"{sorted(panel.selected_texts)}")
    panel.select_group(g2)
    check("只选文字建组：再点组标题取消",
          not panel.selected_texts and not panel.selected)

    # --- 双击组名改名
    grows = [w for w in panel._rows() if w.__class__.__name__ == "GroupRow"]
    grows[0]._start_rename()
    grows[0].name_edit.setText("线稿组")
    grows[0]._finish_rename()
    check("双击组名能改名", win.doc.groups[gid].name == "线稿组",
          f"{win.doc.groups[gid].name} visible={grows[0].name_edit.isVisible()}")

    # --- 文字移出组
    panel.move_text_to_group(0, "")
    check("文字能拖出组", win.doc.texts[0].group == "")
    panel.move_text_to_group(0, gid)

    # --- 在画布上动手后，图层面板里的文字选中要自动取消
    panel.select_text(0)
    win.rail.select("brush")
    cv0 = win.canvas
    cv0._inside = True
    cv0.pointer_down(QPointF(400, 400), 1.0)
    cv0.pointer_move(QPointF(460, 430), 1.0)
    cv0.pointer_up()
    check("画布操作后取消文字选中", panel.active_text is None,
          f"active_text={panel.active_text}")

    # --- 涂抹 + 对称：笔迹和光标
    win.rail.select("smudge")
    cv = win.canvas
    cv.symmetry["mode"] = "vertical"
    cv._inside = True
    cv._mouse = QPointF(200, 300)
    cv.pointer_down(QPointF(200, 300), 1.0)
    for x in range(200, 320, 6):
        cv.pointer_move(QPointF(x, 300), 1.0)
    cv.pointer_up()
    check("对称涂抹能落笔不报错", True)
    r = cv._cursor_rect()
    m = cv.screen_to_doc(cv._mouse)
    mirror = cv.doc_to_screen(QPointF(2 * cv.symmetry["cx"] - m.x(), m.y()))
    check("镜像位置在重绘区里", r.contains(mirror.toPoint()),
          f"{r} vs {mirror}")

    # --- 组隐藏后文字不画
    win.doc.groups[gid].visible = False
    vis, _op = win.doc.text_state(win.doc.texts[0])
    check("隐藏组后文字不显示", vis is False)
    win.doc.groups[gid].visible = True
    # 不调用 close()：closeEvent 里有「未保存是否保存」的模态框，离屏环境会卡住
except Exception:
    ok = False
    traceback.print_exc()

print("\n结果:", "全部通过" if ok else "有失败项")
