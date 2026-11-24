# -*- coding: utf-8 -*-
"""v3.0：文件 → 导入图片为图层"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QFileDialog

app = QApplication([])
import theme

theme.apply_theme(app)
from main_window import MainWindow

ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("  OK  " if cond else " FAIL ") + name + ("  " + str(extra) if extra else ""))


win = MainWindow()
win.show()
app.processEvents()

file_menu = [a.text() for a in win.menus[0].actions() if a.text()]
check("文件菜单里有「导入图片为图层…」", "导入图片为图层…" in file_menu, file_menu)
check("原来的「打开图片」改成「打开图片为新文档…」",
      "打开图片为新文档…" in file_menu, file_menu)

# 造两张图：小图（居中）、和画布同尺寸（原位）
tmp = os.path.join(os.environ["TEMP"], "_import_small.png")
img = QImage(120, 80, QImage.Format_ARGB32)
img.fill(QColor(220, 60, 70))
img.save(tmp, "PNG")

tmp2 = os.path.join(os.environ["TEMP"], "_import_full.png")
img2 = QImage(win.doc.w, win.doc.h, QImage.Format_ARGB32)
img2.fill(QColor(0, 0, 0, 0))
img2.fill(QColor(40, 160, 90))
img2.save(tmp2, "PNG")

QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (tmp, ""))

n0 = len(win.doc.layers)
win.import_image_as_layer()
app.processEvents()
check("导入后多了一个图层", len(win.doc.layers) == n0 + 1, len(win.doc.layers))
nl = win.doc.layers[win.doc.active]
check("图层名是「图片 N」", nl.name.startswith("图片"), nl.name)
doc = win.doc
check("小图居中放置",
      nl.image.pixelColor(doc.w // 2, doc.h // 2).name() == "#dc3c46",
      nl.image.pixelColor(doc.w // 2, doc.h // 2).name())
check("小图四角没有内容", nl.image.pixelColor(2, 2).alpha() == 0)
win.undo()
app.processEvents()
check("导入可撤销", len(win.doc.layers) == n0, len(win.doc.layers))

# 同尺寸图按原位贴
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (tmp2, ""))
win.import_image_as_layer()
app.processEvents()
nl = win.doc.layers[win.doc.active]
check("同尺寸图按原位放置",
      nl.image.pixelColor(5, 5).name() == "#28a05a",
      nl.image.pixelColor(5, 5).name())
win.undo()
app.processEvents()

# 取消选择文件 = 什么都不做
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))
n1 = len(win.doc.layers)
win.import_image_as_layer()
app.processEvents()
check("取消文件对话框不改文档", len(win.doc.layers) == n1)

print("\n结果:", "全部通过" if ok else "有失败项")
sys.exit(0 if ok else 1)
