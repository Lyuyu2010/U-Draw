# -*- coding: utf-8 -*-
"""打包脚本：生成多尺寸 ico，再用 PyInstaller 打成**目录版**（onedir）。

为什么不用单文件版：单文件版每次启动都要把约 172MB 解到 %TEMP%，
启动要 3 秒左右，被强杀还会留垃圾。目录版直接跑，启动 0.6 秒左右。

用法：  python build_exe.py
输出：  上级目录 U Draw/U Draw.exe  +  U Draw/_internal/...
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.dirname(HERE)
APP_EXE = "U Draw.exe"


def main():
    # 可选参数：输出目录（默认上级目录）。exe 正在运行时先打到别处再替换。
    out_dir = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else OUT_DIR

    # 切到目录版之后，根目录里那个单文件 exe 就是旧产物了
    legacy = os.path.join(out_dir, APP_EXE)
    if os.path.isfile(legacy):
        try:
            os.remove(legacy)
            print("已删除旧的单文件 exe:", APP_EXE)
        except OSError:
            print("旧单文件 exe 正在运行，删不掉（关掉软件后重跑一次）")

    # 上次「软件正开着」时替换 exe 会留下一个 _old_locked 文件，这里顺手清掉
    for junk in ("U Draw_old_locked.exe", "U Draw.old.exe"):
        path = os.path.join(out_dir, junk)
        if os.path.isfile(path):
            try:
                os.remove(path)
                print("已清理旧 exe:", junk)
            except OSError:
                print("旧 exe 还在运行，暂时删不掉:", junk)

    # 图标由 make_app_icon.py 从 IMG_20261022_194513.png 生成（多尺寸 ico + 内联 png）
    import make_app_icon
    ico = os.path.abspath(make_app_icon.main())
    print("icon:", ico, os.path.getsize(ico), "bytes")

    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onedir", "--windowed",
        "--name", "U Draw",
        "--icon", ico,
        "--version-file", os.path.join(HERE, "version_info.txt"),
        "--distpath", out_dir,
        "--workpath", os.path.join(HERE, "_build"),
        "--specpath", os.path.join(HERE, "_build"),
        "--exclude-module", "PySide6.QtQml",
        "--exclude-module", "PySide6.QtQuick",
        "--exclude-module", "PySide6.QtQuickWidgets",
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.QtWebEngineWidgets",
        "--exclude-module", "PySide6.QtMultimedia",
        "--exclude-module", "PySide6.QtMultimediaWidgets",
        "--exclude-module", "PySide6.QtSql",
        "--exclude-module", "PySide6.QtTest",
        "--exclude-module", "PySide6.QtPdf",
        "--exclude-module", "PySide6.QtCharts",
        "--exclude-module", "PySide6.Qt3DCore",
        "--exclude-module", "PySide6.QtDataVisualization",
        "--exclude-module", "tkinter",
        "--exclude-module", "unittest",
        # sponsor_data 是在函数里 import 的（点「赞助」时才会用到），
        # 说明显写进来，别指望静态分析一定扫得到
        "--hidden-import", "sponsor_data",
        os.path.join(HERE, "main.py"),
    ]
    # Qt 自带的中文翻译（输入框右键菜单、文件框等）要跟着打进包里，
    # 否则单文件 exe 里 QLibraryInfo 指向的目录是空的
    import PySide6
    tr_dir = os.path.join(os.path.dirname(PySide6.__file__), "translations")
    data = []
    for name in ("qtbase_zh_CN.qm", "qt_zh_CN.qm"):
        f = os.path.join(tr_dir, name)
        if os.path.isfile(f):
            data += ["--add-data", f + ";PySide6/translations"]

    # 内置笔刷缩略图：预生成，避免启动/滚动时逐支实时渲染
    thumb_dir = os.path.join(HERE, "brush_thumbs")
    if os.path.isdir(thumb_dir):
        data += ["--add-data", thumb_dir + ";brush_thumbs"]
        print("brush_thumbs:", len([f for f in os.listdir(thumb_dir) if f.endswith(".png")]), "个")
    popup_dir = os.path.join(HERE, "brush_thumbs_popup")
    if os.path.isdir(popup_dir):
        data += ["--add-data", popup_dir + ";brush_thumbs_popup"]
        print("brush_thumbs_popup:", len([f for f in os.listdir(popup_dir) if f.endswith(".png")]), "个")

    # 文字库：内置字体（原版 PhotoCraft 自带的那几套 OFL 字体）
    font_dir = os.path.join(HERE, "assets", "fonts")
    if os.path.isdir(font_dir):
        data += ["--add-data", font_dir + ";assets/fonts"]
        print("fonts:", len([f for f in os.listdir(font_dir) if f.lower().endswith((".ttf", ".otf"))]),
              "个")
    args[-1:-1] = data

    print(" ".join(args))
    r = subprocess.run(args, cwd=HERE)
    if r.returncode != 0:
        return r.returncode
    exe = os.path.join(out_dir, "U Draw", APP_EXE)
    if not os.path.isfile(exe):
        print("没找到产物:", exe)
        return 1
    total = 0
    for root, _dirs, files in os.walk(os.path.dirname(exe)):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    print("\n构建完成:", exe)
    print("目录大小: %.0f MB（含 _internal）" % (total / 1024 / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
