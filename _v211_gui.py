# -*- coding: utf-8 -*-
"""v2.1.1 界面截图：颜色面板（最近使用）/ 文字选项栏 / 对称高亮。"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from PySide6.QtCore import QPointF, Qt
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

    # 颜色面板：灌一些「最近使用」看看效果
    cp = win.color_panel
    cp._recent = ["#E04040", "#F2B33D", "#3DBE7A", "#3D8BF2", "#8B5CF6",
                  "#111111", "#FFFFFF"]
    cp.recent.set_colors(cp._recent)
    cp.set_color(QColor("#E04040"))
    app.processEvents()
    win.grab().save(os.path.join(OUT, "v211_window_full.png"))
    cp.grab().save(os.path.join(OUT, "v211_color_panel.png"))
    print("-> color panel")

    # 文字选项栏：文字颜色 + 最近使用
    win.rail.select("text")
    win.canvas.text_color = QColor("#E04040")
    win._text_recent = ["#E04040", "#1E1E1E", "#FFFFFF", "#3D8BF2"]
    win._build_options()
    app.processEvents()
    win.options_bar.grab().save(os.path.join(OUT, "v211_text_options.png"))
    print("-> text options")

    # 对称开启时的画笔选项栏 + 面板
    win.rail.select("brush")
    win.canvas.symmetry["mode"] = "radial"
    win.canvas.symmetry["count"] = 8
    win.sym_panel.sync()
    win._sync_sym_bar()
    win.sym_panel.set_collapsed(False)
    app.processEvents()
    win.options_bar.grab().save(os.path.join(OUT, "v211_sym_bar.png"))
    win.sym_panel.grab().save(os.path.join(OUT, "v211_sym_panel.png"))
    win.grab().save(os.path.join(OUT, "v211_window_sym.png"))
    print("-> sym bar + panel")
    return 0


if __name__ == "__main__":
    sys.exit(main())
