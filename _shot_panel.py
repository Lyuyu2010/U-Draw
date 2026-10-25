# -*- coding: utf-8 -*-
"""用真实窗口截 2.15.15 验收图：组选中时文字也一起被选中 + 文字多选。"""
import os, sys
sys.path.insert(0, r"C:\Users\20688\Desktop\U Draw Project files\app")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor
from PySide6.QtCore import QTimer, Qt

app = QApplication([])
import theme  # noqa
from main_window import MainWindow
from core import TextItem

OUT = r"C:\Users\20688\Desktop\U Draw Project files\交付内容"

win = MainWindow()
win.resize(1500, 950)
win.show()

doc = win.doc
doc.layers[0].image.fill(QColor("#ffffff"))
doc.layers[0].has_content = True
doc.add_layer("线稿")
doc.add_layer("上色")
doc.add_text(TextItem("我的天", 150, 180, "SimSun", 120))
doc.texts[0].name = "文字 我的天"
doc.add_text(TextItem("标题", 150, 360, "SimSun", 64))
doc.texts[1].name = "文字 标题"
gid = doc.add_group("标题组", [1], [0])       # 组里同时有图层和文字

panel = win.layers_panel
panel.refresh()
panel.select_group(gid)                        # 单击组标题 → 图层和文字一起选中
win.canvas.update()


def shoot():
    # 滚到组标题那一行，保证组和组里的文字都在画面里
    grows = [w for w in panel._rows() if w.__class__.__name__ == "GroupRow"]
    if grows:
        panel.scroll.ensureWidgetVisible(grows[0], 0, 60)
    app.processEvents()
    win.grab().save(os.path.join(OUT, "界面_2.15.15.png"))
    panel.grab().save(os.path.join(OUT, "图层面板_2.15.15.png"))
    app.quit()


QTimer.singleShot(700, shoot)
sys.exit(app.exec())
