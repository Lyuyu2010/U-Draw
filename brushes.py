# -*- coding: utf-8 -*-
"""画笔预设：内置笔型、用户自建笔刷的保存 / 导出 / 导入

内置笔按「分类 + 笔型 + 参数」组织，提供可直接使用的预设。
没有完整参考素材，不代表对其他软件笔刷的 1:1 复现：

* **分类**（`GROUPS`）：常用 / 铅笔 / 勾线 / 炭笔粉笔 / 马克笔 / 水彩 / 油画 /
  蜡笔色粉 / 喷枪 / 纹理 / 漫画网点 / 特效 / 印章形状 / 我的
* **笔型**（`core.KINDS`）：决定笔尖的质感。铅笔有纸纹、蜡笔边缘毛糙、
  马克笔是扁头、油画笔是一排鬃毛、星星笔就是真的星星……
  不是只改大小 —— 同名参数不同笔型，画出来完全是两支笔。
"""

import json
import os
import tempfile
import uuid

from PySide6.QtCore import QStandardPaths

from core import Brush


# 分类顺序：预设区按这个顺序显示标签
GROUPS = ["基础", "铅笔", "勾线", "炭笔粉笔", "马克笔", "水彩", "油画",
          "蜡笔色粉", "喷枪", "纹理", "漫画网点", "毛发织物", "植被花卉",
          "图案装饰", "光效天气", "特效", "印章形状", "我的"]

RECENT_GROUP = "__recent__"
FAVORITE_GROUP = "常用"
RECENT_LIMIT = 32
FAVORITE_LIMIT = 64
# 旧版「常用」分类里的六支笔，首次升级时迁移成可编辑的常用收藏。
DEFAULT_FAVORITES = ("硬圆笔", "软圆笔", "硬圆压感笔", "软圆压感笔",
                     "平涂圆笔", "柔边喷枪")
_LIBRARY_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "photocraft-draw.user-brushes")

# 用户自建 / 导入的笔默认落在这一组
USER_GROUP = "我的"


def _b(group, name, kind="round", **kw) -> Brush:
    b = Brush()
    b.group = group
    b.name = name
    b.kind = kind
    for k, v in kw.items():
        setattr(b, k, v)
    # 压感笔的「最小直径」别超过 30%：再高的话轻压和重压几乎一样粗，
    # 用户会觉得「这支笔没有压感」。真要等粗就把「压感控制大小」关掉。
    if b.pressure_size and b.min_size > 0.30:
        b.min_size = 0.30
    return b


