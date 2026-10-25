# -*- coding: utf-8 -*-
"""复制 / 粘贴回归：整层、选区内、跨文档、跨窗口、系统剪贴板。"""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, r"C:\Users\20688\Desktop\U Draw Project files\app")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QAction, QColor, QImage, QPainter, QKeyEvent
from PySide6.QtCore import QPointF, QRect, Qt

app = QApplication([])
from main_window import MainWindow, PASTE_BUF
import main_window as mw

ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("  OK  " if cond else " FAIL ") + name + ("  " + extra if extra else ""))


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

# 1. 整层复制 + 粘贴
n0 = len(doc.layers)
win.copy_selection()
check("复制整层进了内部剪贴板", PASTE_BUF["image"] is not None
      and PASTE_BUF["image"].size() == layer.image.size())
check("复制也进了系统剪贴板",
      not QApplication.clipboard().image().isNull())
win.paste_clipboard()
check("粘贴出一个新图层", len(doc.layers) == n0 + 1, f"{n0}->{len(doc.layers)}")
new_layer = doc.layers[doc.active]
check("粘贴的图层名是「粘贴 N」", new_layer.name.startswith("粘贴"), new_layer.name)
check("原位粘贴：红色块还在 100,100",
      new_layer.image.pixelColor(150, 150).red() > 180,
      new_layer.image.pixelColor(150, 150).name())
doc.undo()
check("粘贴可撤销", len(doc.layers) == n0)

# 2. 选区复制
doc.set_selection_path = None
from PySide6.QtGui import QPainterPath
path = QPainterPath()
path.addRect(QRect(100, 100, 60, 50))
doc.selection = path
win.copy_selection()
check("选区复制：只复制选区大小",
      PASTE_BUF["image"].width() == 60 and PASTE_BUF["image"].height() == 50,
      f"{PASTE_BUF['image'].width()}x{PASTE_BUF['image'].height()}")
check("选区复制：位置记的是选区左上角", PASTE_BUF["pos"] == QRect(100, 100, 60, 50).topLeft())
win.paste_clipboard()
check("选区粘贴回到原位置",
      doc.layers[doc.active].image.pixelColor(120, 120).red() > 180)
doc.undo()
doc.selection = None

# 3. 跨文档粘贴（同一窗口的另一个文档）
win._add_doc(win.make_blank_doc(doc.w, doc.h, QColor(255, 255, 255, 255)))
win.copy_selection()          # 先在新文档上复制（空的），再切回
win._switch_doc(0)
win.copy_selection()          # 复制原文档的整层
other = win.docs[1]
win._switch_doc(1)
win.paste_clipboard()
check("跨文档粘贴成功", len(win.doc.layers) == 3, f"{len(win.doc.layers)}")
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
n2 = len(win2.doc.layers)
win2.paste_clipboard()
check("独立窗口里也能粘贴", len(win2.doc.layers) == n2 + 1,
      f"{n2}->{len(win2.doc.layers)}")

# 5. 快捷键：Ctrl+C / Ctrl+V 走 keyPressEvent
win.canvas.setFocus()
n1 = len(win.doc.layers)
win.copy_selection()
win.paste_clipboard()
check("复制粘贴后图层 +1", len(win.doc.layers) == n1 + 1)

# 6. 系统剪贴板里换了一张图（比如截图），粘贴用它
ext = QImage(40, 30, QImage.Format_ARGB32)
ext.fill(QColor(20, 200, 60))
QApplication.clipboard().setImage(ext)
win.paste_clipboard()
got = win.doc.layers[win.doc.active]
cx, cy = win.doc.w // 2, win.doc.h // 2       # 尺寸不同 → 居中粘贴
check("系统剪贴板的新图会被用上", got.image.pixelColor(cx, cy).green() > 150,
      got.image.pixelColor(cx, cy).name())

# 7. Ctrl+C / Ctrl+V 没有注册成 QAction（否则会抢走文字编辑框里的复制粘贴）
bound = set()
for a in win.findChildren(QAction):
    s = a.shortcut().toString()
    if s:
        bound.add(s)
check("Ctrl+C / Ctrl+V 没被注册成窗口快捷键",
      "Ctrl+C" not in bound and "Ctrl+V" not in bound, f"{sorted(bound)}")

print("\n结果:", "全部通过" if ok else "有失败项")
