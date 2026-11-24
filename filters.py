# -*- coding: utf-8 -*-
"""U Draw - 滤镜（三种：高斯模糊 / 像素化 / 黑白）

约定：每个滤镜都是「输入 QImage，输出一张新的 QImage」，**不碰文档、不记撤销**。
预览、选区裁剪、贴回、撤销都由主窗口负责 —— 这样滤镜本身可以单独测，
也不会出现「滤镜里偷偷改了图层」这种难查的问题。

每个滤镜带一组参数定义（PARAMS），主窗口据此生成滑杆：
    (参数名, 显示名, 最小值, 最大值, 默认值)

颜色通道说明：QImage.Format_ARGB32 在小端机器内存里是 B,G,R,A，
所以 `_to_arr` 取出来要换一次顺序，`_from_arr` 再换回去。
"""

import math

from PySide6.QtGui import QImage

from lazynp import np


# ---------------------------------------------------------------- 转换
def _to_arr(img: QImage):
    """QImage → (h, w, 4) float32，通道顺序 RGBA，值域 0~255。"""
    img = img.convertToFormat(QImage.Format_ARGB32)
    w, h = img.width(), img.height()
    buf = np.frombuffer(img.constBits(), dtype=np.uint8, count=img.sizeInBytes())
    a = buf.reshape(h, img.bytesPerLine())[:, : w * 4].reshape(h, w, 4)
    # 小端 ARGB32：内存顺序 B,G,R,A
    return a[:, :, [2, 1, 0, 3]].astype(np.float32)


def _from_arr(arr):
    """(h, w, 4) float32 → QImage（越界值截断到 0~255）。"""
    h, w = arr.shape[:2]
    a = np.clip(np.rint(arr), 0.0, 255.0).astype(np.uint8)
    out = np.empty((h, w, 4), dtype=np.uint8)
    out[:, :, 0] = a[:, :, 2]
    out[:, :, 1] = a[:, :, 1]
    out[:, :, 2] = a[:, :, 0]
    out[:, :, 3] = a[:, :, 3]
    img = QImage(out.data, w, h, w * 4, QImage.Format_ARGB32)
    return img.copy()          # 必须 copy：out 是临时内存，出函数就没了


# ---------------------------------------------------------------- 卷积 / 模糊
def _box(arr, r: int):
    """半径 r 的方框模糊（先横后竖），边界用边缘像素延拓。

    用累积和做滑动窗口：O(像素数)，和半径无关 —— 半径 40 也不会变慢。
    """
    if r < 1:
        return arr
    k = 2 * r + 1
    h, w, c = arr.shape

    pad = np.pad(arr, ((0, 0), (r, r), (0, 0)), mode="edge")
    csum = np.cumsum(pad, axis=1)
    zero = np.zeros((h, 1, c), dtype=csum.dtype)
    csum = np.concatenate([zero, csum], axis=1)
    tmp = (csum[:, k:, :] - csum[:, :-k, :]) / k

    pad = np.pad(tmp, ((r, r), (0, 0), (0, 0)), mode="edge")
    csum = np.cumsum(pad, axis=0)
    zero = np.zeros((1, w, c), dtype=csum.dtype)
    csum = np.concatenate([zero, csum], axis=0)
    return (csum[k:, :, :] - csum[:-k, :, :]) / k


def _box2(a, r: int):
    """单通道方框模糊（给线稿用）。"""
    if r < 1:
        return a
    k = 2 * r + 1
    h, w = a.shape
    pad = np.pad(a, ((0, 0), (r, r)), mode="edge")
    cs = np.cumsum(pad, axis=1)
    cs = np.concatenate([np.zeros((h, 1), dtype=cs.dtype), cs], axis=1)
    t = (cs[:, k:] - cs[:, :-k]) / k
    pad = np.pad(t, ((r, r), (0, 0)), mode="edge")
    cs = np.cumsum(pad, axis=0)
    cs = np.concatenate([np.zeros((1, w), dtype=cs.dtype), cs], axis=0)
    return (cs[k:, :] - cs[:-k, :]) / k


