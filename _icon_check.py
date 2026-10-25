# -*- coding: utf-8 -*-
"""把新图标渲染成一张对照图（16px 实际尺寸 + 4x 放大），确认一眼能认出。"""
import sys

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication

import icons
from theme import C, apply_theme

app = QApplication(sys.argv)
apply_theme(app)

NAMES = ["group", "ungroup", "pin", "layers", "plus", "merge", "reset", "symmetry"]
CELL_W, CELL_H = 120, 110
img = QImage(CELL_W * len(NAMES), CELL_H, QImage.Format_ARGB32)
img.fill(QColor(C.CARD))
p = QPainter(img)
f = QFont("Microsoft YaHei UI", 8)
p.setFont(f)
for i, n in enumerate(NAMES):
    x = i * CELL_W
    pm16 = icons.pixmap(n, C.ICON, 16, 1.0)
    pm32 = icons.pixmap(n, C.ICON, 32, 1.0)
    pm64 = icons.pixmap(n, C.ICON, 64, 1.0)
    p.drawPixmap(x + 12, 16, pm64)
    p.drawPixmap(x + 84, 16, pm32)
    p.drawPixmap(x + 84, 56, pm16)
    p.setPen(QColor(C.TEXT_DIM))
    p.drawText(QRect(x + 8, 86, CELL_W - 16, 18), Qt.AlignLeft | Qt.AlignVCenter, n)
p.end()
img.save("_v21_out/icons_new.png")
print("ok", img.width(), "x", img.height())
