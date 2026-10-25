# -*- coding: utf-8 -*-
"""内置笔刷缩略图缓存：随程序预生成，滚动时不再逐支实时渲染。"""
import hashlib
import sys
from pathlib import Path

from PySide6.QtGui import QColor, QPixmap

from core import Brush, preview_image

THUMB_W, THUMB_H, THUMB_SS = 68, 35, 3
THUMB_COLOR = QColor(226, 226, 226)
POPUP_W, POPUP_H, POPUP_SS = 316, 108, 2


def _data_dir(name: str) -> Path:
    here = Path(__file__).resolve().parent
    roots = [here]
    if getattr(sys, "_MEIPASS", None):
        roots += [Path(sys._MEIPASS), Path(sys._MEIPASS) / "app"]
    for root in roots:
        candidate = root / name
        if candidate.is_dir():
            return candidate
    return here / name


THUMB_DIR = _data_dir("brush_thumbs")
POPUP_DIR = _data_dir("brush_thumbs_popup")


def _key(brush: Brush, w: int, h: int, ss: int) -> str:
    fields = tuple(getattr(brush, f) for f in Brush.FIELDS)
    raw = repr((fields, w, h, ss, THUMB_COLOR.rgba())).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def thumb_key(brush: Brush) -> str:
    return _key(brush, THUMB_W, THUMB_H, THUMB_SS)


def thumb_path(brush: Brush) -> Path:
    return THUMB_DIR / (thumb_key(brush) + ".png")


def popup_path(brush: Brush) -> Path:
    return POPUP_DIR / (_key(brush, POPUP_W, POPUP_H, POPUP_SS) + ".png")


def _load_or_render(brush, path, w, h, ss) -> QPixmap:
    if path.is_file():
        pm = QPixmap(str(path))
        if not pm.isNull():
            pm.setDevicePixelRatio(ss)
            return pm
    img = preview_image(brush, w, h, THUMB_COLOR, ss)
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(ss)
    return pm


def thumb_pixmap(brush: Brush) -> QPixmap:
    """优先读预生成缩略图；自定义/改过参数的笔刷才走实时渲染。"""
    return _load_or_render(brush, thumb_path(brush), THUMB_W, THUMB_H, THUMB_SS)


def popup_pixmap(brush: Brush) -> QPixmap:
    return _load_or_render(brush, popup_path(brush), POPUP_W, POPUP_H, POPUP_SS)
