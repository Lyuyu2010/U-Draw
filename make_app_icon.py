# -*- coding: utf-8 -*-
"""从 IMG_20261022_194513.png 生成 U Draw 的应用图标。

产物：
  app_icon.ico        多尺寸 Windows 图标（16~256），供 exe 资源用
  appicon.png         256px 透明圆角 PNG，运行时窗口图标用
  appicon_data.py     上面那张 PNG 的 base64 内联版（打包后无需外部文件）
"""

import base64
import os
import struct

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "IMG_20261022_194513.png")
SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]
RADIUS = 0.215          # 圆角半径占边长比例（接近 iOS squircle）


def content_bbox(im: QImage, thr=250):
    """找画面的非白包围盒（用 numpy 加速）。"""
    im = im.convertToFormat(QImage.Format.Format_ARGB32)
    w, h = im.width(), im.height()
    ptr = im.constBits()
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, im.bytesPerLine()))[:, : w * 4]
    arr = arr.reshape(h, w, 4)
    # BGRA，看三通道是否都接近 255
    mask = arr[:, :, :3].min(axis=2) < thr
    ys, xs = np.where(mask)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def rounded_mask(size: int, dpr: int = 4) -> QImage:
    """4 倍超采样的圆角方形遮罩，边缘更顺滑。"""
    big = size * dpr
    m = QImage(big, big, QImage.Format.Format_ARGB32_Premultiplied)
    m.fill(Qt.transparent)
    p = QPainter(m)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 255))
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, big, big), big * RADIUS, big * RADIUS)
    p.drawPath(path)
    p.end()
    return m.scaled(size, size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)


def unsharp(im: QImage, amount=0.55, radius=1) -> QImage:
    """小尺寸图标补一点锐度，缩到 16/24px 后不至于糊成一团。"""
    im = im.convertToFormat(QImage.Format.Format_ARGB32)
    w, h = im.width(), im.height()
    arr = np.frombuffer(im.constBits(), dtype=np.uint8).reshape((h, im.bytesPerLine()))
    arr = arr[:, : w * 4].reshape(h, w, 4).astype(np.float32)
    rgb = arr[:, :, :3]
    blur = rgb.copy()
    for _ in range(radius):
        p = np.pad(blur, ((1, 1), (1, 1), (0, 0)), mode="edge")
        blur = (p[1:-1, 1:-1] + p[:-2, 1:-1] + p[2:, 1:-1]
                + p[1:-1, :-2] + p[1:-1, 2:]) / 5.0
    out = np.clip(rgb + (rgb - blur) * amount, 0, 255)
    arr[:, :, :3] = out
    buf = arr.astype(np.uint8).tobytes()
    res = QImage(buf, w, h, im.bytesPerLine(), QImage.Format.Format_ARGB32).copy()
    return res


def main():
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
    src = QImage(SRC)
    if src.isNull():
        raise SystemExit("找不到源图: " + SRC)
    x0, y0, x1, y1 = content_bbox(src)
    cw, ch = x1 - x0, y1 - y0
    print(f"画面包围盒 {x0},{y0} - {x1},{y1}  ({cw}×{ch})")

    # 以画面中心裁一个正方形：画面占边长约 86%，四周留白均匀
    side = int(max(cw, ch) * 1.16)
    side = min(side, src.width(), src.height())
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    left = max(0, min(src.width() - side, cx - side // 2))
    top = max(0, min(src.height() - side, cy - side // 2))
    crop = src.copy(left, top, side, side)
    print(f"裁切 {left},{top} 边长 {side}")

    mask_small = {}
    blobs = {}
    for s in SIZES:
        # 小尺寸（任务栏 16/20/24）把画面再放大一点，避免留白吃掉可辨识度
        src_crop = crop
        if s <= 24:
            inset = int(side * 0.05)
            src_crop = crop.copy(inset, inset, side - inset * 2, side - inset * 2)
        # 先缩到 4 倍，再补锐度，最后落到目标尺寸
        sup = src_crop.scaled(s * 4, s * 4, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        if s <= 48:
            sup = unsharp(sup, amount=0.6 if s <= 24 else 0.35)
        im = sup.scaled(s, s, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        im = im.convertToFormat(QImage.Format.Format_ARGB32)
        m = mask_small.get(s) or rounded_mask(s)
        mask_small[s] = m
        out = QImage(s, s, QImage.Format.Format_ARGB32)
        out.fill(Qt.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.drawImage(0, 0, im)
        p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        p.drawImage(0, 0, m)
        p.end()
        path = os.path.join(HERE, f"_ico_{s}.png")
        out.save(path, "PNG")
        blobs[s] = open(path, "rb").read()
        os.remove(path)

    # --- 写 ICO（PNG 压缩条目，Vista+ 支持） ---
    count = len(SIZES)
    header = struct.pack("<HHH", 0, 1, count)
    offset = 6 + 16 * count
    entries, body = b"", b""
    for s in SIZES:
        data = blobs[s]
        dim = 0 if s >= 256 else s
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        body += data
        offset += len(data)
    ico = os.path.join(HERE, "app_icon.ico")
    with open(ico, "wb") as f:
        f.write(header + entries + body)
    print(f"图标: {ico}  {os.path.getsize(ico) // 1024} KB")

    # --- 运行时用的大图 + base64 内联 ---
    png = os.path.join(HERE, "appicon.png")
    with open(png, "wb") as f:
        f.write(blobs[256])
    b64 = base64.b64encode(blobs[256]).decode("ascii")
    lines = [b64[i:i + 96] for i in range(0, len(b64), 96)]
    py = ["# -*- coding: utf-8 -*-",
          '"""U Draw 应用图标（256px PNG 的 base64 内联，由 make_app_icon.py 生成）"""',
          "",
          "ICON_PNG_B64 = (",
          ]
    py += [f'    "{ln}"' for ln in lines]
    py += [")", ""]
    with open(os.path.join(HERE, "appicon_data.py"), "w", encoding="utf-8") as f:
        f.write("\n".join(py))
    print(f"运行时图标: {png}  {os.path.getsize(png) // 1024} KB")
    print(f"内联数据: appicon_data.py  {os.path.getsize(os.path.join(HERE, 'appicon_data.py')) // 1024} KB")

    # 安装向导用的小 logo（Tk 的 subsample 对带 alpha 的 PNG 不靠谱，这里预生成好尺寸）
    for s in (72, 108):
        out = crop.scaled(s * 4, s * 4, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        out = out.scaled(s, s, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).convertToFormat(
            QImage.Format.Format_ARGB32)
        small = QImage(s, s, QImage.Format.Format_ARGB32)
        small.fill(Qt.transparent)
        qp = QPainter(small)
        qp.setRenderHint(QPainter.Antialiasing, True)
        qp.drawImage(0, 0, out)
        qp.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        qp.drawImage(0, 0, rounded_mask(s))
        qp.end()
        small.save(os.path.join(HERE, f"appicon_{s}.png"), "PNG")
    print("安装向导 logo: appicon_72.png / appicon_108.png")
    return ico


if __name__ == "__main__":
    main()
