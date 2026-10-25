# -*- coding: utf-8 -*-
"""U Draw - 文字工具：画布上的就地编辑框 + 把文字画进图层

交互：选文字工具 → 在画布上点一下 → 出现虚线文本框直接打字 →
Enter = 换行；Esc / Ctrl+Enter / 点画布别处 / 切工具 = 落字到图层。
顶部选项栏的 ✓ / ✗ 可手动确认或取消。
"""

from html import escape as html_escape
import re

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFontMetricsF, QPainter, QPen,
                           QTextBlockFormat, QTextCharFormat, QTextCursor,
                           QTextFormat, QTextOption)
from PySide6.QtWidgets import QApplication, QTextEdit, QWidget

import fonts as fontlib

PAD = 2          # 编辑框内边距（屏幕像素）


def _scale_html(html: str, k: float) -> str:
    """把 HTML 里的 font-size:Npx 按 k 缩放。

    html 里存的是**文档坐标**的字号；编辑框里要用屏幕像素（文档 × 缩放）。
    不缩放的话，45% 缩放下点开编辑框，字会按 100% 显示 —— 看着「放大很多」，
    而且框是按屏幕尺寸算的，超出的部分直接被切掉（显示不全）。
    """
    if not html or abs(k - 1.0) < 1e-3:
        return html

    def rep(m):
        return "font-size:%dpx" % max(1, int(round(int(m.group(1)) * k)))

    return re.sub(r"font-size:(\d+)px", rep, html)


