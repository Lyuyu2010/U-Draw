# -*- coding: utf-8 -*-
"""U Draw - 文字库（字体清单）

内置字体是原版 PhotoCraft 自带的那几套 OFL 开源字体（从原版里原样取出来的
sfnt 文件，见 assets/fonts/），加上系统里可用的中文字体，做成文字工具的字体库。
"""

import os
import sys

from PySide6.QtGui import QFont, QFontDatabase

# (文件名, 显示名, 备注)  —— 顺序就是下拉框里的顺序
BUNDLED_FILES = [
    ("BIZ UDPGothic.ttf", "BIZ UD 哥特", "内置 · 黑体"),
    ("BIZ UDPGothic Bold.ttf", "BIZ UD 哥特 粗", "内置 · 黑体"),
    ("BIZ UDMincho.ttf", "BIZ UD 明朝", "内置 · 宋体"),
    ("Shippori Mincho Regular.ttf", "Shippori 明朝", "内置 · 衬线"),
]

# 系统字体里优先出现的（中文创作最常用），不存在就跳过
PREFERRED = [
    "微软雅黑", "Microsoft YaHei",
    "思源黑体", "Source Han Sans SC", "Noto Sans CJK SC", "Noto Sans SC",
    "思源宋体", "Source Han Serif SC", "Noto Serif CJK SC", "Noto Serif SC",
    "黑体", "SimHei",
    "宋体", "SimSun",
    "楷体", "KaiTi",
    "仿宋", "FangSong",
    "等线", "DengXian",
    "苹方", "PingFang SC",
    "Segoe UI", "Arial", "Times New Roman", "Georgia", "Consolas",
]

_loaded = False
_entries = []


def asset_dir() -> str:
    """内置字体目录（兼容 PyInstaller 单文件包）。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        p = os.path.join(base, "assets", "fonts")
        if os.path.isdir(p):
            return p
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")


def _register_bundled():
    """把内置字体注册进 Qt；返回 {显示名: 实际 family}。"""
    out = {}
    d = asset_dir()
    for fname, label, _note in BUNDLED_FILES:
        path = os.path.join(d, fname)
        if not os.path.isfile(path):
            continue
        fid = QFontDatabase.addApplicationFont(path)
        if fid < 0:
            continue
        fams = QFontDatabase.applicationFontFamilies(fid)
        if not fams:
            continue
        out[label] = fams[0]
    return out


def entries():
    """返回 [{'label','family','bundled'}]，内置字体排在前面。"""
    global _loaded, _entries
    if _loaded:
        return _entries
    _loaded = True
    bundled = _register_bundled()
    have = set(QFontDatabase.families())
    out = []
    seen = set()

    for _fname, label, note in BUNDLED_FILES:
        fam = bundled.get(label)
        if not fam:
            continue
        # 粗体那一份和常规体同 family，只列一次（粗体靠字重自动选中）
        if fam in seen:
            continue
        seen.add(fam)
        out.append({"label": f"{label}（{note}）", "family": fam, "bundled": True})

    for fam in PREFERRED:
        if fam in have and fam not in seen:
            seen.add(fam)
            out.append({"label": fam, "family": fam, "bundled": False})

    rest = []
    cjk = set()
    for fam in QFontDatabase.families():
        if fam in seen:
            continue
        rest.append(fam)
        try:
            ws = QFontDatabase.writingSystems(fam)
        except Exception:
            ws = []
        if any(w in ws for w in (QFontDatabase.WritingSystem.SimplifiedChinese,
                                 QFontDatabase.WritingSystem.TraditionalChinese,
                                 QFontDatabase.WritingSystem.Japanese,
                                 QFontDatabase.WritingSystem.Korean)):
            cjk.add(fam)
    # 文字库只放「写得出中文」的字体 + 常用西文，几百个字体全塞进下拉框没法用
    rest = [f for f in rest if f in cjk or f in ("Arial", "Georgia", "Consolas",
                                                 "Times New Roman", "Verdana",
                                                 "Courier New", "Impact")]
    rest.sort(key=lambda s: s.lower())
    for fam in rest:
        out.append({"label": fam, "family": fam, "bundled": False})

    _entries = out
    return out


_default_cache = None


def default_family() -> str:
    """默认字体：优先内置哥特（跟原版一致），否则退回系统第一个中文字体。

    注意不要走 entries()：那个要把系统几百个字体全枚举一遍、再逐个查书写系统
    （实测 76ms，全压在启动路径上）。这里只需要「第一支内置字体」，
    注册 4 个内置字体就够了。
    """
    global _default_cache
    if _default_cache:
        return _default_cache
    bundled = _register_bundled()
    for _fname, label, _note in BUNDLED_FILES:
        fam = bundled.get(label)
        if fam:
            _default_cache = fam
            return fam
    have = set(QFontDatabase.families())
    for fam in ("微软雅黑", "Microsoft YaHei", "SimHei", "SimSun"):
        if fam in have:
            _default_cache = fam
            return fam
    fams = QFontDatabase.families()
    _default_cache = fams[0] if fams else "sans-serif"
    return _default_cache


def family_of(label_or_family: str) -> str:
    """把下拉框里的显示名换回真正的 family。"""
    for e in entries():
        if label_or_family in (e["label"], e["family"]):
            return e["family"]
    return label_or_family


def make_font(family: str, px: float, bold: bool = False,
              italic: bool = False) -> QFont:
    f = QFont(family)
    # 回退链：选中的字体缺字（比如西文字体里没有中文）时，Qt 会自己找替代字体，
    # 替代字体的字面大小常常和原字体差一截，看着就是「一会儿大一会儿小」。
    # 明确给一条中文回退链，缺字时用的字体就固定了。
    try:
        f.setFamilies([family, "Microsoft YaHei", "微软雅黑", "SimHei",
                       "Noto Sans CJK SC", "Source Han Sans SC",
                       "Segoe UI", "Arial"])
    except Exception:
        pass
    f.setPixelSize(max(1, int(round(px))))
    f.setBold(bool(bold))
    f.setItalic(bool(italic))
    f.setHintingPreference(QFont.PreferNoHinting)   # 缩放预览时字形不发毛
    f.setStyleStrategy(QFont.PreferAntialias)
    return f
