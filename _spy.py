# -*- coding: utf-8 -*-
"""临时探针：抓出「启动时闪一下的窗口」是谁 show 的。

只有设置了环境变量 UDRAW_SPY 才启用；抓到的东西写到 TEMP/udraw_spy.txt。
"""

import os
import traceback

from PySide6.QtWidgets import QWidget


def _log(path, obj, how):
    try:
        if not obj.isWindow():
            return
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n=== %s  %s  %dx%d  title=%r  parent=%r\n"
                    % (how, type(obj).__name__, obj.width(), obj.height(),
                       obj.windowTitle(), obj.parent()))
            f.write("".join(traceback.format_stack()[-9:]))
    except Exception:
        pass


def install(app):
    if not os.environ.get("UDRAW_SPY"):
        return None
    path = os.path.join(os.environ.get("TEMP", "."), "udraw_spy.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("spy start\n")

    orig_show = QWidget.show
    orig_visible = QWidget.setVisible

    def show(self, *a, **k):
        _log(path, self, "show()")
        return orig_show(self, *a, **k)

    def set_visible(self, on, *a, **k):
        if on:
            _log(path, self, "setVisible(True)")
        return orig_visible(self, on, *a, **k)

    QWidget.show = show
    QWidget.setVisible = set_visible
    return True