DEFAULTS = [
    # ================================================================ 常用
    # 平时画东西最常用的几支：软硬圆笔 + 压感版 + 平涂
    _b("基础", "硬圆笔", "round", size=28, hardness=1.0, opacity=1.0, flow=1.0,
       spacing=0.02, min_size=0.10, stabilize=0.22),
    _b("基础", "软圆笔", "airbrush", size=48, hardness=0.0, opacity=1.0, flow=0.55,
       spacing=0.02, min_size=0.55, stabilize=0.18),
    _b("基础", "硬圆压感笔", "round", size=22, hardness=1.0, opacity=1.0, flow=1.0,
       spacing=0.02, pressure_size=True, min_size=0.28, stabilize=0.20),
    _b("基础", "软圆压感笔", "airbrush", size=38, hardness=0.0, opacity=0.9, flow=0.5,
       spacing=0.02, pressure_size=True, pressure_opacity=True, min_size=0.22,
       stabilize=0.16),
    _b("基础", "平涂圆笔", "round", size=36, hardness=0.95, opacity=1.0, flow=0.85,
       spacing=0.02, min_size=0.80, stabilize=0.26),
    _b("基础", "柔边喷枪", "airbrush", size=72, hardness=0.0, opacity=0.35, flow=0.18,
       spacing=0.02, min_size=0.6, stabilize=0.05),

    # ================================================================ 铅笔
    _b("铅笔", "素描铅笔", "pencil", size=10, hardness=0.5, opacity=0.8, flow=0.5,
       spacing=0.03, grain=0.45, grain_scale=2, taper=0.32, min_size=0.3,
       pressure_opacity=True, stabilize=0.24),
    _b("铅笔", "HB 铅笔", "pencil", size=6, hardness=0.62, opacity=0.85, flow=0.55,
       spacing=0.03, grain=0.38, grain_scale=2, taper=0.28, min_size=0.42,
       pressure_opacity=True, stabilize=0.30),
    _b("铅笔", "2B 铅笔", "pencil", size=12, hardness=0.55, opacity=0.9, flow=0.55,
       spacing=0.03, grain=0.55, grain_scale=3, taper=0.25, min_size=0.3,
       pressure_opacity=True, stabilize=0.26),
    _b("铅笔", "6B 软铅", "pencil", size=18, hardness=0.4, opacity=0.95, flow=0.6,
       spacing=0.03, grain=0.7, grain_scale=4, taper=0.2, min_size=0.25,
       pressure_opacity=True, stabilize=0.20),
    _b("铅笔", "机械铅笔", "pencil", size=3, hardness=0.8, opacity=1.0, flow=0.9,
       spacing=0.02, grain=0.25, grain_scale=1.5, min_size=0.7, stabilize=0.35),
    _b("铅笔", "素描侧锋", "pencil", size=24, hardness=0.35, opacity=0.85, flow=0.5,
       spacing=0.05, grain=0.72, grain_scale=5, scatter=0.12, roundness=0.42,
       angle=18, angle_jitter=0.12, min_size=0.4, stabilize=0.15),
    _b("铅笔", "彩色铅笔", "colored_pencil", size=10, hardness=0.6, opacity=0.85,
       flow=0.55, spacing=0.04, grain=0.5, grain_scale=2, size_jitter=0.08,
       hue_jitter=0.04, sat_jitter=0.05, val_jitter=0.06, taper=0.25,
       min_size=0.35, stabilize=0.22),
    _b("铅笔", "蜡质彩铅", "colored_pencil", size=9, hardness=0.7, opacity=0.95,
       flow=0.7, spacing=0.03, grain=0.35, grain_scale=2, val_jitter=0.08,
       taper=0.2, min_size=0.4, stabilize=0.20),
    _b("铅笔", "速写铅笔", "pencil", size=7, hardness=0.55, opacity=0.9, flow=0.6,
       spacing=0.03, grain=0.4, grain_scale=2, taper=0.38, min_size=0.28,
       stabilize=0.18),
    _b("铅笔", "炭精铅笔", "pencil", size=14, hardness=0.45, opacity=0.92, flow=0.55,
       spacing=0.03, grain=0.8, grain_scale=3, taper=0.22, min_size=0.3,
       pressure_opacity=True, stabilize=0.20),

    # ================================================================ 勾线
    _b("勾线", "钢笔", "ballpoint", size=4, hardness=1.0, opacity=1.0, flow=1.0,
       spacing=0.02, taper=0.18, min_size=0.5, pressure_size=False, stabilize=0.30),
    _b("勾线", "G 笔", "round", size=6, hardness=1.0, opacity=1.0, flow=1.0,
       spacing=0.02, taper=0.35, min_size=0.2, pressure_size=True, stabilize=0.35),
    _b("勾线", "针管笔", "round", size=3, hardness=1.0, opacity=1.0, flow=1.0,
       spacing=0.02, min_size=0.9, pressure_size=False, stabilize=0.30),
    _b("勾线", "圆珠笔", "ballpoint", size=4, hardness=1.0, opacity=1.0, flow=1.0,
       spacing=0.02, min_size=0.85, pressure_size=False, stabilize=0.25),
    _b("勾线", "中性笔", "ballpoint", size=5, hardness=1.0, opacity=1.0, flow=0.95,
       spacing=0.02, min_size=0.8, pressure_size=False, stabilize=0.26),
    _b("勾线", "毛笔勾线", "round", size=9, hardness=0.9, opacity=1.0, flow=0.95,
       spacing=0.02, taper=0.20, min_size=0.12, pressure_size=True, stabilize=0.40),
    _b("勾线", "纤维笔", "marker", size=4, hardness=0.9, opacity=1.0, flow=1.0,
       spacing=0.03, roundness=0.85, angle_follow=1.0, min_size=0.75,
       stabilize=0.28),
    _b("勾线", "美工笔", "block", size=6, hardness=1.0, opacity=1.0, flow=1.0,
       spacing=0.03, roundness=0.5, angle=-90, angle_follow=1.0, min_size=0.55,
       stabilize=0.30),

    # ============================================================ 炭笔粉笔
    _b("炭笔粉笔", "炭笔", "charcoal", size=26, hardness=0.35, opacity=0.9, flow=0.5,
       spacing=0.05, grain=0.8, grain_scale=4, scatter=0.2, size_jitter=0.18,
       roundness=0.75, angle=32, angle_jitter=0.2, taper=0.28, min_size=0.4,
       stabilize=0.18),
    _b("炭笔粉笔", "软炭条", "charcoal", size=40, hardness=0.28, opacity=0.9,
       flow=0.45, spacing=0.42, grain=0.9, grain_scale=6, scatter=0.32,
       scatter_count=2, size_jitter=0.25, roundness=0.7, angle=30,
       angle_jitter=0.3, min_size=0.45, stabilize=0.12),
    _b("炭笔粉笔", "硬炭笔", "charcoal", size=16, hardness=0.55, opacity=0.92,
       flow=0.6, spacing=0.04, grain=0.7, grain_scale=3, scatter=0.12,
       taper=0.3, min_size=0.4, stabilize=0.22),
    _b("炭笔粉笔", "重炭笔", "charcoal", size=46, hardness=0.34, opacity=0.9,
       flow=0.5, spacing=0.05, grain=0.86, grain_scale=5, scatter=0.22,
       size_jitter=0.2, roundness=0.7, angle=32, angle_jitter=0.24, taper=0.3,
       min_size=0.4, stabilize=0.18),
    _b("炭笔粉笔", "石纹笔", "charcoal", size=44, hardness=0.28, opacity=0.85,
       flow=0.45, spacing=0.42, grain=0.9, grain_scale=8, scatter=0.34,
       scatter_count=2, size_jitter=0.24, roundness=0.7, angle=40,
       angle_jitter=0.3, min_size=0.5, stabilize=0.10),
    _b("炭笔粉笔", "粉笔", "chalk", size=40, hardness=0.2, opacity=0.88, flow=0.45,
       spacing=0.06, grain=0.85, grain_scale=5, scatter=0.15, size_jitter=0.14,
       roundness=0.85, angle=20, min_size=0.45, stabilize=0.16),
    _b("炭笔粉笔", "黑板粉笔", "chalk", size=26, hardness=0.25, opacity=0.8,
       flow=0.5, spacing=0.05, grain=0.9, grain_scale=6, scatter=0.2,
       size_jitter=0.18, min_size=0.5, stabilize=0.14),
    _b("炭笔粉笔", "炭粉", "chalk", size=32, hardness=0.18, opacity=0.75, flow=0.4,
       spacing=0.3, grain=1.0, grain_scale=6, scatter=0.4, scatter_count=2,
       size_jitter=0.3, min_size=0.4, stabilize=0.10),

    # ============================================================== 马克笔
    _b("马克笔", "方头马克笔", "block", size=34, hardness=1.0, opacity=1.0, flow=1.0,
       spacing=0.02, roundness=0.45, angle=-90, angle_follow=1.0, min_size=0.7,
       stabilize=0.28),
    _b("马克笔", "圆头马克笔", "marker", size=24, hardness=0.9, opacity=0.55,
       flow=0.9, spacing=0.02, min_size=0.7, stabilize=0.24),
    _b("马克笔", "淡彩马克笔", "marker", size=38, hardness=0.82, opacity=0.40,
       flow=0.75, spacing=0.02, roundness=0.55, angle=35, min_size=0.65,
       stabilize=0.20),
    _b("马克笔", "速涂笔", "marker", size=54, hardness=0.85, opacity=0.45, flow=0.9,
       spacing=0.02, roundness=0.6, angle=60, min_size=0.5, stabilize=0.15),
    _b("马克笔", "速写笔", "marker", size=24, hardness=0.92, opacity=0.95, flow=0.85,
       spacing=0.02, roundness=0.82, angle=38, min_size=0.35, stabilize=0.16),
    _b("马克笔", "方头硬笔", "marker", size=34, hardness=1.0, opacity=1.0, flow=1.0,
       spacing=0.01, roundness=0.92, angle=0, min_size=0.9, stabilize=0.25),
    _b("马克笔", "高光笔", "marker", size=5, hardness=1.0, opacity=1.0, flow=1.0,
       spacing=0.02, min_size=0.85, pressure_size=False, stabilize=0.30),
    _b("马克笔", "柔头马克笔", "marker", size=20, hardness=0.55, opacity=0.8,
       flow=0.8, spacing=0.02, roundness=0.8, angle=25, min_size=0.45,
       stabilize=0.20),

    # ================================================================ 水彩
    _b("水彩", "水彩笔", "watercolor", size=50, hardness=0.16, opacity=0.75, flow=0.3,
       spacing=0.03, grain=0.35, grain_scale=4, wet=0.45, taper=0.42, min_size=0.35,
       stabilize=0.12),
    _b("水彩", "水彩湿边笔", "watercolor", size=34, hardness=0.1, opacity=0.85,
       flow=0.38, spacing=0.03, grain=0.3, grain_scale=3, wet=0.78, taper=0.22,
       min_size=0.5, stabilize=0.14),
    _b("水彩", "湿画笔", "watercolor", size=42, hardness=0.14, opacity=0.8, flow=0.35,
       spacing=0.03, grain=0.55, grain_scale=4, wet=0.62, scatter=0.12,
       val_jitter=0.06, taper=0.25, min_size=0.45, stabilize=0.13),
    _b("水彩", "淡彩笔", "watercolor", size=28, hardness=0.2, opacity=0.8, flow=0.42,
       spacing=0.03, grain=0.4, grain_scale=3, wet=0.65, taper=0.3, min_size=0.45,
       stabilize=0.15),
    _b("水彩", "水彩晕染", "cloud", size=46, hardness=0.0, opacity=0.55, flow=0.45,
       spacing=0.05, grain=0.2, grain_scale=3, wet=0.5, taper=0.2, min_size=0.5,
       stabilize=0.12),
    _b("水彩", "水痕笔", "watercolor", size=30, hardness=0.12, opacity=0.7, flow=0.4,
       spacing=0.04, grain=0.45, grain_scale=4, wet=1.0, taper=0.24, min_size=0.45,
       stabilize=0.14),
    _b("水彩", "水粉笔", "bristle", size=42, hardness=0.7, opacity=0.85, flow=0.5,
       spacing=0.06, grain=0.25, grain_scale=3, wet=0.25, roundness=0.8, angle=-90,
       angle_follow=1.0, min_size=0.5, stabilize=0.18),
    _b("水彩", "水彩细笔", "watercolor", size=10, hardness=0.3, opacity=0.85,
       flow=0.5, spacing=0.03, grain=0.25, grain_scale=2, wet=0.6, taper=0.4,
       min_size=0.3, stabilize=0.20),
    _b("水彩", "湿边晕染", "watercolor", size=54, hardness=0.08, opacity=0.5,
       flow=0.3, spacing=0.04, grain=0.5, grain_scale=5, wet=0.9, min_size=0.55,
       stabilize=0.10),
    _b("水彩", "水彩点染", "watercolor", size=22, hardness=0.18, opacity=0.8,
       flow=0.45, spacing=0.15, grain=0.4, grain_scale=3, wet=0.7, scatter=0.3,
       size_jitter=0.2, min_size=0.4, stabilize=0.12),

    # ================================================================ 油画
    _b("油画", "油画笔", "bristle", size=36, hardness=0.8, opacity=0.95, flow=0.6,
       spacing=0.06, grain=0.2, grain_scale=3, roundness=0.7, angle=-90,
       angle_follow=1.0, min_size=0.5, stabilize=0.18),
    _b("油画", "厚涂笔", "bristle", size=44, hardness=0.9, opacity=1.0, flow=0.7,
       spacing=0.05, grain=0.35, grain_scale=4, roundness=0.75, angle=-90,
       angle_follow=1.0, min_size=0.6, stabilize=0.20),
    _b("油画", "猪鬃刷", "bristle", size=58, hardness=0.6, opacity=0.8, flow=0.45,
       spacing=0.1, grain=0.3, grain_scale=4, scatter=0.15, roundness=0.85,
       angle=-90, angle_follow=1.0, min_size=0.5, stabilize=0.14),
    _b("油画", "干油画刷", "bristle", size=30, hardness=0.5, opacity=0.78, flow=0.48,
       spacing=0.18, grain=0.5, grain_scale=5, roundness=0.6, angle=-90,
       angle_follow=1.0, min_size=0.45, stabilize=0.14),
    _b("油画", "刮刀", "block", size=30, hardness=1.0, opacity=0.9, flow=0.85,
       spacing=0.05, roundness=0.18, angle=40, grain=0.25, grain_scale=3,
       min_size=0.7, stabilize=0.22),
    _b("油画", "丙烯笔", "bristle", size=28, hardness=0.85, opacity=0.9, flow=0.7,
       spacing=0.04, roundness=0.8, angle=-90, angle_follow=1.0, min_size=0.55,
       stabilize=0.20),
    _b("油画", "油彩拖笔", "bristle", size=24, hardness=0.6, opacity=0.8, flow=0.5,
       spacing=0.5, grain=0.4, grain_scale=4, scatter=0.1, roundness=0.7,
       angle=-90, angle_follow=1.0, min_size=0.4, stabilize=0.12),
    _b("油画", "淡油彩笔", "marker", size=38, hardness=0.7, opacity=0.35, flow=0.6,
       spacing=0.02, roundness=0.5, angle=35, grain=0.22, grain_scale=3,
       min_size=0.6, stabilize=0.18),

    # ============================================================ 蜡笔色粉
    _b("蜡笔色粉", "蜡笔", "crayon", size=34, hardness=0.45, opacity=0.85, flow=0.55,
       spacing=0.05, grain=0.75, grain_scale=5, scatter=0.12, size_jitter=0.12,
       taper=0.25, min_size=0.45, stabilize=0.16),
    _b("蜡笔色粉", "粗纹纸笔", "crayon", size=32, hardness=0.42, opacity=0.8,
       flow=0.5, spacing=0.05, grain=0.74, grain_scale=5, scatter=0.12,
       size_jitter=0.12, taper=0.26, min_size=0.42, stabilize=0.16),
    _b("蜡笔色粉", "蜡笔侧涂", "crayon", size=42, hardness=0.4, opacity=0.8,
       flow=0.5, spacing=0.06, grain=0.8, grain_scale=6, roundness=0.35, angle=20,
       angle_jitter=0.1, min_size=0.5, stabilize=0.14),
    _b("蜡笔色粉", "色粉笔", "chalk", size=34, hardness=0.22, opacity=0.85,
       flow=0.4, spacing=0.08, grain=0.8, grain_scale=5, scatter=0.18,
       size_jitter=0.2, min_size=0.45, stabilize=0.14),
    _b("蜡笔色粉", "干粉笔", "chalk", size=42, hardness=0.15, opacity=0.7,
       flow=0.35, spacing=0.3, grain=0.95, grain_scale=6, scatter=0.3,
       size_jitter=0.25, min_size=0.4, stabilize=0.10),
    _b("蜡笔色粉", "油性粉笔", "crayon", size=20, hardness=0.8, opacity=0.95,
       flow=0.7, spacing=0.04, grain=0.45, grain_scale=3, taper=0.2,
       min_size=0.45, stabilize=0.20),
    _b("蜡笔色粉", "干笔刷", "crayon", size=16, hardness=0.5, opacity=0.85,
       flow=0.6, spacing=0.04, grain=0.6, grain_scale=3, scatter=0.1,
       size_jitter=0.1, taper=0.35, min_size=0.35, stabilize=0.20),
    _b("蜡笔色粉", "色粉擦笔", "cloud", size=38, hardness=0.0, opacity=0.5,
       flow=0.3, spacing=0.06, grain=0.3, grain_scale=3, scatter=0.2,
       min_size=0.5, stabilize=0.12),

    # ================================================================ 喷枪
    _b("喷枪", "喷点笔", "spray", size=70, hardness=1.0, opacity=0.95, flow=0.6,
       spacing=0.55, scatter=0.2, size_jitter=0.2, min_size=0.4, stabilize=0.06),
    _b("喷枪", "软喷枪", "airbrush", size=80, hardness=0.0, opacity=0.4, flow=0.2,
       spacing=0.02, min_size=0.6, stabilize=0.05),
    _b("喷枪", "细雾喷枪", "spray", size=34, hardness=1.0, opacity=0.8, flow=0.55,
       spacing=0.22, scatter=0.1, size_jitter=0.1, min_size=0.4, stabilize=0.06),
    _b("喷枪", "大喷枪", "spray", size=150, hardness=1.0, opacity=0.6, flow=0.3,
       spacing=0.75, scatter=0.3, size_jitter=0.25, min_size=0.4, stabilize=0.05),
    _b("喷枪", "硬喷枪", "airbrush", size=48, hardness=0.55, opacity=0.5, flow=0.35,
       spacing=0.02, min_size=0.6, stabilize=0.08),
    _b("喷枪", "沙粒喷枪", "noise", size=42, hardness=1.0, opacity=0.8, flow=0.5,
       spacing=0.55, scatter=0.2, size_jitter=0.3, min_size=0.4, stabilize=0.06),
    _b("喷枪", "色彩喷枪", "spray", size=80, hardness=0.2, opacity=0.8,
       flow=0.5, size_jitter=0.2, scatter=0.2, spacing=0.5, hue_jitter=0.3, sat_jitter=0.2, val_jitter=0.15,
       min_size=0.4, stabilize=0.06),

    # ================================================================ 纹理
    _b("纹理", "干拖笔", "crayon", size=26, hardness=0.35, opacity=0.75, flow=0.55,
       spacing=0.6, grain=0.7, grain_scale=5, scatter=0.22, size_jitter=0.18,
       roundness=0.75, angle=30, min_size=0.4, stabilize=0.12),
    _b("纹理", "噪点笔", "noise", size=34, hardness=1.0, opacity=0.8, flow=0.5,
       spacing=0.3, grain=0.3, grain_scale=3, scatter=0.15, min_size=0.4,
       stabilize=0.08),
    _b("纹理", "海绵", "noise", size=50, hardness=1.0, opacity=0.8, flow=0.5,
       spacing=0.60, scatter=0.35, size_jitter=0.35, min_size=0.4, stabilize=0.08),
    _b("纹理", "云纹", "cloud", size=54, hardness=0.0, opacity=0.6, flow=0.4,
       spacing=0.3, scatter=0.25, size_jitter=0.2, min_size=0.5, stabilize=0.08),
    _b("纹理", "烟雾", "cloud", size=76, hardness=0.0, opacity=0.4, flow=0.3,
       spacing=0.4, scatter=0.4, size_jitter=0.3, min_size=0.5, stabilize=0.06),
    _b("纹理", "麻布纹", "bristle", size=38, hardness=0.5, opacity=0.8, flow=0.5,
       spacing=0.12, grain=0.6, grain_scale=5, roundness=0.9, angle=-90,
       min_size=0.5, stabilize=0.10),
    _b("纹理", "磨砂", "noise", size=58, hardness=1.0, opacity=0.7, flow=0.4,
       spacing=0.7, grain=0.4, grain_scale=4, scatter=0.3, size_jitter=0.3,
       min_size=0.4, stabilize=0.06),
    _b("纹理", "树皮纹", "bristle", size=30, hardness=0.4, opacity=0.85, flow=0.5,
       spacing=0.2, grain=0.7, grain_scale=6, roundness=0.6, angle=90,
       min_size=0.5, stabilize=0.10),

    # ============================================================ 漫画网点
    _b("漫画网点", "网点笔", "halftone", size=30, hardness=0.9, opacity=0.95,
       flow=0.8, spacing=0.02, min_size=0.6, stabilize=0.20),
    _b("漫画网点", "粗网点", "halftone", size=54, hardness=0.9, opacity=0.95,
       flow=0.8, spacing=0.02, min_size=0.6, stabilize=0.20),
    _b("漫画网点", "细网点", "halftone", size=16, hardness=0.9, opacity=0.95,
       flow=0.8, spacing=0.02, min_size=0.6, stabilize=0.20),
    _b("漫画网点", "半调渐变", "halftone", size=42, hardness=0.9, opacity=0.5,
       flow=0.4, spacing=0.02, pressure_opacity=True, min_size=0.5,
       stabilize=0.16),
    _b("漫画网点", "排线笔", "block", size=6, hardness=1.0, opacity=0.9, flow=0.9,
       spacing=0.04, roundness=0.12, angle=45, min_size=0.8, stabilize=0.28),

    # ================================================================ 特效
    _b("特效", "星光笔", "sparkle", size=30, hardness=1.0, opacity=0.9, flow=0.9,
       spacing=1.0, scatter=0.2, size_jitter=0.3, min_size=0.5, stabilize=0.10),
    _b("特效", "闪光点", "sparkle", size=16, hardness=1.0, opacity=0.95, flow=0.9,
       spacing=1.2, scatter=0.5, size_jitter=0.4, min_size=0.4, stabilize=0.08),
    _b("特效", "星星笔", "star", size=28, hardness=1.0, opacity=0.95, flow=0.9,
       spacing=1.2, scatter=0.3, size_jitter=0.3, angle_jitter=1.0, min_size=0.5,
       stabilize=0.08),
    _b("特效", "气泡笔", "bubble", size=40, hardness=1.0, opacity=0.9, flow=0.9,
       spacing=1.4, scatter=0.3, size_jitter=0.4, min_size=0.4, stabilize=0.08),
    _b("特效", "圆环笔", "ring", size=30, hardness=1.0, opacity=0.9, flow=0.9,
       spacing=1.1, scatter=0.15, size_jitter=0.25, min_size=0.5, stabilize=0.08),
    _b("特效", "飞溅笔", "splatter", size=44, hardness=1.0, opacity=0.9, flow=0.75,
       angle_jitter=0.3, spacing=0.55, scatter=0.25, size_jitter=0.15, min_size=0.5, stabilize=0.08),
    _b("特效", "雪花笔", "sparkle", size=10, hardness=1.0, opacity=0.95, flow=0.9,
       spacing=1.5, scatter=0.6, size_jitter=0.5, min_size=0.35, stabilize=0.06),
    _b("特效", "雨点笔", "splatter", size=18, hardness=1.0, opacity=0.85, flow=0.7,
       spacing=0.50, scatter=0.4, size_jitter=0.2, angle_jitter=0.3, min_size=0.4,
       stabilize=0.06),
    _b("特效", "火星笔", "sparkle", size=8, hardness=1.0, opacity=1.0, flow=1.0,
       spacing=1.0, scatter=0.5, size_jitter=0.45, hue_jitter=0.15,
       val_jitter=0.2, min_size=0.35, stabilize=0.06),

    # ============================================================ 印章形状
    _b("印章形状", "树叶笔", "leaf", size=44, hardness=1.0, opacity=0.95, flow=0.9,
       spacing=1.5, scatter=0.6, size_jitter=0.35, angle_jitter=1.0, min_size=0.5,
       stabilize=0.06),
    _b("印章形状", "花瓣笔", "leaf", size=32, hardness=1.0, opacity=0.9, flow=0.9,
       spacing=1.2, scatter=0.5, roundness=0.5, size_jitter=0.3, angle_jitter=1.0,
       min_size=0.5, stabilize=0.06),
    _b("印章形状", "星星印章", "star", size=30, hardness=1.0, opacity=0.95,
       flow=0.9, spacing=2.0, scatter=0.3, size_jitter=0.3, min_size=0.5,
       stabilize=0.06),
    _b("印章形状", "泡泡印章", "bubble", size=28, hardness=1.0, opacity=0.9,
       flow=0.9, spacing=2.0, scatter=0.4, size_jitter=0.35, min_size=0.4,
       stabilize=0.06),
    _b("印章形状", "草叶笔", "grass", size=30, hardness=1.0, opacity=0.9, flow=0.85,
       spacing=0.15, scatter=0.1, size_jitter=0.25, angle_jitter=0.2, min_size=0.5,
       stabilize=0.10),
    _b("印章形状", "毛发笔", "grass", size=20, hardness=1.0, opacity=0.9, flow=0.85,
       spacing=0.1, grain=0.3, grain_scale=2, scatter=0.08, size_jitter=0.2,
       min_size=0.4, stabilize=0.12),
]

