# -*- coding: utf-8 -*-
"""U Draw - 程序入口"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

import theme
from main_window import APP_NAME, MainWindow


class _TooltipGuard(QObject):
    """启动头一秒内不弹提示气泡。

    窗口打开时正好在鼠标底下，Qt 会在 0.7 秒后弹出「鼠标下那个控件」的提示气泡 ——
    看起来就像「先弹一个小窗，然后软件才打开」。这里直接吃掉这段时间的 ToolTip 事件。
    """

    def eventFilter(self, obj, ev):
        return ev.type() == QEvent.ToolTip


def app_icon() -> QIcon:
    """应用图标：make_app_icon.py 生成的 256px 圆角 PNG，base64 内联在代码里。"""
    import base64
    from appicon_data import ICON_PNG_B64
    pm = QPixmap()
    pm.loadFromData(base64.b64decode(ICON_PNG_B64), "PNG")
    return QIcon(pm)


def dark_title_bar(win):
    """Windows 10/11 深色标题栏，让原生边框和内部深色界面统一。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = int(win.winId())
        value = ctypes.c_int(1)
        for attr in (20, 19):          # DWMWA_USE_IMMERSIVE_DARK_MODE
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attr, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass


def run_check(out_path: str) -> int:
    """打包自检：确认 numpy / 填充 / 图层 / 存取 / 内嵌图片在 exe 内可用。"""
    import base64
    import struct
    import time
    from PySide6.QtGui import QColor
    from core import Document, flood_fill, load_project, save_project

    lines = []
    t0 = time.time()
    doc = Document(900, 700, QColor(255, 255, 255, 255))
    doc.add_layer("测试层")
    edit = flood_fill(doc, 20, 20, QColor(220, 40, 40))
    dt = time.time() - t0
    import sys as _s
    lines.append("numpy=%s" % ("bundled" if "numpy" in _s.modules else "fallback"))
    lines.append("fill=%.3fs changed=%s" % (dt, edit is not None))
    lines.append("layer_px=%s" % doc.composite.pixelColor(30, 30).name())
    tmp = out_path + ".pcdraw"
    save_project(doc, tmp)
    d2 = load_project(tmp)
    lines.append("roundtrip_layers=%d" % len(d2.layers))

    # 收款码是点「赞助」时才 import 的，单文件包里最容易漏 —— 这里直接验一遍
    import sponsor_data
    for key in ("WECHAT", "ALIPAY"):
        blob = base64.b64decode(getattr(sponsor_data, "QR_%s_PNG_B64" % key))
        ok = blob[:8] == b"\x89PNG\r\n\x1a\n"
        w = h = 0
        if ok and len(blob) > 24:
            w, h = struct.unpack(">II", blob[16:24])
        lines.append("qr_%s=%dx%d %dKB png=%s" % (key.lower(), w, h, len(blob) // 1024, ok))

    import about_dialogs
    lines.append("dialogs=%s" % bool(about_dialogs.AboutDialog and about_dialogs.SponsorDialog))

    # Qt 自带中文包 + 自绘弹窗能建出来（单文件包里最容易漏这两样）
    from PySide6.QtWidgets import QApplication as _QApp
    _app = _QApp.instance() or _QApp([])
    lines.append("zh_translator=%s" % bool(install_qt_chinese(_app)))
    import dialogs as _dlg
    _d = _dlg.MessageDialog(None, "自检", "对话框模块可用",
                            [("close", "知道了", "primary")])
    lines.append("message_dialog=%dx%d" % (_d.width(), _d.height()))

    # ---- 新功能：对称 / 涂抹 / 文字 / 文字库 ----
    from PySide6.QtCore import QPointF as _P
    from PySide6.QtCore import QRect as _R
    from core import Brush as _Brush, SmudgeStroke, new_symmetry, symmetry_targets
    sym = new_symmetry(400, 300)
    sym["mode"] = "radial"
    sym["count"] = 6
    lines.append("sym_radial=%d" % len(symmetry_targets(sym, 10, 10)))
    sym["mode"] = "quad"
    lines.append("sym_quad=%d" % len(symmetry_targets(sym, 10, 10)))

    d3 = Document(120, 120, QColor(255, 255, 255, 255))
    _p = QPainter(d3.layers[0].image)
    _p.fillRect(_R(40, 40, 40, 40), QColor(200, 20, 20))
    _p.end()
    d3.recompose()
    sm = SmudgeStroke(d3, d3.layers[0], _Brush(size=30, hardness=0.5), 0.6, None)
    sm.begin(_P(60, 60), 1.0)
    sm.move(_P(95, 95), 1.0)
    _ed = sm.end()
    lines.append("smudge=%s px=%s" % (bool(_ed),
                                      d3.layers[0].image.pixelColor(95, 95).name()))

    import fonts as _fonts
    import text_tool as _text
    _ents = _fonts.entries()
    lines.append("fonts=%d bundled=%d" % (len(_ents),
                                          sum(1 for e in _ents if e["bundled"])))
    d4 = Document(360, 140, QColor(255, 255, 255, 255))
    _r = _text.draw_text(d4.layers[0].image, "U Draw 文字", _P(12, 12),
                         _fonts.default_family(), 44, True, False,
                         QColor(0, 0, 0), "left")
    lines.append("text=%s %dx%d" % (not _r.isEmpty(), _r.width(), _r.height()))

    # ---- v2.1.1：背景层固定 / 图层组按钮 / 文字独立层 / 最近使用 / 触摸板 ----
    from core import MoveOp as _MoveOp
    d5 = Document(160, 120, QColor(255, 255, 255, 255))
    d5.add_layer("L")
    _p = QPainter(d5.layers[1].image)
    _p.fillRect(_R(120, 40, 35, 35), QColor(240, 30, 30))
    _p.end()
    d5.layers[1].touch()
    d5.recompose()
    bg = d5.bg_layer
    pinned = (bg is not None and d5.layers[0] is bg
              and d5.move_layer(0, 1) is False)
    _mv = _MoveOp(d5, d5.layers[1])
    d5.push(_mv.finish(60, 0))
    d5.recompose()
    _mv2 = _MoveOp(d5, d5.layers[1])
    d5.push(_mv2.finish(-60, 0))
    d5.recompose()
    back = d5.layers[1].image.pixelColor(140, 50).red() > 200
    lines.append("bg_pin=%s move_restore=%s lost=%s" % (pinned, back, _mv.lost))

    from panels import LayersPanel as _LP, RecentStore as _RS
    _lp = _LP()
    lines.append("layer_buttons=%d ungroup=%s" % (
        len(getattr(_lp, "tb", {})), "ungroup" in getattr(_lp, "tb", {})))

    d6 = Document(200, 120, QColor(255, 255, 255, 255))
    from canvas import Canvas as _Canvas
    _c = _Canvas(d6)
    _c.resize(300, 200)
    _c.text_size = 40
    _n0 = len(d6.layers)
    _c._begin_text(_c.doc_to_screen(_P(20, 30)))
    _c.text_overlay().setPlainText("自检")
    _c.commit_text()
    lines.append("text_obj=%d no_layer=%s name=%s" % (
        len(d6.texts), len(d6.layers) == _n0,
        d6.texts[0].name[:8] if d6.texts else "-"))
    # 再点同一处 = 继续编辑，而不是新建
    _it = d6.texts[0]
    _c._begin_text(_c.doc_to_screen(_P(_it.x + 4, _it.y + 8)))
    lines.append("text_reedit=%s" % (_c._edit_index == 0))
    _c.cancel_text()

    from main_window import MainWindow as _MW
    _blank = _MW.make_blank_doc(120, 90, QColor(255, 255, 255, 255))
    lines.append("bg_lock=%s auto_layer=%s" % (_blank.layers[0].locked,
                                               len(_blank.layers) == 2))

    # v2.2.0：工作区可拖 + 色板放大 + 面板自带滚动
    from panels import Section as _Sec, SwatchGrid as _SG
    _sg = _SG()
    lines.append("splits=%d swatch=%dx%d/%dpx section_scroll=%s" % (
        len(_MW.SPLIT_KEYS), _sg.COLS, _sg.ROWS, _sg.height(),
        getattr(_Sec("x", None, scroll=True), "_scroll", None) is not None))

    # v2.3.0：缩放跟随鼠标 + 铺满画布的色块吸附
    _c.set_zoom(1.0)
    _hp = _P(90, 70)
    _c._hover_pos = _hp
    _b4 = _c.screen_to_doc(_hp)
    _c.zoom_step(True)
    _af = _c.screen_to_doc(_hp)
    lines.append("zoom_anchor=%s (%.2f,%.2f)" % (
        abs(_af.x() - _b4.x()) < 1.5 and abs(_af.y() - _b4.y()) < 1.5,
        _af.x() - _b4.x(), _af.y() - _b4.y()))

    from brushes import DEFAULTS as _BD
    lines.append("brushes=%d" % len(_BD))

    _d8 = Document(120, 90, QColor(255, 255, 255, 255))
    _f8 = _d8.add_layer("色块")
    _p8 = QPainter(_f8.image)
    _p8.fillRect(_R(0, 0, 120, 90), QColor(20, 120, 200))
    _p8.end()
    _f8.touch()
    _mo = _MoveOp(_d8, _f8)
    _mo.finish(4, -3)
    lines.append("snap=%s/%s" % (_mo.snap, _mo.snapped))

    _st = _RS("color/recent_selftest", 4)
    _st.save([])
    _st.push(_st.load(), "#336699")
    lines.append("recent=%s" % ("#336699" in _st.load()))

    import psd_export as _psd
    _d7 = Document(80, 60, QColor(255, 255, 255, 255))
    _d7.add_layer("层 2")
    _psd_path = out_path + ".psd"
    _n = _psd.export_psd(_d7, _psd_path)
    with open(_psd_path, "rb") as _f:
        _sig = _f.read(4)
    lines.append("psd=%dKB sig=%s" % (_n // 1024, _sig.decode("latin-1")))

    _c.symmetry["mode"] = "vertical"
    _c.symmetry["guides"] = True
    _hit = _c._sym_handle_hit(_c.doc_to_screen(
        _P(_c.symmetry["cx"], _c.symmetry["cy"])))
    from PySide6.QtGui import QWheelEvent as _WEv
    from PySide6.QtCore import QPoint as _Pt
    _ox = _c.ox
    _c.wheelEvent(_WEv(_P(100, 100), _P(100, 100), _Pt(10, 0), _Pt(0, 0),
                       Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False))
    lines.append("sym_drag_hit=%s trackpad_pan=%s" % (_hit, _c.ox != _ox))

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    # 自检模式没有事件循环，函数返回时局部 Qt 对象会被析构，打包版里这一步
    # 偶尔会直接崩（0xC0000409 / exit 1）。结果文件已经落盘，直接退出最稳。
    # 注意别在这里 flush 标准输出：--windowed 打包后 sys.stdout 是 None。
    os._exit(0)


def install_qt_chinese(app):
    """给 Qt 自带的零碎界面装中文：输入框右键菜单、文件框、滚动条提示……

    自己的弹窗（dialogs.py）本来就是中文，不依赖这个；但 QLineEdit 的
    「剪切 / 复制 / 粘贴」是 Qt 自己拼的，不装翻译包就是英文。
    找不到 qtbase_zh_CN.qm 时静默跳过，不影响使用。
    """
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
    base = getattr(sys, "_MEIPASS", None)
    cands = [QLibraryInfo.path(QLibraryInfo.TranslationsPath)]
    if base:
        cands.append(os.path.join(base, "PySide6", "translations"))
        cands.append(os.path.join(base, "translations"))
    tr = QTranslator(app)
    for p in cands:
        if p and os.path.isdir(p) and tr.load(
                QLocale(QLocale.Chinese, QLocale.China), "qtbase", "_", p):
            app.installTranslator(tr)
            return tr
    return None


def project_arg() -> str:
    """命令行里带的项目文件（双击 .pcdraw 时 Windows 会把它当参数传进来）。"""
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--check", "--screenshot"):     # 这两个后面还跟一个值
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        if os.path.isfile(a):
            return a
        i += 1
    return ""


# ---------------------------------------------------------------- 单实例
# 双击工程文件时 Windows 会再启动一份程序；已经有窗口在跑就把文件转给它，
# 不然同一个项目会被两份程序同时打开、互相覆盖。
SERVER_NAME = "UDraw.SingleInstance"


def forward_to_running(path: str) -> bool:
    try:
        from PySide6.QtNetwork import QLocalSocket
        s = QLocalSocket()
        s.connectToServer(SERVER_NAME)
        if not s.waitForConnected(250):
            return False
        s.write((path or "").encode("utf-8"))
        s.flush()
        s.waitForBytesWritten(250)
        s.disconnectFromServer()
        return True
    except Exception:
        return False


class SingleInstance:
    """监听本地管道：第二份程序启动时把文件路径发过来。"""

    def __init__(self, win):
        self.win = win
        self.srv = None
        try:
            from PySide6.QtNetwork import QLocalServer
            QLocalServer.removeServer(SERVER_NAME)     # 上次崩溃留下的残根
            self.srv = QLocalServer(win)
            self.srv.newConnection.connect(self._on_conn)
            self.srv.listen(SERVER_NAME)
        except Exception:
            self.srv = None

    def _on_conn(self):
        try:
            c = self.srv.nextPendingConnection()
            c.readyRead.connect(lambda: self._read(c))
        except Exception:
            pass

    def _read(self, c):
        try:
            path = bytes(c.readAll()).decode("utf-8", "ignore").strip()
        except Exception:
            path = ""
        self.win.raise_()
        self.win.activateWindow()
        if path and os.path.isfile(path):
            self.win.open_project_file(path)


def _debug_log(message):
    path = os.environ.get("UDRAW_DEBUG_LOG")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(message + "\n")
    except OSError:
        pass


def cleanup_stale_meipass():
    """删掉上次被强杀 / 崩溃留下的临时解包目录。

    单文件包每次启动都要把约 170MB 解到 %TEMP%\\_MEIxxxx，正常退出会自动清理；
    但被任务管理器结束、蓝屏、断电之后就会留下，日积月累能占几个 GB。
    只删「带我们自己的资源目录 + 超过 10 分钟没动」的那些，别人的 _MEI 不碰。
    """
    import shutil
    import tempfile
    import time as _t
    try:
        meipass = getattr(sys, "_MEIPASS", None)
        root = tempfile.gettempdir()
        now = _t.time()
        for name in os.listdir(root):
            if not name.startswith("_MEI"):
                continue
            path = os.path.join(root, name)
            if meipass and os.path.abspath(path) == os.path.abspath(meipass):
                continue
            if not os.path.isdir(path):
                continue
            try:
                if now - os.path.getmtime(path) < 600:
                    continue          # 可能是别的程序刚解出来的，别碰
                inner = os.listdir(path)
                # 我们的包里一定有这两样（笔刷缩略图 + 字体资源）
                if "brush_thumbs" not in inner or "assets" not in inner:
                    continue
                shutil.rmtree(path, ignore_errors=True)
            except OSError:
                continue
    except Exception:
        pass


def _start_cleanup():
    import threading
    threading.Thread(target=cleanup_stale_meipass, daemon=True).start()


def main():
    global SERVER_NAME
    _debug_log("argv=" + repr(sys.argv))
    # 源码试用使用独立单实例管道，避免被旧版 EXE 抢走；不终止旧窗口。
    if "--source" in sys.argv:
        SERVER_NAME += "-source-brush-library"
    if "--check" in sys.argv:
        i = sys.argv.index("--check")
        out = sys.argv[i + 1] if len(sys.argv) > i + 1 else "check.txt"
        return run_check(out)

    # 从 Windows「应用和功能」卸载：走安装包里写的 UninstallString
    # （"U Draw.exe" --uninstall），不需要单独塞一个 100MB 的卸载程序。
    if "--uninstall" in sys.argv:
        import uninstall
        return uninstall.main(sys.argv)

    # 性能基准（发布前测机器要求用）
    if "--bench" in sys.argv:
        i = sys.argv.index("--bench")
        out = sys.argv[i + 1] if len(sys.argv) > i + 1 else "bench.txt"
        import bench
        return bench.run(out)

    target = project_arg()
    _debug_log("target=" + repr(target))
    if forward_to_running(target):
        _debug_log("forwarded-to-running")
        return 0            # 已经有窗口了：文件交给它打开，这份直接退出

    _start_cleanup()        # 后台清掉上次强杀留下的临时解包目录（不挡启动）

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName("U Draw")
    # 任务栏 / 窗口标题一律显示 "U Draw"（不是可执行文件名）
    QGuiApplication.setDesktopFileName(APP_NAME)
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("UDraw.Paint")
    except Exception:
        pass
    install_qt_chinese(app)
    theme.apply_theme(app)
    app.setWindowIcon(app_icon())

    # 启动期间屏蔽提示气泡：窗口正好开在鼠标底下，Qt 会弹「鼠标下那个控件」的提示，
    # 看起来就像「先弹个小窗，然后软件才打开」。要在建窗口之前就装上 ——
    # 构造过程中也可能触发。1.5 秒后自动撤掉。

    _guard = _TooltipGuard()
    app.installEventFilter(_guard)
    QTimer.singleShot(1500, lambda: app.removeEventFilter(_guard))

    win = MainWindow()
    _debug_log("main-window-created")
    win.setWindowIcon(app_icon())
    if "--brush-demo" in sys.argv:
        from brush_demo import populate_window
        populate_window(win)
    win.show()
    dark_title_bar(win)
    win._single = SingleInstance(win)      # 保住引用，否则监听会被回收

    ready_path = os.environ.get("UDRAW_READY_FILE")
    if ready_path:
        def report_ready():
            import json
            import brushes
            try:
                with open(ready_path, "w", encoding="utf-8") as f:
                    json.dump({"pid": os.getpid(), "visible": win.isVisible(),
                               "platform": QGuiApplication.platformName(),
                               "title": win.windowTitle(),
                               "source_directory": HERE,
                               "brush_count": len(win.brush_panel.presets),
                               "recent_count": len(win.brush_panel.recent_presets()),
                               "settings_file": brushes.user_file()}, f, ensure_ascii=False, indent=2)
            except OSError:
                pass
        QTimer.singleShot(700, report_ready)

    if target:
        QTimer.singleShot(0, lambda: win.open_project_file(target))

    shot = None
    for i, a in enumerate(sys.argv):
        if a == "--screenshot" and i + 1 < len(sys.argv):
            shot = sys.argv[i + 1]
    if shot:
        def grab():
            pm = win.grab()
            ok = pm.save(shot)
            _debug_log("grab=%s visible=%s null=%s save=%s path=%s" % (
                pm.width(), win.isVisible(), pm.isNull(), ok, shot))
            app.quit()
        QTimer.singleShot(600, grab)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
