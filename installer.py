# -*- coding: utf-8 -*-
"""U Draw 安装程序（安装 / 卸载二合一）。

打包：见 build_installer.py —— 会把 U Draw.exe 作为数据文件塞进本程序，
所以用户拿到的是**一个 setup.exe**，双击即可安装。

安装做的事：
  1. 把 U Draw.exe 复制到安装目录（默认 %LOCALAPPDATA%\\Programs\\U Draw）
  2. 把本程序复制成 <安装目录>\\uninstall.exe，供「应用和功能」卸载
  3. 建桌面 / 开始菜单快捷方式（可选）
  4. 写 HKCU 卸载项（显示在 Windows「应用和功能」里，带版本、图标、大小）

卸载（uninstall.exe 或 setup.exe --uninstall）：
  删快捷方式 → 删注册表项 → 延迟删除安装目录（自己正在里面运行，得等它退出）

命令行（给自动化测试用）：
  setup.exe --silent --dir="D:\\path" [--no-desktop] [--no-startmenu] [--no-run]
  setup.exe --uninstall --silent
"""

import os
import shutil
import subprocess
import sys
import winreg

APP_NAME = "U Draw"
try:                       # build_installer.py 打包前写进来，避免版本号两处维护
    from installer_version import APP_VERSION
except Exception:          # noqa: BLE001
    APP_VERSION = "0.0.0"
PUBLISHER = "宇"
EXE_NAME = "U Draw.exe"
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\UDraw"

# 和主程序同一套配色，安装界面不至于像另一个软件
BG = "#252525"
CARD = "#2E2E2E"
TEXT = "#E6E6E6"
DIM = "#9A9A9A"
FAINT = "#6E6E6E"
ACCENT = "#3C8CE7"
BORDER = "#3A3A3A"

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


# ----------------------------------------------------------------- 路径
def default_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Programs", APP_NAME)


PAYLOAD = "payload.zip"


def payload_path() -> str:
    """被安装的目录版程序打成的 zip：打包后在 _MEIPASS，开发时在 app 目录。"""
    here = getattr(sys, "_MEIPASS", None)
    if here:
        p = os.path.join(here, PAYLOAD)
        if os.path.isfile(p):
            return p
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), PAYLOAD)


def desktop_dir() -> str:
    return os.path.join(os.path.expanduser("~"), "Desktop")


def startmenu_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Microsoft", "Windows", "Start Menu", "Programs", APP_NAME)


def _shortcut(lnk: str, target: str, workdir: str):
    """用 WScript.Shell 建 .lnk（不依赖 pywin32）。"""
    os.makedirs(os.path.dirname(lnk), exist_ok=True)
    ps = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
        "$s.TargetPath='{t}';$s.WorkingDirectory='{w}';"
        "$s.IconLocation='{t},0';$s.Description='{n}';$s.Save()"
    ).format(lnk=lnk.replace("'", "''"), t=target.replace("'", "''"),
             w=workdir.replace("'", "''"), n=APP_NAME)
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                   creationflags=NO_WINDOW, check=False)


def _remove(path: str):
    try:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