# 新库：每一种新笔型只有一个主预设，避免以细小调参凑数；旧名称完整保留。
STUDIO_DEFAULTS = [
    _b("勾线", "斜切书法笔", "chisel", size=30, spacing=0.04, angle=35, min_size=0.22),
    _b("勾线", "多线排齿笔", "rake", size=38, spacing=0.04, angle=90, angle_follow=1.0, min_size=0.7),
    _b("铅笔", "石墨接触笔", "graphite", size=24, spacing=0.05, flow=0.75, pattern_scale=9, pressure_opacity=True, build_up=True),
    _b("蜡笔色粉", "破碎色粉", "pastel", size=40, spacing=0.12, flow=0.85, pattern_scale=18, build_up=True),
    _b("蜡笔色粉", "蜡质拖痕", "wax", size=36, spacing=0.06, flow=0.9, pattern_scale=14, build_up=True),
    _b("勾线", "枯墨飞白", "dry_ink", size=36, spacing=0.04, angle=90, angle_follow=1.0, pattern_scale=18),
    _b("纹理", "孔洞海绵", "sponge", size=54, spacing=0.4, flow=0.95, pattern_scale=22, size_jitter=0.15),
    _b("水彩", "盐析水彩", "salt", size=56, spacing=0.08, opacity=0.75, flow=0.8, wet=0.4, pattern_scale=20, build_up=True),
    _b("水彩", "水渍晕花", "bloom", size=64, spacing=0.22, opacity=0.65, flow=0.85, wet=0.65, pattern_scale=28, build_up=True),
    _b("油画", "油彩堆色纹", "impasto", size=42, spacing=0.06, flow=1.0, angle=90, angle_follow=1.0, pattern_scale=16, build_up=True),
    _b("油画", "刀锋刮痕", "knife", size=44, spacing=0.06, flow=1.0, angle=40, pattern_scale=18),
    _b("毛发织物", "弧形发丝束", "fur", size=40, spacing=0.45, angle=90, angle_follow=1.0, size_jitter=0.12),
    _b("植被花卉", "尖叶草丛", "grass_blade", size=44, spacing=0.8, size_jitter=0.22, scatter=0.1, min_size=0.6),
    _b("植被花卉", "蕨叶枝条", "fern", size=58, spacing=1.15, angle_jitter=0.12, min_size=0.65),
    _b("植被花卉", "独立花瓣", "petal", size=34, spacing=1.0, angle_jitter=0.5, size_jitter=0.2),
    _b("植被花卉", "五瓣花簇", "blossom", size=38, spacing=1.15, size_jitter=0.2, angle_jitter=0.25),
    _b("植被花卉", "卷层玫瑰", "rose", size=44, spacing=1.2, angle_jitter=0.3, size_jitter=0.18),
    _b("光效天气", "六角雪晶", "snowflake", size=34, spacing=1.3, scatter=0.25, angle_jitter=0.2, size_jitter=0.3),
    _b("光效天气", "斜落雨丝", "rain", size=44, spacing=0.85, scatter=0.35, size_jitter=0.2, pressure_size=False),
    _b("毛发织物", "细脉羽毛", "feather", size=54, spacing=1.1, angle=35, angle_jitter=0.12, min_size=0.6),
    _b("图案装饰", "心形印章", "heart", size=30, spacing=1.15, size_jitter=0.15),
    _b("图案装饰", "六边形印章", "hexagon", size=28, spacing=1.05, pressure_size=False),
    _b("图案装饰", "金属链环", "chain", size=26, spacing=0.65, angle_follow=1.0, pressure_size=False),
    _b("毛发织物", "花边蕾丝", "lace", size=38, spacing=0.85, angle_follow=1.0, pressure_size=False),
    _b("毛发织物", "手缝线迹", "stitch", size=20, spacing=0.9, angle_follow=1.0, pressure_size=False),
    _b("漫画网点", "连续斜排线", "hatch", size=52, spacing=0.04, pattern_scale=12, angle=45, pressure_size=False),
    _b("漫画网点", "交叉排线纹", "crosshatch", size=52, spacing=0.04, pattern_scale=14, angle=45, pressure_size=False),
    _b("漫画网点", "随机点描纹", "stipple", size=52, spacing=0.05, pattern_scale=12, pressure_size=False),
    _b("图案装饰", "错缝砖墙", "brick", size=64, spacing=0.04, pattern_scale=22, pressure_size=False),
    _b("图案装饰", "鱼鳞纹样", "scales", size=64, spacing=0.04, pattern_scale=18, pressure_size=False),
    _b("光效天气", "霓虹光芯", "neon", size=38, spacing=0.04, flow=0.95, min_size=0.5),
    _b("光效天气", "连续彩虹", "rainbow", size=26, spacing=0.03, color_cycle=240, flow=1.0, min_size=0.5),
]
DEFAULTS.extend(STUDIO_DEFAULTS)

