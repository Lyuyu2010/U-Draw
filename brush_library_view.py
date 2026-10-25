# -*- coding: utf-8 -*-
"""分类画笔库的大窗口：真实笔触缩略图，共用原画布的 BrushPanel 与历史。"""
from PySide6.QtCore import Qt, QRectF, QSize, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QVBoxLayout, QListWidget,
    QListWidgetItem, QLabel, QLineEdit, QScrollArea, QWidget, QGridLayout, QPushButton)
import brushes
from brush_thumbs import thumb_pixmap
from core import KIND_NAMES
from theme import C


class BrushCard(QWidget):
    chosen = Signal(int)
    def __init__(self, index, brush, selected, parent=None):
        super().__init__(parent)
        self.index, self.brush, self.selected = index, brush, selected
        self.setMinimumSize(230, 112)
        self.setMaximumHeight(112)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(brushes.brush_description(brush))
    def sizeHint(self):
        return QSize(244, 112)
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(C.PRESSED if self.selected else C.FIELD))
        p.setPen(QPen(QColor(C.ACCENT if self.selected else C.FIELD_BORDER), 1.5 if self.selected else 1))
        p.drawRoundedRect(QRectF(1, 1, self.width()-2, self.height()-2), 8, 8)
        f = QFont(self.font()); f.setPointSizeF(10); f.setBold(True); p.setFont(f)
        p.setPen(QColor(C.TEXT))
        p.drawText(QRectF(14, 8, self.width()-28, 22), Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(self.brush.name, Qt.ElideRight, self.width()-28))
        f.setPointSizeF(8); f.setBold(False); p.setFont(f); p.setPen(QColor(C.TEXT_FAINT))
        p.drawText(QRectF(14, 29, self.width()-28, 17), Qt.AlignLeft | Qt.AlignVCenter,
                   f"{KIND_NAMES.get(self.brush.kind, self.brush.kind)}  ·  {self.brush.size:g} px")
        pix = thumb_pixmap(self.brush)
        p.drawPixmap(QRectF(13, 47, self.width()-26, 60), pix, QRectF(pix.rect()))
        p.end()
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.chosen.emit(self.index)


