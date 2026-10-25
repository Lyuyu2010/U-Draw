# -*- coding: utf-8 -*-
"""U Draw - 导出 Photoshop 工程（.psd）

只写「能进 PS 继续修」需要的东西：尺寸、图层顺序、每层位置（整层铺满画布，
内容位置天然保留）、可见性、不透明度、图层名（含中文）、透明通道，外加一张合成图。

不写：混合模式（本程序只有「正常」）、图层组（PSD 的组要 lsct 段，成本高收益低，
这里按 z 序摊平成普通图层）、图层样式、蒙版、文字层（文字已经落成像素）。

文件结构按 Adobe 的 PSD 规范（8BPS / version 1 / RGB / 8bit / 4 通道），
通道数据用 PackBits（RLE）压，PS / GIMP / Krita / Affinity 都能直接打开。
"""

import re
import struct

from PySide6.QtGui import QImage, QPainter

SIG = b"8BPS"
BLEND_NORMAL = b"norm"
_RUN = re.compile(rb"(.)\1\1+", re.S)      # 连续 3 个以上相同字节


# ------------------------------------------------------------------ PackBits
def _emit_literal(out: bytearray, chunk: bytes):
    i = 0
    while i < len(chunk):
        piece = chunk[i:i + 128]
        out.append(len(piece) - 1)
        out += piece
        i += 128


def _packbits(data: bytes) -> bytes:
    """PSD 的 RLE 编码（PackBits）。

    用正则找「连续 3 个以上相同字节」的段，其余当字面量发出去 —— 逐字节扫
    在 1920×1080 上要 0.6 秒/层，正则走 C 层快一个数量级。
    """
    out = bytearray()
    pos, n = 0, len(data)
    while pos < n:
        m = _RUN.search(data, pos)
        if m is None:
            _emit_literal(out, data[pos:])
            break
        start, end = m.start(), m.end()
        if start > pos:
            _emit_literal(out, data[pos:start])
        val = data[start]
        run = end - start
        while run > 0:
            k = min(128, run)
            if k >= 3:
                out.append((257 - k) & 0xFF)      # -(k-1)
                out.append(val)
            else:
                _emit_literal(out, bytes([val]) * k)
            run -= k
        pos = end
    return bytes(out)


def _rle_channel(rows):
    """rows: [bytes, ...] 每行一段原始字节 → (每行编码长度列表, 编码后的数据)。"""
    lengths, chunks = [], []
    for row in rows:
        enc = _packbits(row)
        lengths.append(len(enc))
        chunks.append(enc)
    return lengths, b"".join(chunks)


# ------------------------------------------------------------------ 小工具
def _pascal(name: str, limit: int = 255) -> bytes:
    """Pascal 字符串：1 字节长度 + 内容，再补齐到 4 的倍数。"""
    raw = name.encode("latin-1", "replace")[:limit]
    out = bytes([len(raw)]) + raw
    pad = (4 - (len(out) % 4)) % 4
    return out + b"\x00" * pad


def _luni_block(name: str) -> bytes:
    """'luni' 段：Unicode 图层名，中文名靠它才不会变成问号。"""
    text = name.encode("utf-16-be")
    payload = struct.pack(">I", len(name)) + text
    pad = len(payload) % 2
    if pad:
        payload += b"\x00"
    return (b"8BIM" + b"luni" + struct.pack(">I", len(payload)) + payload)


def _channel_bytes(img: QImage):
    """把一张 ARGB32 图拆成 4 个通道的原始字节（每行一段）。"""
    w, h = img.width(), img.height()
    out = {0: [], 1: [], 2: [], 3: []}
    for y in range(h):
        row = img.constScanLine(y)
        # Qt 的 ARGB32 在小端机上是 B,G,R,A
        b = bytes(row)[: w * 4]
        out[0].append(b[2::4])     # R
        out[1].append(b[1::4])     # G
        out[2].append(b[0::4])     # B
        out[3].append(b[3::4])     # A
    return out


