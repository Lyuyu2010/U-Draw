# -*- coding: utf-8 -*-
"""U Draw 性能基准（`U Draw.exe --bench 输出.txt`）。

量的是「用户能感觉到的东西」：
  · 一笔下去，每移动一次要多久（笔迹跟不跟手）
  · 图层多了以后合成一次要多久
  · 大画布上的一笔要多久
  · 整块画布重绘一次要多久（缩放 / 平移 / 切窗口时的卡顿）
  · 各种文档规模下的内存占用
  · 存盘 / 读盘耗时与文件大小

所有时间单位毫秒；内存单位 MB（工作集 Working Set）。
"""

import ctypes
import ctypes.wintypes
import gc
import os
import time

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QPainter, QPen


# ---------------------------------------------------------------- 内存
class _PMC(ctypes.Structure):
    _fields_ = [("cb", ctypes.wintypes.DWORD),
                ("PageFaultCount", ctypes.wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t)]


def mem():
    """(工作集 MB, 私有内存 MB, 峰值工作集 MB)

    GetCurrentProcess() 必须声明成 HANDLE：64 位下按默认 c_int 返回会把句柄截断，
    K32GetProcessMemoryInfo 会静默失败返回 0。
    """
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetCurrentProcess.restype = ctypes.wintypes.HANDLE
        k32.K32GetProcessMemoryInfo.argtypes = [ctypes.wintypes.HANDLE,
                                                ctypes.POINTER(_PMC),
                                                ctypes.wintypes.DWORD]
        k32.K32GetProcessMemoryInfo.restype = ctypes.wintypes.BOOL
        pmc = _PMC()
        pmc.cb = ctypes.sizeof(_PMC)
        if not k32.K32GetProcessMemoryInfo(k32.GetCurrentProcess(),
                                           ctypes.byref(pmc), pmc.cb):
            return (0.0, 0.0, 0.0)
        mb = 1024.0 * 1024.0
        return (pmc.WorkingSetSize / mb, pmc.PrivateUsage / mb,
                pmc.PeakWorkingSetSize / mb)
    except Exception:
        return (0.0, 0.0, 0.0)


# ---------------------------------------------------------------- 计时
def ms(fn, n=1, warm=1):
    for _ in range(warm):
        fn()
    t0 = time.perf_counter()
    for _ in range(n):
        fn()
    return (time.perf_counter() - t0) * 1000.0 / n