_CURATED_LEGACY = frozenset((
    "硬圆笔", "软圆笔", "硬圆压感笔", "平涂圆笔", "素描铅笔", "素描侧锋", "彩色铅笔",
    "G 笔", "针管笔", "毛笔勾线", "美工笔", "炭笔", "软炭条", "粉笔",
    "方头马克笔", "淡彩马克笔", "水彩笔", "水彩湿边笔", "水粉笔", "油画笔",
    "猪鬃刷", "蜡笔", "蜡笔侧涂", "喷点笔", "细雾喷枪", "大喷枪", "网点笔",
    "星光笔", "星星笔", "气泡笔", "飞溅笔", "树叶笔", "烟雾"))
_SPECIAL_KINDS = frozenset(b.kind for b in STUDIO_DEFAULTS) | frozenset((
    "spray", "splatter", "leaf", "grass", "star", "sparkle", "bubble", "ring", "halftone"))
_DESCRIPTIONS = {
    "chisel": "斜切平头，转弯时形成宽窄书法笔画", "rake": "多齿平行线束，随运笔方向转动",
    "graphite": "细碎石墨接触纹，可按压力控制浓淡并逐笔叠色", "pastel": "多尺度破碎粉末，不是毛边圆笔",
    "wax": "块状蜡质与纵向拖痕", "dry_ink": "干墨飞白，保留断续空隙", "sponge": "不规则孔洞与块状接触",
    "salt": "水彩中的盐析留白；视觉近似而非液体模拟", "bloom": "不规则水渍与晕花；视觉近似",
    "impasto": "带方向纹路的堆色观感，不计算真实颜料厚度", "knife": "刀边与疏密刮痕",
    "fur": "弯曲成束发丝，沿笔画转向", "grass_blade": "从根部向外伸展的尖叶草束",
    "fern": "主枝与成对小叶组成的蕨叶", "petal": "单片弧形花瓣", "blossom": "完整五瓣花朵",
    "rose": "层叠卷曲轮廓的玫瑰花", "snowflake": "六角枝干和侧分支，不再复用四芒星",
    "rain": "有方向与长短变化的雨丝", "feather": "羽轴与两侧细羽枝", "heart": "独立心形轮廓",
    "hexagon": "六边形几何印章", "chain": "沿路径排列的椭圆链环", "lace": "带镂空的花边装饰",
    "stitch": "沿路径延伸的分段线迹", "hatch": "按画布坐标对齐的斜排线",
    "crosshatch": "两组交错排线，反复涂画不糊成圆笔", "stipple": "画布坐标随机点描分布",
    "brick": "错缝砖墙线纹", "scales": "连续叠瓦式鳞片线纹", "neon": "彩色柔光晕和白色光芯，深色底更明显",
    "rainbow": "沿实际运笔长度连续变色，可调整色彩周期",
}


