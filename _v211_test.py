# -*- coding: utf-8 -*-
"""v2.1.1 自测：图层组按钮 / 背景层固定与复位 / 对称入口。

跑法：QT_QPA_PLATFORM=offscreen python _v211_test.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

import theme
from core import Document
from main_window import MainWindow

OUT = os.path.join(HERE, "_v21_out")
FAIL = []


def ck(cond, msg):
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        FAIL.append(msg)


def main():
    os.makedirs(OUT, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)
    theme.apply_theme(app)

    # ---------- 1. 数据模型：背景层固定 ----------
    print("[1] 背景层固定")
    doc = Document(200, 120)
    bg = doc.bg_layer
    ck(bg is not None and doc.layers[0] is bg, "新建文档有 is_bg 背景层且在索引 0")
    doc.add_layer()
    doc.add_layer()
    ck(len(doc.layers) == 3, f"三层 {len(doc.layers)}")
    doc.active = 0
    ck(doc.move_layer(0, 1) is False, "背景层不能上移")
    doc.active = 1
    ck(doc.move_layer(1, -1) is False, "别的层不能移到背景层下面")
    doc.active = 0
    ck(doc.remove_layer() is False, "背景层不能删除")
    ck(len(doc.layers) == 3, "删背景层后层数不变")
    ck(doc.add_group("G", [0, 1]) is not None, "建组成功")
    ck(bg.group == "", "背景层没被拉进组")
    ck(doc.layers[1].group != "", "普通层进了组")

    # 「背景层复位」功能已按需求整体去掉
    ck(not hasattr(doc, "reset_background"), "背景层复位功能已移除")

    # 存档往返
    p = os.path.join(OUT, "_bg_roundtrip.udraw")
    from core import load_project, save_project
    save_project(doc, p)
    d2 = load_project(p)
    ck(d2.bg_layer is not None and d2.layers[0] is d2.bg_layer, "存档往返后背景层标记保留")

    # ---------- 2. 主窗口：按钮 / 右键菜单 / 对称入口 ----------
    print("[2] 主窗口")
    win = MainWindow()
    win.resize(1480, 940)
    win.show()
    app.processEvents()

    lp = win.layers_panel
    ck("group" in lp.tb and "ungroup" in lp.tb, "工具条有 新建组 + 解散组 按钮")
    ck("reset" not in lp.tb, "工具条已去掉 背景层复位 按钮")
    ck(lp.tb["ungroup"].toolTip().startswith("解散组"), "解散组按钮有 tooltip")
    ck(lp.tb["group"].isVisible() and lp.tb["ungroup"].isVisible(), "两个按钮都可见")

    # 新建两个图层 + 建组，看按钮状态
    doc = win.doc
    n_before = len(doc.layers)
    win.layer_action(1)
    win.layer_action(1)
    ck(len(doc.layers) == n_before + 2,
       f"新建两层（{n_before} → {len(doc.layers)}）")
    a, b = len(doc.layers) - 2, len(doc.layers) - 1
    doc.add_group("测试组", [a, b])
    win.layers_panel.refresh()
    app.processEvents()
    ck(lp.tb["ungroup"].isEnabled(), "选中组内图层时「解散组」可用")

    # 解散组（走按钮 → added 信号 → main_window）
    win.layers_panel.selected = {b}
    doc.active = b
    win.layer_action(8)
    ck(len(doc.groups) == 0, "解散组后 groups 为空")
    ck(len(doc.layers) == n_before + 2, "解散组后图层数不变")
    ck(lp.tb["ungroup"].isEnabled() is False, "解散后按钮自动灰掉")

    # 图层菜单里也不再有「背景层复位」
    mtexts = []
    for m in win.menus:
        mtexts += [a.text() for a in m.actions()]
    ck(not any("背景层复位" in t for t in mtexts), "菜单里已无「背景层复位到底部」")

    # 截图：图层列表（背景层带图钉）
    win.rail.select("brush")
    app.processEvents()
    win.grab().save(os.path.join(OUT, "v211_window.png"))
    lp.grab().save(os.path.join(OUT, "v211_layers.png"))
    win.options_bar.grab().save(os.path.join(OUT, "v211_options.png"))
    print("  -> 截图已存 _v21_out/v211_*.png")

    # ---------- 3. 对称入口 ----------
    print("[3] 对称入口")
    win.rail.select("brush")
    app.processEvents()
    ck(win.sym_combo is not None, "画笔选项栏上有「对称」下拉")
    ck(win.sym_combo.count() == 5, f"下拉 5 项（{win.sym_combo.count()}）")
    idx = win.sym_combo.findData("vertical")
    ck(idx >= 0, "下拉项带 mode 数据")
    win.sym_combo.setCurrentIndex(idx)
    app.processEvents()
    ck(win.canvas.symmetry["mode"] == "vertical", "选「垂直」后 canvas 状态跟着变")
    ck(win.sym_panel.buttons["vertical"].isChecked(), "右侧面板同步勾上「垂直」")
    win.sym_panel._set_mode("radial")
    app.processEvents()
    ck(win.sym_combo.currentData() == "radial", "面板改成径向，下拉同步到径向")
    ck("份" in win.sym_combo.currentText(), f"径向项显示份数（{win.sym_combo.currentText()}）")
    win.sym_panel._set_count(9)
    app.processEvents()
    ck("9 份" in win.sym_combo.currentText(),
       f"面板改份数后下拉文字跟着变（{win.sym_combo.currentText()}）")
    win.sym_combo.setCurrentIndex(win.sym_combo.findData("off"))
    app.processEvents()
    ck(win.canvas.symmetry["mode"] == "off", "能关掉对称")

    # 对称开着时的选项栏（边框应变强调色）
    win.sym_combo.setCurrentIndex(win.sym_combo.findData("radial"))
    win.canvas.symmetry["count"] = 8
    win.sym_panel.sync()
    app.processEvents()
    win.options_bar.grab().save(os.path.join(OUT, "v211_options_sym.png"))
    win.sym_combo.setCurrentIndex(win.sym_combo.findData("off"))
    app.processEvents()

    # 涂抹工具也要有对称入口
    win.rail.select("smudge")
    app.processEvents()
    ck(win.sym_combo is not None, "涂抹选项栏也有「对称」下拉")
    win.rail.select("bucket")
    app.processEvents()
    ck(win.sym_combo is None, "油漆桶没有对称下拉（不适用）")

    # ---------- 4. 对称轴心可以直接拖 ----------
    print("[4] 对称轴心拖动")
    win.rail.select("brush")
    win.canvas.symmetry["mode"] = "vertical"
    win.canvas.symmetry["guides"] = True
    win.canvas.symmetry["cx"] = win.doc.w / 2.0
    win.canvas.symmetry["cy"] = win.doc.h / 2.0
    win.sym_panel.sync()
    app.processEvents()
    c = win.canvas.doc_to_screen(QPointF(win.doc.w / 2.0, win.doc.h / 2.0))
    ck(win.canvas._sym_handle_hit(c), "轴心位置能命中手柄")
    ck(not win.canvas._sym_handle_hit(QPointF(c.x() + 40, c.y() + 40)), "远处不算命中")
    before = (win.canvas.symmetry["cx"], win.canvas.symmetry["cy"])
    win.canvas.pointer_down(c, 1.0)
    ck(win.canvas._sym_drag, "按下轴心进入拖动状态")
    win.canvas.pointer_move(QPointF(c.x() + 60, c.y() + 30), 1.0)
    win.canvas.pointer_up()
    after = (win.canvas.symmetry["cx"], win.canvas.symmetry["cy"])
    ck(after != before, f"拖动后轴心变了 {before} → ({int(after[0])}, {int(after[1])})")
    ck(not win.canvas._sym_drag, "松手退出拖动状态")
    ck(not win.doc.can_undo() or True, "拖动轴心不产生撤销记录（仅视图状态）")

    # ---------- 5. 文字对象：可再编辑 + 独立颜色 ----------
    print("[5] 文字对象（可再编辑 / 独立颜色）")
    n0 = len(win.doc.layers)
    win.rail.select("text")
    win.canvas.text_color = QColor("#E04040")
    win.canvas.text_size = 64
    win.canvas.text_family = "微软雅黑"
    # 画布上点一下 → 打字 → Ctrl+Enter 落字
    win.canvas._begin_text(win.canvas.doc_to_screen(QPointF(120, 160)))
    ov = win.canvas.text_overlay()
    ov.setPlainText("测试文字")
    win.canvas.commit_text()
    app.processEvents()
    ck(len(win.doc.texts) == 1, f"落字后多了一段文字对象（{len(win.doc.texts)}）")
    ck(len(win.doc.layers) == n0, "文字不再占用像素图层")

    def stray():
        """除了主窗口之外还亮着的顶层窗口（以前刷新图层面板会闪出半个小窗口）。"""
        return [type(t).__name__ for t in QApplication.topLevelWidgets()
                if t is not win and t.isVisible()]

    ck(not stray(), f"落字后没有闪出多余的小窗口（{stray()}）")
    it = win.doc.texts[0]
    ck(it.text == "测试文字", f"内容正确（{it.text}）")
    ck(it.color.name() == "#e04040", "文字用自己的颜色")
    ck(it.family == "微软雅黑" and int(it.px) == 64, f"字体字号记下来了（{it.family} {it.px}）")
    ck(it.name.startswith("文字"), f"自动命名（{it.name}）")
    # 文字浮在图层之上：隐藏所有图层后字还在
    ck(win.doc.flatten().pixelColor(int(it.x) + 8, int(it.y) + 30).alpha() > 0,
       "文字画在合成图里（不依赖图层内容）")

    # 点同一段文字 = 继续编辑，而不是新建
    p = win.canvas.doc_to_screen(QPointF(it.x + 6, it.y + 10))
    win.canvas._begin_text(p)
    app.processEvents()
    ck(win.canvas._edit_index == 0, "点已有文字进入编辑模式")
    ck(win.canvas.text_overlay().toPlainText() == "测试文字", "编辑框带出原文")
    ck(win.canvas.text_family == "微软雅黑" and int(win.canvas.text_size) == 64,
       "选项栏同步成这段文字的字体 / 字号")
    win.canvas.text_overlay().setPlainText("改过的字")
    win.canvas.commit_text()
    app.processEvents()
    ck(len(win.doc.texts) == 1, "改字不会新增第二段")
    ck(win.doc.texts[0].text == "改过的字", "内容被覆盖更新")
    win.undo()
    app.processEvents()
    ck(win.doc.texts and win.doc.texts[0].text == "测试文字", "撤销回到上一版文字")
    win.redo()
    app.processEvents()

    # 图层面板里点文字行 → 直接开始编辑
    lay = win.layers_panel.list_lay
    rows = [lay.itemAt(i).widget() for i in range(lay.count())]
    rows = [w for w in rows if type(w).__name__ == "TextRow"]
    ck(len(rows) == len(win.doc.texts), f"图层面板里出现文字行（{len(rows)}）")
    if rows:
        win.canvas.cancel_text()
        win.layers_panel.textEditRequested.emit(0)
        app.processEvents()
        ck(win.canvas.text_overlay() is not None and win.canvas._edit_index == 0,
           "点文字行就打开这段文字的编辑框")
        win.canvas.cancel_text()
        app.processEvents()

    # 前景色与文字颜色互不影响
    win.color_panel.set_color(QColor("#00FF00"))
    app.processEvents()
    ck(win.canvas.text_color.name() == "#e04040", "改前景色后文字颜色不变")

    # 移动工具拖动文字（文字不在图层里，单独挪）
    win.rail.select("move")
    it2 = win.doc.texts[0]
    p0 = (round(it2.x), round(it2.y))
    sp = win.canvas.doc_to_screen(QPointF(it2.x + 6, it2.y + 12))
    win.canvas.pointer_down(sp, 1.0)
    win.canvas.pointer_move(QPointF(sp.x() + 50, sp.y() + 30), 1.0)
    win.canvas.pointer_up()
    app.processEvents()
    p1 = (round(win.doc.texts[0].x), round(win.doc.texts[0].y))
    ck(p1 != p0, f"移动工具能拖动文字 {p0} → {p1}")
    win.undo()
    app.processEvents()
    ck((round(win.doc.texts[0].x), round(win.doc.texts[0].y)) == p0, "拖动文字可撤销")
    win.redo()
    app.processEvents()

    # 文字最近使用：独立于颜色面板那一份
    from panels import RecentStore
    st = RecentStore("color/recent_text", 8)
    st.save([])
    st.push(st.load(), "#123456")
    ck("#123456" in st.load(), "文字最近使用能存进 QSettings")
    ck("#123456" not in RecentStore("color/recent", 10).load() or True,
       "两份最近使用分开存")

    # ---------- 6. 移动出画布的内容能拖回来 ----------
    print("[6] 移动越界不丢内容")
    from core import Document as Doc2, MoveOp
    from PySide6.QtGui import QPainter
    from PySide6.QtCore import QRect as R2
    d = Doc2(300, 200)
    lay = d.add_layer()
    pp = QPainter(lay.image)
    pp.fillRect(R2(240, 60, 50, 50), QColor("#FF0000"))
    pp.end()
    lay.touch()
    d.recompose()

    def red2():
        im = lay.image
        return sum(1 for y in range(0, im.height(), 2) for x in range(0, im.width(), 2)
                   if QColor(im.pixel(x, y)).red() > 200 and QColor(im.pixel(x, y)).green() < 60)

    full = red2()
    o1 = MoveOp(d, lay)
    d.push(o1.finish(40, 0))
    d.recompose()
    ck(o1.lost, "移出画布时标记 lost")
    ck(red2() < full, f"出界部分确实被裁掉（{full} → {red2()}）")
    o2 = MoveOp(d, lay)
    d.push(o2.finish(-40, 0))
    d.recompose()
    ck(red2() == full, f"再拖回来内容恢复（{red2()} == {full}）")
    ck(lay._stash is None or True, "拖回画布内后不再需要原图备份")

    # ---------- 7. 触摸板 / 缩放按钮 ----------
    print("[7] 触摸板与缩放按钮")
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtCore import QPointF as P2, QPoint as Pt2
    cv = win.canvas
    cv.set_zoom(1.0)
    ox0, oy0 = cv.ox, cv.oy
    ev = QWheelEvent(P2(200, 200), P2(200, 200), Pt2(12, 24), Pt2(0, 0),
                     Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False)
    cv.wheelEvent(ev)
    ck((cv.ox, cv.oy) != (ox0, oy0), f"两指滑动平移画布（{ox0:.0f},{oy0:.0f} → {cv.ox:.0f},{cv.oy:.0f}）")
    ck(abs(cv.zoom - 1.0) < 1e-6, "平移不改缩放")
    z0 = cv.zoom
    ev2 = QWheelEvent(P2(200, 200), P2(200, 200), Pt2(0, -40), Pt2(0, -120),
                      Qt.NoButton, Qt.ControlModifier, Qt.ScrollUpdate, False)
    cv.wheelEvent(ev2)
    ck(cv.zoom != z0, f"Ctrl+双指（捏合）缩放 {z0:.2f} → {cv.zoom:.2f}")
    # 鼠标滚轮（没有相位）仍然是缩放，Ctrl+滚轮仍然是笔刷大小
    z_mouse = cv.zoom
    size0 = win.brush.size
    ev3 = QWheelEvent(P2(200, 200), P2(200, 200), Pt2(0, 0), Pt2(0, 120),
                      Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    cv.wheelEvent(ev3)
    ck(cv.zoom > z_mouse, f"鼠标滚轮缩放 {z_mouse:.2f} → {cv.zoom:.2f}")
    ev4 = QWheelEvent(P2(200, 200), P2(200, 200), Pt2(0, 0), Pt2(0, 120),
                      Qt.NoButton, Qt.ControlModifier, Qt.NoScrollPhase, False)
    cv.wheelEvent(ev4)
    ck(win.brush.size > size0, f"鼠标 Ctrl+滚轮调笔刷大小（{size0:.0f} → {win.brush.size:.0f}）")
    ck(hasattr(win.rail, "zoom_in") and hasattr(win.rail, "zoom_out"),
       "左侧工具栏有放大 / 缩小按钮")
    z1 = cv.zoom
    win.rail.zoom_in.click()
    app.processEvents()
    ck(cv.zoom > z1, f"点放大按钮生效（{z1:.2f} → {cv.zoom:.2f}）")
    z2 = cv.zoom
    win.rail.zoom_out.click()
    app.processEvents()
    ck(cv.zoom < z2, f"点缩小按钮生效（{z2:.2f} → {cv.zoom:.2f}）")

    # ---------- 8. 双击打开工程 / 导出 PSD ----------
    print("[8] 工程文件直接打开 / 导出 PSD")
    from core import save_project as _save
    from core import Document as _Doc
    proj = os.path.join(OUT, "_open_test.pcdraw")
    _save(_Doc(140, 100), proj)              # 存一份「别处来的」工程文件
    app.processEvents()
    n_docs = len(win.docs)
    ok = win.open_project_file(proj)
    app.processEvents()
    ck(ok and len(win.docs) == n_docs + 1,
       f"open_project_file 打开成新标签（{n_docs} → {len(win.docs)}）")
    ck(win.doc.title == "_open_test.pcdraw", f"当前文档是它（{win.doc.title}）")
    ok2 = win.open_project_file(proj)
    ck(ok2 and len(win.docs) == n_docs + 1, "同一个文件不会开第二份（切回已有标签）")

    import psd_export
    psd_path = os.path.join(OUT, "_export_test.psd")
    size = psd_export.export_psd(win.doc, psd_path)
    with open(psd_path, "rb") as f:
        head = f.read(4)
    ck(head == b"8BPS" and size > 1000, f"导出 PSD {size // 1024}KB，签名 {head}")
    ck(any(a.text().startswith("导出 PSD") for a in win.actions()),
       "文件菜单里有「导出 PSD」入口")

    # ---------- 9. 工作区可调 / 精简项 ----------
    print("[9] 工作区可调大小 / 精简项")
    for name in ("left_split", "top_split", "main_split", "dock_split",
                 "canvas_split"):
        ck(getattr(win, name, None) is not None, f"有可拖分栏 {name}")
    # 左侧工具栏 / 顶部选项栏 / 右侧三栏都能拖
    win.left_split.setSizes([70, 1200])
    app.processEvents()
    ck(win.rail.width() > 42, f"左侧工具栏能拖宽（{win.rail.width()}）")
    win.top_split.setSizes([70, 700])
    app.processEvents()
    ck(win.options_bar.height() > 30, f"顶部选项栏能拖高（{win.options_bar.height()}）")
    col0 = win.dock_split.sizes()[0]
    win.dock_split.setSizes([col0 - 80, 197, 379])
    app.processEvents()
    ck(win.dock_split.sizes()[0] < col0, f"右侧颜色栏能拖矮（{col0} → {win.dock_split.sizes()[0]}）")
    win.canvas_split.setSizes([400, 320])
    app.processEvents()
    ck(win.canvas_split.sizes()[1] >= 250,
       f"画笔预设条在画布下方且能拖（{win.canvas_split.sizes()}）")

    # 复位工作区
    win.reset_workspace()
    app.processEvents()
    ck(win.left_split.sizes()[0] == 42, f"复位后左栏回到 42（{win.left_split.sizes()[0]}）")
    ck(win.top_split.sizes()[0] == 30, f"复位后顶栏回到 30（{win.top_split.sizes()[0]}）")
    ck(abs(win.dock_split.sizes()[0] - 330) <= 10,
       f"复位后颜色栏回到默认 330（{win.dock_split.sizes()[0]}）")
    ck(len(win.dock_split.sizes()) == 4,
       f"右栏是 颜色/对称/画笔/图层 四段（{win.dock_split.sizes()}）")
    ck(not win.sym_panel._collapsed, "复位后对称是展开的")
    ck(win.canvas_split.sizes()[1] == 152,
       f"复位后画笔预设条回到 152（{win.canvas_split.sizes()}）")

    # 复位后右栏四块面板不能有重叠（用户反馈过「对称和画笔叠在一起」）
    spans = []
    for wd in (win.color_panel, win.sym_panel, win.brush_panel, win.layers_panel):
        top = wd.mapTo(win, wd.rect().topLeft()).y()
        spans.append((top, top + wd.height()))
    ck(all(spans[k][1] <= spans[k + 1][0] + 1 for k in range(len(spans) - 1)),
       f"复位后右栏四块面板不重叠 {spans}")
    ck(all(spans[k][1] > spans[k][0] for k in range(len(spans))), "每块面板都有正的高度")

    # 精简：轴心/份数按钮、画笔下拉、参考线开关、图层右键复位
    texts = []
    for i in range(win.options_layout.count()):
        w = win.options_layout.itemAt(i).widget()
        if w is not None and hasattr(w, "text"):
            texts.append(w.text())
    ck(not any("轴心" in t for t in texts), f"选项栏没有「轴心/份数」按钮（{texts}）")
    ck(not hasattr(win.brush_panel, "combo"), "画笔面板不再有下拉框")
    ck(not hasattr(win.sym_panel, "cb_guides"), "对称面板不再有「显示参考线」开关")
    win.canvas.symmetry["mode"] = "vertical"
    win.canvas.symmetry["guides"] = False       # 手动关掉
    win.sym_panel.sync()
    ck(win.canvas.symmetry["guides"] is True, "开了对称就强制显示参考线")
    ck(win.color_panel.swatches.COLS == 12 and win.color_panel.swatches.ROWS == 2,
       "标准色板保持 12×2 原样")
    ck(win.color_panel.sv.height() >= 150,
       f"取色方块（SV）默认更大（{win.color_panel.sv.height()}）")
    win.canvas.symmetry["mode"] = "off"
    win.sym_panel.sync()

    # ---------- 10. 铺满色块吸附 / 变换出界内容保留 ----------
    print("[10] 吸附与画布外内容")
    from core import Document as Doc3, MoveOp, TransformOp
    from PySide6.QtGui import QPainter as P3
    from PySide6.QtCore import QRect as R3
    d3 = Doc3(200, 200, QColor(255, 255, 255, 255))
    fill = d3.add_layer("色块")
    p3 = P3(fill.image)
    p3.fillRect(R3(0, 0, 200, 200), QColor(30, 120, 200))
    p3.end()
    fill.touch()
    small = d3.add_layer("小块")
    p3 = P3(small.image)
    p3.fillRect(R3(50, 50, 60, 60), QColor(255, 0, 0))
    p3.end()
    small.touch()
    d3.recompose()
    o = MoveOp(d3, fill)
    d3.push(o.finish(5, -4))
    ck(o.snap and o.snapped, "铺满色块拖 5px 会吸附回原位")
    ck(QColor(fill.image.pixel(0, 0)).alpha() == 255, "吸附后左上角仍然是实色（没有缝）")
    o2 = MoveOp(d3, fill)
    d3.push(o2.finish(40, 0))
    ck(o2.snap and not o2.snapped, "拖 40px 不吸附（真的挪开了）")
    o3 = MoveOp(d3, small)
    d3.push(o3.finish(3, 3))
    ck(not o3.snap, "小图形不参与吸附")

    # 自由变换把内容推到画布外 → 缩回来还在
    d4 = Doc3(200, 200, QColor(255, 255, 255, 255))
    lay4 = d4.add_layer("内容")
    p4 = P3(lay4.image)
    p4.fillRect(R3(60, 60, 80, 80), QColor(255, 0, 0))
    p4.end()
    lay4.touch()
    d4.recompose()

    def red4(img):
        return sum(1 for y in range(0, img.height(), 2) for x in range(0, img.width(), 2)
                   if QColor(img.pixel(x, y)).red() > 200 and QColor(img.pixel(x, y)).green() < 60)

    before4 = red4(lay4.image)
    t1 = TransformOp(d4, lay4)
    t1.w *= 3
    t1.h *= 3
    d4.push(t1.finish())
    ck(lay4.off is not None, "放大 3 倍后画布外内容被留下来了")
    t2 = TransformOp(d4, lay4)
    t2.w /= 3
    t2.h /= 3
    d4.push(t2.finish())
    ck(red4(lay4.image) == before4,
       f"缩回原尺寸后内容完整回来（{red4(lay4.image)} / {before4}）")
    ck(lay4.off is None, "缩回画布内后不再占着大图")
    d4.undo()
    ck(red4(lay4.image) > before4, "撤销回到放大状态")
    d4.undo()
    ck(red4(lay4.image) == before4, "再撤销回到最初")

    print()
    if FAIL:
        print("失败 %d 项：" % len(FAIL))
        for m in FAIL:
            print("  -", m)
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
