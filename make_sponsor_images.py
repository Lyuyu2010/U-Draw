# -*- coding: utf-8 -*-
"""把两张收款码海报裁成干净的二维码卡片，并写成内嵌数据。

原始海报是「彩色底 + 白色圆角卡片」的样式，直接把整张图塞进暗色对话框会很难看，
所以这里只取那张白色卡片：自动找出白色区域的外接矩形 → 内缩 2px 去彩色描边 →
按原圆角半径切掉四角 → 存 PNG，同时把 base64 写进 sponsor_data.py。

跑法： python make_sponsor_images.py
"""

import base64
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import (QBrush, QColor, QGuiApplication, QImage,  # noqa: E402
                           QPainter, QPainterPath)

SRC = {
    "wechat": r"C:\Users\20688\Downloads\mm_facetoface_collect_qrcode_1792675315618.png",
    "alipay": r"C:\Users\20688\Downloads\1792675328569.jpg",
}
OUT_DIR = os.path.join(HERE, "assets")


def white_mask(img: QImage, step: int = 4, thresh: int = 224):
    """缩成 1/step 的白色掩码。卡片是连成一片的白，二维码里的白模块也连着它。"""
    w, h = img.width() // step, img.height() // step
    mask = bytearray(w * h)
    for y in range(h):
        row = y * w
        for x in range(w):
            c = img.pixelColor(x * step, y * step)
            if min(c.red(), c.green(), c.blue()) >= thresh:
                mask[row + x] = 1
    return mask, w, h


def largest_white_blob(img: QImage, step: int = 4):
    """连成一片的最大白色区域（4 邻域洪泛），返回原图坐标下的外接矩形。"""
    mask, mw, mh = white_mask(img, step)
    seen = bytearray(len(mask))
    best = (0, 0, 0, 0)
    best_area = 0
    from collections import deque
    for sy in range(mh):
        for sx in range(mw):
            i = sy * mw + sx
            if not mask[i] or seen[i]:
                continue
            q = deque([(sx, sy)])
            seen[i] = 1
            x0 = x1 = sx
            y0 = y1 = sy
            area = 0
            while q:
                cx, cy = q.popleft()
                area += 1
                if cx < x0: x0 = cx
                if cx > x1: x1 = cx
                if cy < y0: y0 = cy
                if cy > y1: y1 = cy
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if 0 <= nx < mw and 0 <= ny < mh:
                        j = ny * mw + nx
                        if mask[j] and not seen[j]:
                            seen[j] = 1
                            q.append((nx, ny))
            # 只看够大的块（小字、噪点不算）
            if area > 400 and area > best_area:
                best_area = area
                best = (x0 * step, y0 * step, (x1 + 1) * step - 1, (y1 + 1) * step - 1)
    if best_area == 0:
        raise SystemExit("没找到白色卡片")
    return best


def refine(img: QImage, box, thresh: int = 224):
    """把粗定位的框按整像素再收一遍，避免 1/step 缩放带来的几个像素误差。"""
    x0, y0, x1, y1 = box
    # 上下：行内白像素占比 > 15% 才算卡片行（二维码那几行也够）
    def row_ok(y):
        n = 0
        for x in range(x0, x1 + 1, 2):
            c = img.pixelColor(x, y)
            if min(c.red(), c.green(), c.blue()) >= thresh:
                n += 1
        return n >= 0.15 * ((x1 - x0) / 2.0)

    def col_ok(x):
        n = 0
        for y in range(y0, y1 + 1, 2):
            c = img.pixelColor(x, y)
            if min(c.red(), c.green(), c.blue()) >= thresh:
                n += 1
        return n >= 0.15 * ((y1 - y0) / 2.0)

    while y0 < y1 and not row_ok(y0):
        y0 += 1
    while y1 > y0 and not row_ok(y1):
        y1 -= 1
    while x0 < x1 and not col_ok(x0):
        x0 += 1
    while x1 > x0 and not col_ok(x1):
        x1 -= 1
    return x0, y0, x1, y1


def card_rect(img: QImage):
    return refine(img, largest_white_blob(img))