def is_curated(brush):
    origin = getattr(brush, "origin", None)
    return origin is None or origin in _CURATED_LEGACY or origin in {b.name for b in STUDIO_DEFAULTS}


def is_special(brush):
    return brush.kind in _SPECIAL_KINDS


def brush_description(brush):
    return _DESCRIPTIONS.get(brush.kind, "原版兼容预设；同家族的参数变体可在全部视图查看")


# 名字 → 内置默认参数（「重置」用），不改旧origin标识，兼容已保存的改名和参数。
BUILTIN = {b.name: b for b in DEFAULTS}

# 分类 → 内置笔数量（预设区标签上显示）
GROUP_COUNT = {}
for _p in DEFAULTS:
    _p.origin = _p.name
    GROUP_COUNT[_p.group] = GROUP_COUNT.get(_p.group, 0) + 1


def brush_key(b):
    """库标识不参与 Brush.FIELDS；改名、改参数和移动均不改变身份。"""
    origin = getattr(b, "origin", None)
    if origin is not None:
        return "builtin:" + origin
    library_id = getattr(b, "_library_id", None)
    try:
        library_id = str(uuid.UUID(str(library_id)))
    except (ValueError, TypeError, AttributeError):
        library_id = str(uuid.uuid4())
    b._library_id = library_id
    return "custom:" + library_id