# ----------------------------------------------------------------- 安装 / 卸载
def install(dest: str, desktop=True, startmenu=True, progress=None):
    src = payload_path()
    if not os.path.isfile(src):
        raise FileNotFoundError("安装包内缺少程序文件（%s）" % PAYLOAD)

    def step(msg):
        if progress:
            progress(msg)

    step("正在创建安装目录…")
    os.makedirs(dest, exist_ok=True)

    # 目录版：把 zip 里的 U Draw.exe + _internal 整棵解出来
    step("正在解压程序文件（约 180MB）…")
    import zipfile
    with zipfile.ZipFile(src) as z:
        names = z.namelist()
        total = max(1, len(names))
        for i, name in enumerate(names):
            z.extract(name, dest)
            if i % 200 == 0:
                step("正在解压程序文件… %d%%" % (i * 100 // total))
    target = os.path.join(dest, EXE_NAME)
    if not os.path.isfile(target):
        raise FileNotFoundError("解压后没找到 %s" % EXE_NAME)
    step("程序文件就位…")

    # 卸载不单独放程序：主程序自带 --uninstall（见 app/uninstall.py），
    # 这样安装目录不会白多出一个 100MB+ 的 uninstall.exe。

    if desktop:
        step("正在创建桌面快捷方式…")
        _shortcut(os.path.join(desktop_dir(), APP_NAME + ".lnk"), target, dest)
    if startmenu:
        step("正在创建开始菜单项…")
        _shortcut(os.path.join(startmenu_dir(), APP_NAME + ".lnk"), target, dest)

    step("正在登记卸载信息…")
    size_kb = 0
    for root, _dirs, files in os.walk(dest):
        for f in files:
            try:
                size_kb += os.path.getsize(os.path.join(root, f)) // 1024
            except OSError:
                pass
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
        winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
        winreg.SetValueEx(k, "Publisher", 0, winreg.REG_SZ, PUBLISHER)
        winreg.SetValueEx(k, "DisplayIcon", 0, winreg.REG_SZ, target)
        winreg.SetValueEx(k, "InstallLocation", 0, winreg.REG_SZ, dest)
        winreg.SetValueEx(k, "UninstallString", 0, winreg.REG_SZ,
                          '"%s" --uninstall' % target)
        winreg.SetValueEx(k, "QuietUninstallString", 0, winreg.REG_SZ,
                          '"%s" --uninstall --silent' % target)
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, max(1, size_kb))
    return target


def uninstall(dest: str, silent=False):
    """卸载：交给安装目录里的主程序（它带 --uninstall，见 uninstall.py）。"""
    exe = os.path.join(dest, EXE_NAME)
    if os.path.isfile(exe):
        cmd = [exe, "--uninstall"] + (["--silent"] if silent else [])
        subprocess.Popen(cmd, creationflags=NO_WINDOW)
        return
    _remove(os.path.join(desktop_dir(), APP_NAME + ".lnk"))
    _remove(startmenu_dir())
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_KEY)
    except OSError:
        pass
    _remove(dest)