def make_doc(w, h, layers=1, paint=True):
    """建一个文档；paint=True 时每层画几笔，让图层里有真实内容（存盘更有代表性）。"""
    from core import Document
    doc = Document(w, h, QColor(255, 255, 255, 255))
    for i in range(layers - 1):
        doc.add_layer("L%d" % (i + 1))
        doc.layers[-1].image.fill(QColor(0, 0, 0, 0))
    if paint:
        for i, layer in enumerate(doc.layers[1:], 1):
            p = QPainter(layer.image)
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setPen(QPen(QColor(40 + i * 12 % 200, 60, 90 + i * 7 % 150),
                          max(2, w // 200)))
            for k in range(4):
                y = h * (k + 1) / 5.0
                p.drawLine(int(w * 0.08), int(y),
                           int(w * 0.9), int(y + (i % 3) * 20 - 20))
            p.end()
            layer.touch()
    doc.recompose()
    return doc


def stroke_cost(doc, size, moves=40, hardness=0.6):
    """画一笔：返回「每次移动平均多少毫秒」（含局部合成）。"""
    from core import Brush, Stroke
    layer = doc.layers[-1]
    br = Brush(size=size, hardness=hardness)
    # 先画一小笔热身：第一笔要建笔刷纹理缓存，不热身第一次的数字会翻十倍
    warm = Stroke(doc, layer, br, QColor(30, 30, 30))
    warm.begin(QPointF(10, 10), 0.9)
    warm.move(QPointF(60, 40), 0.9)
    warm.end()

    st = Stroke(doc, layer, br, QColor(30, 30, 30))
    st.begin(QPointF(40, 40), 0.9)
    step = max(2, int(doc.w / (moves + 1)))
    t0 = time.perf_counter()
    for i in range(moves):
        st.move(QPointF(40 + step * (i + 1), 40 + (i % 7) * 12), 0.9)
    dt = (time.perf_counter() - t0) * 1000.0 / moves
    st.end()
    return dt


def mem_of(w, h, layers):
    """建一个这么大的文档，量工作集涨了多少，然后释放。"""
    gc.collect()
    base = mem()[0]
    doc = make_doc(w, h, layers)
    gc.collect()
    used = mem()[0]
    del doc
    gc.collect()
    return round(used - base, 1)


def run(out_path):
    import main as app_main
    from main_window import MainWindow
    import brushes

    lines = []

    def put(k, v):
        lines.append("%s=%s" % (k, v))

    app = app_main.QApplication.instance() or app_main.QApplication([])
    import theme
    theme.apply_theme(app)

    # ---- 1. 主窗口（用户看到的「打开软件」）----
    t0 = time.perf_counter()
    win = MainWindow()
    win.resize(1440, 900)
    win.show()
    app.processEvents()
    put("startup_window_ms", round((time.perf_counter() - t0) * 1000, 1))
    put("mem_idle_ws", round(mem()[0], 1))
    put("mem_idle_priv", round(mem()[1], 1))

    canvas = win.canvas
    doc = win.doc
    doc.layers[0].image.fill(QColor(255, 255, 255, 255))
    doc.recompose()
    app.processEvents()

    # ---- 2. 整块画布重绘（缩放 / 平移 / 切文档时的卡顿来源）----
    put("canvas_px", "%dx%d" % (canvas.width(), canvas.height()))
    put("repaint_ms", round(ms(lambda: canvas.grab(), n=6), 1))

    # ---- 3. 笔迹跟手度：不同笔径，每移动一次多少毫秒 ----
    for size in (8, 60, 150, 300):
        put("stroke_%dpx_ms" % size, round(stroke_cost(doc, size), 2))
    app.processEvents()

    # ---- 3b. 整帧：笔迹 + 局部合成 + 画布重绘（用户真正感觉到的那一下）----
    try:
        from PySide6.QtCore import Qt
        named = {b.name: b for b in brushes.DEFAULTS}
        c = win.canvas
        c.tool = "brush"
        c.set_zoom(1.0)
        for pen_name in ("G 笔", "素描铅笔"):
            c.brush = named[pen_name].copy()
            c.brush.size = 8
            # 热身一笔
            c.pointer_down(QPointF(60, 60), 0.9, Qt.LeftButton, Qt.NoModifier)
            for i in range(6):
                c.pointer_move(QPointF(60 + i * 20, 70), 0.9)
            c.pointer_up()
            app.processEvents()

            c.pointer_down(QPointF(60, 60), 0.9, Qt.LeftButton, Qt.NoModifier)
            t0 = time.perf_counter()
            n = 24
            for i in range(n):
                c.pointer_move(QPointF(60 + i * 18, 70 + (i % 5) * 4), 0.9)
                c.repaint()          # 同步重绘：把「画」这一步也算进来
            dt = (time.perf_counter() - t0) * 1000.0 / n
            c.pointer_up()
            app.processEvents()
            put("frame_%s_8px_ms" % ("pen" if pen_name == "G 笔" else "pencil"), round(dt, 2))
    except Exception as e:      # noqa: BLE001
        put("frame_error", repr(e))

    # ---- 4. 图层越多，合成越慢 ----
    d10 = make_doc(1600, 1200, 10)
    d40 = make_doc(1600, 1200, 40)
    put("recompose_10layer_ms", round(ms(d10.recompose, n=4), 1))
    put("recompose_40layer_ms", round(ms(d40.recompose, n=4), 1))
    put("stroke_60px_10layer_ms", round(stroke_cost(d10, 60), 2))
    put("stroke_60px_40layer_ms", round(stroke_cost(d40, 60), 2))
    put("stroke_8px_40layer_ms", round(stroke_cost(d40, 8), 2))
    del d40
    gc.collect()

    # ---- 5. 大画布 ----
    d4k = make_doc(4000, 3000, 3)
    put("bigcanvas_recompose_ms", round(ms(d4k.recompose, n=4), 1))
    put("bigcanvas_stroke_60px_ms", round(stroke_cost(d4k, 60), 2))
    put("bigcanvas_stroke_300px_ms", round(stroke_cost(d4k, 300), 2))
    del d4k
    gc.collect()

    # ---- 6. 存盘 / 读盘 ----
    from core import load_project, save_project
    tmp = out_path + "_bench.pcdraw"
    save_ms = ms(lambda d=d10: save_project(d, tmp), n=3)
    size_mb = os.path.getsize(tmp) / (1024.0 * 1024.0)
    load_ms = ms(lambda: load_project(tmp), n=3)
    put("save_1600x1200x10layer_ms", round(save_ms, 1))
    put("load_1600x1200x10layer_ms", round(load_ms, 1))
    put("project_file_mb", round(size_mb, 2))
    try:
        os.remove(tmp)
    except OSError:
        pass

    # ---- 7. 内存：不同文档规模各占多少（每次测完释放，互不叠加）----
    put("docmem_1600x1200x1_mb", mem_of(1600, 1200, 1))
    put("docmem_1600x1200x10_mb", mem_of(1600, 1200, 10))
    put("docmem_2480x3508x10_mb", mem_of(2480, 3508, 10))       # A4 300dpi
    put("docmem_4000x3000x10_mb", mem_of(4000, 3000, 10))
    del d10
    gc.collect()

    ws, priv, peak = mem()
    put("mem_final_ws", round(ws, 1))
    put("mem_final_priv", round(priv, 1))
    put("mem_peak_ws", round(peak, 1))
    put("brushes", len(brushes.DEFAULTS))

    win._force_close = True
    win.close()

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return 0