def clean_recent(presets, recent):
    """保留 MRU 顺序，剔除过期 / 重复标识，最多 32 支。"""
    valid = {brush_key(b) for b in presets}
    out = []
    for key in recent if isinstance(recent, list) else []:
        if isinstance(key, str) and key in valid and key not in out:
            out.append(key)
            if len(out) == RECENT_LIMIT:
                break
    return out


def clean_favorites(presets, favorites):
    """常用收藏按用户添加顺序保存，剔除已删除 / 重复项，最多 64 支。"""
    valid = {brush_key(b) for b in presets}
    out = []
    for key in favorites if isinstance(favorites, list) else []:
        if isinstance(key, str) and key in valid and key not in out:
            out.append(key)
            if len(out) == FAVORITE_LIMIT:
                break
    return out


def user_dir() -> str:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    if not base:
        base = os.path.expanduser("~/.photocraftdraw")
    path = os.path.join(base, "brushes")
    os.makedirs(path, exist_ok=True)
    return path


def user_file() -> str:
    return os.path.join(user_dir(), "user_brushes.json")


def load_library():
    """返回 (presets, meta)，含分类、改名、移动、MRU、当前笔和浏览状态。

    读取异常时仍提供内置笔，但用 _load_error 阻止后续覆盖损坏的原件。
    旧自建笔用唯一名字生成确定性 UUID，首次正常保存完成迁移。
    """
    data = {}
    error = None
    path = None
    try:
        path = user_file()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("笔刷库顶层必须是 JSON 对象")
        for key, kind in (("groups", list), ("brushes", list), ("renames", dict),
                          ("moves", dict), ("edits", dict), ("recent", list),
                          ("favorites", list), ("browse", dict)):
            if data.get(key) is not None and not isinstance(data[key], kind):
                raise ValueError(f"笔刷库字段 {key} 格式错误")
        if any(not isinstance(it, dict) for it in data.get("brushes") or []):
            raise ValueError("笔刷库 brushes 条目格式错误")
        for key in ("renames", "moves"):
            if any(not isinstance(v, str) for v in (data.get(key) or {}).values()):
                raise ValueError(f"笔刷库字段 {key} 的值必须是文字")
        if any(not isinstance(v, dict) for v in (data.get("edits") or {}).values()):
            raise ValueError("笔刷库 edits 条目格式错误")
    except FileNotFoundError:
        data = {}
    except Exception as e:
        data = {}
        error = str(e)
    meta = {"groups": [g for g in (data.get("groups") or [])
                       if isinstance(g, str) and g != RECENT_GROUP],
            "renames": dict(data.get("renames") or {}),
            "moves": dict(data.get("moves") or {}),
            "recent": list(data.get("recent") or []),
            "favorites": list(data.get("favorites") or []),
            "favorites_seeded": "favorites" in data,
            "current_key": data.get("current_key"),
            "browse": dict(data.get("browse") or {}),
            "migrated": dict(data.get("migrated") or {})}
    edits = dict(data.get("edits") or {})
    presets = []
    for b in DEFAULTS:
        c = b.copy()
        c.name = meta["renames"].get(b.name, b.name)
        c.group = meta["moves"].get(b.name, b.group)
        c.origin = b.name
        for field, value in (edits.get(b.name) or {}).items():
            if field in Brush.FIELDS and field not in ("name", "group"):
                setattr(c, field, value)
        presets.append(c)
    names = {b.name for b in presets}
    ids = set()
    for item in data.get("brushes", []) or []:
        try:
            b = Brush.from_dict(item)
            if not isinstance(b.name, str) or not b.name:
                raise ValueError("自建笔名称无效")
            if not isinstance(b.group, str):
                raise ValueError("自建笔分类无效")
        except Exception as e:
            error = error or str(e)
            continue
        if not item.get("group"):
            b.group = USER_GROUP
        base, n = b.name, 2
        while b.name in names:
            b.name = f"{base} {n}"
            n += 1
        names.add(b.name)
        try:
            b._library_id = str(uuid.UUID(str(item["_library_id"])))
        except (KeyError, ValueError, TypeError, AttributeError):
            b._library_id = str(uuid.uuid5(_LIBRARY_NAMESPACE, b.name))
        if b._library_id in ids:
            b._library_id = str(uuid.uuid5(_LIBRARY_NAMESPACE, "duplicate:" + b.name))
            while b._library_id in ids:
                b._library_id = str(uuid.uuid5(_LIBRARY_NAMESPACE, b._library_id + b.name))
        ids.add(b._library_id)
        presets.append(b)
    # 「常用」现在是虚拟收藏分类，不能再作为普通分组，避免笔刷被藏起来。
    for b in presets:
        if b.group == FAVORITE_GROUP:
            b.group = "基础" if getattr(b, "origin", None) else USER_GROUP
    # v2.15.6 一次性迁移：老库里很多笔的「最小直径」是 0.5~0.9，压感几乎看不出来。
    # 只做一次，之后用户自己调的值不再被动。
    if not meta["migrated"].get("min_size_v2"):
        for b in presets:
            if b.pressure_size and b.min_size > 0.30:
                b.min_size = 0.30
        meta["migrated"]["min_size_v2"] = 1
    meta["recent"] = clean_recent(presets, meta["recent"])
    # 首次升级：把旧「常用」分类里的六支笔迁移为可增删的收藏。
    if not meta.pop("favorites_seeded", False):
        by_name = {b.name: brush_key(b) for b in presets}
        meta["favorites"] = [by_name[n] for n in DEFAULT_FAVORITES if n in by_name]
    else:
        meta["favorites"] = clean_favorites(presets, meta["favorites"])
    # 空的自定义分类（例如历史遗留的「11」）不再显示，也不再写回。
    used_groups = {b.group for b in presets}
    meta["groups"] = [g for g in meta["groups"] if g in used_groups]
    if not isinstance(meta["current_key"], str) or meta["current_key"] not in {brush_key(b) for b in presets}:
        meta["current_key"] = None
    if error is not None:
        meta["_load_error"] = error
        meta["_load_error_path"] = path
    return presets, meta


