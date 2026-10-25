# -*- coding: utf-8 -*-
"""v2.1 界面自测：把主窗口在几个工具状态下截下来，确认布局没被撑坏。"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from PySide6.QtWidgets import QApplication

import theme
from main_window import MainWindow

OUT = os.path.join(HERE, "_v21_out")


def main():
    os.makedirs(OUT, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)
    theme.apply_theme(app)
    win = MainWindow()
    win.resize(1480, 940)
    win.show()
    app.processEvents()

    for tool in ("brush", "smudge", "text", "bucket"):
        win.rail.select(tool)
        app.processEvents()
        p = os.path.join(OUT, f"gui_{tool}.png")
        win.grab().save(p)
        print("->", p)

    # 对称面板：径向 8 份
    win.canvas.symmetry["mode"] = "radial"
    win.canvas.symmetry["count"] = 8
    win.sym_panel.sync()
    win.rail.select("brush")
    win.canvas.update()
    app.processEvents()
    p = os.path.join(OUT, "gui_symmetry.png")
    win.grab().save(p)
    print("->", p)

    # 文字工具：在画布上落一段字，确认能进图层、能撤销
    win.rail.select("text")
    win.canvas.text_family = win.canvas.text_family
    win.canvas.text_size = 64
    win.canvas._begin_text(win.canvas.doc_to_screen(__import__("PySide6").QtCore.QPointF(200, 260)))
    ov = win.canvas.text_overlay()
    ov.setPlainText("U Draw 2.1 对称 · 涂抹 · 文字")
    win.canvas.commit_text()
    win.canvas.update()
    app.processEvents()
    p = os.path.join(OUT, "gui_text_committed.png")
    win.grab().save(p)
    print("->", p, "undo:", win.doc.can_undo())
    win.undo()
    print("   undo ok:", not win.doc.can_undo())
    return 0


if __name__ == "__main__":
    sys.exit(main())
