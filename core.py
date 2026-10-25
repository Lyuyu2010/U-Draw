# -*- coding: utf-8 -*-
"""U Draw - 文档 / 图层 / 笔刷引擎 / 撤销 / 文件读写（不依赖界面，便于后续移植）"""

import json
import math
import os

from lazynp import np          # 惰性 numpy：启动时不需要它（省 95ms）
import random
import time
import zipfile
from dataclasses import dataclass

from PySide6.QtCore import QBuffer, QIODevice, QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFontMetricsF, QImage, QPainter,
                           QPainterPath, QPen, QPixmap, QRadialGradient,
                           QTextDocument, QTransform)

if __package__:
    from . import special_tips
else:
    import special_tips

# ---------------------------------------------------------------- 图层合成
# 混合模式已按需求整体移除：图层永远按「正常」叠在一起（只叠加不透明度）。
# Layer.blend 字段保留，只为能继续读旧版 .pcdraw / 旧预设，实际不参与合成。
BLEND_NAMES = ["正常"]

MAX_LAYERS = 200          # 原版不限，这里给到 200（远高于你要求的 50）
FORMAT_ARGB = QImage.Format_ARGB32_Premultiplied
# 笔画缓冲单独用 16 位/通道：
# 低流量 + 柔边笔刷时，一颗笔点只有 1% 左右的不透明度，笔尖柔边那圈（比如 8%）
# 乘下来是 0.08% —— 8 位下不到 1/255，四舍五入成 0，**永远累积不起来**，
# 结果软笔刷只剩中间一条细线（「做不出 PS 那种云绵绵」的根因）。
# 缓冲改成 64 位后每颗笔点按 1/65535 累积，柔边才真的能一层层叠上去。
FORMAT_BUF = QImage.Format_RGBA64_Premultiplied


# ---------------------------------------------------------------- 笔刷
# 笔型：决定笔尖的「质感」，不只是参数不同
KINDS = ("round", "pencil", "colored_pencil", "crayon", "chalk", "charcoal",
         "ballpoint", "marker", "airbrush", "watercolor",
         "spray", "leaf", "halftone",
         # v2.13 新增：让内置笔刷库像画世界 Pro 一样「每支笔长得都不一样」
         "bristle", "noise", "cloud", "splatter", "star", "sparkle",
         "bubble", "ring", "block", "grass") + special_tips.KINDS
KIND_NAMES = {
    "round": "圆笔", "pencil": "铅笔", "colored_pencil": "彩色铅笔",
    "crayon": "蜡笔", "chalk": "粉笔", "charcoal": "炭笔",
    "ballpoint": "圆珠笔", "marker": "马克笔",
    "airbrush": "喷枪", "watercolor": "水彩",
    "spray": "喷雾", "leaf": "树叶", "halftone": "网点",
    "bristle": "鬃毛", "noise": "沙粒", "cloud": "云雾",
    "splatter": "飞溅", "star": "星星", "sparkle": "闪光",
    "bubble": "气泡", "ring": "圆环", "block": "方头", "grass": "草丛",
}
KIND_NAMES.update(special_tips.KIND_NAMES)
# 这些笔型的笔尖边缘是「毛的」：往边缘糊几团半透明小圆，边界不齐
_RAGGED = ("pencil", "colored_pencil", "crayon", "chalk", "charcoal")
# 这两种笔型每一颗笔点都**现算随机点**（不走缓存贴图）：贴图只有几套变体，
# 笔点一密就看得出重复，而喷雾 / 飞溅最怕的就是「一眼看出规律」。
_RANDOM_DABS = ("spray", "splatter")
# 顶部「密度」只给离散图章笔和喷点笔：普通圆笔/铅笔不需要这个滑杆。
STAMP_KINDS = ("star", "sparkle", "bubble", "ring", "heart", "hexagon", "chain",
               "snowflake", "feather", "leaf", "grass", "grass_blade",
               "petal", "blossom", "rose")
SPRAY_KINDS = ("spray", "splatter")

# 这些笔型的笔尖是「自己画出来的形状」，不能再垫一个实心圆（垫了就糊成一团）
_NO_DISC = ("spray", "leaf", "bristle", "noise", "cloud", "splatter",
            "star", "sparkle", "bubble", "ring", "block", "grass")
# 笔尖就是一颗柔/硬圆：这类笔的柔边完全靠笔点一层层叠出来，
# 低流量时必须拉大笔点间隔，否则柔边会被 8 位量化吃掉（见 Stroke.__init__）
_SMOOTH_TIP = ("round", "airbrush", "marker", "ballpoint",
               "pencil", "colored_pencil", "crayon", "chalk", "charcoal",
               "watercolor")


def _clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else (hi if v > hi else v)


# ---------------------------------------------------------------- 压感曲线
# 数位板送来的压力并不是「均匀分布」的：绝大多数人画画时笔压都落在
# 0.05~0.4 这一段，只有用力压才到 0.7 以上。如果直接按线性去乘笔径，
# 轻压画出来的线只有 1~2px —— 在 3000px 的画布上基本等于「画不出来」。
#
# 所以这里给压力过一条**指数曲线** p^gamma：gamma < 1 时轻压被抬起来，
# 手重的用户可以把「轻压灵敏度」往左拖（gamma 变大，回到线性甚至更钝）。
PRESS_CURVE = 0.75          # 内置默认：轻压灵敏度 75%


def _press_gamma(curve) -> float:
    """把「轻压灵敏度」0~1 换成指数：0 → 1.45（要压才出墨），1 → 0.45（轻碰就出墨）。"""
    return 1.45 - _clamp(curve)


def _press(p, curve=PRESS_CURVE) -> float:
    """压力 → 有效压力（过曲线）。0 仍然返回 0，不会凭空出墨。"""
    p = _clamp(p)
    if p <= 0.0:
        return 0.0
    return p ** _press_gamma(curve)



def _dist(a: QPointF, b: QPointF) -> float:
    dx = b.x() - a.x()
    dy = b.y() - a.y()
    return (dx * dx + dy * dy) ** 0.5


# ---------------------------------------------------------------- 对称
# 对称不是「画完再镜像一份」，而是每一颗笔点就照对称轴复制出去：
# 这样压感、抖动、颗粒都是同一次落笔的结果，左右两半才是真正的镜像。
SYM_MODES = ("off", "vertical", "horizontal", "quad", "radial")
SYM_NAMES = {
    "off": "关闭",
    "vertical": "垂直（左右）",
    "horizontal": "水平（上下）",
    "quad": "四象限",
    "radial": "径向",
}
SYM_HINTS = {
    "off": "关掉对称，正常绘画",
    "vertical": "以竖轴左右镜像，画一半得一半",
    "horizontal": "以横轴上下镜像，画一半得一半",
    "quad": "竖轴 + 横轴，画一角得四角",
    "radial": "绕轴心旋转复制（雪花 / 曼陀罗）",
}


def new_symmetry(w: int = 0, h: int = 0) -> dict:
    return {"mode": "off", "cx": w / 2.0, "cy": h / 2.0,
            "count": 6, "guides": True, "locked": False}


def symmetry_targets(sym, x: float, y: float):
    """把一颗笔点展开成 [(x, y, 旋转角, 翻转位)]。

    翻转位：1 = 左右翻、2 = 上下翻、3 = 都翻（点对称）。
    笔尖本身是不对称形状（马克笔的扁头）时，翻转位保证镜像后笔锋也是反的。
    """
    if not sym:
        return [(x, y, 0.0, 0)]
    mode = sym.get("mode", "off")
    if mode == "off" or mode not in SYM_MODES:
        return [(x, y, 0.0, 0)]
    cx = float(sym.get("cx", 0.0))
    cy = float(sym.get("cy", 0.0))
    out = [(x, y, 0.0, 0)]
    if mode in ("vertical", "quad"):
        out.append((2.0 * cx - x, y, 0.0, 1))
    if mode in ("horizontal", "quad"):
        out.append((x, 2.0 * cy - y, 0.0, 2))
    if mode == "quad":
        out.append((2.0 * cx - x, 2.0 * cy - y, 0.0, 3))
    elif mode == "radial":
        n = max(2, min(24, int(sym.get("count", 6))))
        dx, dy = x - cx, y - cy
        for k in range(1, n):
            a = 2.0 * math.pi * k / n
            ca, sa = math.cos(a), math.sin(a)
            out.append((cx + dx * ca - dy * sa, cy + dx * sa + dy * ca,
                        math.degrees(a), 0))
    return out



@dataclass
class Brush:
    """笔刷参数，字段与 PhotoCraft / PS 的画笔设置一一对应。"""
    name: str = "圆笔"
    kind: str = "round"
    group: str = "常用"        # 笔刷分类（预设区按分类筛选）
    size: float = 24.0          # 直径（画布像素）
    opacity: float = 1.0        # 整笔浓度上限；跨笔叠色由 build_up 控制
    flow: float = 1.0           # 单个笔点的浓度（同一笔内会叠加）
    hardness: float = 0.85      # 0..1 边缘硬度
    spacing: float = 0.06       # 笔点间距（占直径比例）
    stabilize: float = 0.0      # 0..1 抖动修正
    # 这两个字段只为兼容旧版笔刷文件保留：拉绳与收笔补齐已并入 stabilize 滑杆 /
    # 恒开，界面上不再暴露
    grain: float = 0.0          # 0..1 纸纹颗粒强度
    grain_scale: float = 1.5    # 颗粒粗细（像素）
    scatter: float = 0.0        # 0..1 散布
    scatter_count: int = 1      # 每个笔点叠几个笔尖
    density: float = 0.5        # 0..1 顶部密度：图章=间距，喷点=数量/聚拢
    spread: float = 0.0         # 喷点范围（画布像素）；0 = 沿用原散布
    roundness: float = 1.0      # 0.05..1 笔尖圆度（<1 变扁，马克笔就是扁头）
    angle: float = 0.0          # 笔尖角度（度）
    size_jitter: float = 0.0
    angle_jitter: float = 0.0
    angle_follow: float = 0.0   # 笔尖跟着运笔方向转（0=固定角度，1=完全顺着笔画走）
    roundness_jitter: float = 0.0
    flow_jitter: float = 0.0
    hue_jitter: float = 0.0
    sat_jitter: float = 0.0
    val_jitter: float = 0.0
    taper: float = 0.0          # 起笔渐细
    wet: float = 0.0            # 湿边（水彩积色）
    pressure_size: bool = True
    pressure_opacity: bool = False
    press_curve: float = PRESS_CURVE   # 轻压灵敏度：越大，轻压时越出墨
    accumulate: bool = True     # 颜色叠加：关掉后同一笔内不再越描越浓
    min_size: float = 0.15      # 最小直径比例（轻压时最细到多少）
    pattern_scale: float = 12.0  # 画布坐标图案 / 媒介纹理尺度（像素）
    color_cycle: float = 240.0   # 彩虹完整色相周期的路径长度（像素）
    build_up: bool = False      # 每次落笔从当前图层叠色；关时保留跨笔上限

    FIELDS = ("name", "kind", "group", "size", "opacity", "flow", "hardness", "spacing",
              "stabilize", "grain", "grain_scale",
              "scatter", "scatter_count", "density", "spread", "roundness", "angle",
              "size_jitter", "angle_jitter", "angle_follow", "roundness_jitter",
              "flow_jitter",
              "hue_jitter", "sat_jitter", "val_jitter", "taper", "wet",
              "pressure_size", "pressure_opacity", "press_curve", "min_size", "accumulate",
              "pattern_scale", "color_cycle", "build_up")
    BOOLS = ("pressure_size", "pressure_opacity", "accumulate", "build_up")
    FLOATS = ("size", "opacity", "flow", "hardness", "spacing", "stabilize",
              "grain", "grain_scale", "scatter", "density", "spread", "roundness", "angle",
              "size_jitter", "angle_jitter", "angle_follow", "roundness_jitter",
              "flow_jitter",
              "hue_jitter", "sat_jitter", "val_jitter", "taper", "wet", "min_size",
              "press_curve", "pattern_scale", "color_cycle")

    def copy(self) -> "Brush":
        return Brush(**{f: getattr(self, f) for f in Brush.FIELDS})

    def apply_from(self, other: "Brush"):
        """原地复制参数（画布/面板共用同一个对象，必须原地改）。"""
        for f in Brush.FIELDS:
            setattr(self, f, getattr(other, f))

    def as_dict(self) -> dict:
        return {f: getattr(self, f) for f in Brush.FIELDS}

    @classmethod
    def from_dict(cls, d: dict) -> "Brush":
        b = cls()
        for f in cls.FIELDS:
            if f not in d:
                continue
            v = d[f]
            if f in cls.BOOLS:
                if isinstance(v, str):
                    v = v.strip().lower() in ("1", "true", "yes", "on")
                else:
                    v = bool(v)
            elif f in cls.FLOATS:
                try:
                    v = float(v)
                    if not math.isfinite(v):
                        continue
                except (TypeError, ValueError):
                    continue
            elif f == "scatter_count":
                try:
                    v = max(1, min(12, int(round(float(v)))))
                except (TypeError, ValueError):
                    v = 1
            setattr(b, f, v)
        if b.kind not in KINDS:
            b.kind = "round"
        b.roundness = max(0.05, min(1.0, b.roundness))
        b.min_size = max(0.0, min(1.0, b.min_size))
        b.angle_follow = max(0.0, min(1.0, b.angle_follow))
        b.spacing = max(0.01, min(4.0, b.spacing))
        b.press_curve = _clamp(b.press_curve)
        b.opacity = _clamp(b.opacity)
        b.flow = _clamp(b.flow)
        b.density = _clamp(b.density)
        b.spread = max(0.0, min(600.0, b.spread))
        b.pattern_scale = max(2.0, min(256.0, b.pattern_scale))
        b.color_cycle = max(8.0, min(8192.0, b.color_cycle))
        return b

    def range_diameter(self) -> float:
        """喷点类的外圈直径（px）。0 表示跟笔刷大小走。"""
        if self.kind in SPRAY_KINDS:
            return max(1.0, self.spread if self.spread > 0.001 else self.size)
        return max(1.0, self.size)

    def diameter(self, pressure: float) -> float:
        size = self.size
        # 喷点类：范围是外圈，笔尖不能比外圈还大。
        if self.kind in SPRAY_KINDS:
            size = min(size, self.range_diameter())
        if not self.pressure_size:
            return max(0.6, size)
        # min_size 留 8% 的活动余量：即使被设成 100%，压感也还有点用，
        # 不会出现「明明勾了压感却画出来一样粗」的情况
        ms = min(self.min_size, 0.92)
        # 压力先过「轻压灵敏度」曲线：驱动送来的 0.05 在默认曲线上约等于 0.13，
        # 轻压才真的画得出来（以前线性映射，轻压只剩 1~2px，看着像没反应）。
        p = ms + (1.0 - ms) * _press(pressure, self.press_curve)
        # 最小 1px：再细就落到亚像素，抗锯齿后是一片淡灰，等于没画。
        return max(1.0, size * p)

    def dab_alpha(self, pressure: float, cover: float = None) -> float:
        """单个笔点的浓度（0~1），**已按间距归一化**。

        间距 5% 时一个像素会被约 20 个笔点扫到：如果每个笔点都直接按流量
        上色，SourceOver 叠完必然接近不透明 —— 流量 100% 和 60% 画出来一样黑，
        滑杆就成了摆设。反解 a = 1-(1-flow)^spacing，让**画一遍**正好到 flow，
        同一笔里再扫过同一处才会继续叠深 —— 这正是「流量会叠色」的手感。

        cover = 「一个像素会被几个笔点扫到」（= 真实笔点间距 / 笔径）。
        不传就退回 spacing 比例 —— 但贴图间距有 0.4px 的下限，小笔 + 极小间距时
        真实间距比 spacing×笔径 大好几倍，按 spacing 算出来的每点浓度会低到 5%，
        而实际只扫到两三颗 —— 画出来发白（中性笔 / 毛笔勾线就踩过这个坑）。
        """
        a = _clamp(self.flow)
        if self.pressure_opacity:
            # 轻压段要抬两下，否则数位板刚接触时报的 0.01~0.05 只出 5% 的墨，
            # 屏幕上几乎看不见 —— 用户反馈的「低力度按压画不出来」就是这个。
            #   1) pr ** 0.85：把低段整体提一档，0.5 以上几乎不变（差 2% 以内）
            #   2) 地板 6% → 12%：保证只要有压力就有一笔看得见的墨
            # 轻压段再垫一层底（0.18 + 0.82·pr）：满压时系数仍是 1.0，
            # 只是把「刚接触」那一档从 5% 的墨抬到 15% 左右 —— 屏幕上才看得见。
            pr = 0.18 + 0.82 * (_press(pressure, self.press_curve) ** 0.9)
            a *= max(0.12, pr)
        s = self.spacing if cover is None else cover
        if 0.01 < s < 1.0:
            a = 1.0 - (1.0 - _clamp(a)) ** s
        return _clamp(a)

    def cover_ratio(self, pressure: float = 1.0, step: int = 1) -> float:
        """一个像素实际会被几个笔点扫到（相对笔径）。"""
        sp = max(0.05, self.stamp_spacing(pressure)) * max(1, int(step))
        return min(1.0, sp / max(1.0, self.diameter(pressure)))

    def spread_radius(self, diameter: float) -> float:
        """喷点副本的偏移半径（px）。

        喷点类的外圈是 range_diameter：笔尖本身占 diameter，剩下的
        (range - diameter)/2 才是副本可以偏移的空间，这样所有点都落在
        范围圈内，范围调大时笔尖本身不会跟着变大。
        """
        if self.kind in SPRAY_KINDS:
            return max(0.0, (self.range_diameter() - diameter) * 0.5)
        if self.spread > 0.001:
            return self.spread
        base = max(self.scatter, 0.06 if self.scatter_count > 1 else 0.0)
        return base * diameter * 0.5

    def stamp_spacing(self, pressure: float) -> float:
        """图章笔的有效间距：密度 50% 是原间距，100% 更密，0% 更疏。"""
        s = self.spacing
        if self.kind in STAMP_KINDS:
            s *= 2.0 ** ((0.5 - _clamp(self.density)) * 2.0)
        gap = s * self.diameter(pressure)
        # 硬且实心的笔（G 笔 / 针管笔 / 中性笔 / 圆珠笔 / 钢笔…）：
        # 相邻笔点几乎完全重合，0.4px 的密间距纯属浪费 —— 笔移动 30px 要盖 90 颗，
        # 低配电脑上就是这么掉帧的。这类笔放宽到 0.9px 起步，肉眼看不出区别，
        # 笔点数少一半以上。铅笔 / 炭笔这类半透明颗粒笔不动：它们的浓淡就是靠
        # 密笔点叠出来的，间距一变质感就变。
        if (self.hardness >= 0.97 and self.flow >= 0.9
                and self.kind not in _RANDOM_DABS
                and self.kind not in STAMP_KINDS
                and self.kind not in SPRAY_KINDS):
            gap = max(0.9, gap)
        return max(0.4, gap)


# ---------------------------------------------------------------- 笔尖贴图
_NOISE_CACHE = {}


def _contrast(img: QImage) -> QImage:
    """把灰度噪声拉伸到满量程。SmoothTransformation 放大后会压掉动态范围，
    不拉回来的话颗粒只剩淡淡的灰雾，看不出纸纹。"""
    w, h = img.width(), img.height()
    bpl = img.bytesPerLine()
    src = img.constBits()
    vals = [src[y * bpl + x] for y in range(h) for x in range(w)]
    lo, hi = min(vals), max(vals)
    if hi - lo < 8:
        return img
    k = 255.0 / (hi - lo)
    out = bytearray(w * h)
    for y in range(h):
        base = y * bpl
        for x in range(w):
            out[y * w + x] = max(0, min(255, int((src[base + x] - lo) * k)))
    return QImage(bytes(out), w, h, w, QImage.Format_Grayscale8).copy()


