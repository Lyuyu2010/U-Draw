# -*- coding: utf-8 -*-
"""文字对象 + 新建文档背景锁定的界面截图。"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor
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
    c = win.canvas

    # 新建文档：白底应该「背景锁定 + 图层 1」
    print("新建白底：", [(l.name, l.locked) for l in win.doc.layers])

    win.rail.select("text")
    c.text_family = "微软雅黑"
    for i, (txt, px, color, pos) in enumerate((
            ("我的的我", 72, "#1E1E1E", (260, 160)),
            ("请问", 56, "#2B7BD8", (520, 420)))):
        c.text_size = px
        c.text_color = QColor(color)
        c._begin_text(c.doc_to_screen(QPointF(*pos)))
        c.text_overlay().setPlainText(txt)
        c.commit_text()
        app.processEvents()
    print("文字对象：", [(t.name, t.text, t.color.name()) for t in win.doc.texts])
    win.grab().save(os.path.join(OUT, "v212_text_rows.png"))
    win.layers_panel.grab().save(os.path.join(OUT, "v212_layers.png"))

    # 点文字行 → 打开编辑框
    win.edit_text(0)
    app.processEvents()
    win.grab().save(os.path.join(OUT, "v212_text_edit.png"))
    print("编辑中：", c._edit_index, c.text_overlay().toPlainText())
    c.cancel_text()
    app.processEvents()

    # 导出 PSD 检查文字也在
    import psd_export
    p = os.path.join(OUT, "text_layers.psd")
    n = psd_export.export_psd(win.doc, p)
    print("PSD:", n // 1024, "KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
