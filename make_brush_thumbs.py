# -*- coding: utf-8 -*-
"""生成内置笔刷缩略图。改内置参数后运行一次即可。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor

import brushes
import core
import brush_thumbs

app = QApplication.instance() or QApplication([])
brush_thumbs.THUMB_DIR.mkdir(parents=True, exist_ok=True)
brush_thumbs.POPUP_DIR.mkdir(parents=True, exist_ok=True)
made = popup = 0
for brush in brushes.DEFAULTS:
    path = brush_thumbs.thumb_path(brush)
    if not path.is_file():
        image = core.preview_image(brush, brush_thumbs.THUMB_W, brush_thumbs.THUMB_H,
                                   QColor(226, 226, 226), brush_thumbs.THUMB_SS)
        image.save(str(path), "PNG")
        made += 1
    path = brush_thumbs.popup_path(brush)
    if not path.is_file():
        image = core.preview_image(brush, brush_thumbs.POPUP_W, brush_thumbs.POPUP_H,
                                   QColor(226, 226, 226), brush_thumbs.POPUP_SS)
        image.save(str(path), "PNG")
        popup += 1
print("thumbnails", len(brushes.DEFAULTS), "new", made, "popup", popup,
      "dirs", brush_thumbs.THUMB_DIR, brush_thumbs.POPUP_DIR)
