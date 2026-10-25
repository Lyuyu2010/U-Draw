# -*- coding: utf-8 -*-
"""惰性 numpy：第一次真正用到才 import。

numpy 只在「填充 / 模糊 / 噪声 / 特殊笔尖」这些重活里用，启动路径用不到，
但 import 一次要 95ms（约占整个启动的 1/10）。这里用一个转发对象把它推迟。

用法：  from lazynp import np
        np.zeros(...)        # 第一次调用时才真正 import numpy

注意：模块级**注解**会在 def 时求值，会立刻把 numpy 拉起来 ——
写成字符串注解（"np.ndarray"）就不会。
"""


class _LazyNumpy:
    _mod = None

    def __getattr__(self, name):
        mod = _LazyNumpy._mod
        if mod is None:
            import importlib
            mod = importlib.import_module("numpy")
            _LazyNumpy._mod = mod
        return getattr(mod, name)


np = _LazyNumpy()
