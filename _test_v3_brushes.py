# -*- coding: utf-8 -*-
"""v3.0 S3：笔刷库 +10 款

验：数量 / 分类 / 笔型合法 / 不重名 / 参数不撞车 / 画得出来 / 长得不一样 /
缩略图齐全 / 预设区能列出来。
"""
import hashlib
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

app = QApplication([])
import brushes
import brush_thumbs
import core
import theme

theme.apply_theme(app)
from core import Brush

NEW = {
    "点彩圆笔": ("基础", "round"),
    "勾线细笔": ("勾线", "ballpoint"),
    "炭条侧涂": ("炭笔粉笔", "charcoal"),
    "硬头马克笔": ("马克笔", "marker"),
    "酒精马克笔": ("马克笔", "marker"),
    "渗边水彩": ("水彩", "watercolor"),
    "平口排刷": ("油画", "bristle"),
    "大号软粉": ("蜡笔色粉", "chalk"),
    "宽幅喷雾": ("喷枪", "spray"),
    "粗颗粒笔": ("纹理", "noise"),
}

ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("  OK  " if cond else " FAIL ") + name + ("  " + str(extra) if extra else ""))


presets = brushes.DEFAULTS
by_name = {b.name: b for b in presets}

check("笔刷总数 143", len(presets) == 143, len(presets))
check("新增的 10 支都在库里", all(n in by_name for n in NEW),
      [n for n in NEW if n not in by_name] or "齐全")
check("分类正确", all(by_name[n].group == g for n, (g, _k) in NEW.items() if n in by_name),
      [(n, by_name[n].group) for n, (g, _k) in NEW.items()
       if n in by_name and by_name[n].group != g] or "全对")
check("笔型正确", all(by_name[n].kind == k for n, (_g, k) in NEW.items() if n in by_name))
check("笔型都合法", all(b.kind in core.KINDS for b in presets))

names = [b.name for b in presets]
check("没有重名", len(set(names)) == len(names))

# 参数签名不能撞车（撞车 = 只是换了个名字）
seen = {}
dup = []
for b in presets:
    sig = tuple(round(float(getattr(b, f)), 4) for f in Brush.FLOATS) + (b.kind,)
    if sig in seen:
        dup.append((seen[sig], b.name))
    seen[sig] = b.name
check("参数没有撞车", not dup, str(dup))

# 每支新笔都要真的出墨
from _brushlib_audit import stroke_ink

dead = []
for n in NEW:
    if n not in by_name:
        continue
    ink = stroke_ink(by_name[n])
    if ink < 20.0:
        dead.append((n, round(ink, 1)))
check("10 支新笔都画得出来", not dead, str(dead))

# 长得不一样：新增的这 10 支，小样不能和库里任何一支撞
# （基线里 钢笔/圆珠笔、网点笔/粗网点 在 68×35 小样下本来就分不出来，不归 v3.0 管）
sigs = {}
for b in presets:
    img = core.preview_image(b, 68, 35, QColor(226, 226, 226), 1)
    sigs.setdefault(hashlib.sha1(bytes(img.constBits())).hexdigest(), []).append(b.name)
clash = []
for n in NEW:
    for h, group_names in sigs.items():
        if n in group_names and len(group_names) > 1:
            clash.append((n, [x for x in group_names if x != n]))
check("新增的笔没有一支和别的笔长得一样", not clash, str(clash))

# 缩略图 / 悬浮大图都要预生成好（打包后靠这些文件，不再实时渲染）
missing = [n for n in NEW
           if not brush_thumbs.thumb_path(by_name[n]).is_file()
           or not brush_thumbs.popup_path(by_name[n]).is_file()]
check("新笔的缩略图已生成", not missing, str(missing))

# 预设区里能列出来
lib, _meta = brushes.load_library()
lib_names = {b.name for b in lib}
check("笔刷库（预设区数据源）里也有这 10 支", all(n in lib_names for n in NEW),
      [n for n in NEW if n not in lib_names] or "齐全")

from main_window import MainWindow

win = MainWindow()
win.show()
app.processEvents()
panel = win.brush_panel
check("画笔面板读到的笔刷数 ≥ 143", len(panel.presets) >= 143, len(panel.presets))
panel_names = {b.name for b in panel.presets}
check("画笔面板里能找到新笔", all(n in panel_names for n in NEW))

print("\n结果:", "全部通过" if ok else "有失败项")
sys.exit(0 if ok else 1)