# ----------------------------------------------------------------- GUI
def run_gui():
    from PySide6.QtCore import Qt, QThread, Signal
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import (QApplication, QCheckBox, QFileDialog, QFrame,
                                   QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                                   QPushButton, QVBoxLayout, QWidget)

    class Worker(QThread):
        tick = Signal(str)
        done = Signal(bool, str)

        def __init__(self, dest, desk, menu):
            super().__init__()
            self.dest, self.desk, self.menu = dest, desk, menu

        def run(self):
            try:
                install(self.dest, self.desk, self.menu, progress=self.tick.emit)
                self.done.emit(True, self.dest)
            except Exception as e:      # noqa: BLE001
                self.done.emit(False, str(e))

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    win = QWidget()
    win.setWindowTitle("%s 安装程序" % APP_NAME)
    win.setFixedSize(520, 348)
    win.setStyleSheet(f"""
        QWidget {{ background: {BG}; color: {TEXT};
                   font-family: "Microsoft YaHei UI", "Microsoft YaHei"; }}
        QLabel {{ background: transparent; }}
        QLineEdit {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 4px;
                     padding: 5px 8px; color: {TEXT}; font-size: 12px; }}
        QLineEdit:focus {{ border-color: {ACCENT}; }}
        QCheckBox {{ font-size: 12px; color: {DIM}; spacing: 8px; }}
        QCheckBox::indicator {{ width: 14px; height: 14px; border-radius: 3px;
                                border: 1px solid {BORDER}; background: {CARD}; }}
        QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
        QPushButton {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 4px;
                       padding: 6px 18px; color: {TEXT}; font-size: 12px; }}
        QPushButton:hover {{ background: #383838; }}
        QPushButton#primary {{ background: {ACCENT}; border-color: {ACCENT}; color: #FFFFFF;
                               font-weight: 600; }}
        QPushButton#primary:hover {{ background: #4C99F0; }}
        QPushButton:disabled {{ color: {FAINT}; background: #2A2A2A; border-color: #333; }}
    """)

    lay = QVBoxLayout(win)
    lay.setContentsMargins(24, 20, 24, 18)
    lay.setSpacing(14)

    head = QHBoxLayout()
    head.setSpacing(14)
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    icon_path = ""
    for name in ("app.ico", "app_icon.ico"):   # build_installer 打进来的是后者
        if os.path.isfile(os.path.join(base, name)):
            icon_path = os.path.join(base, name)
            break
    if icon_path and os.path.isfile(icon_path):
        ico = QLabel()
        ico.setPixmap(QIcon(icon_path).pixmap(44, 44))
        ico.setFixedSize(44, 44)
        head.addWidget(ico, 0, Qt.AlignTop)
    col = QVBoxLayout()
    col.setSpacing(3)
    t = QLabel("%s  %s" % (APP_NAME, APP_VERSION))
    t.setStyleSheet(f"font-size: 17px; font-weight: 600; color: {TEXT};")
    s = QLabel("Windows 平台轻量级数字绘画软件　·　无需安装运行库，装完即用")
    s.setStyleSheet(f"font-size: 11px; color: {FAINT};")
    col.addWidget(t)
    col.addWidget(s)
    head.addLayout(col, 1)
    lay.addLayout(head)

    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {BORDER};")
    lay.addWidget(line)

    lay.addWidget(QLabel("安装位置"))
    row = QHBoxLayout()
    row.setSpacing(8)
    path = QLineEdit(default_dir())
    row.addWidget(path, 1)
    browse = QPushButton("浏览…")
    browse.setFixedWidth(74)
    row.addWidget(browse)
    lay.addLayout(row)

    desk = QCheckBox("创建桌面快捷方式")
    desk.setChecked(True)
    menu = QCheckBox("创建开始菜单项")
    menu.setChecked(True)
    run_after = QCheckBox("安装完成后立即运行")
    run_after.setChecked(True)
    opts = QHBoxLayout()
    opts.setSpacing(18)
    opts.addWidget(desk)
    opts.addWidget(menu)
    opts.addWidget(run_after)
    opts.addStretch(1)
    lay.addLayout(opts)

    status = QLabel("准备就绪，点击「开始安装」。")
    status.setStyleSheet(f"font-size: 11px; color: {DIM};")
    lay.addWidget(status)
    lay.addStretch(1)

    bottom = QHBoxLayout()
    bottom.addStretch(1)
    cancel = QPushButton("取消")
    cancel.setFixedWidth(88)
    go = QPushButton("开始安装")
    go.setObjectName("primary")
    go.setFixedWidth(104)
    bottom.addWidget(cancel)
    bottom.addWidget(go)
    lay.addLayout(bottom)

    state = {"busy": False, "worker": None}

    def choose():
        d = QFileDialog.getExistingDirectory(win, "选择安装位置", path.text())
        if d:
            path.setText(os.path.join(d, APP_NAME))

    def finish(ok, info):
        state["busy"] = False
        go.setEnabled(True)
        cancel.setText("关闭")
        if not ok:
            status.setText("安装失败。")
            QMessageBox.warning(win, "安装失败", str(info))
            return
        status.setText("安装完成。程序已安装到 %s" % info)
        go.setText("完成")
        if run_after.isChecked():
            try:
                subprocess.Popen([os.path.join(info, EXE_NAME)], cwd=info)
            except OSError:
                pass
            win.close()

    def start():
        if state["busy"]:
            return
        dest = path.text().strip() or default_dir()
        state["busy"] = True
        go.setEnabled(False)
        cancel.setText("取消")
        status.setText("正在安装…")
        w = Worker(dest, desk.isChecked(), menu.isChecked())
        w.tick.connect(status.setText)
        w.done.connect(finish)
        state["worker"] = w
        w.start()

    browse.clicked.connect(choose)
    go.clicked.connect(lambda: (win.close() if go.text() == "完成" else start()))
    cancel.clicked.connect(win.close)

    win.show()
    return app.exec()


# ----------------------------------------------------------------- 入口
def main(argv):
    args = [a for a in argv[1:]]
    silent = "--silent" in args
    do_uninstall = "--uninstall" in args
    dest = default_dir()
    for a in args:
        if a.startswith("--dir="):
            dest = a.split("=", 1)[1].strip('"')

    if do_uninstall:
        uninstall(dest, silent)
        return 0

    if silent:
        install(dest, desktop="--no-desktop" not in args,
                startmenu="--no-startmenu" not in args,
                progress=(lambda m: print(m)))
        print("已安装到", dest)
        return 0

    return run_gui()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
