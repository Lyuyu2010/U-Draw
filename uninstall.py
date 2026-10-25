# -*- coding: utf-8 -*-
"""U Draw 卸载逻辑（由 `U Draw.exe --uninstall` 调用）。

为什么放在主程序里：安装包如果把「安装程序自身」复制成 uninstall.exe，
安装目录会白白多出 100MB+。让主程序自己带一个 `--uninstall` 分支，
卸载信息里写 `"U Draw.exe" --uninstall` 就够了。

做的事：
  1. 确认（有窗口时弹确认框；`--silent` 不问）
  2. 删桌面 / 开始菜单快捷方式
  3. 删 HKCU 的卸载注册表项
  4. 延迟删除安装目录：主程序自己就在这个目录里运行，直接删不掉 ——
     写一个 .bat 到临时目录，等本进程退出后由它删目录并自删
"""

import os
import subprocess
import sys
import tempfile
import time
import winreg

APP_NAME = "U Draw"
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\UDraw"
NO_WINDOW = 0x08000000
DETACHED = 0x00000008


def install_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def desktop_lnk() -> str:
    return os.path.join(os.path.expanduser("~"), "Desktop", APP_NAME + ".lnk")


def startmenu_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Microsoft", "Windows", "Start Menu", "Programs", APP_NAME)


def _remove(path: str):
    try:
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path, topdown=False):
                for f in files:
                    try:
                        os.remove(os.path.join(root, f))
                    except OSError:
                        pass
                for d in dirs:
                    try:
                        os.rmdir(os.path.join(root, d))
                    except OSError:
                        pass
            os.rmdir(path)
        elif os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def _schedule_dir_delete(dest: str):
    """写一个 bat：等本进程退出 → 反复尝试删目录 → 自删。

    只删一次往往失败：exe 的句柄要等进程彻底结束才释放。
    """
    bat = os.path.join(tempfile.gettempdir(), "udraw_uninstall_%d.bat" % int(time.time()))
    body = (
        "@echo off\r\n"
        "ping -n 3 127.0.0.1 >nul\r\n"
        "for /L %%i in (1,1,20) do (\r\n"
        '  if not exist "{d}" goto done\r\n'
        '  rd /s /q "{d}" >nul 2>&1\r\n'
        "  ping -n 2 127.0.0.1 >nul\r\n"
        ")\r\n"
        ":done\r\n"
        'del /q "%~f0" >nul 2>&1\r\n'
    ).format(d=dest)
    try:
        with open(bat, "w", encoding="gbk", errors="replace") as f:
            f.write(body)
    except OSError:
        return
    subprocess.Popen(["cmd", "/c", bat],
                     creationflags=NO_WINDOW | DETACHED,
                     close_fds=True)


def main(argv) -> int:
    silent = "--silent" in argv
    dest = install_dir()

    if not silent:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication(argv)
        box = QMessageBox()
        box.setWindowTitle("卸载 %s" % APP_NAME)
        box.setText("确定要卸载 %s 吗？" % APP_NAME)
        box.setInformativeText("安装目录：%s\n\n软件已保存的工程文件（.pcdraw）不会被删除。"
                               % dest)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        box.button(QMessageBox.Yes).setText("卸载")
        box.button(QMessageBox.No).setText("取消")
        if box.exec() != QMessageBox.Yes:
            return 0
        app.processEvents()

    _remove(desktop_lnk())
    _remove(startmenu_dir())
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_KEY)
    except OSError:
        pass

    _schedule_dir_delete(dest)
    if silent:
        print("已卸载：", dest)
    return 0
