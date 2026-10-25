# -*- coding: utf-8 -*-
"""独立生成真实试笔页；不触碰个人画作，不向最近使用添加演示记录。"""
import math
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QFont
from core import Document, Stroke
import brushes


def make_demo_document():
    doc = Document(1800, 1200, QColor("#171d25"))
    layer = doc.add_layer("内置笔刷真实试笔")
    choices = [
        ("素描铅笔", "#b9c5cc"), ("枯墨飞白", "#d5e2f0"),
        ("盐析水彩", "#77bad5"), ("蜡质拖痕", "#eba683"),
        ("油彩堆色纹", "#dd8ab6"), ("孔洞海绵", "#b6cc8a"),
        ("尖叶草丛", "#88c9ab"), ("蕨叶枝条", "#81b998"),
        ("五瓣花簇", "#e5afc5"), ("卷层玫瑰", "#dba1bc"),
        ("细脉羽毛", "#c6c9e0"), ("六角雪晶", "#9ed6eb"),
        ("连续斜排线", "#c8c3df"), ("金属链环", "#dbcbaa"),
        ("霓虹光芯", "#a987e9"), ("连续彩虹", "#80c3cb"),
    ]
    painter = QPainter(layer.image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QColor("#e6edf5")); painter.setFont(QFont("Microsoft YaHei", 29, QFont.Bold))
    painter.drawText(QRectF(52, 28, 1696, 51), Qt.AlignLeft | Qt.AlignVCenter, "U Draw · 内置笔刷试画")
    painter.setFont(QFont("Microsoft YaHei", 13)); painter.setPen(QColor("#9cacbf"))
    painter.drawText(QRectF(54, 83, 1692, 28), Qt.AlignLeft | Qt.AlignVCenter,
                     "真实引擎渲染  /  分类浏览  /  最近使用自动保存，重启保留  /  可以直接在此页试笔")
    for index, (name, color) in enumerate(choices):
        x = 44 + index % 4 * 432; y = 142 + index // 4 * 248
        painter.setPen(QColor("#344254")); painter.setBrush(QColor("#222d3a"))
        painter.drawRoundedRect(QRectF(x,y,414,229),12,12)
        painter.setFont(QFont("Microsoft YaHei", 15, QFont.Bold)); painter.setPen(QColor("#e4edf6"))
        painter.drawText(QRectF(x+20,y+13,374,30),Qt.AlignLeft|Qt.AlignVCenter,name)
        preset = brushes.BUILTIN[name]
        painter.setFont(QFont("Microsoft YaHei",10)); painter.setPen(QColor("#91a7bd"))
        painter.drawText(QRectF(x+20,y+48,374,21),Qt.AlignLeft|Qt.AlignVCenter,preset.group)
    painter.setPen(QColor("#8a9db2")); painter.setFont(QFont("Microsoft YaHei",10))
    painter.drawText(QRectF(52,1152,1696,28),Qt.AlignLeft|Qt.AlignVCenter,
                     "演示笔触不会加入最近使用；点选画笔或实际落笔后才记录你的使用顺序。材质是二维视觉近似。")
    painter.end(); layer.touch()
    for index,(name,color) in enumerate(choices):
        x = 44 + index % 4 * 432; y = 142 + index // 4 * 248
        b = brushes.BUILTIN[name].copy(); b.size = min(72,max(b.size,20)); b.stabilize = 0
        st = Stroke(doc,layer,b,QColor(color))
        for i in range(81):
            t = i / 80
            pos = QPointF(x+22+370*t,y+147-37*math.sin(t*math.tau))
            pressure = 0.32+0.68*math.sin(t*math.pi)**0.6
            if i == 0:
                st.begin(pos,pressure)
            else:
                st.move(pos,pressure)
        st.end()
    doc.recompose(); doc._stroke_session = None
    doc.title = "内置笔刷试画（演示）"; doc.modified = False
    return doc


def populate_window(window):
    doc = make_demo_document()
    window.doc = doc; window.docs = [doc]; window.doc_index = 0
    window.canvas.set_document(doc)
    window.layers_panel.set_document(doc)
    window._refresh_tabs()
    window._refresh_title()
    window.hint.setText("内置笔刷真实试画页 · 点击「打开笔刷库」按分类挑笔 · 最近使用会自动保存")