# ------------------------------------------------------------------ 写 PSD
def build_psd(doc) -> bytes:
    """把 Document 打包成 PSD 字节流。"""
    w, h = int(doc.w), int(doc.h)
    if w <= 0 or h <= 0 or w > 30000 or h > 30000:
        raise ValueError("PSD 支持的画布范围是 1~30000 像素")

    # PSD 的图层顺序是「从下往上」，正好和 doc.layers 一致；文字浮在最上面
    sources = []
    for layer in doc.layers:
        vis, op = doc.layer_state(layer)
        sources.append((layer.name, layer.image, vis, op))
    for it in doc.texts:
        img = QImage(w, h, QImage.Format_ARGB32)
        img.fill(0)
        was = it.visible
        it.visible = True          # 隐藏的文字也导出成「隐藏图层」，PS 里能再打开
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        it.draw(p)
        p.end()
        it.visible = was
        sources.append((it.name, img, was, 1.0))

    chunks = []
    for name, img, vis, op in sources:
        if img.width() != w or img.height() != h:
            img = img.scaled(w, h)
        chans = _channel_bytes(img)
        enc = {}
        for cid, rows in chans.items():
            lengths, data = _rle_channel(rows)
            enc[cid] = (lengths, data)
        chunks.append((name, vis, op, enc))

    # ---- 图层信息段
    layer_records = bytearray()
    channel_data = bytearray()
    layer_records += struct.pack(">h", len(chunks))
    for name, vis, op, enc in chunks:
        # 每层都铺满画布：位置信息天然保留（内容在哪就在哪）
        layer_records += struct.pack(">iiii", 0, 0, h, w)
        ids = [-1, 0, 1, 2]                     # A, R, G, B
        layer_records += struct.pack(">H", len(ids))
        for cid in ids:
            lengths, data = enc[cid if cid >= 0 else 3]
            total = 2 + 2 * len(lengths) + len(data)
            layer_records += struct.pack(">hI", cid, total)
        layer_records += b"8BIM" + BLEND_NORMAL      # 混合模式：签名 + 键
        # 组是摊平成普通图层的，所以组的可见性 / 不透明度要算进每层里
        layer_records += bytes([
            max(0, min(255, int(round(op * 255)))),
            0,                                   # clipping
            2 if not vis else 0,                 # flags: bit1 = 隐藏
            0,                                   # filler
        ])
        extra = bytearray()
        extra += struct.pack(">I", 0)            # 图层蒙版数据
        extra += struct.pack(">I", 0)            # 混合区间
        extra += _pascal(name or "图层")
        extra += _luni_block(name or "图层")
        layer_records += struct.pack(">I", len(extra))
        layer_records += extra

    for name, vis, op, enc in chunks:
        for cid in (-1, 0, 1, 2):
            lengths, data = enc[cid if cid >= 0 else 3]
            channel_data += struct.pack(">H", 1)          # 1 = RLE
            channel_data += b"".join(struct.pack(">H", n) for n in lengths)
            channel_data += data

    layer_info = bytes(layer_records) + bytes(channel_data)
    if len(layer_info) % 2:
        layer_info += b"\x00"          # 规范要求这一段长度是偶数
    # 「图层与蒙版信息段」本身还有一个外层长度，漏了它 PS / psd-tools 都会读崩
    section = (struct.pack(">I", len(layer_info)) + layer_info
               + struct.pack(">I", 0))      # 全局图层蒙版信息（空）
    if len(section) % 2:
        section += b"\x00"
    lmi = struct.pack(">I", len(section)) + section

    # ---- 合成图（PS 打开时先显示的这张）
    flat = doc.flatten().convertToFormat(QImage.Format_ARGB32)
    if flat.width() != w or flat.height() != h:
        flat = flat.scaled(w, h)
    chans = _channel_bytes(flat)
    comp_lengths, comp_chunks = [], []
    for cid in (0, 1, 2, 3):
        lengths, data = _rle_channel(chans[cid])
        comp_lengths += lengths
        comp_chunks.append(data)
    image_data = struct.pack(">H", 1)
    image_data += b"".join(struct.pack(">H", n) for n in comp_lengths)
    image_data += b"".join(comp_chunks)

    header = (SIG + struct.pack(">H", 1) + b"\x00" * 6
              + struct.pack(">HIIHH", 4, h, w, 8, 3))
    return (header
            + struct.pack(">I", 0)          # 颜色模式数据
            + struct.pack(">I", 0)          # 图像资源
            + lmi
            + image_data)


def export_psd(doc, path: str):
    """写一个 .psd 文件；返回字节数。"""
    blob = build_psd(doc)
    with open(path, "wb") as f:
        f.write(blob)
    return len(blob)
