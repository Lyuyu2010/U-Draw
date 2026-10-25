# -*- coding: utf-8 -*-
"""拖入图片的回归：落点、图层名、画布外内容、撤销。"""
import os, sys, tempfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, r"C:\Users\20688\Desktop\U Draw Project files\app")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QImage
from PySide6.QtCore import QPointF, Qt

app = QApplication([])
from main_window import MainWindow

ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("  OK  " if cond else " FAIL ") + name + ("  " + extra if extra else ""))


tmp = tempfile.mkdtemp(prefix="udraw_drop_")
p1 = os.path.join(tmp, "小猫.png")
im = QImage(120, 80, QImage.Format_ARGB32)
im.fill(QColor(30, 120, 220, 255))
im.save(p1)
p2 = os.path.join(tmp, "背景图.jpg")
im2 = QImage(400, 300, QImage.Format_RGB32)
im2.fill(QColor(240, 200, 60))
im2.save(p2)
bad = os.path.join(tmp, "notimage.png")
open(bad, "wb").write(b"not a png")

win = MainWindow()
win.resize(1200, 800)
win.show()
doc = win.doc
n0 = len(doc.layers)

win._on_files_dropped([p1], QPointF(200, 150))
check("拖入一张图 = 多一个图层", len(doc.layers) == n0 + 1, f"{n0}->{len(doc.layers)}")
lay = doc.layers[doc.active]
check("图层名用文件名", lay.name == "小猫", lay.name)
# 图片 120x80 以 (200,150) 为中心 → 左上角 (140,110)
c = lay.image.pixelColor(200, 150)
check("图片落在鼠标位置", c.blue() > 180 and c.red() < 80, c.name())
check("画布外部分被保留（set_ext 生效）", lay.off is None or lay.off.width() >= 120)

win._on_files_dropped([p1, p2], QPointF(600, 400))
check("一次拖两张 = 两个图层", len(doc.layers) == n0 + 3, f"{len(doc.layers)}")

n_before = len(doc.layers)
win._on_files_dropped([bad], QPointF(300, 300))
check("读不出的文件不会加图层", len(doc.layers) == n_before)

# 撤销：一次拖入算一步（5 层 → 撤销回到 3 层）
n_after_two = len(doc.layers)
doc.undo()
check("撤销一次拖入（两张）", len(doc.layers) == n_after_two - 2,
      f"{n_after_two}->{len(doc.layers)}")

# 拖到画布外：内容仍在（off）
win._on_files_dropped([p1], QPointF(-100, -100))
lay2 = doc.layers[doc.active]
check("拖到画布外也不丢内容", lay2.off is not None or lay2.image.pixelColor(0, 0).alpha() > 0)

# 文件后缀过滤（Canvas._drop_files）
from canvas import Canvas
from PySide6.QtCore import QMimeData, QUrl
md = QMimeData()
md.setUrls([QUrl.fromLocalFile(p1), QUrl.fromLocalFile(tmp + "/x.txt")])
open(tmp + "/x.txt", "w").write("hi")
md2 = QMimeData()
md2.setUrls([QUrl.fromLocalFile(p1), QUrl.fromLocalFile(tmp + "/x.txt")])
got = Canvas._drop_files(md2)
check("只挑图片后缀", [os.path.basename(g) for g in got] == [os.path.basename(p1)],
      f"{got}")

print("\n结果:", "全部通过" if ok else "有失败项")