def _box_blur(src: "np.ndarray", r: int) -> "np.ndarray":
    """对 (h, w, 4) float32 做一次盒式模糊（先横后竖），r = 半径（像素）。

    用前缀和实现：不管半径多大，代价都一样（几遍 cumsum），
    比反复做 1px 卷积快一个数量级 —— 涂抹每一步都要用，必须便宜。
    """
    if r < 1:
        return src
    h, w = src.shape[:2]
    r = int(min(r, max(1, min(h, w) // 3)))
    k = 2 * r + 1
    p = np.pad(src, ((0, 0), (r, r), (0, 0)), mode="edge")
    c = np.cumsum(p, axis=1, dtype=np.float32)
    c = np.concatenate([np.zeros((h, 1, 4), np.float32), c], axis=1)
    out = (c[:, k:k + w] - c[:, 0:w]) / k
    p2 = np.pad(out, ((r, r), (0, 0), (0, 0)), mode="edge")
    c2 = np.cumsum(p2, axis=0, dtype=np.float32)
    c2 = np.concatenate([np.zeros((1, w, 4), np.float32), c2], axis=0)
    return (c2[k:k + h, :] - c2[0:h, :]) / k


def _periodic_noise(n: int, res: int, seed: int) -> "np.ndarray":
    """n×n 的**无缝**值噪声：res×res 随机格点 + smoothstep 平滑插值。

    为什么不用「随机块直接最近邻放大」：那样放大后就是一格一格的方块，
    画布一放大，笔迹里全是硬边马赛克（用户反馈的「很多画笔有马赛克质感」
    就是它）。这里改成平滑插值，颗粒是一团一团的纸纹，没有方块边。
    索引取模 → 贴图左右上下天然接得上，平铺时看不到接缝。
    """
    res = max(2, min(int(n), int(res)))
    rng = np.random.default_rng(seed)
    lat = rng.random((res, res)).astype(np.float32)
    if res >= n:
        return lat                     # 逐像素噪声，不需要插值（省一次 512² 采样）
    t = np.arange(n, dtype=np.float32) * (res / float(n))
    base = np.floor(t)
    i0 = base.astype(np.int64) % res
    i1 = (i0 + 1) % res
    f = t - base
    f = f * f * (3.0 - 2.0 * f)          # smoothstep：格点之间是平滑过渡
    fx = f[None, :]
    fy = f[:, None]
    a = lat[np.ix_(i0, i0)]
    b = lat[np.ix_(i0, i1)]
    c = lat[np.ix_(i1, i0)]
    d = lat[np.ix_(i1, i1)]
    return ((a * (1.0 - fx) + b * fx) * (1.0 - fy)
            + (c * (1.0 - fx) + d * fx) * fy)


def grain_tile(level: float, scale: float, variant: int) -> QImage:
    """512×512 的无缝纸纹（白色 + 变化的 alpha）。

    level 越大吃掉越多墨；scale 越大颗粒越粗（铅笔细腻 1px，蜡笔成块 5~6px）。

    三层倍频叠加：主颗粒（scale px 一团）+ 两个更细的倍频。
    只有主颗粒时看着像一团一团的云，加两层次要的细齿才是纸面；
    而且全程平滑插值，放大到 300% 也不会出现方块。
    """
    lv = int(round(_clamp(level) * 20))
    cell = max(1, min(8, int(round(scale))))
    key = (lv, cell, variant % 3)
    img = _NOISE_CACHE.get(key)
    if img is not None:
        return img
    g = lv / 20.0
    n = 512
    res = max(4, n // max(1, cell))
    seed = 4409 + lv * 131 + cell * 17 + (variant % 3) * 7
    # 倍频只在「更细还有意义」时才叠：cell=1 时主颗粒已经是逐像素噪声，
    # 再叠两层同样密的倍频只是白算（实测这一条把 52ms 降到 18ms）。
    v = 0.62 * _periodic_noise(n, res, seed)
    if res * 2 <= n:
        v += 0.26 * _periodic_noise(n, res * 2, seed + 911)
    if res * 4 <= n:
        v += 0.12 * _periodic_noise(n, res * 4, seed + 1777)
    lo, hi = float(v.min()), float(v.max())
    if hi - lo > 1e-6:
        v = (v - lo) / (hi - lo)         # 拉满动态范围，颗粒才明显
    a = (255.0 * (1.0 - g + g * v)).astype(np.uint8)
    buf = np.empty((n, n, 4), dtype=np.uint8)
    buf[..., 0] = a
    buf[..., 1] = a
    buf[..., 2] = a
    buf[..., 3] = a
    img = QImage(buf.tobytes(), n, n, n * 4, FORMAT_ARGB).copy()
    if len(_NOISE_CACHE) > 64:           # 每张 1MB，别让缓存无限长
        _NOISE_CACHE.clear()
    _NOISE_CACHE[key] = img
    return img


# 圆笔尖渐变的缓存：同一支笔一笔画下来，(硬度, 内圈比例, 颜色) 基本不变，
# 只有圆心和半径在动。以前每颗笔点都重建一次渐变（12 次 setColorAt + 12 个 QColor），
# 8px 铅笔一笔要盖 6000 颗 —— 光这一步就占了笔迹时间的一半。
_DISC_CACHE = {}


def _disc_gradient(hard: float, inner: float, color: QColor, edge: float):
    """按 (硬度, 内圈比例, 颜色) 取一个渐变模板；停靠点只在模板第一次建时算。"""
    key = (hard >= 0.97, round(inner, 2), color.rgba())
    g = _DISC_CACHE.get(key)
    if g is not None:
        return g
    g = QRadialGradient(QPointF(0.0, 0.0), 1.0)
    c0 = QColor(color)
    c0.setAlpha(255)
    c1 = QColor(color)
    c1.setAlpha(0)
    if hard >= 0.97:
        g.setColorAt(0.0, c0)
        g.setColorAt(min(0.999, inner), c0)
        g.setColorAt(1.0, c1)
    else:
        g.setColorAt(0.0, c0)
        g.setColorAt(inner, c0)
        steps = 12
        for k in range(1, steps + 1):
            u = k / steps
            t = inner + (1.0 - inner) * u
            a = int(round(255 * (1.0 - u) ** 1.55))
            col = QColor(color)
            col.setAlpha(max(0, min(255, a)))
            g.setColorAt(min(0.999, t), col)
    if len(_DISC_CACHE) > 240:          # 颜色 / 压力变化多的笔别把缓存撑爆
        _DISC_CACHE.clear()
    _DISC_CACHE[key] = g
    return g


def _paint_disc(p: QPainter, cx: float, cy: float, rad: float,
                hard: float, color: QColor, edge: float = 1.7):
    """画一颗柔/硬恰到好处的圆笔尖。

    edge = 边缘过渡带宽度（和 rad 同一单位，也就是「笔尖贴图里的像素」）。
    这个值必须由调用方按**贴图分辨率**给：
      · 2 倍分辨率生成再缩小的贴图 → 1.8（缩完约 0.9px）
      · 直接按实际尺寸现画（3~8px 的小笔）→ 0.9（就 0.9px）
    以前这里写死 1.7：小笔现画时 4px 的笔只有 2px 半径，过渡带就占了 1.7px，
    整支笔看着像喷枪 —— G 笔 / 圆珠笔 / 中性笔这些硬笔边缘发糊就是这么来的。
    """
    if rad <= 0.25:
        return
    hard = _clamp(hard)
    if hard >= 0.97:
        inner = min(0.999, 1.0 - edge / max(1.0, rad))
    else:
        # 硬笔（硬度 90%+）在半径只有 3~4px 时，原来把过渡全挤在最后 15% 半径里
        # （不到半个像素），等于没有抗锯齿 —— 4px 的硬笔放大看就是一格一格的楼梯。
        # 过渡带按 edge 反推：小笔也有干净的边缘，大笔完全不受影响。
        inner = max(0.02, min(hard * 0.94, 1.0 - edge / max(1.0, rad)))
    g = _disc_gradient(hard, inner, color, edge)
    # 渐变模板是单位半径、圆心在原点的：这里只挪圆心和半径，不再重建停靠点。
    g.setCenter(QPointF(cx, cy))
    g.setFocalPoint(QPointF(cx, cy))
    g.setRadius(rad)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QRectF(cx - rad, cy - rad, rad * 2, rad * 2))


def _make_stamp(kind: str, d: int, hard: float, color: QColor,
                grain: float, gscale: float, variant: int) -> QImage:
    # 1~2px 的笔尖如果还按圆去抗锯齿，会淡到几乎看不见（半径只有 0~0.5px）。
    # 这里直接给一个实心像素块，保证 1px 笔真的能画出 1px。
    if d <= 2:
        img = QImage(d, d, FORMAT_ARGB)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, False)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(color))
        p.drawRect(0, 0, d, d)
        p.end()
        return img
    if kind in special_tips.KINDS:
        return special_tips.make_stamp(kind, d, hard, color, variant)
    rnd = random.Random(1013 + d * 97 + int(hard * 100) * 7 + variant * 911)
    img = QImage(d, d, FORMAT_ARGB)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    r = d / 2.0 - 0.5
    cx = cy = d / 2.0
    if kind not in _NO_DISC:
        _paint_disc(p, cx, cy, r, hard, color)

    if kind == "spray":
        # 喷枪：不是一团雾，而是**一堆小点**撒在笔尖范围内（和 PS 的喷枪一致）。
        # v2.14：点更少、大小差得更开、偶尔来一滴大的 —— 不然密集的小点会糊成一团雾。
        p.end()
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        # 和实时落点用同一套点数/点径公式：改成缓存贴图后外观不变，
        # 但每个笔点只 drawImage 一次，不再现画几百个圆。
        n = int(max(40, min(360, 100 + r * 0.6)))
        for _ in range(n):
            ang = rnd.uniform(0, math.tau)
            rr = r * (rnd.random() ** 0.55) * 1.05          # 略微往外散，边缘也有点
            dot = max(0.5, min(4.5, r * (0.004 + 0.016 * rnd.random() ** 1.4)))
            if rnd.random() < 0.05:
                dot *= rnd.uniform(1.5, 2.4)                # 偶尔一滴大的，才像喷出来的
            c = QColor(color)
            c.setAlpha(int(255 * rnd.uniform(0.30, 1.0)))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(c))
            p.drawEllipse(QPointF(cx + math.cos(ang) * rr,
                                  cy + math.sin(ang) * rr), dot, dot)
        p.end()
        return img
    if kind == "leaf":
        # 树叶：一头尖一头圆的叶片 + 一条叶脉
        p.end()
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        path = QPainterPath()
        path.moveTo(cx, cy - r)                       # 叶尖
        path.cubicTo(cx + r * 0.95, cy - r * 0.55,
                     cx + r * 0.85, cy + r * 0.55, cx, cy + r * 0.95)
        path.cubicTo(cx - r * 0.85, cy + r * 0.55,
                     cx - r * 0.95, cy - r * 0.55, cx, cy - r)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(color))
        p.drawPath(path)
        if r > 6:
            pen = QPen(QColor(255, 255, 255, 150), max(0.6, r * 0.05))
            p.setPen(pen)
            p.drawLine(QPointF(cx, cy - r * 0.85), QPointF(cx, cy + r * 0.85))
        p.end()
        return img
    if kind == "bristle":
        # 鬃毛笔（油画 / 水粉刷）：笔尖由一排平行细毛组成，毛与毛之间有空隙，
        # 所以画出来是一道道有方向性的丝，而不是一块平涂。毛的方向是笔尖的
        # 局部 Y 轴 —— 配「角度跟随」就永远顺着运笔方向。
        p.end()
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        n = max(5, min(40, int(round(d * 0.55))))
        for i in range(n):
            u = -1.0 + 2.0 * (i + 0.5) / n
            x = cx + u * r * 0.94
            half = math.sqrt(max(0.0, 1.0 - u * u)) * r
            if half <= 0.3:
                continue
            half *= rnd.uniform(0.66, 1.0)          # 每根毛长短不一，两头留缺口
            off = rnd.uniform(-0.14, 0.14) * r
            c = QColor(color)
            c.setAlpha(int(255 * rnd.uniform(0.42, 1.0)))
            p.setPen(QPen(c, max(0.7, r * 0.14), Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(x, cy - half + off), QPointF(x, cy + half + off))
        p.end()
        return img
    if kind == "noise":
        # 沙粒 / 噪点：比喷雾密得多、点也小得多，撒出来是「磨砂」质感
        p.end()
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        n = max(24, min(1200, int(r * r * 1.1)))
        for _ in range(n):
            ang = rnd.uniform(0, math.tau)
            rr = r * math.sqrt(rnd.random())
            dot = max(0.35, r * rnd.uniform(0.015, 0.055))
            c = QColor(color)
            c.setAlpha(int(255 * rnd.uniform(0.30, 1.0)))
            p.setBrush(QBrush(c))
            p.drawEllipse(QPointF(cx + math.cos(ang) * rr,
                                  cy + math.sin(ang) * rr), dot, dot)
        p.end()
        return img
    if kind == "cloud":
        # 云雾：几团柔边小圆堆在一起，边缘是「絮状」的，不是一颗规整的软圆
        p.end()
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        for i in range(10):
            ang = rnd.uniform(0, math.tau)
            # 前几团往中间靠（保证笔尖中心够实），后面几团散开做絮状边缘
            rr = r * (rnd.uniform(0.0, 0.18) if i < 4 else rnd.uniform(0.0, 0.5))
            p.setOpacity(rnd.uniform(0.5, 0.95))
            _paint_disc(p, cx + math.cos(ang) * rr, cy + math.sin(ang) * rr,
                        r * rnd.uniform(0.32, 0.58), 0.0, color)
        p.end()
        return img
    if kind == "splatter":
        # 飞溅：甩上去的墨。主体是 1~3 团偏心的不规则墨团，周围是**少而散**的液滴，
        # 大小差得很开、有的甩到笔尖外，再撒几粒极小的雾点 —— 才像「墨水喷溅」，
        # 而不是一圈挤在一起的小圆点。
        p.end()
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        for _ in range(rnd.randint(1, 3)):
            ox = rnd.uniform(-0.24, 0.24) * r
            oy = rnd.uniform(-0.24, 0.24) * r
            _paint_disc(p, cx + ox, cy + oy, r * rnd.uniform(0.14, 0.32), 0.5, color)
        for _ in range(rnd.randint(4, 9)):
            ang = rnd.uniform(0, math.tau)
            rr = r * (0.30 + 1.05 * rnd.random() ** 0.45)   # 偏外，形成「甩」出去的感觉
            dot = max(0.5, r * rnd.uniform(0.012, 0.075))
            if rnd.random() < 0.18:
                dot *= rnd.uniform(1.8, 3.2)                # 偶尔一颗特别大的墨滴
            c = QColor(color)
            c.setAlpha(int(255 * rnd.uniform(0.45, 1.0)))
            p.setBrush(QBrush(c))
            p.drawEllipse(QPointF(cx + math.cos(ang) * rr,
                                  cy + math.sin(ang) * rr), dot, dot)
        for _ in range(rnd.randint(3, 8)):
            ang = rnd.uniform(0, math.tau)
            rr = r * rnd.uniform(0.2, 1.2)
            c = QColor(color)
            c.setAlpha(int(255 * rnd.uniform(0.25, 0.7)))
            p.setBrush(QBrush(c))
            p.drawEllipse(QPointF(cx + math.cos(ang) * rr,
                                  cy + math.sin(ang) * rr), 0.6, 0.6)
        p.end()
        return img
    if kind == "star":
        # 五角星印章：撒星星、贴纸效果
        p.end()
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        path = QPainterPath()
        for i in range(10):
            ang = -math.pi / 2.0 + i * math.pi / 5.0
            rad = r if i % 2 == 0 else r * 0.42
            pt = QPointF(cx + math.cos(ang) * rad, cy + math.sin(ang) * rad)
            if i == 0:
                path.moveTo(pt)
            else:
                path.lineTo(pt)
        path.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(color))
        p.drawPath(path)
        p.end()
        return img
    if kind == "sparkle":
        # 四芒闪光：中间一点 + 四个方向的尖角（星光笔、闪光特效）
        p.end()
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        k = r * 0.15
        path = QPainterPath()
        path.moveTo(cx, cy - r)
        path.quadTo(cx + k, cy - k, cx + r, cy)
        path.quadTo(cx + k, cy + k, cx, cy + r)
        path.quadTo(cx - k, cy + k, cx - r, cy)
        path.quadTo(cx - k, cy - k, cx, cy - r)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(color))
        p.drawPath(path)
        _paint_disc(p, cx, cy, r * 0.30, 0.0, color)
        p.end()
        return img
    if kind == "bubble":
        # 气泡：一圈亮边 + 一层极淡的内部 + 左上角高光
        p.end()
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        inner = QColor(color)
        inner.setAlpha(26)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(inner))
        p.drawEllipse(QPointF(cx, cy), r * 0.86, r * 0.86)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(color, max(0.8, r * 0.16)))
        p.drawEllipse(QPointF(cx, cy), r * 0.86, r * 0.86)
        hi = QColor(255, 255, 255, 190)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(hi))
        p.drawEllipse(QPointF(cx - r * 0.34, cy - r * 0.34), r * 0.16, r * 0.16)
        p.end()
        return img
    if kind == "ring":
        # 空心圆环：描边笔 / 光环
        p.end()
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        w = max(0.8, r * 0.30)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(color, w))
        p.drawEllipse(QPointF(cx, cy), r - w / 2.0, r - w / 2.0)
        p.end()
        return img
    if kind == "block":
        # 方头：真正的方块笔尖（配角度 / 圆度就是扁头马克笔、排线笔）
        p.end()
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(color))
        rr = max(0.4, r * 0.10)
        p.drawRoundedRect(QRectF(cx - r, cy - r, r * 2, r * 2), rr, rr)
        p.end()
        return img
    if kind == "grass":
        # 草丛 / 毛发：一束从中心向外散开的细尖毛，配角度抖动就是毛刷
        p.end()
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        n = max(6, min(60, int(round(d * 0.45))))
        for _ in range(n):
            ang = rnd.uniform(0, math.tau)
            ln = r * rnd.uniform(0.45, 1.0)
            c = QColor(color)
            c.setAlpha(int(255 * rnd.uniform(0.45, 1.0)))
            p.setPen(QPen(c, max(0.6, r * 0.075), Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(cx + math.cos(ang) * r * 0.06,
                               cy + math.sin(ang) * r * 0.06),
                       QPointF(cx + math.cos(ang) * ln,
                               cy + math.sin(ang) * ln))
        p.end()
        return img
    if kind in _RAGGED:
        # 边缘毛刺：往周围糊几团软圆，笔尖就不是一个干净的正圆了
        blobs = 3 if kind in ("colored_pencil", "pencil") else 5
        for _ in range(blobs + int(rnd.random() * 3)):
            ang = rnd.uniform(0, math.tau)
            rr = r * rnd.uniform(0.30, 0.92)
            _paint_disc(p, cx + math.cos(ang) * rr, cy + math.sin(ang) * rr,
                        r * rnd.uniform(0.22, 0.52),
                        min(1.0, hard + rnd.uniform(0.0, 0.25)), color)
    p.end()

    # 颗粒不再贴在笔尖上：贴在这里会被重叠的笔点平均掉（等于没效果），
    # 改成整笔合成时按画布坐标平铺（见 Stroke._apply_grain）。
    return img


class StampCache:
    """按 (直径, 硬度, 颜色, 颗粒, 粗细, 笔型) 缓存笔尖；每种生成若干随机变体，
    落笔时轮流取，避免整笔出现同一个印子重复盖章的假感。"""

    VARIANTS = 3
    # 这些笔型「一个笔尖就是一幅小画」：多给几套随机变体，飞溅 / 喷雾才不会看出规律
    MANY = ("splatter", "spray", "noise", "cloud", "grass", "star", "sparkle",
            "bubble", "leaf") + special_tips.RANDOM_TEXTURES
    BYTE_BUDGET = 48 * 1024 * 1024
    MAX_DIAMETER = 1024

    def __init__(self):
        self._d = {}
        self._order = []
        self._bytes = 0

    def get(self, diameter: float, hardness: float, color: QColor,
            grain: float = 0.0, gscale: float = 1.5, kind: str = "round"):
        d = max(1, min(self.MAX_DIAMETER, int(round(diameter))))
        hq = int(round(_clamp(hardness, 0.0, 0.995) * 50))
        gq = int(round(_clamp(grain) * 10))
        sq = max(1, min(8, int(round(gscale))))
        key = (d, hq, color.rgba(), gq, sq, kind)
        lst = self._d.get(key)
        if lst is not None:
            return lst
        # 小/中笔尖按 2 倍分辨率生成再缩回目标尺寸：特殊笔刷的细线、尖角
        # 不再是一格一格的马赛克；大笔尖本身像素够多，保持 1 倍省内存。
        # 喷雾/飞溅本身是细碎小点，不需要 2 倍，否则第一次落笔要等贴图生成。
        if kind in ("spray", "splatter"):
            render_d = d
            n = 6 if d <= 192 else 4
        else:
            render_d = d * 2 if d <= 128 else d
            n = (10 if kind in self.MANY else self.VARIANTS) if d <= 72 else (3 if d <= 192 else 1)
        cost = render_d * render_d * 4 * n
        while self._order and (self._bytes + cost > self.BYTE_BUDGET or len(self._d) >= 260):
            old = self._d.pop(self._order.pop(0))
            self._bytes -= sum(img.sizeInBytes() for img in old)
        lst = [_make_stamp(kind, render_d, hq / 50.0, color, gq / 10.0, sq, v)
               for v in range(n)]
        if cost <= self.BYTE_BUDGET:
            self._d[key] = lst
            self._order.append(key)
            self._bytes += sum(img.sizeInBytes() for img in lst)
        return lst


STAMPS = StampCache()
_SCREEN_CACHE = {}          # 网点屏的平铺小块（按格子大小缓存）


# ---------------------------------------------------------------- 笔画缓冲
class StrokeBuffer:
    """随笔画增长的离屏缓冲（文档坐标）。

    笔点先画进缓冲、再整笔一次合成到图层：整笔不透明度在合成时统一施加，
    不会变成「笔点各按不透明度画一遍」那样越描越黑，橡皮也不会擦出阶梯。
    缓冲内部按流量叠加 —— 流量低时反复扫同一处会慢慢积色，这是有意的。
    """

    BLOCK = 192

    def __init__(self, w: int, h: int):
        self.w = int(w)
        self.h = int(h)
        self.img = None
        self.rect = QRect()

    def ensure(self, need: QRect) -> bool:
        need = need.intersected(QRect(0, 0, self.w, self.h))
        if need.isEmpty():
            return False
        if self.img is not None and self.rect.contains(need):
            return False
        b = self.BLOCK
        x0 = max(0, (need.left() // b) * b)
        y0 = max(0, (need.top() // b) * b)
        x1 = min(self.w, ((need.right() // b) + 1) * b)
        y1 = min(self.h, ((need.bottom() // b) + 1) * b)
        nr = QRect(x0, y0, max(1, x1 - x0), max(1, y1 - y0))
        if self.img is not None:
            nr = nr.united(self.rect)
        img = QImage(nr.width(), nr.height(), FORMAT_BUF)
        img.fill(Qt.transparent)
        if self.img is not None:
            p = QPainter(img)
            p.setCompositionMode(QPainter.CompositionMode_Source)
            p.drawImage(self.rect.topLeft() - nr.topLeft(), self.img)
            p.end()
        self.img = img
        self.rect = nr
        return True


class Stroke:
    """一次完整的落笔：采样 → 抖动修正 → 中点样条 → 笔点 → 整笔合成。

    结束后生成一条撤销记录（只存脏矩形，很省内存）。
    """

    def __init__(self, doc, layer, brush: Brush, color: QColor, erase: bool = False,
                 sym=None, preview: bool = False):
        self.doc = doc
        self.layer = layer
        self.brush = brush.copy()
        self.color = QColor(color)
        self.erase = erase
        self.sym = sym
        # 缩略图只关心最后一整笔，不需要每个 move 都合成一次；
        # 否则颗粒/图案笔刷会把同一块纹理重复算 60 遍。
        self.preview = preview
        # 默认沿用跨笔浓度上限；任何参数改变都必须换会话，不能把旧纹理重算成新笔。
        # build_up 每次从当前图层起步，只在一笔内封顶。
        sig = (tuple(sorted(self.brush.as_dict().items())), self.color.rgba(), bool(erase))
        sess = getattr(doc, "_stroke_session", None)
        reuse = (not self.brush.build_up and sess is not None
                 and sess.get("layer") is layer and sess.get("sig") == sig)
        if reuse:
            self.before = sess["snap"]           # 会话起点，只读
            self.buf = sess["buf"]
            self.undo_before = layer.image.copy()   # 撤销要的是「这一笔之前」
        else:
            self.before = layer.image.copy()
            self.buf = StrokeBuffer(layer.image.width(), layer.image.height())
            self.undo_before = self.before
            sess = {"layer": layer, "sig": sig, "snap": self.before, "buf": self.buf}
            if hasattr(doc, "_stroke_session"):
                doc._stroke_session = sess
        self._session = sess
        self.dirty = QRect()        # 整笔脏区（撤销用）
        self._pending = QRect()     # 还没合成到图层的区域

        self.active = True
        self.travel = 0.0           # 已画长度，用于起笔渐细
        self._carry = 0.0           # 上一段没走满的间距（跨小段累积，间距才准）
        # 颗粒贴图的起始偏移：每笔错开，两笔不会用同一块纹理（看着更像纸）
        if "grain_off" not in sess:
            sess["grain_off"] = (random.randrange(512), random.randrange(512))
        self._grain_off = sess["grain_off"]
        self.smooth = None          # 平滑后的落笔点
        self.last_p = 1.0
        self.last_raw = None        # 原始笔尖位置（收笔补齐用）
        self._noise = sess.get("flow_tile")  # 同一跨笔会话保持遮罩，避免整片纹理跳动
        # 低流量时归一化出来的笔点 alpha 很小（flow 30% / 间距 3% → 1%）。
        # QPainter 会把「笔点 alpha × 不透明度」按 8 位算，1% 的笔点再乘上柔边
        # 那圈 8% 就 < 1/255，直接变成 0 —— 柔边永远叠不上去，软笔刷退化成
        # 中间一条细线（用户反馈「做不出 PS 那种云绵绵」就是这个）。
        # 所以低流量时别画那么密：隔几个笔点画一个、每个浓一点。总浓度不变，
        # 但每一颗都够浓，柔边才累积得起来。硬笔刷边缘本来就实，不需要这样，
        # 所以阈值随硬度收放（越软，隔得越多）。
        a0 = max(1e-4, brush.dab_alpha(1.0, brush.cover_ratio(1.0)))
        soft = 1.0 - _clamp(brush.hardness)
        # 只有「一颗软圆」这类笔尖才需要拉大间隔：它们的柔边就是靠笔点一层层
        # 叠出来的。云雾 / 喷点 / 图章 / 鬃毛这些笔尖本身是一堆小形状，
        # 间隔一大就会看出一颗颗鼓包（串珠），所以它们保持原来的密间距。
        if brush.kind in _SMOOTH_TIP:
            target = 0.008 + 0.058 * soft * soft
        else:
            target = 0.008
        self._dab_step = max(1, min(12, int(math.ceil(target / a0))))
        self._dab_i = 0
        self._anchor = None         # 中点样条的起点
        self._stab = None           # 抖动修正的绳头
        self._hist = []             # 最近的原始笔点（直线吸附用）
        self._snap_w = 0.0          # 直线吸附的权重（做低通，避免折角）
        self._stab_n = 0            # 起笔阶段跟得更紧，避免开头被拉成一条弦
        self._t_last = None         # 上一个移动事件的时间（防抖按时间算，不按事件数）
        self._pending_first = None  # 扁笔的第一颗笔点，等知道方向再画
        sel = doc.selection if doc.has_selection() else None
        self._sel = QPainterPath(sel) if sel is not None else None
        # 颜色动态：一次落笔内保持整体色相偏移，笔点之间再做微扰
        self._dh = random.uniform(-1, 1) * 0.10 * brush.hue_jitter
        self._ds = random.uniform(-1, 1) * brush.sat_jitter
        self._dv = random.uniform(-1, 1) * brush.val_jitter
        # 角度跟随：记住上一个笔点位置，用它算运笔方向（0°=向右）
        self._prev_pos = None
        self._dir = 0.0
        self._dir_smooth = None
        self._path_length = 0.0     # 实际采样轨迹弧长，不用事件次数或整段预加的 travel
        self._path_pos = None

    # -- 落点 → 缓冲 ------------------------------------------------
    def _stamp(self, pts):
        if not pts:
            return
        b = self.brush
        maxd = 0.0
        for _, pr in pts:
            maxd = max(maxd, b.diameter(pr))
        # 方头旋转的对角线、闪光边缘、飞溅外滴及散布旋转都要计入脏区。
        extent = 1.0 if b.kind in _RANDOM_DABS else math.sqrt(0.5)
        spread_px = b.spread_radius(maxd)
        pad = maxd * extent + spread_px * 1.5 + 4.0
        xs = [p.x() for p, _ in pts]
        ys = [p.y() for p, _ in pts]
        box = QRectF(min(xs) - pad, min(ys) - pad,
                     max(xs) - min(xs) + pad * 2,
                     max(ys) - min(ys) + pad * 2).toAlignedRect()
        # 对称镜像出去的笔点可能落在很远的地方：缓冲和脏区都要把它们圈进来，
        # 否则镜像出来的那一半会被缓冲边界裁掉。
        if self.sym and self.sym.get("mode", "off") != "off":
            for pos, _pr in pts:
                for tx, ty, _a, _f in symmetry_targets(self.sym, pos.x(), pos.y()):
                    box = box.united(QRectF(tx - pad, ty - pad,
                                            pad * 2, pad * 2).toAlignedRect())
        self.buf.ensure(box)
        if self.buf.img is None:
            # 完全在画布外的轨迹也计入彩虹周期，重新入画不能跳回起始色。
            for pos, _pr in pts:
                if self._path_pos is not None:
                    self._path_length += _dist(self._path_pos, pos)
                self._path_pos = QPointF(pos)
            return
        p = QPainter(self.buf.img)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        # 笔尖本身带空隙的笔（排齿 / 排线 / 网点 / 图章 / 星星…）：
        # 拐弯时笔尖会跟着转，前后两颗笔点的细线互相交叉，交叉处的抗锯齿边缘
        # 会叠出更深的颜色 —— 就是用户说的「拐弯颜色重叠」。
        # 这类笔在**同一笔内**改成「取最大浓度」，线条交叉处不再变深。
        b = self.brush
        if (b.flow >= 0.98 and b.opacity >= 0.98 and not b.build_up
                and (b.kind in special_tips.KINDS or b.kind in STAMP_KINDS)):
            p.setCompositionMode(QPainter.CompositionMode_Lighten)
        p.translate(-self.buf.rect.left(), -self.buf.rect.top())
        if self._sel is not None:
            p.setClipPath(self._sel)
        for pos, pr in pts:
            if self._path_pos is not None:
                self._path_length += _dist(self._path_pos, pos)
            self._path_pos = QPointF(pos)
            self._dab_i += 1
            # 第一个笔点一定画：不然低流量时隔点会让笔画晚十几像素才出现
            if self._dab_step > 1 and (self._dab_i - 1) % self._dab_step:
                continue
            self._dab(p, pos, pr)
        p.end()
        self._pending = self._pending.united(box)

    def _dab(self, p: QPainter, pos: QPointF, pressure: float):
        b = self.brush
        # 角度跟随：先用「上一个笔点 → 这一个笔点」的方向更新笔尖朝向，
        # 之后所有随机量（散布 / 抖动）都在这个朝向上再叠，笔尖才是真的顺着笔画走。
        if b.angle_follow > 0.001:
            if self._prev_pos is not None:
                dx = pos.x() - self._prev_pos.x()
                dy = pos.y() - self._prev_pos.y()
                if dx * dx + dy * dy > 0.25:
                    raw = math.degrees(math.atan2(dy, dx))
                    if self._dir_smooth is None:
                        self._dir_smooth = raw
                    else:
                        # 角度不能「一下就转过去」：拐弯时笔尖瞬间转 90°，
                        # 前后几颗笔点就是好几个不同角度的笔尖叠在一起 ——
                        # 排齿 / 排线这类带空隙的笔尖会交叉成一片，看着就是
                        # 「拐弯处颜色重叠」。这里每颗笔点最多转掉 40% 的角度差，
                        # 笔尖像真笔一样「顺着拐」，线束是弯的而不是糊成一团。
                        d = ((raw - self._dir_smooth + 180.0) % 360.0) - 180.0
                        self._dir_smooth += d * 0.4
                    self._dir = self._dir_smooth
            self._prev_pos = QPointF(pos)
        # 数位板轻触时驱动可能只给 0.01~0.05 的压力。若原样乘进大小/浓淡，
        # 算出来的 alpha 会低到 QPainter 直接当 0，表现为「轻轻画完全不出墨」。
        # 这里给有效压力一个 10% 的地板，并给浓淡压感一个最小可见 alpha。
        p_eff = _clamp(pressure)
        if b.pressure_size or b.pressure_opacity:
            # 驱动刚接触时经常报 0 / 0.01：这里给一个「激活力」地板。
            # 以前是 0.02 —— 数位板轻压时只出 5% 的墨，屏幕上几乎看不见，
            # 就是用户说的「低力度按压画不出来」。抬到 0.05：轻压能画出可见的细线，
            # 又不至于把 0~10% 整段压平（地板再大就会「轻压全是一样粗」）。
            p_eff = max(0.05, p_eff)
        d = b.diameter(p_eff)
        # 起笔渐细：前 taper 段里笔尖由细变粗，模仿笔锋
        if b.taper > 0.001:
            span = max(10.0, b.size * 3.0) * b.taper
            d *= min(1.0, 0.18 + 0.82 * (self.travel / span))
        count = max(1, min(12, int(b.scatter_count)))
        if b.kind in SPRAY_KINDS:
            # 密度 50% = 原样；往右加副本（更密/更聚），往左减副本（更疏/更散）。
            mult = 2.0 ** ((_clamp(b.density) - 0.5) * 4.0)
            count = max(1, min(12, int(round(b.scatter_count * mult))))
            # 范围是外圈直径：范围每扩大一倍，面积是四倍，按面积补副本，
            # 大范围才不会变成几团分开的雾；上限 12 保证跟手。
            ratio = b.range_diameter() / max(1.0, d)
            if ratio > 1.05:
                fill = ratio * ratio * (0.6 + 0.8 * _clamp(b.density))
                count = max(count, min(12, int(math.ceil(fill))))
        for _ in range(count):
            dd = d
            if b.size_jitter > 0.001:
                dd *= 1.0 - b.size_jitter * random.random()
            if dd < 0.15:
                continue
            a = min(1.0, b.dab_alpha(p_eff, b.cover_ratio(p_eff, self._dab_step)))
            if b.pressure_opacity:
                # 轻触 / 驱动掉帧也要留一点可见的墨；不然 alpha 会被量化成 0。
                # 地板给小一点，浓淡压感才有足够的层次。
                a = max(a, 0.010)
            if b.flow_jitter > 0.001:
                # 逐笔点的墨量抖动：间距大 / 软笔时看得到粗糙的浓淡颗粒。
                # 不要挪到合成时去乘 —— 那会让每一小段的浓度不同，
                # 段与段的交界会留下一条条硬边（试过，像贴了胶带）。
                a *= 1.0 - b.flow_jitter * random.random() * 0.9
            if a <= 0.0006:
                continue          # 真正低到看不见才跳过；门槛高了笔画会断成一段一段
            px, py = pos.x(), pos.y()
            rad = b.spread_radius(dd)
            if rad > 0.001 or count > 1:
                if b.kind in SPRAY_KINDS:
                    # 密度高 → 半径指数更大，点更靠中心；密度低 → 更靠外圈。
                    p_exp = max(0.2, min(1.6, 0.55 + (b.density - 0.5) * 1.5))
                    rr = rad * (random.random() ** p_exp)
                    ang = random.uniform(0, math.tau)
                    px += math.cos(ang) * rr
                    py += math.sin(ang) * rr
                else:
                    px += random.uniform(-rad, rad)
                    py += random.uniform(-rad, rad)
            ang = b.angle
            if b.angle_follow > 0.001:
                # 完全跟随 = 笔尖朝向永远等于运笔方向；半跟随则是两者的折中
                ang = b.angle + b.angle_follow * self._dir
            if b.angle_jitter > 0.001:
                ang += random.uniform(-180, 180) * b.angle_jitter
            rnd = b.roundness
            if b.roundness_jitter > 0.001:
                rnd = max(0.05, min(1.0, rnd + random.uniform(-1, 1) * b.roundness_jitter))
            color = self._dab_color()
            # 1~2px 的笔：不套用抗锯齿贴图，直接落一个实心像素，
            # 否则会淡成一片灰、看起来像「画不出来」。
            # 只到 2.5px —— 3~5px 也走整数方块的话，压感就只剩 1/2/3/4 这几档
            # （小笔刷「只有几档粗细」就是这么来的）。3px 以上改用贴图，
            # 宽度可以是小数，压感才是连续的。
            if dd <= 2.5:
                side = max(1.0, float(int(dd + 0.5)))
                for tx, ty, _da, _flip in symmetry_targets(self.sym, px, py):
                    p.save()
                    p.setOpacity(a)
                    p.setPen(Qt.NoPen)
                    p.setBrush(QBrush(color))
                    p.setRenderHint(QPainter.Antialiasing, False)
                    # 对齐整数像素：1~2px 的笔必须是干脆的实心像素，不能被半像素糊成灰边。
                    half = int(side) // 2
                    x0 = round(tx) - half
                    y0 = round(ty) - half
                    p.drawRect(QRectF(x0, y0, side, side))
                    p.restore()
                continue
            # 小笔（3~8px）直接现画一颗柔/硬圆，不走缩放贴图：
            # 贴图是按整数直径缓存、再缩到实际尺寸的，4px 这种缩得只剩两三个像素，
            # 抗锯齿那圈基本被抹掉，放大看就是一格一格的楼梯（硬笔尤其明显）。
            # 现画的圆是解析出来的，边缘一定是平滑的。
            if (dd <= 8.0 and b.kind not in _NO_DISC
                    and b.kind not in special_tips.KINDS):
                for tx, ty, _da, _flip in symmetry_targets(self.sym, px, py):
                    p.save()
                    p.setOpacity(a)
                    p.translate(tx, ty)
                    if rnd < 0.995:
                        p.scale(1.0, max(0.05, rnd))
                    # 现画 = 1:1，过渡带就是 0.9px，硬笔边缘干净但不生硬
                    _paint_disc(p, 0.0, 0.0, max(0.35, dd / 2.0), b.hardness,
                                color, edge=0.9)
                    p.restore()
                continue
            # 喷雾 / 飞溅也改走缓存贴图：以前每颗笔点现画 100~360 个圆，
            # 大笔刷下每帧几百次 drawEllipse，笔画会明显慢半拍。
            random_tip = False
            color_tip = b.kind in ("neon", "rainbow")
            random_start = random.getstate() if random_tip else None
            random_end = None
            if not random_tip and not color_tip:
                # 小笔尖按整数像素缓存，5px 不能被四舍五入成 4px；
                # 大笔尖仍按偶数分桶，避免尺寸滑杆把缓存撑爆。
                if dd <= 32:
                    bucket = max(1, int(round(dd)))
                else:
                    bucket = max(2, int(round(dd / 2.0)) * 2)
                stamps = STAMPS.get(bucket, b.hardness, color, b.grain,
                                    b.grain_scale, b.kind)
                stamp = stamps[random.randrange(len(stamps))]
            # 变换顺序是世界旋转 × 世界镜像 × 笔尖旋转 × 圆度。
            # 不用“任意翻转都取负角”的近似，双轴翻转也能正确处理非对称笔尖。
            for tx, ty, dda, flip in symmetry_targets(self.sym, px, py):
                p.save()
                p.setOpacity(a)
                p.translate(tx, ty)
                if abs(dda) > 0.01:
                    p.rotate(dda)
                p.scale(-1.0 if flip & 1 else 1.0, -1.0 if flip & 2 else 1.0)
                if abs(ang) > 0.01:
                    p.rotate(ang)
                if rnd < 0.995:
                    p.scale(1.0, max(0.05, rnd))
                if random_tip:
                    # 同一 dab 重放同一随机状态，镜像分支不额外推进全局 RNG。
                    if random_end is not None:
                        random.setstate(random_start)
                    self._random_dab(p, dd, a, color)
                    if random_end is None:
                        random_end = random.getstate()
                elif color_tip:
                    special_tips.paint_color_tip(p, dd, color, b.kind, b.hardness)
                else:
                    p.drawImage(QRectF(-dd / 2.0, -dd / 2.0, dd, dd), stamp,
                                QRectF(0, 0, stamp.width(), stamp.height()))
                p.restore()
            if random_tip:
                random.setstate(random_end)

    def _random_dab(self, p: QPainter, d: float, a: float, color: QColor):
        """喷雾 / 飞溅的单个笔点：现算一堆大小不一的点。

        喷雾 = 又密又细的小点（PS 的喷枪就是这样）；飞溅 = 大小差得很开的墨滴 + 墨团。
        都在笔点里现随机，所以整笔不会有「同一块贴图重复盖章」的假感。
        """
        b = self.brush
        r = d / 2.0
        if r <= 0.3 or a <= 0.002:
            return
        p.setPen(Qt.NoPen)
        p.setOpacity(1.0)          # 浓度已经算进每颗点的 alpha 里
        if b.kind == "spray":
            # 关键：点要**看得见是一颗一颗**（PS 喷漆就是这种散点）。
            # 点太小、太密就成了灰雾 —— 之前笔刷一调大就糊成一团就是这个原因。
            # 每颗笔点的点数基本恒定（点的大小随笔尖放大）：这样笔刷调大调小，
            # 看起来都是「同样密度的散点」，不会小笔是雾、大笔是糊
            n = int(max(40, min(360, 100 + r * 0.6)))
            for _ in range(n):
                ang = random.uniform(0, math.tau)
                rr = r * (random.random() ** 0.75) * 1.02   # 中间密、边缘稀
                # 点是「细颗粒」：大小约占笔尖的 1%~4%，大笔也不会变成一堆大圆饼
                dot = max(0.5, min(4.5, r * (0.004 + 0.016 * random.random() ** 1.4)))
                if random.random() < 0.05:
                    dot *= random.uniform(1.5, 2.4)         # 偶尔一颗大的
                c = QColor(color)
                # 单颗点浓一点：PS 的喷漆是「一颗一颗看得见」，不是一层灰雾
                c.setAlphaF(max(0.0, min(1.0, a * random.uniform(0.45, 1.0))))
                p.setBrush(QBrush(c))
                p.drawEllipse(QPointF(math.cos(ang) * rr, math.sin(ang) * rr), dot, dot)
            return
        # ---- 飞溅：墨团 + 大小差得很开的液滴 ----
        for _ in range(random.randint(2, 5)):
            cx = random.uniform(-0.45, 0.45) * r
            cy = random.uniform(-0.45, 0.45) * r
            base = r * random.uniform(0.08, 0.22)
            c = QColor(color)
            c.setAlphaF(max(0.05, min(1.0, a * random.uniform(0.7, 1.0))))
            p.setBrush(QBrush(c))
            # 一团墨由 3~5 个错位小圆叠出来，边缘就不是一个正圆了
            for _k in range(random.randint(3, 5)):
                ox = random.uniform(-0.7, 0.7) * base
                oy = random.uniform(-0.7, 0.7) * base
                p.drawEllipse(QPointF(cx + ox, cy + oy),
                              base * random.uniform(0.5, 1.0),
                              base * random.uniform(0.5, 1.0))
        n = int(max(12, min(240, r * r * 0.055)))
        for _ in range(n):
            ang = random.uniform(0, math.tau)
            rr = r * (random.random() ** 0.45) * 1.15
            dot = max(0.45, r * (random.random() ** 2.6) * 0.16)
            if random.random() < 0.07:
                dot *= random.uniform(2.0, 4.0)         # 偶尔一颗特别大的墨滴
            c = QColor(color)
            # 一部分墨滴是半透明的，叠起来才有「墨」的层次
            al = (random.uniform(0.30, 1.0) if random.random() < 0.8
                  else random.uniform(0.12, 0.40))
            c.setAlphaF(max(0.0, min(1.0, a * al)))
            p.setBrush(QBrush(c))
            p.drawEllipse(QPointF(math.cos(ang) * rr, math.sin(ang) * rr), dot, dot)

    def _dab_color(self) -> QColor:
        b = self.brush
        c = QColor(self.color)
        if b.kind == "rainbow":
            h = max(0.0, c.hsvHueF())
            cycle = max(8.0, min(8192.0, b.color_cycle))
            c = QColor.fromHsvF((h + self._path_length / cycle) % 1.0,
                               max(0.8, c.hsvSaturationF()), max(0.85, c.valueF()), c.alphaF())
        if b.hue_jitter < 0.001 and b.sat_jitter < 0.001 and b.val_jitter < 0.001:
            return c
        h, s, v, _ = c.getHsvF()
        h = (h + self._dh + random.uniform(-1, 1) * 0.02 * b.hue_jitter) % 1.0
        s = max(0.0, min(1.0, s - self._ds * 0.5 + random.uniform(-1, 1) * 0.10 * b.sat_jitter))
        v = max(0.02, min(1.0, v - self._dv * 0.4 + random.uniform(-1, 1) * 0.10 * b.val_jitter))
        return QColor.fromHsvF(h, s, v, c.alphaF())

    def _wet_ring(self, p: QPainter, px: float, py: float, d: float,
                  a: float, color: QColor):
        """湿边：在笔尖外沿压一圈略深的颜色，水彩会自然积色。"""
        b = self.brush
        outer = QPainterPath()
        outer.addEllipse(QRectF(px - d / 2.0, py - d / 2.0, d, d))
        inner = QPainterPath()
        kk = max(0.30, 0.72 - 0.25 * b.wet)
        id_ = d * kk
        inner.addEllipse(QRectF(px - id_ / 2.0, py - id_ / 2.0, id_, id_))
        c = QColor(color).darker(135)
        c.setAlpha(int(max(0, min(255, 255 * a * b.wet * 0.45))))
        p.save()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(c))
        p.setOpacity(1.0)            # 环本身的 alpha 已经算过浓度
        p.drawPath(outer.subtracted(inner))
        p.restore()

    # -- 采样 -------------------------------------------------------
    def _curve_to(self, p1: QPointF, pr1: float):
        """中点二次样条：以上一点为控制点、从上一段中点画到本段中点。

        这样既消掉了折线的硬拐角，又不会像「镜像控制点」那样在急转弯处过冲，
        抬笔/急停时不会甩出钩子。
        """
        p0 = self.smooth if self.smooth is not None else p1
        a = self._anchor if self._anchor is not None else p0
        m = QPointF((p0.x() + p1.x()) / 2.0, (p0.y() + p1.y()) / 2.0)
        pr0 = self.last_p
        approx = _dist(a, m) + _dist(p0, p1) * 0.5
        step = self.brush.stamp_spacing(pr0)
        out = []
        # 关键：从上一段剩下的余量接着走，而不是「每小段至少画 2 个笔点」——
        # 后者会让间距永远失效（鼠标每次只移动几像素，间距调多大都是一条实线）。
        dist = self._carry
        guard = 0
        while dist <= approx and guard < 4000:
            u = dist / approx if approx > 1e-6 else 1.0
            iu = 1.0 - u
            x = iu * iu * a.x() + 2 * u * iu * p0.x() + u * u * m.x()
            y = iu * iu * a.y() + 2 * u * iu * p0.y() + u * u * m.y()
            out.append((QPointF(x, y), pr0 + (pr1 - pr0) * u))
            dist += step
            guard += 1
        self._carry = max(0.0, dist - approx)
        self.travel += approx
        self._anchor = m
        return out

    def _line_to(self, p1: QPointF, pr: float):
        p0 = self._anchor if self._anchor is not None else p1
        d = _dist(p0, p1)
        if d < 1e-6:
            return []
        step = self.brush.stamp_spacing(pr)
        out = []
        dist = self._carry
        guard = 0
        while dist <= d and guard < 4000:
            u = dist / d
            out.append((QPointF(p0.x() + (p1.x() - p0.x()) * u,
                                p0.y() + (p1.y() - p0.y()) * u), pr))
            dist += step
            guard += 1
        self._carry = max(0.0, dist - d)
        self.travel += d
        self._anchor = QPointF(p1)
        return out

    def _stabilized(self, pos: QPointF) -> QPointF:
        """抖动修正。三种作用叠加，用户只拖一根滑杆：

        - **迟滞（拉绳）**：笔尖在几像素内乱抖时笔迹不动，只有拉出一定距离才跟上。
          这是「手抖被吃掉」的关键 —— 低通只能把抖动变小，迟滞才能把抖动压平。
        - **低通**：跟上之后也是慢慢跟，把折角磨圆，线条更顺。
        - **直线吸附**：最近一小段原始笔迹如果本来就接近一条直线，就把输出点投影到
          这条直线上（最小二乘拟合）。所以「手大致画直」时出来的是一条真正笔直的线，
          就是画世界那种能拉出直线的感觉；真在画弯的地方残差大，不会被吸附。

        三者强度都随 stabilize 增长。0 = 完全跟手；1 = 最稳（直线画得最直，代价是急转弯略微滞后）。
        """
        b = self.brush
        st = _clamp(b.stabilize)
        if st <= 0.001:
            return QPointF(pos)
        if self._stab is None:
            self._stab = QPointF(pos)
            self._hist = [(pos.x(), pos.y())]
            return QPointF(pos)
        dx = pos.x() - self._stab.x()
        dy = pos.y() - self._stab.y()
        d = (dx * dx + dy * dy) ** 0.5
        if d < 1e-6:
            return QPointF(self._stab)
        # 迟滞半径 0~9px：常见手抖在 2~4px，滑杆过 60% 就能吃掉
        slack = st * st * 9.0
        if d <= slack:
            return QPointF(self._stab)
        # 低通系数按**时间**算，不按事件数：
        # 以前是「每个移动事件走剩余距离的 4%」（st=1），事件密的设备跟得紧、
        # 稀的设备拖成一条直弦；而且手一快（一次移动几十像素）永远追不上，
        # 画个圈最后只剩一条直线（用户反馈的「画笔跟不上光标」）。
        now = time.monotonic()
        if self._t_last is None:
            dt = 0.012
        else:
            dt = min(0.05, max(0.002, now - self._t_last))
        self._t_last = now
        tau = 0.006 + 0.30 * st * st          # st=1 → 0.31s 的时间常数
        k = 1.0 - math.exp(-dt / max(1e-4, tau))
        # 滞后上限：允许笔迹落在光标后面（这就是「稳」的来源），但不能无限掉队。
        # 上限跟笔径挂钩 —— 22px 的笔拖出 90px 的差距，看起来就像「笔不跟手」了。
        lag_max = max(8.0, b.size * 0.8) + 24.0 * st * st
        if d > lag_max:
            k = max(k, 1.0 - lag_max / d)
        # 起笔前几个点几乎完全跟手：否则高防抖下「笔尖慢慢追上来」，
        # 开头会被拉成一条明显的直弦（画圆时右边会多一个折角）
        self._stab_n += 1
        if self._stab_n < 4:
            k = k + (1.0 - k) * (1.0 - self._stab_n / 4.0)
        self._stab = QPointF(self._stab.x() + dx * k, self._stab.y() + dy * k)
        # 记录原始点（只留最近一小段），用来自动吸附成直线
        self._hist.append((pos.x(), pos.y()))
        win = 6 + int(round(st * 42))
        if len(self._hist) > win:
            del self._hist[:len(self._hist) - win]
        if st > 0.18:
            self._snap_straight(st)
        return QPointF(self._stab)

    def _snap_straight(self, st: float):
        """把平滑后的点投影到「最近一小段笔迹」的拟合直线上（拉直线）。

        用协方差矩阵的主方向当直线方向，垂直于它的残差 RMS 判断「这一段到底直不直」：
        够直才吸附，画弯的地方不动 —— 所以不会把曲线硬掰成直线。
        """
        pts = self._hist
        n = len(pts)
        if n < 10:
            return
        span = math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1])
        if span < 10.0:
            return                  # 点一下、抖一抖不该被拉成一条线
        mx = sum(p[0] for p in pts) / n
        my = sum(p[1] for p in pts) / n
        sxx = sum((p[0] - mx) ** 2 for p in pts) / n
        syy = sum((p[1] - my) ** 2 for p in pts) / n
        sxy = sum((p[0] - mx) * (p[1] - my) for p in pts) / n
        ang = 0.5 * math.atan2(2.0 * sxy, sxx - syy)
        dx, dy = math.cos(ang), math.sin(ang)
        # 垂直于主方向的残差 RMS = 协方差矩阵较小特征值的平方根
        rms = math.sqrt(max(0.0, (sxx + syy) / 2.0
                            - math.hypot((sxx - syy) / 2.0, sxy)))
        tol = 0.7 + 2.6 * st        # 滑杆越高，允许的抖动越大（越好拉直线）
        if rms >= tol:
            w = 0.0
        else:
            w = min(1.0, (1.0 - rms / tol) * 1.6)
        # 权重也做低通：吸附 / 松开是渐变的，否则曲线拐弯处会留下一个折角
        self._snap_w += (w - self._snap_w) * 0.25
        if self._snap_w <= 0.01:
            return
        vx = self._stab.x() - mx
        vy = self._stab.y() - my
        t = vx * dx + vy * dy
        sx = mx + dx * t
        sy = my + dy * t
        k = self._snap_w
        self._stab = QPointF(self._stab.x() + (sx - self._stab.x()) * k,
                             self._stab.y() + (sy - self._stab.y()) * k)

    def _flow_tile(self) -> QImage:
        """流量抖动用的噪声遮罩（白色 + 变化的 alpha，平滑放大成 192×192）。

        整笔共用一张、按**文档坐标**平铺，相邻两次合成对得上，不会留下接缝。
        """
        if self._noise is not None:
            return self._noise
        n = 10
        j = _clamp(self.brush.flow_jitter)
        small = QImage(n, n, FORMAT_ARGB)
        small.fill(Qt.transparent)
        p = QPainter(small)
        for y in range(n):
            for x in range(n):
                a = int(round(255 * (1.0 - 0.85 * j * random.random())))
                p.fillRect(x, y, 1, 1, QColor(255, 255, 255, a))
        p.end()
        # 镜像拼成 2n×2n 再放大：左右、上下边缘的取值天然相等，
        # 平铺时不会每隔一个贴图宽度冒出一条接缝（不镜像的话一眼就能看见）。
        big = QImage(n * 2, n * 2, FORMAT_ARGB)
        big.fill(Qt.transparent)
        q = QPainter(big)
        q.drawImage(0, 0, small)
        q.drawImage(n, 0, small.mirrored(True, False))
        q.drawImage(0, n, small.mirrored(False, True))
        q.drawImage(n, n, small.mirrored(True, True))
        q.end()
        self._noise = big.scaled(n * 32, n * 32, Qt.IgnoreAspectRatio,
                                 Qt.SmoothTransformation)
        self._session["flow_tile"] = self._noise
        return self._noise

    def _apply_grain(self, patch: QImage, r: QRect):
        """纸纹颗粒：按**文档坐标**平铺，所以笔点叠多少遍都不会被平均掉。

        （以前是给每个笔尖贴随机颗粒，间距一小就叠成一团糊，看着像没效果。）
        """
        b = self.brush
        tile = grain_tile(b.grain, b.grain_scale, 0)
        ts = tile.width()
        ox, oy = self._grain_off
        q = QPainter(patch)
        q.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        x = -((r.left() + ox) % ts)
        while x < r.width():
            y = -((r.top() + oy) % ts)
            while y < r.height():
                q.drawImage(QPointF(x, y), tile)
                y += ts
            x += ts
        q.end()

    def _apply_wet_final(self):
        """湿边：整笔画完后，沿**整笔的外沿**压一圈深色。

        以前是每合成一次就压一次 —— 笔画没画完时，当前那一小段的外沿也会被压，
        于是沿路径留下一串月牙形的深色弧线（用户反馈的「弯弯的月牙线条」就是这个）。
        """
        b = self.brush
        if b.wet <= 0.02 or self.erase or self.buf.img is None:
            return
        r = self.dirty.intersected(self.buf.rect)
        r = r.intersected(QRect(0, 0, self.layer.image.width(), self.layer.image.height()))
        if r.width() < 4 or r.height() < 4:
            return
        src_rect = r.translated(-self.buf.rect.left(), -self.buf.rect.top())
        src = self.buf.img.copy(src_rect)
        w, h = src.width(), src.height()
        k = max(2, int(round(max(w, h) / 26)))
        blur = src.scaled(max(1, w // k), max(1, h // k), Qt.IgnoreAspectRatio,
                          Qt.SmoothTransformation)
        blur = blur.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        edge = src.copy()
        q = QPainter(edge)
        q.setCompositionMode(QPainter.CompositionMode_DestinationOut)
        q.drawImage(0, 0, blur)
        q.setCompositionMode(QPainter.CompositionMode_SourceIn)
        col = QColor(self.color).darker(150)
        col.setAlpha(int(255 * min(1.0, 0.35 + b.wet * 0.65)))
        q.fillRect(QRectF(0, 0, w, h), col)
        q.end()
        if b.kind in special_tips.MASK_KINDS:
            special_tips.apply_pattern(edge, r, b.kind, b.pattern_scale)
        p = QPainter(self.layer.image)
        p.setOpacity(_clamp(b.opacity))
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        p.drawImage(r.topLeft(), edge)
        p.end()
        self.layer.touch()

    def _apply_screen(self, patch: QImage, r: QRect):
        """网点屏：把整笔按**画布坐标**打上一层圆点阵列（半色调效果）。

        笔尖里画网格是不行的：笔点位置一变，网格就对不齐，叠出来是糊的。
        """
        b = self.brush
        step = int(max(4, min(28, round(b.size * 0.26))))
        tile = _SCREEN_CACHE.get(step)
        if tile is None:
            tile = QImage(step, step, FORMAT_ARGB)
            tile.fill(Qt.transparent)
            tp = QPainter(tile)
            tp.setRenderHint(QPainter.Antialiasing, True)
            tp.setPen(Qt.NoPen)
            tp.setBrush(QBrush(QColor(255, 255, 255, 255)))
            rad = max(0.8, step * 0.34)
            tp.drawEllipse(QPointF(step / 2.0, step / 2.0), rad, rad)
            tp.end()
            _SCREEN_CACHE[step] = tile
        q = QPainter(patch)
        q.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        x = -(r.left() % step)
        while x < r.width():
            y = -(r.top() % step)
            while y < r.height():
                q.drawImage(QPointF(x, y), tile)
                y += step
            x += step
        q.end()

    def _apply_wet(self, patch: QImage):
        """湿边：只在**整笔的外沿**压一圈深色（每颗笔点都压的话会糊成一片）。"""
        b = self.brush
        w, h = patch.width(), patch.height()
        if w < 4 or h < 4:
            return
        # 缩小再放大 ≈ 模糊，用来求「内缩后的 alpha」。
        # 缩得越狠，边带越宽（水彩的积色边通常 2~4px）
        k = max(2, int(round(max(w, h) / 26)))
        blur = patch.scaled(max(1, w // k), max(1, h // k), Qt.IgnoreAspectRatio,
                            Qt.SmoothTransformation)
        blur = blur.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        edge = patch.copy()
        q = QPainter(edge)
        q.setCompositionMode(QPainter.CompositionMode_DestinationOut)
        q.drawImage(0, 0, blur)          # edge.alpha = 原 alpha - 模糊 alpha
        q.setCompositionMode(QPainter.CompositionMode_SourceIn)
        col = QColor(self.color).darker(150)
        col.setAlpha(int(255 * min(1.0, 0.35 + b.wet * 0.65)))
        q.fillRect(QRectF(0, 0, w, h), col)
        q.end()
        p = QPainter(patch)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        p.drawImage(0, 0, edge)
        p.end()

    # -- 合成 -------------------------------------------------------
    def _composite(self) -> QRect:
        r = self._pending.intersected(
            QRect(0, 0, self.layer.image.width(), self.layer.image.height()))
        if r.isEmpty() or self.buf.img is None:
            self._pending = QRect()
            return QRect()
        self._pending = QRect()
        p = QPainter(self.layer.image)
        if self._sel is not None:
            p.setClipPath(self._sel)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.drawImage(r, self.before, r)
        # 这里只乘不透明度：它是「整笔的上限」，笔内怎么叠都不会超过它。
        # 流量已经在笔点里算过（按间距归一化），所以在同一笔里反复扫过同一处
        # 会继续加深；只有 build_up 开启时，第二笔才从当前图层继续叠色。
        p.setOpacity(_clamp(self.brush.opacity))
        p.setCompositionMode(QPainter.CompositionMode_DestinationOut if self.erase
                             else QPainter.CompositionMode_SourceOver)
        src_rect = r.translated(-self.buf.rect.left(), -self.buf.rect.top())
        b = self.brush
        pattern = b.kind in special_tips.MASK_KINDS
        needs_patch = pattern or (not self.erase and
                       (b.flow_jitter > 0.001 or b.grain > 0.005
                        or b.kind == "halftone"))
        if needs_patch:
            patch = self.buf.img.copy(src_rect)
            if b.flow_jitter > 0.001:
                # 笔点叠满后浓度一律到顶，逐笔点的抖动会被吃掉；这里给整笔蒙一张
                # 按文档坐标平铺的噪声，墨量才有「忽多忽少」的起伏（而且没有接缝）。
                q = QPainter(patch)
                q.setCompositionMode(QPainter.CompositionMode_DestinationIn)
                tile = self._flow_tile()
                ts = tile.width()
                x = -(r.left() % ts)
                while x < r.width():
                    y = -(r.top() % ts)
                    while y < r.height():
                        q.drawImage(QPointF(x, y), tile)
                        y += ts
                    x += ts
                q.end()
            if b.grain > 0.005:
                self._apply_grain(patch, r)
            if b.kind == "halftone":
                self._apply_screen(patch, r)
            if pattern:
                special_tips.apply_pattern(patch, r, b.kind, b.pattern_scale)
            p.drawImage(r.topLeft(), patch)
        else:
            p.drawImage(r, self.buf.img, src_rect)
        p.end()
        self.layer.touch()
        self.dirty = self.dirty.united(r)
        return r

    # -- 对外 -------------------------------------------------------
    def _needs_dir(self) -> bool:
        """笔尖是不是「有朝向」的：扁笔、方头、凿头这些，方向不对就一眼看出来。"""
        b = self.brush
        return b.angle_follow > 0.001 and b.roundness < 0.985

    def begin(self, pos: QPointF, pressure: float) -> QRect:
        p = QPointF(pos)
        self.smooth = QPointF(p)
        self._anchor = QPointF(p)
        self._stab = QPointF(p)
        self._hist = [(p.x(), p.y())]
        self._snap_w = 0.0
        self._stab_n = 0
        self.last_raw = QPointF(p)
        self.last_p = pressure
        self._carry = 0.0
        self._prev_pos = QPointF(p)      # 让第一颗笔点也能算出运笔方向
        if self._needs_dir():
            # 扁笔 / 方头笔的第一颗笔点还不知道往哪走，先攒着：
            # 立刻画的话会按「笔刷默认角度」印一个方块，笔画头上就多一个
            # 方向不对的小尾巴（方头马克笔上下画时最明显）。
            self._pending_first = (QPointF(p), pressure)
            return QRect()
        self._stamp([(QPointF(p), pressure)])
        # 起笔这一颗已经落下了，间距游标要往前推一格：
        # 否则下一段采样的第一个点正好还落在起笔点上，等于原地盖了两颗 ——
        # 印章类笔刷（星星 / 爱心 / 六边形…）看着就是「落笔处两个粘在一起」。
        self._carry = self.brush.stamp_spacing(pressure)
        return QRect() if self.preview else self._composite()

    def move(self, pos: QPointF, pressure: float) -> QRect:
        if not self.active:
            return QRect()
        if self.smooth is None:
            return self.begin(pos, pressure)
        self.last_raw = QPointF(pos)
        tgt = self._stabilized(pos)
        # 攒着的第一颗笔点：现在知道往哪走了，按真实方向补画上去
        if self._pending_first is not None:
            p0, pr0 = self._pending_first
            self._pending_first = None
            dx0 = tgt.x() - p0.x()
            dy0 = tgt.y() - p0.y()
            if dx0 * dx0 + dy0 * dy0 > 0.25:
                self._dir = math.degrees(math.atan2(dy0, dx0))
            self._stamp([(p0, pr0)])
            # 同上：这颗补画的起笔点已经占了位置，间距游标往前推一格
            self._carry = self.brush.stamp_spacing(pr0)
        if _dist(self.smooth, tgt) < 0.15:
            # 笔没动（手停在原地）：不要再盖笔点。
            # 以前只在「压力也没变」时才跳过，可数位板停住时压力一直在抖，
            # 于是原地叠了几十颗 —— 排齿 / 排线这类带空隙的笔尖会被填满，
            # 看着就是「停留处颜色重叠变深」。
            return QRect()
        # 一次移动跨得太远（甩笔/修正拉绳）时拆成小段，避免把曲线截成一条直线
        cur = QPointF(self.smooth)
        remain = _dist(cur, tgt)
        guard = 0
        pts = []
        while remain > 1e-6 and guard < 400:
            step = min(remain, max(4.0, self.brush.size * 1.2))
            u = step / remain if remain > 0 else 1.0
            nxt = QPointF(cur.x() + (tgt.x() - cur.x()) * u,
                          cur.y() + (tgt.y() - cur.y()) * u)
            self.smooth = cur
            pts.extend(self._curve_to(nxt, pressure))
            cur = nxt
            remain -= step
            guard += 1
        self.smooth = QPointF(tgt)
        self.last_p = pressure
        if pts:
            self._stamp(pts)
        return QRect() if self.preview else self._composite()

    def _finish_tail(self, raw: QPointF):
        """收笔补齐：沿**真实轨迹**把防抖欠下的那一小段走完。

        以前是直接朝抬笔点拉一条直线 —— 防抖越重笔迹落后越多，收笔就成了一条
        明显的直弦（画圆时右边会多出一个折角）。现在从原始点历史里找出
        「笔迹已经走到哪」，把后面剩下的原始点**再过一遍抖动修正**补过去：
        形状跟手画的一致，也不会把刚被抹平的手抖重新画回来。
        """
        b = self.brush
        cur = QPointF(self.smooth if self.smooth is not None else raw)
        path = [QPointF(x, y) for x, y in self._hist]
        best_i, best_d = -1, 1e18
        for i, p in enumerate(path):
            d = (p.x() - cur.x()) ** 2 + (p.y() - cur.y()) ** 2
            if d < best_d:
                best_i, best_d = i, d
        tail = path[best_i + 1:] if best_i >= 0 else []
        if not tail or _dist(tail[-1], raw) > 0.5:
            tail.append(QPointF(raw))
        # 这段顺着真实笔迹走，可以给得长一些；实在太长（甩笔）才截断
        limit = max(140.0, b.size * 6.0)
        total = 0.0
        prev = cur
        last = QPointF(cur)
        for p in tail:
            total += _dist(prev, p)
            prev = p
            if total > limit:
                break
            self.smooth = QPointF(last)
            sp = self._stabilized(p)
            pts = self._curve_to(sp, self.last_p)
            if pts:
                self._stamp(pts)
            last = QPointF(sp)
        # 收笔**必须停在抬笔点**：防抖欠下的那一段沿直线补过去。
        # 以前是反复喂同一个点让低通慢慢收敛（30 次只走掉七成），防抖拉满时
        # 笔迹会明显停在光标圈外面 —— 用户看到的就是「笔不跟着鼠标」。
        self.smooth = QPointF(last)
        gap = _dist(self._anchor if self._anchor is not None else last, raw)
        if gap > 0.6:
            pts = self._line_to(QPointF(raw), self.last_p)
            if pts:
                self._stamp(pts)
            self.smooth = QPointF(raw)

    def end(self):
        if not self.active:
            return None
        if self._pending_first is not None:
            # 只点了一下、没移动：按笔刷默认角度补一颗（不然点了没反应）
            p0, pr0 = self._pending_first
            self._pending_first = None
            self._stamp([(p0, pr0)])
        raw = self.last_raw
        if raw is not None:
            self._finish_tail(raw)
        self._composite()
        self._apply_wet_final()      # 湿边：整笔画完只压一次外沿
        self.active = False
        if self.dirty.isEmpty():
            return None
        self.layer.has_content = True
        r = self.dirty.intersected(
            QRect(0, 0, self.layer.image.width(), self.layer.image.height()))
        if r.isEmpty():
            return None
        edit = PixelEdit(self.layer, r, self.undo_before.copy(r),
                         self.layer.image.copy(r))
        edit.from_stroke = True      # push() 见到这个标记就不清会话
        return edit


# ---------------------------------------------------------------- 涂抹
class SmudgeStroke:
    """涂抹工具：把颜色「抓」进笔里，再一路拖着糊出去。

    和 PS 的涂抹对齐的四条规则（也是这版重写的原因）：

    ① **每一步做线性插值**：out = 画布×(1-kM) + 笔里颜色×kM（k = 力度，
       M = 笔尖遮罩）。遮罩边缘靠拢得少、中心靠拢得多，过渡才是连续的；
       alpha 也一起插值，所以透明图层上的硬边也能被抹柔。
    ② **每一步的混合量按「走过一个笔径」定义**，不再按笔刷 spacing 归一化。
       以前按 6% 间距归一化后每步只有 1.3%：8bit 下只有 3 级色阶，遮罩边缘
       那圈（0.2×1.3% = 0.26 级）直接被四舍五入成 0 —— 落色只剩中间一块，
       一步一道硬边，叠起来就是「暴力分层」。现在 20% 力度 ≈ 每步 10%，
       柔边有 25 级色阶，才真的柔。
    ③ **落点按走过的距离排**，不按事件数排。手一快事件间隔只有 2px，
       按事件落点等于间距变成 2px，抓色/落色都快十倍，颜色瞬间被冲淡，
       拖出来是一条发白的带子。
    ④ **笔里的颜色每步重新抓一把**（k×0.55），并带一点模糊：抓得太少会把
       颜色「冻」在笔里，和脚下的新颜色之间留一条硬断层；太多又变成原地糊。

    它必须直接改图层像素（涂抹要读到自己刚糊过的结果），所以没走 Stroke 的
    离屏缓冲；撤销记录仍然只存脏矩形，和画笔一样省。
    """

    # 内部间距（占直径比例）。涂抹看的是「覆盖」，不跟笔刷的 spacing 走：
    # 6% 的间距会让每步的混合量小到被 8bit 吃掉；18% 又会让每一步的笔头
    # 在轨迹边缘留下一个「串珠」状的小鼓包。12% 是既没有串珠、混合量又够大的点。
    STEP = 0.12

    def __init__(self, doc, layer, brush: Brush, strength: float = 0.2, sym=None):
        self.doc = doc
        self.layer = layer
        self.brush = brush
        # 力度下限 6%：再低每步就不到 1 级色阶，边缘会被量化成硬边（见类注释 ②）
        self.strength = max(0.06, min(1.0, float(strength)))
        # 「力度」= 笔走过**一个笔径**之后，颜色被带走多少。换算成每一步的混合量，
        # 这样改内部间距时手感不会跟着变。12% 间距下 20% 力度 ≈ 每步 10%，
        # 8bit 下有 25 级色阶，柔边不会被四舍五入吃掉。
        self._k = 1.0 - (1.0 - self.strength) ** (self.STEP / 0.25)
        # 抓色比例：每步把落点颜色按 0.35×k 混进笔里。
        # 抓得多 → 笔里立刻变成脚下（多是空白），颜色带不出去、拖两下就没了；
        # 抓得少 → 颜色能带得远，但要靠「每步模糊」把硬边糊开，才不会像挪色块。
        self._grab_amount = self._k * 0.35
        self._carry = 1.0                     # 距离下一个落点还差多少（跨事件累积）
        self.sym = sym
        self.before = layer.image.copy()      # 整层快照（撤销用，和画笔一致）
        self.dirty = QRect()
        self._pending = QRect()
        self._last = None
        self.active = True
        # 笔里的颜色缓冲：起笔时按**当前笔径**分配，压感变大再扩容。
        # 以前扩容是「旧内容居中不缩放」，笔里会多出一圈透明，那一圈盖到画布上
        # 就是一道硬边环 —— 涂抹时压力一变就出现「分层」。现在扩容连内容一起缩放。
        self._n = 0
        # 每个对称副本一个缓冲：共用一个的话，镜像那一半每步都在重复同一个图案，
        # 拖出来是一排梳齿状的条纹（用户反馈的「对称涂抹另一边有条纹」）。
        self._ntargets = max(1, len(symmetry_targets(sym, 0.0, 0.0)))
        self._bufs = []
        self._mask = None
        sel = doc.selection if doc.has_selection() else None
        self._sel = QPainterPath(sel) if sel is not None else None

    # -- 笔里的那团颜色 ---------------------------------------------
    def _build_mask(self):
        """笔尖遮罩。

        涂抹的笔头要比画笔更软：PS 的涂抹默认就是柔边，硬边会把颜色推成
        一圈一圈的分层。最高只到 40% 硬度。
        另外存一份 0~1 的 float 数组，落色时按像素乘力度用。
        """
        n = self._n
        mask = QImage(n, n, FORMAT_ARGB)
        mask.fill(Qt.transparent)
        p = QPainter(mask)
        p.setRenderHint(QPainter.Antialiasing, True)
        soft = min(0.30, max(0.05, self.brush.hardness * 0.40))
        _paint_disc(p, n / 2.0, n / 2.0, max(0.8, n / 2.0 - 0.8),
                    soft, QColor(255, 255, 255, 255))
        p.end()
        self._mask = mask
        a = np.frombuffer(mask.constBits(), dtype=np.uint8).reshape(n, n, 4)[..., 3]
        self._mask_arr = a.astype(np.float32) / 255.0
        self._mask4 = self._mask_arr[..., None]
        self._mask_cache = {}
        # 大笔径下每步要算 240×240×4 个浮点，反复 new 数组会明显拖慢；
        # 这几块临时区按尺寸复用（涂抹是逐笔点的热路径）。
        self._pa = np.empty((n, n, 4), dtype=np.float32)
        self._out = np.empty((n, n, 4), dtype=np.float32)
        self._blur = np.empty((n, n, 4), dtype=np.float32)

    def _prepare(self, d: float):
        """按当前笔径准备缓冲；笔径变了就重采样（**旧内容一起缩放**，
        不能居中留一圈透明 —— 那一圈就是涂抹「分层」的来源）。

        差 4px 以内不重建：每颗笔点都重采样一次 240×240 太贵，
        而 4px 的笔径误差肉眼看不出来。
        """
        d = max(2.0, float(d))
        n = int(round(d)) + 2
        if self._bufs and abs(n - self._n) <= 4:
            return
        olds, old_n = self._bufs, self._n
        bufs = []
        for i in range(self._ntargets):
            buf = QImage(n, n, FORMAT_ARGB)
            buf.fill(Qt.transparent)
            if i < len(olds):
                p = QPainter(buf)
                p.setRenderHint(QPainter.SmoothPixmapTransform, True)
                p.drawImage(QRectF(0, 0, n, n), olds[i], QRectF(0, 0, old_n, old_n))
                p.end()
            bufs.append(buf)
        self._bufs = bufs
        self._n = n
        self._build_mask()

    def _grab(self, cx: float, cy: float, mix: float, buf):
        """抓一把落点处的颜色，按 mix 混进笔里。透明也要抓 —— 不然涂抹永远擦不淡。

        全程 numpy：区域直接从图层字节里取（出界的部分补透明），
        和「DestinationIn 压淡 + SourceOver 叠上」相比，
        既是真的线性插值（不会在透明边缘多压掉一截、越涂越白），也快得多。
        """
        n = self._n
        img = self.layer.image
        W, H = img.width(), img.height()
        x0 = int(round(cx - n / 2.0))
        y0 = int(round(cy - n / 2.0))
        ix0, iy0 = max(0, x0), max(0, y0)
        ix1, iy1 = min(W, x0 + n), min(H, y0 + n)
        pa = self._pa
        pa.fill(0.0)
        if ix1 > ix0 and iy1 > iy0:
            src = np.frombuffer(img.constBits(), dtype=np.uint8).reshape(H, W, 4)
            pa[iy0 - y0:iy1 - y0, ix0 - x0:ix1 - x0] = src[iy0:iy1, ix0:ix1]
        # 注意：这里**不能**再乘一次遮罩。遮罩只在落色时用（k×M）；
        # 笔里的颜色要是也被遮罩压过一遍，落色就成了「双重衰减」——
        # 每步 alpha 会按 (1 - kM(1-M)) 往下掉，在同一处多抹几下画面就没了，
        # 表现就是「涂抹越涂越像橡皮擦」。
        m = max(0.02, min(1.0, mix))
        ba = np.frombuffer(buf.bits(), dtype=np.uint8).reshape(n, n, 4)
        out = self._out
        blur = self._blur
        np.multiply(ba, 1.0 - m, out=out)
        np.multiply(pa, m, out=blur)
        out += blur
        # 每步给笔里的颜色做一次盒式模糊，半径跟着「一步走多远」走：
        # 一步走 10px 就糊开 3~4px，相邻两次落色才叠得平、看不出梳齿；
        # 只搬不糊的话，涂抹就只是「把一块颜色挪个位置」，看着像橡皮擦。
        r = max(1, min(14, int(round(min(self.STEP * n, 26.0) * 0.6))))
        out = _box_blur(out, r)
        out += 0.5
        np.clip(out, 0.0, 255.0, out=out)
        ba[:] = out

    def _stamp_arrays(self, d: float, buf):
        """笔里颜色 / 遮罩按当前笔径取一份。

        笔里颜色每一步都在变，所以不能缓存；遮罩是固定的，按尺寸缓存。
        返回 (src, mask, keep)：keep 是缩放出来的临时图，必须一直被引用着，
        否则 numpy 视图会指向已经释放的内存。
        """
        n = self._n
        keep = None
        if abs(d - n) <= 5.0:
            src = np.frombuffer(buf.constBits(),
                                dtype=np.uint8).reshape(n, n, 4)
            msk = self._mask_arr
        else:
            k = max(2, int(round(d)))
            keep = buf.scaled(k, k, Qt.IgnoreAspectRatio,
                              Qt.SmoothTransformation)
            src = np.frombuffer(keep.constBits(), dtype=np.uint8).reshape(k, k, 4)
            msk = self._mask_cache.get(k)
            if msk is None:
                mi = self._mask.scaled(k, k, Qt.IgnoreAspectRatio,
                                       Qt.SmoothTransformation)
                msk = (np.frombuffer(mi.constBits(), dtype=np.uint8)
                       .reshape(k, k, 4)[..., 3].astype(np.float32) / 255.0)
                if len(self._mask_cache) > 24:
                    self._mask_cache.clear()
                self._mask_cache[k] = msk
        return src, msk, keep

    def _blend(self, cx: float, cy: float, d: float, amount: float, buf):
        """落点：out = 画布×(1-kM) + 笔里颜色×kM（k = 力度，M = 遮罩）。

        这是**线性插值**，不是「叠一层」。差别在透明边缘：
        SourceOver 只会让 alpha 变大，涂抹永远只能把形状往外撑；
        插值能把 alpha 一起带过去，硬边才会被抹柔（和 PS 一致）。
        8bit 下每步有 0.06~1.0 的混合量，柔边不会被四舍五入成硬边。
        """
        img = self.layer.image
        W, H = img.width(), img.height()
        src, msk, _keep = self._stamp_arrays(d, buf)
        sh, sw = msk.shape[:2]
        x0 = int(round(cx - sw / 2.0))
        y0 = int(round(cy - sh / 2.0))
        ix0, iy0 = max(0, x0), max(0, y0)
        ix1, iy1 = min(W, x0 + sw), min(H, y0 + sh)
        if ix1 <= ix0 or iy1 <= iy0:
            return
        k = msk[iy0 - y0:iy1 - y0, ix0 - x0:ix1 - x0][..., None] * amount
        dst = np.frombuffer(img.bits(), dtype=np.uint8).reshape(H, W, 4)
        sub = dst[iy0:iy1, ix0:ix1].astype(np.float32)
        sub *= (1.0 - k)
        sub += src[iy0 - y0:iy1 - y0, ix0 - x0:ix1 - x0] * k
        sub += 0.5
        np.clip(sub, 0.0, 255.0, out=sub)
        if self._sel is None:
            dst[iy0:iy1, ix0:ix1] = sub        # 直接写图层字节，省一次贴图
        else:
            w, h = ix1 - ix0, iy1 - iy0
            pim = QImage(sub.astype(np.uint8).tobytes(), w, h, w * 4,
                         FORMAT_ARGB).copy()
            p = QPainter(img)
            p.setClipPath(self._sel)
            p.setCompositionMode(QPainter.CompositionMode_Source)
            p.drawImage(ix0, iy0, pim)
            p.end()
        r = QRect(ix0, iy0, ix1 - ix0, iy1 - iy0)
        self.layer.touch()
        self.dirty = self.dirty.united(r)
        self._pending = self._pending.united(r)

    def _step(self, x: float, y: float, d: float):
        # 每个对称副本各用各的缓冲：先落色再抓色，两边互不干扰，
        # 镜像那一半才不会每步重复同一个图案（条纹）。
        for i, (tx, ty, _a, _flip) in enumerate(symmetry_targets(self.sym, x, y)):
            if i >= len(self._bufs):
                break
            buf = self._bufs[i]
            self._blend(tx, ty, d, self._k, buf)
            self._grab(tx, ty, self._grab_amount, buf)

    # -- 对外 -------------------------------------------------------
    def begin(self, pos: QPointF, pressure: float) -> QRect:
        d = max(2.0, self.brush.diameter(pressure))
        self._prepare(d)
        for i, (tx, ty, _a, _f) in enumerate(symmetry_targets(self.sym, pos.x(), pos.y())):
            if i >= len(self._bufs):
                break
            self._grab(tx, ty, 1.0, self._bufs[i])   # 起笔：每个副本先抓满
        self._last = QPointF(pos)
        self._carry = max(1.0, min(self.STEP * d, 26.0))  # 先走满一个间距才落第一笔
        return QRect()

    def move(self, pos: QPointF, pressure: float) -> QRect:
        if not self.active:
            return QRect()
        if self._last is None:
            return self.begin(pos, pressure)
        d = max(2.0, self.brush.diameter(pressure))
        self._prepare(d)
        p0 = self._last
        dist = _dist(p0, pos)
        if dist < 0.05:
            return QRect()
        step = max(1.0, min(self.STEP * d, 26.0))
        # 落点必须按**走过的距离**排，不能按事件数排：手一快，事件间隔 2px，
        # 按事件落点就等于间距变成 2px —— 抓色/落色都快十倍，颜色瞬间被冲淡，
        # 拖出来的是一条发白的带子。这里跨事件累积距离，间距永远等于 STEP。
        acc = self._carry
        guard = 0
        while acc <= dist and guard < 400:
            f = acc / dist
            self._step(p0.x() + (pos.x() - p0.x()) * f,
                       p0.y() + (pos.y() - p0.y()) * f, d)
            acc += step
            guard += 1
        self._carry = acc - dist
        self._last = QPointF(pos)
        r = self._pending
        self._pending = QRect()
        return r

    def end(self):
        if not self.active:
            return None
        self.active = False
        if self.dirty.isEmpty():
            return None
        self.layer.has_content = True
        r = self.dirty.intersected(
            QRect(0, 0, self.layer.image.width(), self.layer.image.height()))
        if r.isEmpty():
            return None
        return PixelEdit(self.layer, r, self.before.copy(r),
                         self.layer.image.copy(r))


# ---------------------------------------------------------------- 试笔图
_PREVIEW_CACHE = {}


class _PreviewDoc:
    """只给 Stroke 用的假文档（试笔预览不需要图层/选区）。"""
    selection = None

    def has_selection(self):
        return False


class _PreviewLayer:
    def __init__(self, img: QImage):
        self.image = img
        self.has_content = True

    def touch(self):
        pass


def preview_image(brush: Brush, w: int, h: int, color: QColor = None,
                  ss: int = 4) -> QImage:
    """用真正的笔刷引擎在 w×h 里画一条 S 形试笔线（预设缩略图 / 预览条共用）。

    缩略图很小（约 60×36），按 1:1 画出来笔触会被抗锯齿糊成一片。
    所以内部按 ss 倍超采样渲染、再把 devicePixelRatio 设成 ss，
    调用方按逻辑尺寸绘制就能得到干净的细笔触（铅笔的纸纹、蜡笔的毛边才看得出来）。

    ss 可以按控件大小调：大预览条用 2 倍就够了，4 倍纯属浪费
    （实测 250×32 从 19ms 降到 5ms，拖参数时的手感差别很明显）。
    """
    color = QColor(226, 226, 226) if color is None else QColor(color)
    ss = max(1, int(ss))
    key = (round(w), round(h), color.rgba(), ss,
           tuple(getattr(brush, f) for f in Brush.FIELDS))
    hit = _PREVIEW_CACHE.get(key)
    if hit is not None:
        return hit
    W, H = max(1, round(w * ss)), max(1, round(h * ss))
    img = QImage(W, H, FORMAT_ARGB)
    img.fill(Qt.transparent)
    layer = _PreviewLayer(img)
    doc = _PreviewDoc()
    # 缩略图里压一下笔尖直径，粗笔也能看清笔触轮廓；颗粒按超采样倍数放大
    b = brush.copy()
    b.size = max(1.5, min(b.size * ss, H * 0.52))
    b.grain_scale = brush.grain_scale * ss
    b.pattern_scale = brush.pattern_scale * ss
    b.color_cycle = brush.color_cycle * ss
    b.taper = 0.0
    b.stabilize = 0.0
    b.wet = brush.wet
    st = Stroke(doc, layer, b, color, preview=True)
    n = 60
    x0, x1 = W * 0.05, W * 0.95
    mid = H * 0.5
    amp = H * 0.30
    pts = []
    for i in range(n + 1):
        t = i / n
        x = x0 + (x1 - x0) * t
        y = mid - math.sin(t * math.pi * 2.0) * amp
        # 两端收细、中间压重，笔锋和压感一眼看得出来
        pr = 0.12 + 0.88 * math.sin(t * math.pi) ** 0.7
        pts.append((QPointF(x, y), pr))
    st.begin(pts[0][0], pts[0][1])
    for p, pr in pts[1:]:
        st.move(p, pr)
    st.end()
    img.setDevicePixelRatio(ss)
    if len(_PREVIEW_CACHE) > 600:      # 内置笔刷多了，缓存太小会边滚边重画
        _PREVIEW_CACHE.clear()
    _PREVIEW_CACHE[key] = img
    return img


# ---------------------------------------------------------------- 撤销
class SelectionEdit:
    """选区变化也能撤销：只记前后两个 QPainterPath，不动像素。

    silent=True 表示「不把文档标成已修改」：选区变了不等于画面变了，
    否则随便框一下就弹出「有未保存的修改」。
    """
    kind = "selection"
    silent = True

    def __init__(self, doc, before, after):
        self.before = QPainterPath(before) if before is not None else None
        self.after = QPainterPath(after) if after is not None else None
        self.rect = QRect(0, 0, doc.w, doc.h)

    @staticmethod
    def _apply(doc, path):
        doc.selection = QPainterPath(path) if path is not None else None

    def undo(self, doc):
        self._apply(doc, self.before)

    def redo(self, doc):
        self._apply(doc, self.after)

    def label(self):
        return "选区"


class PixelEdit:
    kind = "pixels"

    def __init__(self, layer, rect: QRect, before: QImage, after: QImage):
        self.layer = layer
        self.rect = QRect(rect)
        self.before = before
        self.after = after

    def _blit(self, img: QImage):
        p = QPainter(self.layer.image)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.drawImage(self.rect.topLeft(), img)
        p.end()

    def undo(self, doc):
        self._blit(self.before)
        self.layer.touch()
        doc.recompose(self.rect)

    def redo(self, doc):
        self._blit(self.after)
        self.layer.touch()
        doc.recompose(self.rect)

    def label(self):
        return "笔迹"


class ExtEdit(PixelEdit):
    """带「画布外内容」的像素撤销：移动 / 自由变换用。

    图层像素只有画布那么大，推到画布外的部分存在 layer.off 里，
    撤销 / 重做时要把这份也一起还原，否则会留下「幽灵内容」。
    """

    def __init__(self, layer, rect, before, after,
                 off_before=None, pos_before=None, off_after=None, pos_after=None):
        super().__init__(layer, rect, before, after)
        self.off_before = off_before
        self.pos_before = QPoint(pos_before) if pos_before is not None else QPoint(0, 0)
        self.off_after = off_after
        self.pos_after = QPoint(pos_after) if pos_after is not None else QPoint(0, 0)

    def undo(self, doc):
        super().undo(doc)
        self.layer.off = self.off_before
        self.layer.off_pos = QPoint(self.pos_before)

    def redo(self, doc):
        super().redo(doc)
        self.layer.off = self.off_after
        self.layer.off_pos = QPoint(self.pos_after)


class StructEdit:
    """图层结构变更（新建/删除/合并/排序/属性）的通用撤销记录。"""
    kind = "struct"

    def __init__(self, doc, label="图层操作"):
        self.label_ = label
        self.before = doc.snapshot()
        self.after = None

    def capture(self, doc):
        self.after = doc.snapshot()

    def undo(self, doc):
        doc.restore(self.before)

    def redo(self, doc):
        doc.restore(self.after)

    def label(self):
        return self.label_


# ---------------------------------------------------------------- 图层
class LayerGroup:
    """图层组：只做分类 / 整体显示隐藏 / 整组锁定，成员仍是普通图层。"""

    def __init__(self, name: str):
        self.name = name
        self.visible = True
        self.locked = False
        self.expanded = True
        self.opacity = 1.0


class Layer:
    _seq = 0

    def __init__(self, name: str, width: int, height: int, fill: QColor = None):
        Layer._seq += 1
        self.uid = Layer._seq
        self.name = name
        self.image = QImage(width, height, FORMAT_ARGB)
        self.image.fill(fill if fill is not None else Qt.transparent)
        self.visible = True
        self.has_content = fill is not None and QColor(fill).alpha() > 0
        self.opacity = 1.0
        self.blend = "正常"
        self.locked = False
        self.group = ""
        # 背景层：固定在最底层，不能拖动 / 上下移 / 删除 / 进组。
        # 只靠「索引 0」判断不可行——用户把背景拖走之后索引就变了，反而更难复位。
        self.is_bg = False
        self._thumb = None
        self._thumb_key = None
        # 画布外的内容：图层像素只有画布这么大，移动 / 自由变换把内容推到画布外时，
        # 外面那部分单独存一张大图（off + off_pos），下次移动 / 变换还能拿回来。
        self.off = None
        self.off_pos = QPoint(0, 0)
        self._stash = None          # 旧字段，保留以免老代码报错

    def touch(self):
        self._thumb = None
        self._thumb_key = None
        self._stash = None

    # -- 画布外内容 -------------------------------------------------
    def ext(self):
        """完整内容图 + 它的左上角文档坐标（有画布外内容时就是那张大图）。"""
        if self.off is not None:
            return self.off, QPoint(self.off_pos)
        return self.image, QPoint(0, 0)

    def set_ext(self, img: QImage, pos, w: int, h: int):
        """把一张可能超出画布的大图拆成「画布内 image」+「画布外 off」。"""
        if isinstance(pos, QPoint):
            pos = QPoint(pos)
        else:
            pos = QPoint(int(pos[0]), int(pos[1]))
        canvas = QImage(w, h, FORMAT_ARGB)
        canvas.fill(Qt.transparent)
        p = QPainter(canvas)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.drawImage(pos.x(), pos.y(), img)      # img 的左上角落在文档坐标 pos 上
        p.end()
        self.image = canvas
        # 只有「画布外面真的有像素」才留着这张大图，否则白白占内存
        outside = (pos.x() < 0 or pos.y() < 0
                   or pos.x() + img.width() > w or pos.y() + img.height() > h)
        if outside:
            outside = _outside_has_content(img, pos.x(), pos.y(), w, h)
        self.off = img if outside else None
        self.off_pos = QPoint(pos) if outside else QPoint(0, 0)
        self._thumb = None
        self._thumb_key = None

    def drop_off(self):
        self.off = None
        self.off_pos = QPoint(0, 0)

    def thumb(self, w=40, h=32) -> QPixmap:
        key = (w, h)
        if self._thumb is not None and self._thumb_key == key:
            return self._thumb
        im = self.image.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pm = QPixmap(w, h)
        pm.fill(QColor("#4A4A4A"))
        p = QPainter(pm)
        # 棋盘底，透明区域一眼可见
        cell = 6
        for yy in range(0, h, cell):
            for xx in range(0, w, cell):
                if ((xx // cell) + (yy // cell)) % 2 == 0:
                    p.fillRect(xx, yy, cell, cell, QColor("#5E5E5E"))
        p.drawImage((w - im.width()) // 2, (h - im.height()) // 2, im)
        p.end()
        self._thumb = pm
        self._thumb_key = key
        return pm


# ---------------------------------------------------------------- 文字对象
class TextItem:
    """一段「活」的文字：不烧进图层像素，随时能再选中改字 / 改字体 / 改颜色。

    参考 PS 的文字图层：位置、字体、字号、粗斜体、颜色、可见性都记在这里，
    每次合成时现画，所以改完立刻生效，也不会被别的图层的不透明度 / 锁定影响。
    """

    _seq = 0

    def __init__(self, text: str, x: float, y: float, family: str, px: float,
                 bold: bool = False, italic: bool = False, color=None, name: str = "",
                 html: str = ""):
        TextItem._seq += 1
        self.uid = TextItem._seq
        self.text = str(text)
        self.x = float(x)
        self.y = float(y)
        self.family = family
        self.px = float(px)
        self.bold = bool(bold)
        self.italic = bool(italic)
        self.color = QColor(color) if color is not None else QColor(20, 20, 20)
        # 用户按选区改过样式（几个字不同色 / 不同字号 / 加粗）时才有 html。
        # 空字符串表示整段同一样式，走原来那条简单路径（渲染结果完全不变）。
        self.html = str(html or "")
        self.visible = True
        self.editing = False          # 正在编辑框里改：合成时先不画，免得重影
        self.group = ""               # 所属图层组的 gid（文字也能进组，空串 = 不在组里）
        self.name = name or self.auto_name()

    def auto_name(self) -> str:
        first = (self.text.strip().split("\n") or [""])[0].strip()
        if len(first) > 10:
            first = first[:10] + "…"
        return f"文字 {first}" if first else "文字"

    # -- 几何 / 绘制
    def font(self):
        import fonts as fontlib
        return fontlib.make_font(self.family, self.px, self.bold, self.italic)

    def rect(self) -> QRectF:
        """渲染后的外接矩形（文档坐标）。"""
        if self.html:
            s = self._rich_doc().size()
            return QRectF(self.x, self.y, max(s.width(), 1.0), max(s.height(), 1.0))
        fm = QFontMetricsF(self.font())
        w = h = 0.0
        for line in self.text.split("\n"):
            w = max(w, fm.horizontalAdvance(line))
            h += fm.height()
        return QRectF(self.x, self.y, max(w, 1.0), max(h, 1.0))

    def contains(self, x: float, y: float, pad: float = 4.0) -> bool:
        return self.rect().adjusted(-pad, -pad, pad, pad).contains(QPointF(x, y))

    def _rich_doc(self):
        doc = QTextDocument()
        doc.setDocumentMargin(0)
        doc.setDefaultFont(self.font())
        doc.setHtml(self.html)
        return doc

    def draw(self, p: QPainter):
        if not self.visible or not self.text.strip():
            return
        if self.html:
            # 局部样式（几个字不同颜色 / 字号）走富文本渲染
            doc = self._rich_doc()
            p.save()
            p.translate(self.x, self.y)
            doc.drawContents(p)
            p.restore()
            return
        f = self.font()
        fm = QFontMetricsF(f)
        p.setFont(f)
        p.setPen(QPen(QColor(self.color)))
        for i, line in enumerate(self.text.split("\n")):
            if not line:
                continue
            p.drawText(QPointF(self.x, self.y + fm.ascent() + i * fm.height()), line)

    # -- 存档 / 撤销
    def to_dict(self) -> dict:
        return {"uid": self.uid, "text": self.text, "x": self.x, "y": self.y,
                "family": self.family, "px": self.px, "bold": self.bold,
                "italic": self.italic, "color": self.color.name(),
                "visible": self.visible, "name": self.name, "html": self.html,
                "group": self.group}

    @staticmethod
    def from_dict(d: dict) -> "TextItem":
        it = TextItem(d.get("text", ""), d.get("x", 0), d.get("y", 0),
                      d.get("family", ""), d.get("px", 48),
                      d.get("bold", False), d.get("italic", False),
                      QColor(d.get("color", "#141414")), d.get("name", ""),
                      d.get("html", ""))
        if d.get("uid"):
            it.uid = int(d["uid"])
        it.visible = bool(d.get("visible", True))
        it.group = d.get("group", "") or ""
        return it


class TextEdit:
    """文字对象的增删改：只存文字列表，不用拷贝整张画布，撤销很轻。"""

    kind = "text"

    def __init__(self, doc, label="文字"):
        self.label_ = label
        self.before = doc.texts_dict()
        self.after = None

    def capture(self, doc):
        self.after = doc.texts_dict()

    def undo(self, doc):
        doc.restore_texts(self.before)

    def redo(self, doc):
        doc.restore_texts(self.after)

    def label(self):
        return self.label_


# ---------------------------------------------------------------- 文档
class Document:
    def __init__(self, width: int, height: int, background: QColor = None,
                 ppi: int = 300):
        self.w = int(width)
        self.h = int(height)
        # 画布分辨率（每英寸像素）。导出 PNG/JPG 时会写进文件，否则看图软件
        # 一律按 96 DPI 显示 —— 明明建的是 300dpi 的 A4，导出来却写 96。
        self.ppi = max(1, int(ppi))
        self.layers = []
        base = Layer("背景", self.w, self.h, background if background is not None
                     else QColor(255, 255, 255, 255))
        base.is_bg = True
        self.layers.append(base)
        self.active = 0
        self.groups = {}           # gid -> LayerGroup
        self.texts = []            # TextItem：浮在图层之上的「活」文字
        self._gseq = 0
        self.selection = None      # QPainterPath（文档坐标）
        self.undo_stack = []
        self.redo_stack = []
        self.path = None
        self.modified = False
        self.title = "未命名"
        self.composite = QImage(self.w, self.h, FORMAT_ARGB)
        self.composite.fill(Qt.transparent)
        self._stroke_session = None   # 见 Stroke.__init__（不透明度封顶用）
        self.recompose()

    # -- 图层 -------------------------------------------------------
    @property
    def layer(self) -> Layer:
        if not self.layers:
            return None
        self.active = max(0, min(self.active, len(self.layers) - 1))
        return self.layers[self.active]

    def snap(self) -> QRect:
        return QRect(0, 0, self.w, self.h)

    @property
    def bg_layer(self):
        """背景层（固定在最底层的那张）。老文件可能没有，返回 None。"""
        for l in self.layers:
            if getattr(l, "is_bg", False):
                return l
        return None

    def add_layer(self, name=None, above=True, select=True):
        if len(self.layers) >= MAX_LAYERS:
            return None
        if name is None:
            n = 1
            existing = {l.name for l in self.layers}
            while f"图层 {n}" in existing:
                n += 1
            name = f"图层 {n}"
        layer = Layer(name, self.w, self.h)
        idx = self.active + 1 if above else self.active
        idx = max(0, min(idx, len(self.layers)))
        self.layers.insert(idx, layer)
        if select:
            self.active = idx
        self.modified = True
        self.recompose()
        return layer

    def add_layer_object(self, layer: Layer, idx=None, select=True):
        idx = len(self.layers) if idx is None else idx
        self.layers.insert(idx, layer)
        if select:
            self.active = idx
        self.recompose()
        return layer

    def remove_layer(self, idx=None):
        if len(self.layers) <= 1:
            return False
        idx = self.active if idx is None else idx
        if not (0 <= idx < len(self.layers)):
            return False
        if getattr(self.layers[idx], "is_bg", False):
            return False          # 背景层不能删，要清空内容请用「清除图层内容」
        self.layers.pop(idx)
        self.active = min(idx, len(self.layers) - 1)
        self.prune_groups()
        self.modified = True
        self.recompose()
        return True

    def duplicate_layer(self, idx=None):
        if len(self.layers) >= MAX_LAYERS:
            return None
        idx = self.active if idx is None else idx
        src = self.layers[idx]
        dup = Layer(src.name + " 副本", self.w, self.h)
        dup.image = src.image.copy()
        dup.visible = src.visible
        dup.opacity = src.opacity
        dup.blend = src.blend
        self.layers.insert(idx + 1, dup)
        self.active = idx + 1
        self.modified = True
        self.recompose()
        return dup

    def move_layer(self, idx: int, delta: int):
        j = idx + delta
        if not (0 <= idx < len(self.layers)) or not (0 <= j < len(self.layers)):
            return False
        if getattr(self.layers[idx], "is_bg", False):
            return False          # 背景层钉在最底层
        if getattr(self.layers[j], "is_bg", False):
            return False          # 没有图层能压到背景层下面
        self.layers[idx], self.layers[j] = self.layers[j], self.layers[idx]
        self.active = j
        self.modified = True
        self.recompose()
        return True

    # -- 图层组 -----------------------------------------------------
    def add_group(self, name: str, indices, texts=None):
        """把若干图层（和文字对象）放进一个新组，并让它们在列表里保持相邻。"""
        members = sorted({i for i in indices
                          if 0 <= i < len(self.layers)
                          and not getattr(self.layers[i], "is_bg", False)})
        tmembers = sorted({i for i in (texts or [])
                           if 0 <= i < len(self.texts)})
        if not members and not tmembers:
            return None
        self._gseq += 1
        gid = f"g{self._gseq}"
        self.groups[gid] = LayerGroup(name or f"组 {self._gseq}")
        if members:
            block = [self.layers[i] for i in members]
            rest = [l for i, l in enumerate(self.layers) if i not in set(members)]
            insert_at = sum(1 for i in range(members[-1] + 1)
                            if i not in set(members))
            self.layers = rest[:insert_at] + block + rest[insert_at:]
            for l in block:
                l.group = gid
            self.active = self.layers.index(block[-1])
        for i in tmembers:
            self.texts[i].group = gid
        self.modified = True
        self.recompose()
        return gid

    def prune_groups(self):
        """删掉已经没有成员的组（合并 / 删除图层 / 删除文字后）。"""
        used = {l.group for l in self.layers if l.group}
        used |= {t.group for t in self.texts if getattr(t, "group", "")}
        for gid in [g for g in self.groups if g not in used]:
            self.groups.pop(gid, None)

    def group_members(self, gid: str):
        return [i for i, l in enumerate(self.layers) if l.group == gid]

    def group_texts(self, gid: str):
        """组里的文字对象下标（按 z 序，后面的在上面）。"""
        return [i for i, t in enumerate(self.texts)
                if getattr(t, "group", "") == gid]

    def dissolve_group(self, gid: str):
        if gid not in self.groups:
            return False
        for l in self.layers:
            if l.group == gid:
                l.group = ""
        for t in self.texts:
            if getattr(t, "group", "") == gid:
                t.group = ""
        self.groups.pop(gid, None)
        self.modified = True
        self.recompose()
        return True

    def group_of(self, layer):
        return self.groups.get(layer.group) if layer is not None and layer.group else None

    def group_of_text(self, item):
        g = getattr(item, "group", "") if item is not None else ""
        return self.groups.get(g) if g else None

    def text_state(self, item):
        """(是否可见, 实际不透明度)——把文字所属组的可见性/不透明度算进去。"""
        g = self.group_of_text(item)
        if g is None:
            return item.visible, 1.0
        return (item.visible and g.visible), g.opacity

    def is_locked(self, layer) -> bool:
        if layer is None:
            return True
        g = self.group_of(layer)
        return bool(layer.locked or (g is not None and g.locked))

    def layer_state(self, layer):
        """(是否可见, 实际不透明度)——把所属组的可见性/不透明度算进去。"""
        g = self.group_of(layer)
        if g is None:
            return layer.visible, layer.opacity
        return (layer.visible and g.visible), layer.opacity * g.opacity

    def merge_down(self, idx=None):
        idx = self.active if idx is None else idx
        if idx <= 0 or idx >= len(self.layers):
            return False
        top, bottom = self.layers[idx], self.layers[idx - 1]
        p = QPainter(bottom.image)
        p.setOpacity(top.opacity)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        if top.visible:
            p.drawImage(0, 0, top.image)
        p.end()
        bottom.touch()
        bottom.drop_off()           # 合并后原来的「画布外内容」就对不上了
        bottom.has_content = True
        self.layers.pop(idx)
        self.active = idx - 1
        self.prune_groups()
        self.modified = True
        self.recompose()
        return True

    def merge_layers(self, indices):
        """把选中的若干图层合并到最下面那一层（保持图层顺序与混合模式）。"""
        idx = sorted({i for i in indices if 0 <= i < len(self.layers)})
        if len(idx) < 2:
            return False
        # 选中里带背景层时一律合并进背景层，别把「固定底层」这张合并掉
        bg_i = next((i for i in idx if getattr(self.layers[i], "is_bg", False)), None)
        if bg_i is not None and bg_i != idx[0]:
            idx = [bg_i] + [i for i in idx if i != bg_i]
        target = self.layers[idx[0]]
        p = QPainter(target.image)
        for i in idx[1:]:
            l = self.layers[i]
            if not l.visible:
                continue
            p.setOpacity(l.opacity)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            p.drawImage(0, 0, l.image)
        p.end()
        target.touch()
        target.has_content = True
        for i in reversed(idx[1:]):
            self.layers.pop(i)
        self.active = idx[0]
        self.prune_groups()
        self.modified = True
        self.recompose()
        return True

    def merge_visible(self):
        vis = [i for i, l in enumerate(self.layers) if l.visible]
        if len(vis) <= 1:
            return False
        target_i = vis[0]
        target = self.layers[target_i]
        p = QPainter(target.image)
        for i in vis[1:]:
            l = self.layers[i]
            p.setOpacity(l.opacity)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            p.drawImage(0, 0, l.image)
        p.end()
        target.touch()
        target.has_content = True
        for i in reversed(vis[1:]):
            self.layers.pop(i)
        self.active = 0
        self.modified = True
        self.recompose()
        return True

    def _apply_grain(self, patch: QImage, r: QRect):
        """纸纹颗粒：按**文档坐标**平铺，所以笔点叠多少遍都不会被平均掉。

        （以前是给每个笔尖贴随机颗粒，间距一小就叠成一团糊，看着像没效果。）
        """
        b = self.brush
        tile = grain_tile(b.grain, b.grain_scale, 0)
        ts = tile.width()
        ox, oy = self._grain_off
        q = QPainter(patch)
        q.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        x = -((r.left() + ox) % ts)
        while x < r.width():
            y = -((r.top() + oy) % ts)
            while y < r.height():
                q.drawImage(QPointF(x, y), tile)
                y += ts
            x += ts
        q.end()

    def _apply_wet_final(self):
        """湿边：整笔画完后，沿**整笔的外沿**压一圈深色。

        以前是每合成一次就压一次 —— 笔画没画完时，当前那一小段的外沿也会被压，
        于是沿路径留下一串月牙形的深色弧线（用户反馈的「弯弯的月牙线条」就是这个）。
        """
        b = self.brush
        if b.wet <= 0.02 or self.erase or self.buf.img is None:
            return
        r = self.dirty.intersected(self.buf.rect)
        r = r.intersected(QRect(0, 0, self.layer.image.width(), self.layer.image.height()))
        if r.width() < 4 or r.height() < 4:
            return
        src_rect = r.translated(-self.buf.rect.left(), -self.buf.rect.top())
        src = self.buf.img.copy(src_rect)
        w, h = src.width(), src.height()
        k = max(2, int(round(max(w, h) / 26)))
        blur = src.scaled(max(1, w // k), max(1, h // k), Qt.IgnoreAspectRatio,
                          Qt.SmoothTransformation)
        blur = blur.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        edge = src.copy()
        q = QPainter(edge)
        q.setCompositionMode(QPainter.CompositionMode_DestinationOut)
        q.drawImage(0, 0, blur)
        q.setCompositionMode(QPainter.CompositionMode_SourceIn)
        col = QColor(self.color).darker(150)
        col.setAlpha(int(255 * min(1.0, 0.35 + b.wet * 0.65)))
        q.fillRect(QRectF(0, 0, w, h), col)
        q.end()
        p = QPainter(self.layer.image)
        p.setOpacity(_clamp(b.opacity))
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        p.drawImage(r.topLeft(), edge)
        p.end()
        self.layer.touch()

    def _apply_screen(self, patch: QImage, r: QRect):
        """网点屏：把整笔按**画布坐标**打上一层圆点阵列（半色调效果）。

        笔尖里画网格是不行的：笔点位置一变，网格就对不齐，叠出来是糊的。
        """
        b = self.brush
        step = int(max(4, min(28, round(b.size * 0.26))))
        tile = _SCREEN_CACHE.get(step)
        if tile is None:
            tile = QImage(step, step, FORMAT_ARGB)
            tile.fill(Qt.transparent)
            tp = QPainter(tile)
            tp.setRenderHint(QPainter.Antialiasing, True)
            tp.setPen(Qt.NoPen)
            tp.setBrush(QBrush(QColor(255, 255, 255, 255)))
            rad = max(0.8, step * 0.34)
            tp.drawEllipse(QPointF(step / 2.0, step / 2.0), rad, rad)
            tp.end()
            _SCREEN_CACHE[step] = tile
        q = QPainter(patch)
        q.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        x = -(r.left() % step)
        while x < r.width():
            y = -(r.top() % step)
            while y < r.height():
                q.drawImage(QPointF(x, y), tile)
                y += step
            x += step
        q.end()

    def _apply_wet(self, patch: QImage):
        """湿边：只在**整笔的外沿**压一圈深色（每颗笔点都压的话会糊成一片）。"""
        b = self.brush
        w, h = patch.width(), patch.height()
        if w < 4 or h < 4:
            return
        # 缩小再放大 ≈ 模糊，用来求「内缩后的 alpha」。
        # 缩得越狠，边带越宽（水彩的积色边通常 2~4px）
        k = max(2, int(round(max(w, h) / 26)))
        blur = patch.scaled(max(1, w // k), max(1, h // k), Qt.IgnoreAspectRatio,
                            Qt.SmoothTransformation)
        blur = blur.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        edge = patch.copy()
        q = QPainter(edge)
        q.setCompositionMode(QPainter.CompositionMode_DestinationOut)
        q.drawImage(0, 0, blur)          # edge.alpha = 原 alpha - 模糊 alpha
        q.setCompositionMode(QPainter.CompositionMode_SourceIn)
        col = QColor(self.color).darker(150)
        col.setAlpha(int(255 * min(1.0, 0.35 + b.wet * 0.65)))
        q.fillRect(QRectF(0, 0, w, h), col)
        q.end()
        p = QPainter(patch)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        p.drawImage(0, 0, edge)
        p.end()

    # -- 合成 -------------------------------------------------------
    def recompose(self, rect: QRect = None):
        r = self.snap() if rect is None else QRect(rect).intersected(self.snap())
        if r.isEmpty():
            return
        p = QPainter(self.composite)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.fillRect(r, Qt.transparent)
        for layer in self.layers:
            vis, op = self.layer_state(layer)
            if not vis or op <= 0.0:
                continue
            p.setOpacity(op)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            p.drawImage(r, layer.image, r)
        # 文字浮在所有图层之上：不受图层不透明度 / 锁定影响，也不会被烧进像素
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setClipRect(r)
        for it in self.texts:
            if it.editing:
                continue
            vis, op = self.text_state(it)
            if not vis or op <= 0.0:
                continue
            p.setOpacity(op)
            it.draw(p)
        p.setOpacity(1.0)
        p.end()

    # -- 文字对象 ---------------------------------------------------
    def add_text(self, item: "TextItem") -> int:
        self.texts.append(item)
        self.modified = True
        self.recompose()
        return len(self.texts) - 1

    def remove_text(self, index: int) -> bool:
        if not (0 <= index < len(self.texts)):
            return False
        self.texts.pop(index)
        self.prune_groups()
        self.modified = True
        self.recompose()
        return True

    def text_at(self, x: float, y: float):
        """点在哪段文字上（从最上面开始找）。组被隐藏时里面的文字点不到。"""
        for i in range(len(self.texts) - 1, -1, -1):
            it = self.texts[i]
            vis, _op = self.text_state(it)
            if vis and not it.editing and it.contains(x, y):
                return i, it
        return None, None

    def texts_dict(self):
        return [t.to_dict() for t in self.texts]

    def restore_texts(self, data):
        self.texts = [TextItem.from_dict(d) for d in (data or [])]
        self.modified = True
        self.recompose()

    def flatten(self) -> QImage:
        out = QImage(self.w, self.h, FORMAT_ARGB)
        out.fill(Qt.transparent)
        p = QPainter(out)
        for layer in self.layers:
            vis, op = self.layer_state(layer)
            if not vis or op <= 0.0:
                continue
            p.setOpacity(op)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            p.drawImage(0, 0, layer.image)
        p.setOpacity(1.0)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        for it in self.texts:
            vis, op = self.text_state(it)
            if not vis or op <= 0.0:
                continue
            p.setOpacity(op)
            it.draw(p)
        p.setOpacity(1.0)
        p.end()
        return out

    def sample(self, x: int, y: int) -> QColor:
        if 0 <= x < self.w and 0 <= y < self.h:
            return self.composite.pixelColor(x, y)
        return QColor(0, 0, 0, 0)

    # -- 快照 / 撤销 ------------------------------------------------
    def snapshot(self):
        return {
            "layers": [(l, l.image.copy(), l.name, l.visible, l.opacity, l.blend, l.group)
                       for l in self.layers],
            "active": self.active,
            "groups": {gid: (g.name, g.visible, g.locked, g.expanded, g.opacity)
                       for gid, g in self.groups.items()},
            "texts": self.texts_dict(),
        }

    def restore(self, snap):
        if not snap:
            return
        self._stroke_session = None
        layers = []
        for item in snap["layers"]:
            l, img, name, vis, op, blend = item[:6]
            l.image = img.copy()
            l.name, l.visible, l.opacity, l.blend = name, vis, op, blend
            l.group = item[6] if len(item) > 6 else ""
            l.touch()
            layers.append(l)
        self.layers = layers
        self.groups = {}
        for gid, val in (snap.get("groups") or {}).items():
            g = LayerGroup(val[0])
            g.visible, g.locked, g.expanded, g.opacity = val[1], val[2], val[3], val[4]
            self.groups[gid] = g
        self.active = min(snap["active"], len(layers) - 1)
        if "texts" in snap:
            self.texts = [TextItem.from_dict(d) for d in (snap.get("texts") or [])]
        self.recompose()

    def clear_session(self):
        self._stroke_session = None

    def push(self, edit):
        if edit is None:
            return
        # 只要不是笔迹本身（填充 / 变换 / 移动 / 图层操作……），会话快照就过期了，
        # 不清掉的话下一笔会拿旧快照去还原，把这次编辑抹掉。
        if not getattr(edit, "from_stroke", False):
            self._stroke_session = None
        self.undo_stack.append(edit)
        if len(self.undo_stack) > 60:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        if not getattr(edit, "silent", False):
            self.modified = True

    def can_undo(self):
        return bool(self.undo_stack)

    def can_redo(self):
        return bool(self.redo_stack)

    def undo(self):
        if not self.undo_stack:
            return False
        self._stroke_session = None
        e = self.undo_stack.pop()
        e.undo(self)
        self.redo_stack.append(e)
        return True

    def redo(self):
        if not self.redo_stack:
            return False
        self._stroke_session = None
        e = self.redo_stack.pop()
        e.redo(self)
        self.undo_stack.append(e)
        return True

    # -- 选区 -------------------------------------------------------
    def has_selection(self) -> bool:
        return self.selection is not None and not self.selection.isEmpty()

    def set_selection(self, path, record: bool = True):
        """改选区，并记一条可撤销的历史（选区本身不是像素编辑）。"""
        before = QPainterPath(self.selection) if self.has_selection() else None
        after = QPainterPath(path) if path is not None else None
        if after is not None and after.isEmpty():
            after = None
        self.selection = QPainterPath(after) if after is not None else None
        if not record:
            return
        same = ((before is None and after is None)
                or (before is not None and after is not None and before == after))
        if not same:
            self.push(SelectionEdit(self, before, after))

    def clear_selection(self):
        self.set_selection(None)

    def select_all(self):
        path = QPainterPath()
        path.addRect(QRectF(0, 0, self.w, self.h))
        self.set_selection(path)

    def invert_selection(self):
        full = QPainterPath()
        full.addRect(QRectF(0, 0, self.w, self.h))
        if self.has_selection():
            self.set_selection(full.subtracted(self.selection))
        else:
            self.set_selection(full)

    # -- 编辑操作 ---------------------------------------------------
    def clear_area(self):
        layer = self.layer
        if layer is None or self.is_locked(layer):
            return None
        before = layer.image.copy()
        p = QPainter(layer.image)
        if self.has_selection():
            p.setClipPath(self.selection)
            r = self.selection.boundingRect().toAlignedRect()
        else:
            r = self.snap()
        p.setCompositionMode(QPainter.CompositionMode_Clear)
        p.fillRect(r, Qt.transparent)
        p.end()
        if not self.has_selection():
            layer.drop_off()        # 整层清空，画布外那部分也一起清掉
        layer.touch()
        layer.has_content = True
        self.recompose(r)
        return PixelEdit(layer, r, before.copy(r), layer.image.copy(r))

    def fill_area(self, color: QColor):
        layer = self.layer
        if layer is None or self.is_locked(layer):
            return None
        before = layer.image.copy()
        p = QPainter(layer.image)
        if self.has_selection():
            p.setClipPath(self.selection)
            r = self.selection.boundingRect().toAlignedRect()
        else:
            r = self.snap()
        p.fillRect(r, color)
        p.end()
        layer.touch()
        layer.has_content = True
        self.recompose(r)
        return PixelEdit(layer, r, before.copy(r), layer.image.copy(r))


# ---------------------------------------------------------------- 移动图层内容
SNAP_PX = 8          # 移动时的吸附容差（像素）


def _fills_canvas(img: QImage, pos, w: int, h: int, step: int = 8) -> bool:
    """这张图摆到 pos 之后，是不是把整个画布都盖住了（四边都不透明）。

    给「整块铺满画布的色块」用的：这种层手一抖挪开几像素，边上就会留一条
    难看的缝，所以松手时要能吸回原位。
    """
    x0, y0 = int(pos[0]), int(pos[1])
    iw, ih = img.width(), img.height()
    for x in range(0, w, step):
        for y in (0, h - 1):
            px, py = x - x0, y - y0
            if not (0 <= px < iw and 0 <= py < ih):
                return False
            if ((img.pixel(px, py) >> 24) & 0xFF) < 250:
                return False
    for y in range(0, h, step):
        for x in (0, w - 1):
            px, py = x - x0, y - y0
            if not (0 <= px < iw and 0 <= py < ih):
                return False
            if ((img.pixel(px, py) >> 24) & 0xFF) < 250:
                return False
    return True


def _outside_has_content(img: QImage, ox: float, oy: float, w: int, h: int,
                         step: int = 4) -> bool:
    """把 img 摆到 (ox,oy) 之后，画布外面还有没有不透明像素。"""
    iw, ih = img.width(), img.height()
    x0, y0 = int(round(ox)), int(round(oy))
    for yy in range(0, ih, step):
        dy = y0 + yy
        if 0 <= dy < h:
            if x0 < 0:
                for xx in range(0, min(iw, -x0), step):
                    if (img.pixel(xx, yy) >> 24) & 0xFF:
                        return True
            if x0 + iw > w:
                for xx in range(max(0, w - x0), iw, step):
                    if (img.pixel(xx, yy) >> 24) & 0xFF:
                        return True
        else:
            for xx in range(0, iw, step):
                if (img.pixel(xx, yy) >> 24) & 0xFF:
                    return True
    return False


class MoveOp:
    """拖动平移图层内容：无选区时移动整层，有选区时只移动选区内的像素。"""

    def __init__(self, doc, layer):
        self.doc = doc
        self.layer = layer
        self.sel = QPainterPath(doc.selection) if doc.has_selection() else None
        self.full = QPainterPath()
        self.full.addRect(QRectF(0, 0, doc.w, doc.h))
        self.lost = False
        # 画布外的内容一起带着走：拖出去再拖回来，外面那部分还在。
        self.off_before = layer.off
        self.pos_before = QPoint(layer.off_pos)
        self.snapped = False
        if self.sel is None:
            src, pos = layer.ext()
            # ext() 在没有画布外内容时返回的就是图层本身，必须拷贝一份：
            # render() 会先清空图层再画这张图，直接画自己等于什么都没画。
            self.src = src.copy()
            self.base = (float(pos.x()), float(pos.y()))
            layer.off = None
            layer.off_pos = QPoint(0, 0)
        else:
            self.src = layer.image.copy()
            self.base = (0.0, 0.0)
        # 整块铺满画布的色块：松手时离原位很近就吸回去，免得边上留一条缝
        self.snap = (self.sel is None
                     and _fills_canvas(self.src, self.base, doc.w, doc.h))

    def _loses_content(self, dx: float, dy: float) -> bool:
        """平移 (dx,dy) 之后有没有内容被推到画布外面（粗采样就够判断）。"""
        im = self.src
        w, h = im.width(), im.height()
        if abs(dx) < 0.5 and abs(dy) < 0.5:
            return False

        def has_pixel(x0, x1, y0, y1):
            x0, y0 = max(0, int(x0)), max(0, int(y0))
            x1, y1 = min(w, int(x1)), min(h, int(y1))
            if x1 <= x0 or y1 <= y0:
                return False
            step = 6
            for yy in range(y0, y1, step):
                for xx in range(x0, x1, step):
                    if (im.pixel(xx, yy) >> 24) & 0xFF:
                        return True
            return False

        if dx > 0 and has_pixel(w - dx, w, 0, h):
            return True
        if dx < 0 and has_pixel(0, -dx, 0, h):
            return True
        if dy > 0 and has_pixel(0, w, h - dy, h):
            return True
        if dy < 0 and has_pixel(0, w, 0, -dy):
            return True
        return False

    def _snap(self, ox: float, oy: float):
        """铺满画布的内容靠近原位时吸附回正，免得边上留一条缝。"""
        if not self.snap:
            return ox, oy
        sx, sy = ox, oy
        if abs(ox) <= SNAP_PX:
            sx = 0.0
        if abs(oy) <= SNAP_PX:
            sy = 0.0
        self.snapped = (abs(sx - ox) > 1e-6 or abs(sy - oy) > 1e-6)
        return sx, sy

    def render(self, dx: float, dy: float):
        img = self.layer.image
        ox, oy = self._snap(self.base[0] + dx, self.base[1] + dy)
        p = QPainter(img)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.fillRect(QRectF(0, 0, img.width(), img.height()), Qt.transparent)
        if self.sel is None:
            p.drawImage(QPointF(ox, oy), self.src)
        else:
            p.save()
            p.setClipPath(self.full.subtracted(self.sel))
            p.drawImage(0, 0, self.src)
            p.restore()
            p.save()
            p.setClipPath(self.sel.translated(ox, oy))
            p.drawImage(QPointF(ox, oy), self.src)
            p.restore()
        p.end()
        self.layer.touch()

    def finish(self, dx: float, dy: float):
        self.render(dx, dy)
        ox, oy = self._snap(self.base[0] + dx, self.base[1] + dy)
        w = self.layer.image.width()
        h = self.layer.image.height()
        rect = QRect(0, 0, w, h)
        if self.sel is not None:
            r = self.sel.boundingRect().toAlignedRect().united(
                self.sel.boundingRect().translated(ox, oy).toAlignedRect())
            rect = r.intersected(rect)
            # 选区要跟着内容一起走（PS 就是这样）。不跟着走的话，下一次拖动
            # 抓的是「原来那块空位」，一拖就散成好几块色块。
            if abs(ox) > 0.01 or abs(oy) > 0.01:
                moved = self.sel.translated(ox, oy)
                self.doc.selection = moved
        before = self.src.copy(rect)
        after = self.layer.image.copy(rect)
        self.layer.has_content = True
        # 内容还在画布外：把「完整内容 + 位置」留着，下次移动 / 变换能拿回来
        self.lost = False
        if self.sel is None:
            self.lost = _outside_has_content(self.src, ox, oy, w, h)
            if self.lost:
                self.layer.off = self.src
                self.layer.off_pos = QPoint(int(round(ox)), int(round(oy)))
            else:
                self.layer.drop_off()
        return ExtEdit(self.layer, rect, before, after,
                       self.off_before, self.pos_before,
                       self.layer.off, self.layer.off_pos)


class GroupEdit:
    """把多个 PixelEdit 合成一步撤销（多图层同时移动 / 合并）。"""

    def __init__(self, edits, label: str = "多图层操作"):
        self.edits = [e for e in edits if e is not None]
        self.label = label

    def undo(self, doc):
        for e in reversed(self.edits):
            e.undo(doc)
        doc.recompose()

    def redo(self, doc):
        for e in self.edits:
            e.redo(doc)
        doc.recompose()


# ---------------------------------------------------------------- 自由变换
class TransformOp:
    """自由变换：移动 / 缩放 / 旋转当前图层（有选区时只变换选区内像素）。"""

    def __init__(self, doc, layer):
        self.doc = doc
        self.layer = layer
        self.sel = QPainterPath(doc.selection) if doc.has_selection() else None
        self.full = QPainterPath()
        self.full.addRect(QRectF(0, 0, doc.w, doc.h))
        # 源内容带上「画布外那部分」：缩回去的时候外面还在
        src, pos = layer.ext()
        self.src_img = src
        self.src_pos = QPoint(pos)
        if self.sel is not None:
            box = self.sel.boundingRect().toRect()
        else:
            box = QRect(pos.x(), pos.y(), src.width(), src.height())
        if box.width() < 1 or box.height() < 1:
            box = QRect(0, 0, doc.w, doc.h)
        self.src_rect = QRectF(box)
        self.content = src.copy(box.translated(-pos.x(), -pos.y()))
        if self.sel is not None:
            mask = QImage(box.size(), FORMAT_ARGB)
            mask.fill(Qt.transparent)
            mp = QPainter(mask)
            mp.setRenderHint(QPainter.Antialiasing, True)
            mp.translate(-box.left(), -box.top())
            mp.fillPath(self.sel, QBrush(QColor(255, 255, 255, 255)))
            mp.end()
            cp = QPainter(self.content)
            cp.setCompositionMode(QPainter.CompositionMode_DestinationIn)
            cp.drawImage(0, 0, mask)
            cp.end()
        self.base = src.copy()
        self.before = layer.image.copy()
        self.off_before = layer.off
        self.pos_before = QPoint(layer.off_pos)
        self.center = QPointF(box.center())
        self.w = float(box.width())
        self.h = float(box.height())
        self.angle = 0.0
        self.flip_h = False
        self.flip_v = False

    # -- 几何 --
    def transform(self) -> QTransform:
        t = QTransform()
        t.translate(self.center.x(), self.center.y())
        t.rotate(self.angle)
        sx = max(0.01, self.w) / max(1.0, self.src_rect.width())
        sy = max(0.01, self.h) / max(1.0, self.src_rect.height())
        t.scale(-sx if self.flip_h else sx, -sy if self.flip_v else sy)
        t.translate(-self.src_rect.center().x(), -self.src_rect.center().y())
        return t

    def handles(self):
        hw, hh = self.w / 2.0, self.h / 2.0
        local = [(-hw, -hh), (0, -hh), (hw, -hh), (hw, 0),
                 (hw, hh), (0, hh), (-hw, hh), (-hw, 0)]
        rot = QTransform()
        rot.translate(self.center.x(), self.center.y())
        rot.rotate(self.angle)
        rot.translate(-self.center.x(), -self.center.y())
        return [rot.map(QPointF(self.center.x() + dx, self.center.y() + dy))
                for dx, dy in local]

    def render(self, extended: bool = False):
        if not extended:
            # 拖动预览：只画到画布这么大（画布外的部分反正看不见），够快
            img = self.layer.image
            p = QPainter(img)
            p.setCompositionMode(QPainter.CompositionMode_Source)
            p.fillRect(QRectF(0, 0, img.width(), img.height()), Qt.transparent)
            if self.sel is not None:
                p.save()
                p.setClipPath(self.full.subtracted(self.sel))
                p.drawImage(self.src_pos, self.base)
                p.restore()
            p.setRenderHint(QPainter.SmoothPixmapTransform, True)
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setTransform(self.transform())
            p.drawImage(self.src_rect.topLeft(), self.content)
            p.end()
            self.layer.touch()
            self.layer.has_content = True
            return
        t = self.transform()
        # 目标区域 = 画布 ∪ 变换后的内容，这样跑到画布外的部分也能留住
        dst = t.mapRect(self.src_rect).toAlignedRect()
        union = dst.united(QRect(0, 0, self.doc.w, self.doc.h))
        big = QImage(union.size(), FORMAT_ARGB)
        big.fill(Qt.transparent)
        p = QPainter(big)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.translate(-union.x(), -union.y())
        if self.sel is not None:
            p.save()
            p.setClipPath(self.full.subtracted(self.sel))
            p.drawImage(self.src_pos, self.base)
            p.restore()
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setTransform(t, True)
        p.drawImage(self.src_rect.topLeft(), self.content)
        p.end()
        self.layer.set_ext(big, union.topLeft(), self.doc.w, self.doc.h)
        self.layer.touch()
        self.layer.has_content = True

    def finish(self):
        self.render(extended=True)      # 落地时把画布外那部分也一起留住
        rect = QRect(0, 0, self.layer.image.width(), self.layer.image.height())
        return ExtEdit(self.layer, rect, self.before, self.layer.image.copy(),
                       self.off_before, self.pos_before,
                       self.layer.off, self.layer.off_pos)


# ---------------------------------------------------------------- 油漆桶
def flood_fill(doc: Document, sx: int, sy: int, color: QColor,
               tolerance: int = 32):
    """在活动图层上做容差填充（选区存在时只填选区内部）。返回 PixelEdit 或 None。"""
    layer = doc.layer
    if layer is None or doc.is_locked(layer):
        return None
    img = layer.image
    if not (0 <= sx < img.width() and 0 <= sy < img.height()):
        return None

    seed = img.pixelColor(sx, sy)
    before = None            # 算完包围盒再取，只存改动的那一块
    if tolerance <= 0 and seed == color and not doc.has_selection():
        return None

    try:
        import numpy as np
    except Exception:
        np = None

    if np is not None:
        # 用非预乘格式算颜色：预乘后的半透明像素 RGB 被 alpha 缩过，
        # 拿它算「离背景多远」会把边缘像素判轻，白边就是这么留下来的。
        src = img.convertToFormat(QImage.Format_ARGB32)
        arr = _qimage_to_np(src, np, fmt=QImage.Format_ARGB32)
        target = np.array([seed.blue(), seed.green(), seed.red(), seed.alpha()],
                          dtype=np.int16)
        # 逐通道取最大差：比 np.abs(arr - target).max(axis=2) 少一个
        # (h,w,4) 的中间数组（3000×2000 下省 40MB 的分配和拷贝）
        diff = np.abs(arr[..., 0].astype(np.int16) - target[0])
        for _i in range(1, 4):
            np.maximum(diff,
                       np.abs(arr[..., _i].astype(np.int16) - target[_i]),
                       out=diff)
        mask = diff <= tolerance
        graph = _run_graph(mask, np)
        if not mask[sy, sx]:
            return None
        reach = _region_from_runs(graph, sx, sy, mask, np)
        clip = _clip_numpy(doc, np)
        if clip is not None:
            reach &= clip
        ys, xs = np.nonzero(reach)
        if ys.size == 0:
            return None
        # 只有这一块会被改动。后面所有浮点运算都只在这个包围盒里做 ——
        # 整图做的话，3000×2000 要反复搬十几遍近百 MB 的数组，一次填色卡一秒多。
        pad = 3
        y0 = max(0, int(ys.min()) - pad)
        y1 = min(img.height(), int(ys.max()) + pad + 1)
        x0 = max(0, int(xs.min()) - pad)
        x1 = min(img.width(), int(xs.max()) + pad + 1)
        sub = (slice(y0, y1), slice(x0, x1))
        sreach = reach[sub]
        sdiff = diff[sub]
        arr_sub = arr[sub]                 # 视图，直接改 arr
        b, g, r_, a_ = color.blue(), color.green(), color.red(), color.alpha()
        arr_sub[sreach] = (b, g, r_, a_)    # uint8 直接写，不建 float 大数组

        # ---- 消白边（纯绘画软件的重点）--------------------------------
        # 笔迹边缘是抗锯齿的：填充区外侧那 1~3px 既不是背景色（所以容差没选中），
        # 也不是笔迹本身，而是「背景 × 笔迹」的混合。不处理的话，填完永远留一圈
        # 白边 —— PS / PhotoCraft 都有这个通病，这里是把它算掉而不是糊过去：
        #   a = 该像素离背景的距离 / 邻域里最深的墨色离背景的距离   → 覆盖度
        #   结果 = 该像素 + (填充色 - 背景色) × (1 - a)
        # a=1 的纯墨色原样保留，a=0 的纯背景换成填充色，中间自然过渡。
        #
        # 只往「里面」补：笔迹外侧那半圈同样也是抗锯齿像素，把它一起染色就会在
        # 形状外面长出一圈灰边。所以先从画布边缘灌一遍背景区域，落在背景里的
        # 像素一律不动（细笔迹两侧也不会串色）。
        band = _dilate(sreach, 2, np) & ~sreach & (sdiff > tolerance)
        if band.any():
            outside = _flood_from_border(mask, np, graph)
            if outside is not None:
                band &= ~outside[sub]
        if band.any():
            # 只算「边上那一圈」像素：整块包围盒做浮点，大画布要搬近百 MB
            yb, xb = np.nonzero(band)
            hh, ww = sdiff.shape
            d_b = sdiff[yb, xb].astype(np.float32)
            ref = d_b.copy()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy or dx:
                        ny = np.clip(yb + dy, 0, hh - 1)
                        nx = np.clip(xb + dx, 0, ww - 1)
                        np.maximum(ref, sdiff[ny, nx].astype(np.float32), out=ref)
            cover = np.clip(d_b / np.maximum(ref, 1.0), 0.0, 1.0)
            delta = np.array([b, g, r_, a_], dtype=np.float32) - \
                target.astype(np.float32)
            px = arr_sub[yb, xb].astype(np.float32) + \
                delta[None, :] * (1.0 - cover)[:, None]
            arr_sub[yb, xb] = np.clip(px, 0.0, 255.0).astype(np.uint8)
        r = QRect(x0, y0, x1 - x0, y1 - y0)
        before = img.copy(r)              # 只存这一块：撤销省内存、也快
        patch = np.ascontiguousarray(arr_sub).tobytes()
        pim = QImage(patch, x1 - x0, y1 - y0, (x1 - x0) * 4,
                     QImage.Format_ARGB32).copy()
        p = QPainter(img)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.drawImage(x0, y0, pim)
        p.end()
    else:
        before = img.copy()
        r = _flood_python(img, sx, sy, seed, tolerance, color,
                          doc.selection if doc.has_selection() else None)

    layer.touch()
    layer.has_content = True
    doc.recompose(r)
    return PixelEdit(layer, r, before, img.copy(r))


def _dilate(m, times: int, np):
    """二值膨胀（4 邻域），用来把填充区往外扩几圈找边缘像素。"""
    out = m
    for _ in range(max(0, int(times))):
        g = out.copy()
        g[1:, :] |= out[:-1, :]
        g[:-1, :] |= out[1:, :]
        g[:, 1:] |= out[:, :-1]
        g[:, :-1] |= out[:, 1:]
        out = g
    return out


def _flood_from_border(mask, np, graph=None):
    """从画布边缘灌一遍「背景区域」，用来判断哪些像素属于笔迹外侧。"""
    h, w = mask.shape
    for y in (0, h - 1):
        idx = np.flatnonzero(mask[y])
        if idx.size:
            return _region_from_runs(graph, int(idx[0]), y, mask, np)
    for x in (0, w - 1):
        idx = np.flatnonzero(mask[:, x])
        if idx.size:
            return _region_from_runs(graph, x, int(idx[0]), mask, np)
    return None


def _shift(a, dy: int, dx: int, np):
    """整体平移（空出来的地方补 0），用来在邻域里取最大值。"""
    out = np.zeros_like(a)
    h, w = a.shape[:2]
    y0, y1 = max(0, dy), min(h, h + dy)
    x0, x1 = max(0, dx), min(w, w + dx)
    out[y0:y1, x0:x1] = a[max(0, -dy): h - max(0, dy),
                          max(0, -dx): w - max(0, dx)]
    return out


def _qimage_to_np(img: QImage, np, fmt=None):
    img = img.convertToFormat(fmt if fmt is not None else FORMAT_ARGB)
    w, h = img.width(), img.height()
    ptr = img.bits()
    arr = np.frombuffer(ptr, dtype=np.uint8, count=img.sizeInBytes())
    arr = arr.reshape(h, img.bytesPerLine())[:, : w * 4].reshape(h, w, 4)
    return arr.copy()          # BGRA 顺序


def _np_to_qimage(arr, dst: QImage, np, fmt=None):
    h, w = arr.shape[:2]
    data = np.ascontiguousarray(arr, dtype=np.uint8)
    dst2 = QImage(data.tobytes(), w, h, w * 4,
                  fmt if fmt is not None else FORMAT_ARGB)
    p = QPainter(dst)
    p.setCompositionMode(QPainter.CompositionMode_Source)
    p.drawImage(0, 0, dst2.copy())
    p.end()


def _run_graph(mask, np):
    """把 mask 拆成「行内连续段」并合并相邻行，返回一张可反复查询的连通图。

    一张 mask 上通常要查两次（填充区域 + 画布边缘的背景区域），
    建图这一步只做一次，省掉一半时间。
    """
    h, w = mask.shape
    pad = np.zeros((h, w + 2), dtype=np.int8)
    pad[:, 1:-1] = mask
    d = np.diff(pad, axis=1)
    ys_s, xs_s = np.nonzero(d == 1)
    _ys_e, xs_e = np.nonzero(d == -1)
    n = int(ys_s.size)
    if n == 0:
        return None
    row_start = np.searchsorted(ys_s, np.arange(h), side="left")
    row_end = np.searchsorted(ys_s, np.arange(h), side="right")
    parent = np.arange(n, dtype=np.int64)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return int(a)

    for y in range(h - 1):
        i, i_end = int(row_start[y]), int(row_end[y])
        j, j_end = int(row_start[y + 1]), int(row_end[y + 1])
        while i < i_end and j < j_end:
            if xs_s[i] < xs_e[j] and xs_s[j] < xs_e[i]:
                ra, rb = find(i), find(j)
                if ra != rb:
                    parent[rb] = ra
            if xs_e[i] <= xs_e[j]:
                i += 1
            else:
                j += 1
    return (ys_s, xs_s, xs_e, row_start, row_end, parent)


def _region_from_runs(g, sx: int, sy: int, mask, np):
    """在连通图上查种子所在的连通块，画回一张和 mask 同尺寸的布尔图。"""
    if g is None:
        return np.zeros_like(mask)
    ys_s, xs_s, xs_e, row_start, row_end, parent = g

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return int(a)

    y0, y1 = int(row_start[sy]), int(row_end[sy])
    if y0 >= y1:
        return np.zeros_like(mask)
    k = y0 + int(np.searchsorted(xs_s[y0:y1], sx, side="right")) - 1
    if k < y0:
        return np.zeros_like(mask)
    root = find(k)
    roots = np.fromiter((find(i) for i in range(ys_s.size)),
                        dtype=np.int64, count=ys_s.size)
    out = np.zeros_like(mask)
    for i in np.nonzero(roots == root)[0]:
        out[ys_s[i], xs_s[i]:xs_e[i]] = True
    return out


def _flood_numpy(mask, sx: int, sy: int):
    """连通区域（4 邻域）：按「行内连续段」建图再做并查集。

    比逐段扫描快一个数量级 —— 一段一行只算一次，合并只发生在相邻两行的
    段之间，Python 里循环的是「段」不是「像素」。
    """
    import numpy as np
    if not mask[sy, sx]:
        return np.zeros_like(mask)
    return _region_from_runs(_run_graph(mask, np), sx, sy, mask, np)


def _clip_numpy(doc, np):
    if not doc.has_selection():
        return None
    path = doc.selection
    w, h = doc.w, doc.h
    br = path.boundingRect().toAlignedRect().intersected(QRect(0, 0, w, h))
    m = np.zeros((h, w), dtype=bool)
    if br.isEmpty():
        return m
    xs = range(br.left(), br.right() + 1)
    for y in range(br.top(), br.bottom() + 1):
        row = m[y]
        fy = y + 0.5
        for x in xs:
            if path.contains(QPointF(x + 0.5, fy)):
                row[x] = True
    return m


def _flood_python(img, sx, sy, seed, tol, color, sel):
    """没有 numpy 时的兜底填充（慢，但结果和 numpy 版一致，同样会消白边）。"""
    from collections import deque
    w, h = img.width(), img.height()
    seen = bytearray(w * h)
    mark = bytearray(w * h)
    dq = deque([(sx, sy)])
    minx, miny, maxx, maxy = sx, sy, sx, sy
    sb, sg, sr, sa = seed.blue(), seed.green(), seed.red(), seed.alpha()

    def dist(c: QColor):
        return max(abs(c.blue() - sb), abs(c.green() - sg),
                   abs(c.red() - sr), abs(c.alpha() - sa))

    p = QPainter(img)
    p.setCompositionMode(QPainter.CompositionMode_Source)
    p.setPen(QPen(color))
    inside = (lambda x, y: True) if sel is None else (lambda x, y: sel.contains(QPointF(x + 0.5, y + 0.5)))
    while dq:
        x, y = dq.popleft()
        if x < 0 or y < 0 or x >= w or y >= h:
            continue
        k = y * w + x
        if seen[k]:
            continue
        seen[k] = 1
        if dist(img.pixelColor(x, y)) > tol or not inside(x, y):
            continue
        p.drawPoint(x, y)
        mark[k] = 1
        minx, maxx = min(minx, x), max(maxx, x)
        miny, maxy = min(miny, y), max(maxy, y)
        dq.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    p.end()
    _feather_py(img, mark, w, h, minx, miny, maxx, maxy,
                sb, sg, sr, sa, color, tol)
    return QRect(minx, miny, maxx - minx + 1, maxy - miny + 1)


def _feather_py(img, mark, w, h, minx, miny, maxx, maxy,
                sb, sg, sr, sa, color, tol, rings: int = 1):
    """兜底路径的消白边：紧贴填充区的那一圈按覆盖度揉进填充色。

    只走一圈是有意的 —— 走多了会跨过细笔迹，把笔迹外侧也染上颜色。
    """
    def dist(c: QColor):
        return max(abs(c.blue() - sb), abs(c.green() - sg),
                   abs(c.red() - sr), abs(c.alpha() - sa))

    x0 = max(0, minx - rings)
    y0 = max(0, miny - rings)
    x1 = min(w - 1, maxx + rings)
    y1 = min(h - 1, maxy + rings)
    for y in range(y0, y1 + 1):
        base = y * w
        for x in range(x0, x1 + 1):
            k = base + x
            if mark[k]:
                continue
            if not ((x > 0 and mark[k - 1]) or (x < w - 1 and mark[k + 1])
                    or (y > 0 and mark[k - w]) or (y < h - 1 and mark[k + w])):
                continue
            c = img.pixelColor(x, y)
            d = dist(c)
            if d <= tol:            # 纯背景：交给填充本身，这里不动
                continue
            ref = 1
            for yy in (y - 1, y, y + 1):
                if not (0 <= yy < h):
                    continue
                for xx in (x - 1, x, x + 1):
                    if 0 <= xx < w:
                        ref = max(ref, dist(img.pixelColor(xx, yy)))
            cover = min(1.0, d / float(max(ref, 1)))
            k2 = 1.0 - cover
            nb = c.blue() + (color.blue() - sb) * k2
            ng = c.green() + (color.green() - sg) * k2
            nr = c.red() + (color.red() - sr) * k2
            na = c.alpha() + (color.alpha() - sa) * k2
            img.setPixelColor(x, y, QColor(
                max(0, min(255, int(round(nr)))),
                max(0, min(255, int(round(ng)))),
                max(0, min(255, int(round(nb)))),
                max(0, min(255, int(round(na))))))


# ---------------------------------------------------------------- 文件
def save_project(doc: Document, path: str):
    manifest = {
        "format": "photocraft-draw",
        "version": 1,
        "width": doc.w,
        "height": doc.h,
        "ppi": int(getattr(doc, "ppi", 300)),
        "active": doc.active,
        "groups": {gid: {"name": g.name, "visible": g.visible, "locked": g.locked,
                         "expanded": g.expanded, "opacity": g.opacity}
                   for gid, g in doc.groups.items()},
        "layers": [{"name": l.name, "visible": l.visible, "opacity": l.opacity,
                    "blend": l.blend, "group": l.group,
                    "is_bg": bool(getattr(l, "is_bg", False)),
                    "file": f"layers/{i}.png",
                    # 画布外那部分（自由变换 / 移动留下的大图）也一起存，
                    # 否则存盘再打开，缩回去时外面就没了
                    "off": f"layers/{i}_off.png" if l.off is not None else None,
                    "off_x": int(l.off_pos.x()), "off_y": int(l.off_pos.y())}
                   for i, l in enumerate(doc.layers)],
        # 文字是「活」对象，只存参数不存像素
        "texts": doc.texts_dict(),
    }
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        for i, l in enumerate(doc.layers):
            buf = QBuffer()
            buf.open(QIODevice.WriteOnly)
            l.image.save(buf, "PNG")
            z.writestr(f"layers/{i}.png", bytes(buf.data()))
            buf.close()
            if l.off is not None:
                buf = QBuffer()
                buf.open(QIODevice.WriteOnly)
                l.off.save(buf, "PNG")
                z.writestr(f"layers/{i}_off.png", bytes(buf.data()))
                buf.close()
    os.replace(tmp, path)
    doc.path = path
    doc.title = os.path.basename(path)
    doc.modified = False


def load_project(path: str) -> Document:
    with zipfile.ZipFile(path, "r") as z:
        manifest = json.loads(z.read("manifest.json").decode("utf-8"))
        doc = Document(manifest["width"], manifest["height"],
                       ppi=int(manifest.get("ppi", 300)))
        doc.layers = []
        for meta in manifest["layers"]:
            layer = Layer(meta["name"], doc.w, doc.h)
            data = z.read(meta["file"])
            img = QImage()
            img.loadFromData(data, "PNG")
            layer.image = img.convertToFormat(FORMAT_ARGB)
            layer.visible = meta.get("visible", True)
            layer.has_content = True
            layer.opacity = float(meta.get("opacity", 1.0))
            layer.blend = "正常"      # 旧文件里的混合模式一律忽略
            layer.group = meta.get("group", "")
            # 老版本没有 is_bg：把最底下那张（或名字还叫「背景」的那张）认成背景层。
            layer.is_bg = bool(meta.get("is_bg", len(doc.layers) == 0))
            off_file = meta.get("off")
            if off_file:
                try:
                    off = QImage()
                    off.loadFromData(z.read(off_file), "PNG")
                    if not off.isNull():
                        layer.off = off.convertToFormat(FORMAT_ARGB)
                        layer.off_pos = QPoint(int(meta.get("off_x", 0)),
                                               int(meta.get("off_y", 0)))
                except KeyError:
                    pass
            doc.layers.append(layer)
    for gid, g in (manifest.get("groups") or {}).items():
        grp = LayerGroup(g.get("name", gid))
        grp.visible = g.get("visible", True)
        grp.locked = g.get("locked", False)
        grp.expanded = g.get("expanded", True)
        grp.opacity = float(g.get("opacity", 1.0))
        doc.groups[gid] = grp
    doc.texts = [TextItem.from_dict(d) for d in (manifest.get("texts") or [])]
    if not doc.layers:
        doc.layers = [Layer("背景", doc.w, doc.h, QColor(255, 255, 255, 255))]
        doc.layers[0].is_bg = True
    if not any(getattr(l, "is_bg", False) for l in doc.layers):
        doc.layers[0].is_bg = True      # 兜底：任何文档都要有一张可复位的背景层
    doc.active = min(manifest.get("active", len(doc.layers) - 1), len(doc.layers) - 1)
    doc.path = path
    doc.title = os.path.basename(path)
    doc.modified = False
    doc.recompose()
    return doc


def open_image_as_document(path: str):
    img = QImage(path)
    if img.isNull():
        return None
    img = img.convertToFormat(FORMAT_ARGB)
    doc = Document(img.width(), img.height())
    doc.layers = []
    base = Layer(os.path.basename(path), img.width(), img.height())
    base.image = img
    base.is_bg = True          # 导入的图片就是这张图的底层，同样钉住
    doc.layers.append(base)
    doc.active = 0
    doc.recompose()
    return doc


def export_image(doc: Document, path: str, quality: int = 95):
    flat = doc.flatten()
    # 把画布分辨率写进文件（PNG 的 pHYs / JPEG 的 JFIF density）：
    # 不写的话所有看图软件都按 96 DPI 显示，300dpi 的画布导出来就变成 96。
    dpm = int(round(max(1, getattr(doc, "ppi", 300)) / 0.0254))
    flat.setDotsPerMeterX(dpm)
    flat.setDotsPerMeterY(dpm)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".jpg", ".jpeg"):
        bg = QImage(flat.size(), QImage.Format_RGB32)
        bg.fill(Qt.white)
        p = QPainter(bg)
        p.drawImage(0, 0, flat)
        p.end()
        bg.setDotsPerMeterX(dpm)
        bg.setDotsPerMeterY(dpm)
        return bg.save(path, "JPEG", quality)
    return flat.save(path, "PNG")
