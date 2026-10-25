# -*- coding: utf-8 -*-
"""安装包端到端验证：静默安装 → 检查文件/注册表 → 卸载 → 检查清理干净。

不动真实桌面和开始菜单（--no-desktop --no-startmenu），
快捷方式单独在临时目录里验证 _shortcut()。
"""
import os
import subprocess
import sys
import tempfile
import time
import winreg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SETUP = os.path.join(ROOT, "U Draw Setup 2.15.41.exe")
REG = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\UDraw"

ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("  OK  " if cond else " FAIL ") + name + ("  " + extra if extra else ""))


def reg_value(name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


dest = os.path.join(tempfile.gettempdir(), "udraw_install_test")
if os.path.isdir(dest):
    for root, dirs, files in os.walk(dest, topdown=False):
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
    try:
        os.rmdir(dest)
    except OSError:
        pass

print("安装到:", dest)
r = subprocess.run([SETUP, "--silent", '--dir=%s' % dest,
                    "--no-desktop", "--no-startmenu"],
                   capture_output=True, timeout=300)
check("静默安装返回 0", r.returncode == 0, r.stderr.decode("utf-8", "ignore")[-200:])

exe = os.path.join(dest, "U Draw.exe")
check("主程序已就位", os.path.isfile(exe),
      "%.0f MB" % (os.path.getsize(exe) / 1024 / 1024) if os.path.isfile(exe) else "缺失")
check("安装目录是目录版（U Draw.exe + _internal）",
      os.path.isdir(dest)
      and sorted(os.listdir(dest)) == ["U Draw.exe", "_internal"],
      str(sorted(os.listdir(dest)) if os.path.isdir(dest) else "-"))
check("_internal 里有解释器",
      os.path.isfile(os.path.join(dest, "_internal", "python313.dll")))
check("注册表有 DisplayName", reg_value("DisplayName") == "U Draw", str(reg_value("DisplayName")))
check("注册表版本正确", reg_value("DisplayVersion") == "2.15.41", str(reg_value("DisplayVersion")))
check("卸载命令指向主程序 --uninstall",
      (reg_value("UninstallString") or "").lower().endswith('u draw.exe" --uninstall'),
      str(reg_value("UninstallString")))
check("注册表记录了安装位置", reg_value("InstallLocation") == dest)

sys.path.insert(0, HERE)
import installer as ins  # noqa: E402

lnk = os.path.join(tempfile.gettempdir(), "udraw_lnk_test", "U Draw.lnk")
ins._shortcut(lnk, exe, dest)
check("能创建 .lnk 快捷方式", os.path.isfile(lnk),
      "%d bytes" % os.path.getsize(lnk) if os.path.isfile(lnk) else "没建出来")

print("卸载…")
subprocess.run([exe, "--uninstall", "--silent"], timeout=180, check=False)
gone = False
for _ in range(40):
    if not os.path.isdir(dest):
        gone = True
        break
    time.sleep(0.5)
check("卸载后安装目录已删除", gone)
check("卸载后注册表项已删除", reg_value("DisplayName") is None)

try:
    os.remove(lnk)
    os.rmdir(os.path.dirname(lnk))
except OSError:
    pass

print("\n结果:", "全部通过" if ok else "有失败项")
sys.exit(0 if ok else 1)