def _conv3(gray, kernel):
    """3×3 卷积（边界延拓）。gray: (h,w)。"""
    h, w = gray.shape
    p = np.pad(gray, 1, mode="edge")
    out = np.zeros_like(gray)
    for dy in range(3):
        for dx in range(3):
            wgt = float(kernel[dy][dx])
            if wgt:
                out += p[dy:dy + h, dx:dx + w] * wgt
    return out


def _luma(arr):
    return arr[:, :, 0] * 0.299 + arr[:, :, 1] * 0.587 + arr[:, :, 2] * 0.114


def _to_gray(arr, v):
    """把亮度图 v 写进 RGB，alpha 保持原样。"""
    out = arr.copy()
    for ch in range(3):
        out[:, :, ch] = v
    return out


# ---------------------------------------------------------------- 三个滤镜
def gaussian_blur(img: QImage, radius: int = 4) -> QImage:
    """高斯模糊：三次方框模糊近似（中心极限定理），够快也够像。"""
    arr = _to_arr(img)
    # 三次方框 ≈ 高斯，等效 σ ≈ r·√3；这里让滑杆数值大致等于可见半径
    r = max(1, int(round(max(1, int(radius)) / 3.0)))
    for _ in range(3):
        arr = _box(arr, r)
    return _from_arr(arr)


def pixelate(img: QImage, size: int = 10) -> QImage:
    """像素化：按 size×size 取块平均，再放大回去。"""
    arr = _to_arr(img)
    h, w = arr.shape[:2]
    s = max(2, int(size))
    hh, ww = (h // s) * s, (w // s) * s
    if hh < s or ww < s:
        return img.copy()
    small = arr[:hh, :ww].reshape(hh // s, s, ww // s, s, 4).mean(axis=(1, 3))
    out = arr.copy()
    out[:hh, :ww] = np.repeat(np.repeat(small, s, axis=0), s, axis=1)
    return _from_arr(out)


def black_white(img: QImage, contrast: int = 100) -> QImage:
    """黑白：按亮度去色，再绕 128 中灰拉对比度（contrast 传百分数）。"""
    arr = _to_arr(img)
    c = max(10, int(contrast)) / 100.0
    v = (_luma(arr) - 128.0) * c + 128.0
    return _from_arr(_to_gray(arr, v))


# ---------------------------------------------------------------- 注册表
# (key, 显示名, 函数, 参数定义)
FILTERS = (
    ("blur", "高斯模糊", gaussian_blur,
     (("radius", "半径", 1, 30, 4),)),
    ("pixelate", "像素化", pixelate,
     (("size", "块大小", 2, 40, 10),)),
    ("bw", "黑白", black_white,
     (("contrast", "对比度", 30, 300, 100),)),
)

_BY_KEY = {k: f for k, _n, f, _p in FILTERS}
_LABEL = {k: n for k, n, _f, _p in FILTERS}
_PARAMS = {k: p for k, _n, _f, p in FILTERS}


def label_for(key: str) -> str:
    return _LABEL.get(key, key)


def resolve(key_or_label: str):
    """key 或显示名都认，认不出来返回 None。

    有这个是因为调用方很容易把「黑白」这种显示名当 key 传进来 ——
    之前那样会静默返回原图，看着就是「点了没反应」。
    """
    if key_or_label in _BY_KEY:
        return key_or_label
    for k, n in _LABEL.items():
        if n == key_or_label:
            return k
    return None


def params_for(key: str):
    """这个滤镜的参数定义；未知 key 返回空元组。"""
    return _PARAMS.get(key, ())


def default_params(key: str) -> dict:
    return {p[0]: p[4] for p in params_for(key)}


def apply_filter(key: str, img: QImage, **params) -> QImage:
    """按 key 跑一个滤镜。未知 key 原样返回，不抛异常（菜单项手滑也不该崩）。"""
    fn = _BY_KEY.get(key)
    if fn is None or img is None or img.isNull():
        return img
    kw = default_params(key)
    for k, v in (params or {}).items():
        if k in kw:
            kw[k] = v
    return fn(img, **kw)