class TextOverlay(QTextEdit):
    """跟着画布缩放走的就地文字编辑框。"""

    committed = Signal(str)
    cancelled = Signal()

    def __init__(self, parent: QWidget, color: QColor):
        super().__init__(parent)
        self._color = QColor(color)
        self._doc_anchor = QPointF(0, 0)     # 文档坐标里的左上角
        self._zoom = 1.0
        self._px = 48.0
        self._family = fontlib.default_family()
        self._bold = False
        self._italic = False
        self._gap = 1.0
        self._closing = False
        self._ime_composing = False   # 中文输入法正在选词：这时回车/esc 不能落字
        self._hold = False        # 打开调色板时临时按住，别因为失焦就把字落下去
        self._to_screen = None
        # 只要用户按选区改过样式（颜色/字号/粗斜），这段文字就要按富文本存
        self._per_char = False
        # 点选项栏调字体 / 字号时不要落字：只有焦点跑出这个「保留区」才提交
        self.keep_parent = None

        self.setFrameShape(QTextEdit.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setLineWrapMode(QTextEdit.NoWrap)
        self.setAcceptRichText(False)
        # 虚线框用样式表画：viewport 是子控件，自己在 paintEvent 里画边框会被盖掉
        self.setStyleSheet(
            "QTextEdit { background: transparent; border: 1px dashed "
            "rgba(255,255,255,150); }")
        self.document().setDocumentMargin(0)
        opt = QTextOption()
        opt.setWrapMode(QTextOption.NoWrap)
        self.document().setDefaultTextOption(opt)
        self._apply_font()

    # ---------------------------------------------------------- 参数
    def setup(self, anchor: QPointF, zoom: float, family: str, px: float,
              bold: bool, italic: bool, color: QColor, gap: float = 1.0,
              to_screen=None):
        self._doc_anchor = QPointF(anchor)
        self._zoom = max(0.02, zoom)
        self._family = family
        self._px = px
        self._bold = bold
        self._italic = italic
        self._gap = gap
        self._color = QColor(color)
        self._to_screen = to_screen
        self._apply_font()
        self.reposition()
        self.setFocus()

    def _font(self):
        """按当前 family / 字号 / 缩放算出一个 QFont（不依赖控件自身的字体）。"""
        return fontlib.make_font(self._family, self._px * self._zoom,
                                 self._bold, self._italic)

    def _restyle(self):
        # 全局样式表里有 `* { font-size: 12px }` / `QWidget { color: ... }`，
        # 它们会盖掉 setFont() 和调色板，结果框里的字永远是 12px 的灰字
        # （就是「字体 / 颜色都没有实时预览」）。控件自己的样式表优先级更高，
        # 所以 family、字号、颜色都在这里写死。
        self.setStyleSheet(
            "QTextEdit { background: transparent; border: 1px dashed "
            "rgba(255,255,255,150);"
            f' font-family: "{self._family}";'
            f" font-size: {max(1, int(round(self._px * self._zoom)))}px;"
            f" color: {self._color.name()}; }}")

    def _apply_font(self):
        f = self._font()
        self._restyle()
        self.document().setDefaultFont(f)
        fmt = QTextCharFormat()
        fmt.setFont(f)
        # 显式把「像素字号」写死：有些字体的 pointSize / 行高特别大，
        # 换字体时 Qt 会按字体自己的度量去排版，框里的字看着一下子变大、
        # 行距也被撑开 —— 预览就和落字后的效果对不上了。
        fmt.setProperty(QTextFormat.Property.FontPixelSize,
                        float(max(1, int(round(self._px * self._zoom)))))
        cur = QTextCursor(self.document())
        if self.has_selection():
            # 有选中就只改选中的那几个字（PS 的用法）
            cur = self.textCursor()
            self._per_char = True
        else:
            cur.select(QTextCursor.SelectionType.Document)
        cur.mergeCharFormat(fmt)
        self.setCurrentCharFormat(fmt)      # 接着输入的字也用新字体
        self._apply_line_height()
        self._apply_color_fmt()
        self.viewport().update()

    def _apply_line_height(self):
        """行高至少按字号算，但不能比字体自己的行高更矮。

        只按「字号 × 1.25」写死（FixedHeight）会把度量偏高的字体切掉下半截
        （笔画「一半不显示」），所以取「字号 × 1.25」和字体实际行高的较大值。
        """
        f = self._font()
        # 一段文字里可能只有几个字被放大过：行高要按**最大的那个字**算，
        # 否则大字的上下会被裁掉（「显示不全」）。
        # 单位要统一：fragment 里的 FontPixelSize 是**屏幕像素**（setHtml 时
        # 已按 zoom 缩放过），而 self._px 是文档坐标的字号 —— 先把 fragment
        # 换回文档坐标再一起乘 zoom。之前直接拿屏幕像素去乘 zoom，
        # 字号被放大过的字行高只算到 45%，那个字就被切成一半。
        zoom = max(0.02, self._zoom)
        px = float(self._px)
        blk = self.document().begin()
        while blk.isValid():
            it = blk.begin()
            while not it.atEnd():
                fr = it.fragment()
                if fr.isValid():
                    cf = fr.charFormat()
                    v = cf.property(QTextFormat.Property.FontPixelSize)
                    if v is None:
                        v = cf.font().pixelSize()
                    try:
                        v = float(v)
                    except (TypeError, ValueError):
                        v = 0.0
                    if v > 0:
                        px = max(px, v / zoom)
                it += 1
            blk = blk.next()
        need = max(px * zoom * 1.25, QFontMetricsF(f).height())
        bf = QTextBlockFormat()
        # 用 MinimumHeight 而不是 FixedHeight：只保证「至少这么高」，
        # 字体或某个放大过的字需要更多空间时让它自己撑开 —— FixedHeight 会切字。
        bf.setLineHeight(max(1, int(round(need))),
                         QTextBlockFormat.LineHeightTypes.MinimumHeight.value)
        cur = QTextCursor(self.document())
        cur.select(QTextCursor.SelectionType.Document)
        cur.mergeBlockFormat(bf)

    def _apply_color_fmt(self):
        """把颜色写进字符格式：QTextEdit 里 QSS 的 color 不一定盖得住已有文字。"""
        fmt = QTextCharFormat()
        fmt.setForeground(QBrush(self._color))
        cur = QTextCursor(self.document())
        if self.has_selection():
            cur = self.textCursor()
            self._per_char = True
        else:
            cur.select(QTextCursor.SelectionType.Document)
        cur.mergeCharFormat(fmt)
        self.textCursor().mergeCharFormat(fmt)      # 后面接着输入的字同色
        self.setPalette(self._palette_for(self._color))
        self.viewport().update()

    def _palette_for(self, color: QColor):
        pal = self.palette()
        pal.setColor(pal.ColorRole.Text, QColor(color))
        return pal

    def set_color(self, color: QColor):
        self._color = QColor(color)
        self._restyle()          # 颜色要写进控件样式表才盖得住全局的 QWidget { color }
        self._apply_color_fmt()

    # ---- 局部（按选中文字）改样式 -------------------------------------
    def has_selection(self) -> bool:
        return self.textCursor().hasSelection()

    def mark_per_char(self):
        self._per_char = True

    def _mark_per_char(self):
        """只要按选区改过一次样式，这段文字就要按富文本存（html）。"""
        if self.has_selection():
            self._per_char = True

    def rich_html(self) -> str:
        """把当前内容导出成极简 HTML（只在用户按选区改过样式时才用）。

        自己拼 HTML 而不是用 toHtml()：后者会带一堆 background-color / 行高，
        画到画布上会多出一块白底。
        """
        if not self._per_char:
            return ""
        out = []
        block = self.document().begin()
        while block.isValid():
            frags = []
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid() and frag.text():
                    cf = frag.charFormat()
                    font = cf.font()
                    col = cf.foreground().color() if cf.foreground().style() else self._color
                    fam = font.family() or self._family
                    px = font.pixelSize() if font.pixelSize() > 0 else int(round(self._px))
                    # 存**文档坐标**的字号（除以缩放）：这样落字后按文档尺度渲染是对的，
                    # 再点进来编辑时按当前缩放还原成屏幕像素
                    px = max(1, int(round(px / max(0.02, self._zoom))))
                    frags.append(
                        '<span style="font-family:%s;font-size:%dpx;color:%s;%s%s">%s</span>'
                        % (fam, px, col.name(),
                           "font-weight:bold;" if font.bold() else "",
                           "font-style:italic;" if font.italic() else "",
                           html_escape(frag.text())))
                it += 1
            out.append('<p style="margin:0;">%s</p>' % ("".join(frags) or "&nbsp;"))
            block = block.next()
        return "<html><body>%s</body></html>" % "".join(out)

    def hold(self, on: bool):
        """临时屏蔽「失焦即落字」（打开调色板这类模态窗口时用）。"""
        self._hold = bool(on)

    def set_style(self, family=None, px=None, bold=None, italic=None, gap=None):
        if family is not None:
            self._family = family
        if px is not None:
            self._px = px
        if bold is not None:
            self._bold = bold
        if italic is not None:
            self._italic = italic
        if gap is not None:
            self._gap = gap
        self._apply_font()
        self.reposition()

    def set_zoom(self, zoom: float):
        self._zoom = max(0.02, zoom)
        self._apply_font()
        self.reposition()

    def setPlainText(self, text: str):
        super().setPlainText(text)
        # 新建的空文档里还没有块格式：设完文字要补一次行高，否则第一眼
        # 和后面改字体时的行距会差一截。
        self._apply_line_height()
        # setPlainText 会把字符格式重置成「默认黑」：不补这一下，整段同色的文字
        # 在框里靠 QSS 的 color 显示是对的，但一落字（存成 html）就变成黑色了。
        self._apply_color_fmt()

    def setHtml(self, html: str):
        super().setHtml(_scale_html(html, self._zoom))
        self._apply_line_height()

    def doc_anchor(self) -> QPointF:
        return QPointF(self._doc_anchor)

    # ---------------------------------------------------------- 几何
    def screen_rect(self) -> QRectF:
        """编辑框在画布控件里的矩形（跟着文字长度自动变宽变高）。"""
        # 用算出来的字体量，不用 self.font()：后者会被全局样式表改成 12px
        fm = QFontMetricsF(self._font())
        lines = self.toPlainText().split("\n")
        w = 0.0
        for line in lines:
            w = max(w, fm.horizontalAdvance(line))
        h = fm.height() * max(1, len(lines))
        # 再用文档自己的排版宽度兜一层：horizontalAdvance 会低估连字 / 回退字体的宽度，
        # 宽度不够时最后几个字就被框切掉了（「预览莫名其妙少一截」就是这么来的）。
        w = max(w, self.document().idealWidth(), fm.horizontalAdvance("文字"))
        # 关键兜底：上面两项都是按**基准字号**算的。一段文字里某个字被放大过
        # （只给那个字调了字号）时，框会明显小于那个字 —— 再点进来编辑就只剩
        # 一半。这里直接取文档排版出来的真实宽高，多大都框得住。
        ds = self.document().size()
        w = max(w, ds.width())
        h = max(h, ds.height())
        return QRectF(0, 0, w + PAD * 2 + 14, h + PAD * 2 + 10)

    def reposition(self):
        r = self.screen_rect()
        if self._to_screen is not None:
            sp = self._to_screen(self._doc_anchor)
            x, y = sp.x(), sp.y()
        else:
            x = self._doc_anchor.x() * self._zoom
            y = self._doc_anchor.y() * self._zoom
        self.setGeometry(int(x - PAD), int(y - PAD),
                         max(40, int(r.width()) + 8), max(20, int(r.height()) + 6))

    # ---------------------------------------------------------- 事件
    def inputMethodEvent(self, e):
        # 中文输入法选词时先别把回车当成「落字」，否则打一个字就提前结束。
        self._ime_composing = bool(e.preeditString())
        super().inputMethodEvent(e)

    def keyPressEvent(self, e):
        if self._ime_composing:
            # 让输入法自己处理选词/上屏，不抢回车和 Esc。
            super().keyPressEvent(e)
            self.reposition()
            return
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and \
                (e.modifiers() & Qt.ControlModifier):
            # Ctrl+Enter 保留为快捷落字；普通回车仍然是换行。
            self.commit(refocus=True)
            return
        if e.key() == Qt.Key_Escape:
            # Esc 落字；Shift+Esc 放弃这次编辑（不落字）。
            if e.modifiers() & Qt.ShiftModifier:
                self.cancel(refocus=True)
            else:
                self.commit(refocus=True)
            return
        super().keyPressEvent(e)
        self.reposition()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        # 点到别处（图层面板、画布…）就等于落字，避免文字「挂」在画布上；
        # 但去选项栏改字体 / 字号 / 颜色不算离开 —— 那正是编辑这段文字的时候。
        if self._closing or self._hold:
            return
        w = QApplication.focusWidget()
        if w is not None and self.keep_parent is not None and \
                (w is self.keep_parent or self.keep_parent.isAncestorOf(w)):
            return
        self.commit()

    def commit(self, refocus: bool = False):
        if self._closing:
            return
        self._closing = True
        text = self.toPlainText()
        self.hide()
        if refocus and self.parentWidget() is not None:
            self.parentWidget().setFocus()      # 落字后键盘快捷键还能接着用
        if text.strip():
            self.committed.emit(text)
        else:
            self.cancelled.emit()

    def cancel(self, refocus: bool = False):
        if self._closing:
            return
        self._closing = True
        self.hide()
        if refocus and self.parentWidget() is not None:
            self.parentWidget().setFocus()
        self.cancelled.emit()


# ---------------------------------------------------------------- 落到图层
def draw_text(img, text: str, anchor: QPointF, family: str, px: float,
              bold: bool, italic: bool, color: QColor, align: str = "left",
              gap: float = 1.0, clip=None):
    """把文字画进图层图像，返回脏矩形（文档坐标）。"""
    font = fontlib.make_font(family, px, bold, italic)
    fm = QFontMetricsF(font)
    lines = text.split("\n")
    line_h = fm.height() * gap

    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    p.setFont(font)
    p.setPen(QPen(QColor(color)))
    if clip is not None:
        p.setClipPath(clip)

    wmax = 0.0
    for line in lines:
        wmax = max(wmax, fm.horizontalAdvance(line))
    x0 = anchor.x()
    if align == "center":
        x0 = anchor.x() - wmax / 2.0
    elif align == "right":
        x0 = anchor.x() - wmax

    for i, line in enumerate(lines):
        if not line:
            continue
        w = fm.horizontalAdvance(line)
        x = x0
        if align == "center":
            x = x0 + (wmax - w) / 2.0
        elif align == "right":
            x = x0 + (wmax - w)
        baseline = anchor.y() + fm.ascent() + i * line_h
        p.drawText(QPointF(x, baseline), line)
    p.end()

    h = max(line_h * len(lines), fm.height())
    pad = max(4.0, px * 0.35)
    return QRectF(x0 - pad, anchor.y() - pad, wmax + pad * 2, h + pad * 2).toAlignedRect()
