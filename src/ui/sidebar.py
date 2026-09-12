# -*- coding: utf-8 -*-
"""侧边栏导航组件 —— 品牌区 + 分组导航 + 药丸指示器 + 主题切换。"""

from PyQt6.QtWidgets import (
    QListWidget, QListWidgetItem, QWidget, QLabel, QHBoxLayout, QVBoxLayout,
    QPushButton,
)
from PyQt6.QtCore import (
    Qt, QSize, pyqtSignal, QPropertyAnimation, QEasingCurve, QRect,
)
from PyQt6.QtGui import QPainter, QColor, QPixmap, QFont

from .._version import __version__
from . import icons
from . import theme


class _PillIndicator(QWidget):
    """侧边栏选中项的药丸形指示器 (3px 宽强调色圆角条)。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(3)
        self.setFixedHeight(20)
        self._color = QColor(theme.color("icon_color_accent"))
        self._anim = QPropertyAnimation(self, b"geometry", self)
        self._anim.setDuration(250)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def set_color(self, color_str: str):
        self._color = QColor(color_str)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._color)
        p.drawRoundedRect(self.rect(), 1.5, 1.5)
        p.end()

    def slide_to(self, target_rect: QRect):
        """平滑滑动到目标位置。"""
        if self._anim.state() == QPropertyAnimation.State.Running:
            self._anim.stop()
        self._anim.setStartValue(self.geometry())
        self._anim.setEndValue(target_rect)
        self._anim.start()


class Sidebar(QWidget):
    """侧边栏: 品牌头部 + 分组导航列表 + 底部主题切换。

    通过 tab_changed(页面索引) 通知页面切换。
    分组标题行为不可选中的小节标签，不占用页面索引。
    """

    tab_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar_root")
        self.setFixedWidth(208)

        self._pill = None
        self._page_of_row = []   # row -> 页面索引 / None (分组标题)
        self._row_of_page = []   # page index -> row
        self._icon_names = []    # row -> 图标名 / None
        self._page_count = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 12, 10, 10)
        root.setSpacing(6)

        # ---- 品牌区 ----
        header = QHBoxLayout()
        header.setSpacing(9)
        self._logo_label = QLabel()
        self._logo_label.setFixedSize(30, 30)
        self._logo_label.setScaledContents(True)
        header.addWidget(self._logo_label)

        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        self._title_label = QLabel("小雪工具箱")
        self._title_label.setObjectName("brand_title")
        self._version_label = QLabel(f"v{__version__}")
        self._version_label.setObjectName("brand_version")
        title_col.addWidget(self._title_label)
        title_col.addWidget(self._version_label)
        header.addLayout(title_col, 1)
        root.addLayout(header)

        # ---- 导航列表 ----
        self._list = QListWidget()
        self._list.setObjectName("sidebar")
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._list.currentRowChanged.connect(self._on_row_changed)
        self._list.setIconSize(QSize(16, 16))
        root.addWidget(self._list, 1)

        self._pill = _PillIndicator(self._list.viewport())
        self._pill.hide()

        # ---- 底部: 主题切换 ----
        self._theme_btn = QPushButton()
        self._theme_btn.setObjectName("sidebar_footer_btn")
        self._theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_btn.setIconSize(QSize(15, 15))
        root.addWidget(self._theme_btn)

        self.set_theme_icons()

    # ----------------------------------------------------------------
    # 构建接口
    # ----------------------------------------------------------------

    def add_section(self, title: str):
        """添加一个不可选中的分组小标题。"""
        item = QListWidgetItem(title)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setSizeHint(QSize(180, 26))
        self._list.addItem(item)
        self._page_of_row.append(None)
        self._icon_names.append(None)
        self._style_section_row(self._list.count() - 1)

    def add_item(self, text: str, icon_name: str = None) -> int:
        """添加一个导航项，返回其对应的页面索引。"""
        item = QListWidgetItem(text)
        item.setSizeHint(QSize(180, 38))
        page = self._page_count
        self._page_count += 1
        self._list.addItem(item)
        row = self._list.count() - 1
        self._page_of_row.append(page)
        self._row_of_page.append(row)
        self._icon_names.append(icon_name)
        self._apply_row_icon(row)
        return page

    # ----------------------------------------------------------------
    # 兼容 QListWidget 的常用接口
    # ----------------------------------------------------------------

    def currentRow(self) -> int:
        row = self._list.currentRow()
        if row < 0:
            return -1
        page = self._page_of_row[row]
        return -1 if page is None else page

    def setCurrentRow(self, row: int):
        """按页面索引选中对应导航项。"""
        if 0 <= row < len(self._row_of_page):
            self._list.setCurrentRow(self._row_of_page[row])

    def item_text(self, page: int) -> str:
        row = self._row_of_page[page]
        return self._list.item(row).text()

    def count(self) -> int:
        return len(self._row_of_page)

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        self._list.setEnabled(enabled)
        self._theme_btn.setEnabled(enabled)

    # ----------------------------------------------------------------
    # 主题联动
    # ----------------------------------------------------------------

    def set_theme_icons(self):
        """主题切换后刷新: 图标颜色、Logo、分组标题、按钮文案。"""
        self._pill.set_color(theme.color("icon_color_accent"))

        logo_path = theme.logo_path()
        if logo_path:
            self._logo_label.setPixmap(QPixmap(logo_path))

        is_dark = theme.get_theme() == "dark"
        self._theme_btn.setText("切换浅色模式" if is_dark else "切换深色模式")
        self._theme_btn.setIcon(
            icons.secondary("ri.sun-line" if is_dark else "ri.moon-line")
        )

        for row, name in enumerate(self._icon_names):
            if name is None:
                self._style_section_row(row)
            else:
                self._apply_row_icon(row)

        self._move_pill(self._list.currentRow())

    def theme_button(self) -> QPushButton:
        return self._theme_btn

    # ----------------------------------------------------------------
    # 内部实现
    # ----------------------------------------------------------------

    def _style_section_row(self, row: int):
        item = self._list.item(row)
        font = QFont()
        font.setPixelSize(11)
        font.setBold(True)
        item.setFont(font)
        item.setForeground(QColor(theme.color("text_tertiary")))

    def _apply_row_icon(self, row: int):
        name = self._icon_names[row]
        item = self._list.item(row)
        if not name:
            return
        selected = row == self._list.currentRow()
        item.setIcon(icons.accent(name) if selected else icons.icon(name))

    def _on_row_changed(self, row: int):
        self._move_pill(row)
        for r, name in enumerate(self._icon_names):
            if name is not None:
                self._apply_row_icon(r)
        if 0 <= row < len(self._page_of_row):
            page = self._page_of_row[row]
            if page is not None:
                self.tab_changed.emit(page)

    def _move_pill(self, row: int):
        if row < 0:
            self._pill.hide()
            return

        rect = self._list.visualItemRect(self._list.item(row))
        pill_h = 20
        y = rect.y() + (rect.height() - pill_h) // 2
        target = QRect(2, y, 3, pill_h)

        if not self._pill.isVisible():
            self._pill.setGeometry(target)
            self._pill.show()
        else:
            self._pill.slide_to(target)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        row = self._list.currentRow()
        if row >= 0:
            self._move_pill(row)