def load_presets():
    """内置预设 + 本机保存的自建预设（不关心分类 / 改名信息时用这个）。"""
    return load_library()[0]


def _edits_of(presets):
    """内置笔里被改过的参数（只记和默认值不一样的字段）。"""
    out = {}
    for b in presets:
        origin = getattr(b, "origin", None)
        if not origin:
            continue
        default = BUILTIN.get(origin)
        if default is None:
            continue
        diff = {}
        for f in Brush.FIELDS:
            if f in ("name", "group"):
                continue
            if getattr(b, f) != getattr(default, f):
                diff[f] = getattr(b, f)
        if diff:
            out[origin] = diff
    return out


def save_library(presets, meta=None):
    """同目录临时文件 + fsync + 原子替换；失败时不截断原件。"""
    if meta is None:
        meta = load_library()[1]
    if meta.get("_load_error"):
        meta["_save_error"] = "笔刷库读取失败，已禁止覆盖原文件：" + meta["_load_error"]
        return False
    temporary = None
    try:
        custom = []
        for b in presets:
            if getattr(b, "origin", None) is None:
                brush_key(b)
                item = b.as_dict()
                item["_library_id"] = b._library_id
                custom.append(item)
        recent = clean_recent(presets, meta.get("recent"))
        favorites = clean_favorites(presets, meta.get("favorites"))
        valid = {brush_key(b) for b in presets}
        current_key = meta.get("current_key")
        if not isinstance(current_key, str) or current_key not in valid:
            current_key = None
        data = {"format": "photocraft-draw/brushes", "version": 3, "brushes": custom,
                "groups": list(meta.get("groups", [])),
                "renames": dict(meta.get("renames", {})),
                "moves": dict(meta.get("moves", {})),
                "edits": _edits_of(presets), "recent": recent,
                "favorites": favorites,
                "current_key": current_key, "browse": dict(meta.get("browse", {})),
                "migrated": dict(meta.get("migrated", {}))}
        content = json.dumps(data, ensure_ascii=False, indent=1, allow_nan=False)
        path = os.path.abspath(user_file())
        fd, temporary = tempfile.mkstemp(prefix=".user_brushes-", suffix=".tmp",
                                         dir=os.path.dirname(path))
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
        temporary = None
        meta["recent"] = recent
        meta["favorites"] = favorites
        meta["current_key"] = current_key
        meta.pop("_save_error", None)
        return True
    except Exception as e:
        meta["_save_error"] = str(e)
        return False
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def save_user_presets(presets, meta=None):
    """兼容旧调用：没有传 meta 就沿用磁盘上已有的分类 / 改名信息。"""
    if meta is None:
        meta = load_library()[1]
    return save_library(presets, meta)


