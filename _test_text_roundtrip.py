# -*- coding: utf-8 -*-
"""文字对象整链路自检：打字 -> 选一个字放大 -> 落字 -> 再点进来编辑 -> 再落字。

关注点：
1. 编辑框尺寸要框得住被放大的那个字（不裁切）
2. 落字后 TextItem 的渲染尺寸和编辑时一致
3. 反复进出编辑框，字号不漂移
"""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, r"C:\Users\20688\Desktop\U Draw Project files\app")

from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtCore import QPointF

app = QApplication([])
import text_tool
from core import Document

ZOOM = 0.45
ok_all = True


def check(name, cond, extra=""):
    global ok_all
    ok_all = ok_all and bool(cond)
    print(("  OK  " if cond else " FAIL ") + name + ("  " + extra if extra else ""))


def overlay_for(doc, it=None, host=None):
    ov = text_tool.TextOverlay(host, QColor("#1e3a3a"))
    base = it.px if it is not None else 48
    ov.setup(QPointF(it.x, it.y) if it is not None else QPointF(200, 300),
             ZOOM, it.family if it is not None else "SimSun", base,
             False, False, QColor("#1e3a3a"), 1.0,
             to_screen=lambda p: QPointF(p.x() * ZOOM, p.y() * ZOOM))
    if it is not None:
        if it.html:
            ov.setHtml(it.html)
            ov.mark_per_char()
        else:
            ov.setPlainText(it.text)
        ov.moveCursor(QTextCursor.MoveOperation.End)
    ov.reposition()
    return ov


doc = Document(1920, 1080, QColor("#ffffff"))
host = QWidget(); host.resize(1400, 900); host.show()

# ---- 第 1 轮：新建文字，把最后一个字放大 ----
ov = overlay_for(doc, None, host)
ov.setPlainText("我发的")
ov.moveCursor(QTextCursor.MoveOperation.End)
# 选中最后一个字
cur = ov.textCursor()
cur.movePosition(QTextCursor.MoveOperation.End)
cur.movePosition(QTextCursor.MoveOperation.Left,
                 QTextCursor.MoveMode.KeepAnchor, 1)
ov.setTextCursor(cur)
ov.set_style(px=214)
geo, need = ov.geometry().height(), ov.document().size().height()
check("编辑框高度框得住放大后的字", geo >= need, f"框 {geo} / 需要 {need:.0f}")

html1 = ov.rich_html()
import re as _re
_sizes = sorted(set(int(m) for m in _re.findall(r"font-size:(\d+)px", html1)))
check("rich_html 存下了每个字的字号", len(_sizes) == 2
      and abs(_sizes[0] - 48) <= 2 and abs(_sizes[1] - 214) <= 2, f"{_sizes}")
check("rich_html 颜色跟文字颜色一致", "#000000" not in html1, html1[:120])
text1 = ov.toPlainText()

from core import TextItem
it = TextItem(text1, 200, 300, "SimSun", 214, html=html1)
it.name = it.auto_name()
doc.add_text(it)
ov.hide(); ov.deleteLater()

# ---- 第 2 轮：再点进来编辑（基准字号 214，里面还有 48px 的小字）----
ov2 = overlay_for(doc, it, host)
geo, need = ov2.geometry().height(), ov2.document().size().height()
check("重新进入编辑：框高度够", geo >= need, f"框 {geo} / 需要 {need:.0f}")
geo_w, need_w = ov2.geometry().width(), ov2.document().size().width()
check("重新进入编辑：框宽度够", geo_w >= need_w, f"框 {geo_w} / 需要 {need_w:.0f}")

# ---- 第 3 轮：落字后 TextItem 的渲染尺寸 ----
r = it.rect()
check("落字后渲染尺寸合理", r.height() >= 90 and r.width() >= 120,
      f"{r.width():.0f}x{r.height():.0f}")

# 把文字画出来，确认最后一行底部有像素（没被切）
from PySide6.QtGui import QImage, QPainter
from PySide6.QtCore import Qt
img = QImage(int(r.width()) + 8, int(r.height()) + 8, QImage.Format_ARGB32)
img.fill(Qt.transparent)
p = QPainter(img)
it.x, it.y = 4, 4
it.draw(p)
p.end()
bottom = max((y for y in range(img.height())
              if any(img.pixelColor(x, y).alpha() > 0 for x in range(0, img.width(), 2))),
             default=-1)
check("大字底部笔画没被裁掉", bottom >= int(r.height()) * 0.7,
      f"最低有像素的行 {bottom} / 总高 {img.height()}")

# ---- 第 4 轮：反复进出编辑框，字号不漂移 ----
size = None
for n in range(4):
    ov3 = overlay_for(doc, it, host)
    h = ov3.rich_html()
    import re
    sizes = sorted(set(int(m) for m in re.findall(r"font-size:(\d+)px", h)))
    if size is None:
        size = sizes
    check(f"第 {n + 2} 次进入编辑字号稳定", sizes == size, f"{sizes}")
    it.html = h
    ov3.hide(); ov3.deleteLater()

print("\n结果:", "全部通过" if ok_all else "有失败项")
