# -*- coding: utf-8 -*-
"""PSD 导出校验：自己按规范把文件读回来，逐层核对位置 / 名称 / 不透明度 / 像素。

跑法：python _psd_test.py
（不依赖第三方库；如果装了 psd-tools 会额外用它再读一遍）
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

OUT = os.path.join(HERE, "_v21_out")
FAIL = []


def ck(cond, msg):
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        FAIL.append(msg)


def _packbits_decode(data, expect):
    out = bytearray()
    i = 0
    while i < len(data) and len(out) < expect:
        n = data[i]
        i += 1
        if n < 128:
            out += data[i:i + n + 1]
            i += n + 1
        elif n > 128:
            out += bytes([data[i]]) * (257 - n)
            i += 1
    return bytes(out[:expect])


def read_psd(path):
    b = open(path, "rb").read()
    assert b[:4] == b"8BPS", "签名不对"
    ver = struct.unpack(">H", b[4:6])[0]
    ch, h, w, depth, mode = struct.unpack(">HIIHH", b[12:26])
    off = 26
    cml = struct.unpack(">I", b[off:off + 4])[0]
    off += 4 + cml
    irl = struct.unpack(">I", b[off:off + 4])[0]
    off += 4 + irl
    # 「图层与蒙版信息段」：外层长度 → 图层信息长度 → ...
    lmi_len = struct.unpack(">I", b[off:off + 4])[0]
    off += 4
    lmi_end = off + lmi_len
    lil = struct.unpack(">I", b[off:off + 4])[0]
    off += 4
    cnt = struct.unpack(">h", b[off:off + 2])[0]
    off += 2
    layers = []
    for _ in range(cnt):
        top, left, bottom, right = struct.unpack(">iiii", b[off:off + 16])
        off += 16
        nch = struct.unpack(">H", b[off:off + 2])[0]
        off += 2
        chans = []
        for _k in range(nch):
            cid, ln = struct.unpack(">hI", b[off:off + 6])
            chans.append([cid, ln, None])
            off += 6
        assert b[off:off + 4] == b"8BIM", "混合模式签名不对"
        blend = b[off + 4:off + 8]
        off += 8
        op, clip, flags = b[off], b[off + 1], b[off + 2]
        off += 4
        ext = struct.unpack(">I", b[off:off + 4])[0]
        off += 4
        extra = b[off:off + ext]
        off += ext
        nl = extra[8]
        name = extra[9:9 + nl].decode("latin-1")
        uname = None
        p = extra.find(b"luni")
        if p > 0:
            blen = struct.unpack(">I", extra[p + 4:p + 8])[0]
            body = extra[p + 8:p + 8 + blen]
            nchars = struct.unpack(">I", body[:4])[0]
            uname = body[4:4 + nchars * 2].decode("utf-16-be")
        layers.append({"rect": (top, left, bottom, right), "name": name,
                       "uname": uname, "blend": blend, "opacity": op,
                       "hidden": bool(flags & 2), "chans": chans})
    # 通道数据
    for lay in layers:
        for ch_info in lay["chans"]:
            comp = struct.unpack(">H", b[off:off + 2])[0]
            off += 2
            rows = lay["rect"][2] - lay["rect"][0]
            if comp == 1:
                lens = [struct.unpack(">H", b[off + 2 * i:off + 2 * i + 2])[0]
                        for i in range(rows)]
                off += 2 * rows
                raw = bytearray()
                for ln in lens:
                    raw += _packbits_decode(b[off:off + ln], w)
                    off += ln
                ch_info[2] = bytes(raw)
            else:
                ch_info[2] = b[off:off + rows * w]
                off += rows * w
    # 合成图
    off = lmi_end
    comp = struct.unpack(">H", b[off:off + 2])[0]
    off += 2
    plane = {}
    if comp == 1:
        lens = [struct.unpack(">H", b[off + 2 * i:off + 2 * i + 2])[0] for i in range(h * ch)]
        off += 2 * h * ch
        for c in range(ch):
            raw = bytearray()
            for y in range(h):
                ln = lens[c * h + y]
                raw += _packbits_decode(b[off:off + ln], w)
                off += ln
            plane[c] = bytes(raw)
    return {"ver": ver, "ch": ch, "w": w, "h": h, "depth": depth, "mode": mode,
            "layers": layers, "comp": plane, "size": len(b)}


def main():
    os.makedirs(OUT, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)
    from core import Document
    import psd_export

    print("[0] PackBits 往返")
    import random
    random.seed(7)
    bad = 0
    for trial in range(300):
        ln = random.randint(1, 400)
        kind = trial % 3
        if kind == 0:
            data = bytes(random.randint(0, 3) for _ in range(ln))
        elif kind == 1:
            data = bytes([7]) * ln
        else:
            data = bytes(random.randint(0, 255) for _ in range(ln))
        enc = psd_export._packbits(data)
        if _packbits_decode(enc, ln) != data:
            bad += 1
    ck(bad == 0, f"300 组随机数据编解码一致（{bad} 组不符）")

    d = Document(200, 120, QColor(255, 255, 255, 255))
    l1 = d.add_layer("红色块")
    p = QPainter(l1.image)
    p.fillRect(QRect(10, 10, 60, 40), QColor(255, 0, 0))
    p.end()
    l1.touch()
    l2 = d.add_layer("蓝色 中文层名")
    p = QPainter(l2.image)
    p.fillRect(QRect(120, 60, 50, 40), QColor(0, 0, 255))
    p.end()
    l2.touch()
    l2.opacity = 0.5
    d.recompose()
    # 文字对象也要作为独立图层进 PSD
    from core import TextItem
    d.add_text(TextItem("PSD 文字", 30, 60, "微软雅黑", 28, False, False,
                        QColor("#00A000")))

    path = os.path.join(OUT, "export_test.psd")
    n = psd_export.export_psd(d, path)
    print("[1] 文件头")
    info = read_psd(path)
    ck(info["ver"] == 1, f"版本 {info['ver']}")
    ck((info["w"], info["h"]) == (200, 120), f"尺寸 {info['w']}x{info['h']}")
    ck(info["ch"] == 4 and info["depth"] == 8 and info["mode"] == 3,
       f"4 通道 / 8bit / RGB（{info['ch']} {info['depth']} {info['mode']}）")
    ck(n == info["size"] and n > 0, f"文件 {n} 字节，可完整读回")

    print("[2] 图层")
    ck(len(info["layers"]) == 4, f"3 个像素层 + 1 个文字层（{len(info['layers'])}）")
    names = [l["uname"] or l["name"] for l in info["layers"]]
    ck(names[:3] == ["背景", "红色块", "蓝色 中文层名"], f"层序与名字 {names}")
    ck(names[3].startswith("文字"), f"文字在最上层且可辨认（{names[3]}）")
    for l in info["layers"]:
        ck(l["rect"] == (0, 0, 120, 200), f"「{l['uname']}」铺满画布（位置保留）")
    ck(info["layers"][2]["opacity"] == 128,
       f"不透明度 50% → {info['layers'][2]['opacity']}")
    ck(all(l["blend"] == b"norm" for l in info["layers"]), "混合模式都是正常")

    print("[3] 像素")
    lay = info["layers"][1]
    alpha = next(c[2] for c in lay["chans"] if c[0] == -1)
    red = next(c[2] for c in lay["chans"] if c[0] == 0)
    at = 20 * 200 + 20
    ck(alpha[at] == 255, f"红块处 alpha={alpha[at]}")
    ck(red[at] == 255, f"红块处 R={red[at]}")
    outside = 5 * 200 + 5
    ck(alpha[outside] == 0, f"空白处 alpha={alpha[outside]}")
    lay2 = info["layers"][2]
    a2 = next(c[2] for c in lay2["chans"] if c[0] == -1)
    b2 = next(c[2] for c in lay2["chans"] if c[0] == 2)
    at2 = 80 * 200 + 140
    ck(a2[at2] == 255 and b2[at2] == 255, f"蓝块处 alpha={a2[at2]} B={b2[at2]}")

    print("[4] 合成图")
    ck(bool(info["comp"]), "合成图数据存在")
    if info["comp"]:
        R, G, B, A = (info["comp"][i] for i in range(4))
        i0 = 30 * 200 + 30
        ck(R[i0] == 255 and G[i0] == 0, f"合成图红块像素 ({R[i0]},{G[i0]},{B[i0]})")
        i1 = 80 * 200 + 140
        ck(B[i1] > 200, f"合成图蓝块 B={B[i1]}")

    # 有 psd-tools 就再验一遍（可选，不随程序发布）
    try:
        from psd_tools import PSDImage
        psd = PSDImage.open(path)
        ck(psd.size == (200, 120), f"psd-tools 读出尺寸 {psd.size}")
        ck(len(list(psd)) == 4, f"psd-tools 读出 {len(list(psd))} 层")
        nm = [l.name for l in psd]
        ck("蓝色 中文层名" in nm, f"psd-tools 读出中文层名 {nm}")
        ck([l.offset for l in psd] == [(0, 0)] * 4, "psd-tools 读出每层偏移都是 (0,0)")
        l2p = list(psd)[2]
        ck(abs(l2p.opacity / 255.0 - 0.5) < 0.02,
           f"psd-tools 读出 50% 不透明度（{l2p.opacity}）")
        # 合成图逐像素对比：PS 里看到的应该和本程序里一致
        comp = psd.composite()
        if comp is not None:
            comp = comp.convert("RGBA")
            ref = d.flatten().convertToFormat(QImage.Format_ARGB32)
            bad = 0
            for (x, y) in ((30, 30), (140, 80), (5, 5), (190, 110)):
                a = comp.getpixel((x, y))
                c = ref.pixelColor(x, y)
                if (abs(a[0] - c.red()) > 6 or abs(a[1] - c.green()) > 6
                        or abs(a[2] - c.blue()) > 6):
                    bad += 1
                    print("    差异", (x, y), a, (c.red(), c.green(), c.blue()))
            ck(bad == 0, "psd-tools 合成的图与本程序一致")
    except ImportError:
        print("  --  没装 psd-tools，跳过第三方校验")

    print()
    if FAIL:
        print("失败 %d 项：" % len(FAIL))
        for m in FAIL:
            print("  -", m)
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