def builtin_origin(brush: Brush):
    """是内置笔就返回它的原名，否则 None。"""
    return getattr(brush, "origin", None)


def all_groups(presets, meta=None) -> list:
    """有笔的真实分类；空分类（如历史遗留「11」）不显示。"""
    custom = list((meta or {}).get("groups") or [])
    virtual = {FAVORITE_GROUP, RECENT_GROUP, USER_GROUP}
    used = {b.group for b in presets if b.group not in virtual}
    order = [g for g in GROUPS if g != USER_GROUP and g in used]
    for g in custom:
        if g in used and g not in order and g != USER_GROUP:
            order.append(g)
    for b in presets:
        if b.group in used and b.group not in order:
            order.append(b.group)
    order.append(USER_GROUP)
    return order


def export_brush(brush: Brush, path: str) -> bool:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"format": "photocraft-draw/brush", "version": 2,
                       "brush": brush.as_dict()}, f, ensure_ascii=False, indent=1)
        return True
    except Exception:
        return False


def export_group(group: str, brushes, path: str) -> bool:
    """把一个分类里的所有笔打包成一个 .pcbrush 文件（分类包）。"""
    items = [b.as_dict() for b in brushes if b.group == group]
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"format": "photocraft-draw/brushpack", "version": 1,
                       "group": group, "brushes": items},
                      f, ensure_ascii=False, indent=1)
        return True
    except Exception:
        return False


def import_brushes(path: str):
    """支持单个笔刷文件，也支持一整个预设包。返回 Brush 列表。"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    out = []
    if isinstance(data, dict):
        if "brush" in data:
            out.append(Brush.from_dict(data["brush"]))
        for item in data.get("brushes", []) or []:
            out.append(Brush.from_dict(item))
    elif isinstance(data, list):
        out = [Brush.from_dict(it) for it in data]
    out = [b for b in out if isinstance(b.name, str) and b.name]
    for b in out:
        # 导入是新副本，即使包里携带旧库 ID，也不能与本机历史共用身份。
        b._library_id = str(uuid.uuid4())
    return out


def import_pack(path: str):
    """读一个分类包，返回 (分类名 or None, [Brush...])。

    分类包就是「把某个分类里的笔整包导出」得到的文件，
    导入时会把它们放回同名分类（没有这个分类就新建一个）。
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    group = None
    if isinstance(data, dict):
        group = data.get("group") or None
    return group, import_brushes(path)