def rounded(img: QImage, radius: float) -> QImage:
    out = QImage(img.width(), img.height(), QImage.Format.Format_ARGB32)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, img.width(), img.height()), radius, radius)
    p.setClipPath(path)
    p.drawImage(0, 0, img)
    p.end()
    return out


def content_box(img: QImage, card, thresh: int = 170):
    """卡片里有墨的部分（二维码 + 名字）的外接矩形，用来定留白。

    只看「灰的黑」（最亮-最暗 <= 60）：卡片圆角外面露出来的蓝色 / 绿色底
    虽然也够暗，但饱和度高，不能算内容。
    """
    x0, y0, x1, y1 = card
    bx0, by0, bx1, by1 = x1, y1, x0, y0
    for y in range(y0, y1 + 1, 2):
        for x in range(x0, x1 + 1, 2):
            c = img.pixelColor(x, y)
            r, g, b = c.red(), c.green(), c.blue()
            if min(r, g, b) < thresh and max(r, g, b) - min(r, g, b) <= 60:
                if x < bx0: bx0 = x
                if x > bx1: bx1 = x
                if y < by0: by0 = y
                if y > by1: by1 = y
    if bx0 > bx1:
        raise SystemExit("卡片里没找到内容")
    return bx0, by0, bx1, by1


def process(key: str):
    src = SRC[key]
    img = QImage(src)
    if img.isNull():
        raise SystemExit(f"读不到 {src}")
    card = card_rect(img)
    cb = content_box(img, card)
    cw, ch = cb[2] - cb[0] + 1, cb[3] - cb[1] + 1
    # 统一成同一个宽高比（0.86）：两张卡在对话框里就能画成一样大，
    # 不然 609x715 和 873x961 并排会一高一矮。多出来的部分用卡片自带的白补。
    w = int(round(cw * 1.14))
    h = int(round(w / 0.86))
    cx = (cb[0] + cb[2]) / 2.0
    cy = (cb[1] + cb[3]) / 2.0
    x0 = int(round(cx - w / 2.0))
    y0 = int(round(cy - h / 2.0))
    x0 = max(card[0], min(x0, card[2] - w + 1))
    y0 = max(card[1], min(y0, card[3] - h + 1))
    x1, y1 = x0 + w - 1, y0 + h - 1
    out = img.copy(x0, y0, w, h)
    out = rounded(out, max(8.0, out.width() * 0.07))
    os.makedirs(OUT_DIR, exist_ok=True)
    dst = os.path.join(OUT_DIR, f"qr_{key}.png")
    out.save(dst, "PNG")
    print(f"{key:<7} 源 {img.width()}x{img.height()}  内容 {cw}x{ch}"
          f"  卡片 {(x0, y0, x1, y1)}  → {out.width()}x{out.height()}"
          f"  ({out.width() / out.height():.3f})  {os.path.getsize(dst) // 1024} KB")
    return out


def b64_of(path: str) -> str:
    with open(path, "rb") as f:
        raw = f.read()
    s = base64.b64encode(raw).decode("ascii")
    return "\n".join(s[i:i + 96] for i in range(0, len(s), 96))


def main():
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
    for key in SRC:
        process(key)

    lines = ['# -*- coding: utf-8 -*-',
             '"""收款码内嵌数据（由 make_sponsor_images.py 自动生成，别手改）。',
             '',
             '打包成单文件 exe 后没有外部资源目录可依赖，图标和收款码统一用 base64',
             '内嵌，运行时解码成 QPixmap —— 换图只要重跑生成脚本。',
             '"""',
             '',
             'QR_WECHAT_PNG_B64 = """']
    lines.append(b64_of(os.path.join(OUT_DIR, "qr_wechat.png")))
    lines.append('"""')
    lines.append('')
    lines.append('QR_ALIPAY_PNG_B64 = """')
    lines.append(b64_of(os.path.join(OUT_DIR, "qr_alipay.png")))
    lines.append('"""')
    lines.append('')
    dst = os.path.join(HERE, "sponsor_data.py")
    with open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("已写入", dst, os.path.getsize(dst) // 1024, "KB")


if __name__ == "__main__":
    sys.exit(main())
