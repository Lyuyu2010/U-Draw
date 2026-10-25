# -*- coding: utf-8 -*-
"""打包安装包：U Draw Setup <版本>.exe

流程：
  1. 确认主程序 exe 已构建（没有就先跑 build_exe.py）
  2. 用 PyInstaller 把 installer.py 打成单文件，并把主程序 exe + 图标作为数据带进去
  3. 输出到上级目录

用法：  python build_installer.py [--rebuild-app]
"""

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.dirname(HERE)
APP_DIR = os.path.join(OUT_DIR, "U Draw")          # 目录版产物
APP_EXE = os.path.join(APP_DIR, "U Draw.exe")
PAYLOAD = os.path.join(HERE, "payload.zip")


def app_version() -> str:
    src = open(os.path.join(HERE, "main_window.py"), encoding="utf-8").read()
    m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', src)
    return m.group(1) if m else "0.0.0"


def main():
    if "--rebuild-app" in sys.argv or not os.path.isfile(APP_EXE):
        print("先构建主程序…")
        r = subprocess.run([sys.executable, os.path.join(HERE, "build_exe.py")], cwd=HERE)
        if r.returncode != 0:
            return r.returncode
    total = 0
    for root, _dirs, files in os.walk(APP_DIR):
        for f in files:
            total += os.path.getsize(os.path.join(root, f))
    print("主程序目录:", APP_DIR, "%.0f MB" % (total / 1024 / 1024))

    # 打成一个 zip 塞进安装程序：安装时解出来就是 U Draw.exe + _internal
    import zipfile
    print("压缩程序文件 →", PAYLOAD)
    if os.path.isfile(PAYLOAD):
        os.remove(PAYLOAD)
    with zipfile.ZipFile(PAYLOAD, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for root, _dirs, files in os.walk(APP_DIR):
            for f in files:
                full = os.path.join(root, f)
                z.write(full, os.path.relpath(full, APP_DIR))
    print("payload.zip: %.0f MB" % (os.path.getsize(PAYLOAD) / 1024 / 1024))

    ver = app_version()
    with open(os.path.join(HERE, "installer_version.py"), "w", encoding="utf-8") as f:
        f.write("# -*- coding: utf-8 -*-\n"
                '"""构建时自动生成，勿手改。"""\n'
                'APP_VERSION = "%s"\n' % ver)
    name = "U Draw Setup %s" % ver
    ico = os.path.join(HERE, "app.ico")
    if not os.path.isfile(ico):
        import make_app_icon
        ico = os.path.abspath(make_app_icon.main())

    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onefile", "--windowed",
        "--name", name,
        "--icon", ico,
        "--distpath", OUT_DIR,
        "--workpath", os.path.join(HERE, "_build_inst"),
        "--specpath", os.path.join(HERE, "_build_inst"),
        # 安装程序只用 QtWidgets，其余全排掉，别把体积撑起来
        "--exclude-module", "PySide6.QtQml",
        "--exclude-module", "PySide6.QtQuick",
        "--exclude-module", "PySide6.QtQuickWidgets",
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.QtWebEngineWidgets",
        "--exclude-module", "PySide6.QtMultimedia",
        "--exclude-module", "PySide6.QtSql",
        "--exclude-module", "PySide6.QtTest",
        "--exclude-module", "PySide6.QtPdf",
        "--exclude-module", "PySide6.QtCharts",
        "--exclude-module", "PySide6.QtNetwork",
        "--exclude-module", "PySide6.QtOpenGL",
        "--exclude-module", "PySide6.QtOpenGLWidgets",
        "--exclude-module", "PySide6.QtDBus",
        "--exclude-module", "tkinter",
        "--exclude-module", "unittest",
        "--exclude-module", "numpy",
        # 主程序作为数据塞进去（安装时原样复制出去）
        "--add-data", PAYLOAD + ";.",
        "--add-data", ico + ";.",
        os.path.join(HERE, "installer.py"),
    ]
    print(" ".join(args))
    r = subprocess.run(args, cwd=HERE)
    if r.returncode != 0:
        return r.returncode
    out = os.path.join(OUT_DIR, name + ".exe")
    print("\n安装包完成:", out, os.path.getsize(out) // (1024 * 1024), "MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