class BrushLibraryWindow(QDialog):
    """浏览不算使用；只有选笔或实际落笔更新 MRU。"""
    def __init__(self, panel, parent=None):
        super().__init__(parent)
        self.panel = panel
        self.setWindowTitle("U Draw · 内置笔刷库")
        self.setMinimumSize(820, 590)
        self.resize(1040, 720)
        self.setStyleSheet(f"QDialog {{ background: {C.CARD}; color: {C.TEXT}; }}")
        self.group = panel.bar.category_combo.currentData() if panel.bar else None
        self._refresh_queued = False
        self._cols = 0
        root = QVBoxLayout(self); root.setContentsMargins(20,16,20,16); root.setSpacing(12)
        title = QLabel("画笔库")
        title.setStyleSheet(f"color: {C.TEXT}; font-size: 21px; font-weight: 600;")
        head = QHBoxLayout(); head.addWidget(title)
        self.total = QLabel(); self.total.setStyleSheet(f"color: {C.TEXT_FAINT};")
        head.addWidget(self.total); head.addStretch()
        head.addWidget(QLabel("搜索"))
        self.search = QLineEdit(); self.search.setPlaceholderText("笔刷名称 / 材质 / 用途")
        self.search.setClearButtonEnabled(True); self.search.setMinimumWidth(220)
        self.search.setText(panel.bar.search_edit.text() if panel.bar else "")
        self.search.textChanged.connect(self._search_changed)
        head.addWidget(self.search); root.addLayout(head)
        body = QHBoxLayout(); body.setSpacing(14)
        self.categories = QListWidget(); self.categories.setFixedWidth(176)
        self.categories.setStyleSheet(
            f"QListWidget {{background: {C.FIELD}; color: {C.TEXT_DIM}; border: 1px solid {C.FIELD_BORDER}; border-radius: 7px; outline: 0;}}"
            f"QListWidget::item {{padding: 8px 10px; min-height: 21px;}}"
            f"QListWidget::item:selected {{background: {C.PRESSED}; color: {C.TEXT}; border-left: 3px solid {C.ACCENT};}}")
        self.categories.currentItemChanged.connect(self._category_changed)
        body.addWidget(self.categories)
        right = QVBoxLayout(); right.setSpacing(8)
        row = QHBoxLayout()
        self.heading = QLabel(); self.heading.setStyleSheet(f"color: {C.TEXT}; font-size: 14px; font-weight: 600;")
        row.addWidget(self.heading); row.addStretch()
        self.detail = QLabel(); self.detail.setStyleSheet(f"color: {C.TEXT_FAINT};")
        row.addWidget(self.detail); right.addLayout(row)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea {border: none; background: transparent;}")
        self.host = QWidget(); self.grid = QGridLayout(self.host)
        self.grid.setContentsMargins(0,0,6,0); self.grid.setSpacing(9)
        self.scroll.setWidget(self.host); right.addWidget(self.scroll,1)
        body.addLayout(right,1); root.addLayout(body,1)
        footer = QHBoxLayout()
        note = QLabel("右键画笔加入常用 · 最近使用/常用重启保留 · 共 133 支")
        note.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 10px;")
        footer.addWidget(note); footer.addStretch()
        back = QPushButton("返回画布试笔"); back.setObjectName("primary"); back.clicked.connect(self.accept)
        footer.addWidget(back); root.addLayout(footer)
        panel.presetChanged.connect(self.queue_refresh)
        self.refresh()

    def _items(self):
        if self.group == brushes.RECENT_GROUP:
            items = self.panel.recent_presets()
        elif self.group == brushes.FAVORITE_GROUP:
            items = self.panel.favorite_presets()
        elif self.group == brushes.USER_GROUP:
            items = [(i,b) for i,b in enumerate(self.panel.presets) if brushes.builtin_origin(b) is None]
        else:
            items = [(i,b) for i,b in enumerate(self.panel.presets)
                     if self.group is None or b.group == self.group]
        words = self.search.text().casefold().split()
        return [(i,b) for i,b in items if all(word in
                (b.name+" "+b.group+" "+KIND_NAMES.get(b.kind,b.kind)+" "+brushes.brush_description(b)).casefold()
                for word in words)]

    def _sync_bar(self):
        bar = self.panel.bar
        if bar is None:
            return
        controls = (bar.category_combo,bar.search_edit)
        states = [control.blockSignals(True) for control in controls]
        try:
            bar.search_edit.setText(self.search.text())
            bar._sync_categories()
            bar.category_combo.setCurrentIndex(max(0,bar.category_combo.findData(self.group)))
        finally:
            for control,state in zip(controls,states):
                control.blockSignals(state)
        bar._filters_changed()

    def _category_changed(self, current, previous=None):
        if current is not None:
            self.group = current.data(Qt.UserRole)
            self._sync_bar()
            self.refresh()
            self.scroll.verticalScrollBar().setValue(0)

    def _search_changed(self, *_):
        self._sync_bar()
        self.refresh()

    def choose(self, index):
        self.panel.select_index(index)
        self.queue_refresh()

    def queue_refresh(self):
        if not self._refresh_queued:
            self._refresh_queued = True
            QTimer.singleShot(0,self.refresh)

    def refresh(self):
        self._refresh_queued = False
        presets = list(enumerate(self.panel.presets))
        groups = [g for g in self.panel.groups() if g != brushes.USER_GROUP]
        entries = [("全部画笔", None, len(presets)),
                   ("最近使用", brushes.RECENT_GROUP, len(self.panel.recent_presets())),
                   ("常用", brushes.FAVORITE_GROUP, len(self.panel.favorite_presets()))]
        entries += [(g,g,sum(b.group==g for _,b in presets)) for g in groups]
        entries.append(("我的",brushes.USER_GROUP,sum(brushes.builtin_origin(b) is None for b in self.panel.presets)))
        blocked = self.categories.blockSignals(True)
        try:
            self.categories.clear()
            for name,key,count in entries:
                item = QListWidgetItem(f"{name}    {count}"); item.setData(Qt.UserRole,key)
                self.categories.addItem(item)
                if key == self.group:
                    self.categories.setCurrentItem(item)
        finally:
            self.categories.blockSignals(blocked)
        self.total.setText(f"{len(presets)} 支画笔  /  {len(groups)} 个分类")
        if self.group == brushes.RECENT_GROUP:
            heading = "最近使用"
        elif self.group == brushes.FAVORITE_GROUP:
            heading = "常用"
        else:
            heading = self.group or "全部画笔"
        self.heading.setText(heading)
        items = self._items(); self.detail.setText(f"{len(items)} 支 · 点击选择，返回画布使用")
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().hide(); item.widget().deleteLater()
        cols = 3 if self.width() >= 1020 else 2
        self._cols = cols
        for col in range(4):
            self.grid.setColumnStretch(col,1 if col < cols else 0)
        for row in range(self.grid.rowCount()):
            self.grid.setRowStretch(row,0)
        for n,(index,b) in enumerate(items):
            card = BrushCard(index,b,index==self.panel.current)
            card.chosen.connect(self.choose); self.grid.addWidget(card,n//cols,n%cols)
            card.show()
        rows = (len(items)+cols-1)//cols
        if not items:
            if self.group == brushes.RECENT_GROUP:
                text = "使用画笔后会自动记录在这里。\n关闭软件再打开，列表和顺序仍会保留。"
            elif self.group == brushes.FAVORITE_GROUP:
                text = "右键任意画笔，选择「添加到常用」。\n关闭软件再打开，常用列表仍会保留。"
            else:
                text = "没有匹配的笔刷，请更换分类或清除搜索。"
            empty = QLabel(text); empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(f"color: {C.TEXT_FAINT}; padding: 36px;")
            self.grid.addWidget(empty,0,0,1,cols); empty.show(); rows = 1
        self.grid.setRowStretch(rows,1)
        self.host.setMinimumHeight(rows*121)
        self.grid.activate()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,"grid") and (3 if self.width() >= 1020 else 2) != self._cols:
            self.queue_refresh()
