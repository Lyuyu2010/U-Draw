# -*- coding: utf-8 -*-
"""复制 / 粘贴回归：整层、选区内、跨文档、跨窗口、系统剪贴板。

注意：v3.0 起 **Ctrl+C 直接生成一个新图层**（保留原内容、可马上拖动），
不再是「先存剪贴板、再粘贴」两步。剪贴板照写一份，跨文档 / 贴到别的软件
仍然能用 —— 所以下面每处复制都会多一层，计数用「前 / 后」对比，不写死数字。
"""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, r"C:\Users\20688\Desktop\U Draw Project files\app")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QAction, QColor, QImage, QPainter
from PySide6.QtCore import QRect

app = QApplication([])
from main_window import MainWindow, PASTE_BUF

ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("  OK  " if cond else " FAIL ") + name + ("  " + str(extra) if extra else ""))


win = MainWindow()
win.resize(1200, 800)
win.show()
doc = win.doc
layer = doc.layer
# 在 (100,100)-(300,200) 画一块红
p = QPainter(layer.image)
p.fillRect(QRect(100, 100, 200, 100), QColor(220, 40, 40))
p.end()
layer.has_content = True
doc.recompose()

# 1. 整层复制 → 直接出新图层（保留原层）；再粘贴 → 又一层
n0 = len(doc.layers)
win.copy_selection()
check("复制整层进了内部剪贴板", PASTE_BUF["image"] is not None
      and PASTE_BUF["image"].size() == layer.image.size())
check("复制也进了系统剪贴板", not QApplication.clipboard().image().isNull())
check("复制不动图层结构（跟着当前图层）", len(doc.layers) == n0,
      f"{n0}->{len(doc.layers)}")
check("复制不改原内容", layer.image.pixelColor(150, 150).red() > 180,
      layer.image.pixelColor(150, 150).name())

win.paste_clipboard()
check("粘贴出一个新图层", len(doc.layers) == n0 + 1, f"{n0}->{len(doc.layers)}")
new_layer = doc.layers[doc.active]
check("粘贴的图层名是「粘贴 N」", new_layer.name.startswith("粘贴"), new_layer.name)
check("原位粘贴：红色块还在 100,100",
      new_layer.image.pixelColor(150, 150).red() > 180,
      new_layer.image.pixelColor(150, 150).name())
doc.undo()
check("粘贴可撤销", len(doc.layers) == n0, len(doc.layers))

# 2. 选区复制：只复制选区那一块，位置记左上角
from PySide6.QtGui import QPainterPath
path = QPainterPath()
path.addRect(QRect(100, 100, 60, 50))
doc.selection = path
n2 = len(doc.layers)
win.copy_selection()
check("选区复制：只复制选区大小",
      PASTE_BUF["image"].width() == 60 and PASTE_BUF["image"].height() == 50,
      f"{PASTE_BUF['image'].width()}x{PASTE_BUF['image'].height()}")
check("选区复制：位置记的是选区左上角",
      PASTE_BUF["pos"] == QRect(100, 100, 60, 50).topLeft())
check("选区复制也不动图层结构", len(doc.layers) == n2, len(doc.layers))
win.paste_clipboard()
check("粘贴出来的图层只含选区那块",
      doc.layers[doc.active].image.pixelColor(120, 120).red() > 180)
doc.undo()
doc.selection = None

# 3. 跨文档粘贴（同一窗口的另一个文档）
win._add_doc(win.make_blank_doc(doc.w, doc.h, QColor(255, 255, 255, 255)))
win._switch_doc(0)
win.copy_selection()          # 复制原文档的整层（顺带在自己身上多一层，无所谓）
win._switch_doc(1)
n_before = len(win.doc.layers)
win.paste_clipboard()
check("跨文档粘贴成功", len(win.doc.layers) == n_before + 1,
      f"{n_before}->{len(win.doc.layers)}")
check("同尺寸跨文档：贴在原坐标",
      win.doc.layers[win.doc.active].image.pixelColor(150, 150).red() > 180)
win.doc.modified = False      # 免得 _close_doc 弹「要保存吗」的模态框
win._close_doc(1)

# 4. 跨窗口（独立窗口共用同一个内部剪贴板）
win2 = MainWindow()
win2.resize(900, 700)
win2.show()
win._switch_doc(0)
win.copy_selection()
n3 = len(win2.doc.layers)
win2.paste_clipboard()
check("独立窗口里也能粘贴", len(win2.doc.layers) == n3 + 1,
      f"{n3}->{len(win2.doc.layers)}")

# 5. 系统剪贴板里换了一张图（比如截图），粘贴用它
ext = QImage(40, 30, QImage.Format_ARGB32)
ext.fill(QColor(20, 200, 60))
QApplication.clipboard().setImage(ext)
win.paste_clipboard()
got = win.doc.layers[win.doc.active]
cx, cy = win.doc.w // 2, win.doc.h // 2       # 尺寸不同 → 居中粘贴
check("系统剪贴板的新图会被用上", got.image.pixelColor(cx, cy).green() > 150,
      got.image.pixelColor(cx, cy).name())

# 6. Ctrl+C / Ctrl+V 没有注册成 QAction（否则会抢走文字编辑框里的复制粘贴）
bound = set()
for a in win.findChildren(QAction):
    s = a.shortcut().toString()
    if s:
        bound.add(s)
check("Ctrl+C / Ctrl+V 没被注册成窗口快捷键",
      "Ctrl+C" not in bound and "Ctrl+V" not in bound, f"{sorted(bound)}")

print("\n结果:", "全部通过" if ok else "有失败项")
sys.exit(0 if ok else 1)
