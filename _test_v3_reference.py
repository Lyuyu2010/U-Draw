# -*- coding: utf-8 -*-
"""v3.0 S2：参考图窗口

验：载入 / 适配 / 以光标为中心缩放 / 图片透明度（只作用在图上，窗口本体不透明）/
翻转 / 锁定 / 置顶 / 悬浮提示 / 设置记忆 / 主窗口入口。
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

app = QApplication([])
import theme

theme.apply_theme(app)
from main_window import MainWindow
from reference_window import BTN_TIPS, ReferenceWindow

ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("  OK  " if cond else " FAIL ") + name + ("  " + str(extra) if extra else ""))


# 造一张左右两半不同色的测试图
src = QImage(200, 100, QImage.Format_ARGB32)
src.fill(QColor(220, 40, 40))
p = QPainter(src)
p.fillRect(100, 0, 100, 100, QColor(40, 60, 220))
p.end()
tmp = os.path.join(tempfile.gettempdir(), "_udraw_v3_ref.png")
src.save(tmp, "PNG")

bad = os.path.join(tempfile.gettempdir(), "_udraw_v3_ref.txt")
with open(bad, "w", encoding="utf-8") as f:
    f.write("not an image")

w = ReferenceWindow()
w.resize(420, 400)
w.show()
app.processEvents()

check("新建时没有图", w.has_image() is False)
check("读不出图片时返回 False", w.load(bad) is False)
check("读失败不会把窗口弄坏", w.has_image() is False)
check("载入图片成功", w.load(tmp) is True)
check("图片已就位", w.has_image() and w.image().width() == 200)
app.processEvents()

# 适配：按图片区实际大小算
vw, vh = w.view.width(), w.view.height()
expect = min(vw / 200.0, vh / 100.0)
check("适配窗口后缩放正确", abs(w.zoom - expect) < 0.02,
      f"{w.zoom:.3f}（期望 {expect:.3f}）")
check("适配后水平居中", abs(w.ox - (vw - 200 * w.zoom) / 2.0) < 0.6, f"{w.ox:.1f}")
check("适配后垂直居中", abs(w.oy - (vh - 100 * w.zoom) / 2.0) < 0.6, f"{w.oy:.1f}")

# 以光标为中心缩放：光标下那个像素必须原地不动
pos = QPointF(120.0, 60.0)
dx_before = (pos.x() - w.ox) / w.zoom
dy_before = (pos.y() - w.oy) / w.zoom
z_before = w.zoom
w.zoom_at(pos, 1.12)
dx_after = (pos.x() - w.ox) / w.zoom
dy_after = (pos.y() - w.oy) / w.zoom
check("滚轮放大生效", w.zoom > z_before + 1e-6, f"{z_before:.2f} → {w.zoom:.2f}")
check("光标下的像素没跑", abs(dx_after - dx_before) < 0.02
      and abs(dy_after - dy_before) < 0.02,
      f"({dx_before:.2f},{dy_before:.2f}) → ({dx_after:.2f},{dy_after:.2f})")
check("手动缩放后不再自动适配", w.fit is False)
w.fit_window()
check("适配按钮把缩放复位", w.fit is True and abs(w.zoom - expect) < 0.02)

# 透明度：只作用在图片上，窗口本体保持不透明（这是「UI 不一致」的修法）
check("窗口本体不透明", abs(w.windowOpacity() - 1.0) < 1e-6, f"{w.windowOpacity():.2f}")
w.set_alpha(0.45)
check("图片透明度生效", abs(w.alpha - 0.45) < 1e-6, f"{w.alpha:.2f}")
check("滑杆跟着动", w.alpha_slider.value() == 45, w.alpha_slider.value())
check("百分比文字跟着动", "45%" in w.alpha_label.text(), w.alpha_label.text())
w.set_alpha(0.001)
check("透明度有下限（不能调到看不见）", w.alpha >= 0.049, f"{w.alpha:.3f}")
w.set_alpha(0.8)

# 滑杆拖到 30% → alpha 0.3（自由调节）
w.alpha_slider.setValue(30)
check("拖滑杆能改透明度", abs(w.alpha - 0.30) < 1e-6, f"{w.alpha:.2f}")

# 翻转：左右像素真的换了位置
before_left = w.shown_image().pixelColor(0, 50)
w.toggle_flip()
check("翻转后左边缘变成原来的右边缘",
      w.shown_image().pixelColor(0, 50) == src.pixelColor(199, 50)
      and w.shown_image().pixelColor(199, 50) == before_left,
      f"{w.shown_image().pixelColor(0, 50).name()}")
w.toggle_flip()
check("再翻一次回到原样", w.shown_image().pixelColor(0, 50) == src.pixelColor(0, 50))

# 悬浮提示：六个按钮都要有
check("六个按钮都在（置顶已按要求移除）",
      set(w.buttons) == {"load", "clear", "fit", "flip", "lock", "close"},
      sorted(w.buttons))
check("没有置顶按钮", "pin" not in w.buttons)
check("有清空参考图的按钮", "clear" in w.buttons)
missing = [k for k, b in w.buttons.items() if not b.toolTip().strip()]
check("每个按钮都有悬浮提示", not missing, missing)
check("提示文案不为空", all(BTN_TIPS[k] for k in BTN_TIPS), "")

# 锁定：锁上之后不能再缩放；图标要变成「红色上锁」
icon_before = w.b_lock.icon().pixmap(14, 14).toImage()
w.toggle_lock()
icon_after = w.b_lock.icon().pixmap(14, 14).toImage()
check("锁定按钮生效", w.locked is True)
check("锁定后图标变了（红色上锁）", icon_before != icon_after)
z_lock = w.zoom
w.zoom_at(QPointF(100, 50), 1.5)
check("锁定后滚轮缩放无效", abs(w.zoom - z_lock) < 1e-9, f"{w.zoom:.3f}")
w.toggle_lock()
check("再点一次解锁", w.locked is False)
check("解锁后图标变回开锁",
      w.b_lock.icon().pixmap(14, 14).toImage() == icon_before)

# 清空参考图
w.load(tmp)
w.fit_window()
w.zoom_at(QPointF(50, 50), 2.0)
check("清空前有图", w.has_image() is True)
w.clear()
check("清空后没有图", w.has_image() is False)
check("清空把缩放也复位了", abs(w.zoom - 1.0) < 1e-6 and w.fit is True, w.zoom)
w.load(tmp)

# 键盘 / 数位板快捷键（ApplicationShortcut：画布有焦点时也要生效）
sc = [a.shortcut().toString() for a in w._key_actions]
check("快捷键齐了", set(sc) == {"Alt+=", "Alt++", "Alt+-", "Alt+0", "Alt+Left",
                                "Alt+Right", "Alt+Up", "Alt+Down"}, sc)
check("快捷键是应用级（画布有焦点也能用）",
      all(a.shortcutContext() == Qt.ApplicationShortcut for a in w._key_actions))

w.fit_window()
z0 = w.zoom
w._key_zoom(True)
check("Alt+= 能放大", w.zoom > z0 + 1e-6, f"{z0:.2f} → {w.zoom:.2f}")
w._key_zoom(False)
check("Alt+- 能缩小回来", abs(w.zoom - z0) < 1e-6, f"{w.zoom:.2f}")
ox0 = w.ox
w._key_pan(1, 0)
check("Alt+右 能平移", abs(w.ox - ox0) > 1.0, f"{ox0:.1f} → {w.ox:.1f}")
w._key_pan(-1, 0)
check("Alt+左 能平移回来", abs(w.ox - ox0) < 1e-6, f"{w.ox:.1f}")

# 标题栏 / 底栏必须自带不透明底色（不能靠父窗口透明合成）
check("标题栏有自己的底色", w.title_bar.objectName() == "refTop", w.title_bar.objectName())
check("底栏有自己的底色", w.bottom.objectName() == "refBottom", w.bottom.objectName())
check("样式表里写死了深色底", "#323232" in w.styleSheet().lower(), w.styleSheet()[:60])

# 设置记忆
w.set_alpha(0.6)
w.toggle_lock()
w._save()
w2 = ReferenceWindow()
check("重开窗口记住透明度", abs(w2.alpha - 0.6) < 0.02, f"{w2.alpha:.2f}")
check("重开窗口记住锁定状态", w2.locked is True)
w2.toggle_lock()
w2.close()

# 主窗口入口
win = MainWindow()
win.resize(1100, 760)
win.show()
app.processEvents()
win.open_reference()
app.processEvents()
check("视图菜单能打开参考图窗口", win._refwin is not None and win._refwin.isVisible())
first = win._refwin
win.open_reference()
app.processEvents()
check("再点一次不会开第二个", win._refwin is first)
check("参考图窗口是独立顶层窗口", win._refwin.isWindow() is True)
# ---------------------------------------------------------------- 缩放快捷键路由
# 规则：Ctrl+= / Ctrl+- / Ctrl+0 / Ctrl+1 作用在「最后点击的那个窗口」上。
w3 = win._refwin
w3.show()
app.processEvents()
w3.load(tmp)
w3.fit_window()
app.processEvents()

check("默认缩放目标是画布", win._zoom_target == "canvas", win._zoom_target)
cz, rz = win.canvas.zoom, w3.zoom
win.zoom_step(True)
app.processEvents()
check("默认时放大作用在画布", win.canvas.zoom > cz + 1e-6, f"{cz:.3f}→{win.canvas.zoom:.3f}")
check("默认时参考图不动", abs(w3.zoom - rz) < 1e-9, w3.zoom)

w3.activated.emit()                 # 等价于「点了参考图窗口里任何一处」
app.processEvents()
check("点过参考图后目标切到参考图", win._zoom_target == "ref", win._zoom_target)
cz, rz = win.canvas.zoom, w3.zoom
win.zoom_step(True)
app.processEvents()
check("此时放大作用在参考图", w3.zoom > rz + 1e-6, f"{rz:.3f}→{w3.zoom:.3f}")
check("此时画布不动", abs(win.canvas.zoom - cz) < 1e-9, win.canvas.zoom)

win.zoom_step(False)
app.processEvents()
check("缩小也作用在参考图", abs(w3.zoom - rz) < 1e-6, f"{w3.zoom:.3f}")

win.zoom_fit()
app.processEvents()
check("Ctrl+0 作用在参考图（适配）", w3.fit is True)
win.zoom_100()
app.processEvents()
check("Ctrl+1 作用在参考图（100%）", abs(w3.zoom - 1.0) < 1e-6, f"{w3.zoom:.3f}")

win.canvas.canvasTouched.emit()     # 等价于「点回画布」
app.processEvents()
check("点回画布后目标切回画布", win._zoom_target == "canvas", win._zoom_target)

# 键盘缩放要跟着鼠标，不是死盯中心
w3._view_pos = QPointF(90.0, 120.0)
bx = (w3._view_pos.x() - w3.ox) / w3.zoom
by = (w3._view_pos.y() - w3.oy) / w3.zoom
w3.zoom_step(True)
ax = (w3._view_pos.x() - w3.ox) / w3.zoom
ay = (w3._view_pos.y() - w3.oy) / w3.zoom
check("键盘缩放以鼠标位置为锚点", abs(ax - bx) < 0.02 and abs(ay - by) < 0.02,
      f"({bx:.2f},{by:.2f}) → ({ax:.2f},{ay:.2f})")

# 锁定只挡误操作，键盘缩放照常
w3.toggle_lock()
z_lock = w3.zoom
w3.zoom_step(True)
app.processEvents()
check("锁定后键盘缩放仍然有效", w3.zoom > z_lock + 1e-6, f"{z_lock:.3f}→{w3.zoom:.3f}")
w3.toggle_lock()

win._refwin.close()
app.processEvents()
check("关掉参考图后目标回到画布", win._zoom_target == "canvas", win._zoom_target)
check("关掉之后实例还在（下次直接复用）", win._refwin is first)

os.remove(tmp)
os.remove(bad)

print("\n结果:", "全部通过" if ok else "有失败项")
sys.exit(0 if ok else 1)
