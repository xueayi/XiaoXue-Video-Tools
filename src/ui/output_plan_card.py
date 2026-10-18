# -*- coding: utf-8 -*-
"""输出方案卡 —— 5 张目标卡映射现有质量预设，「更多预设」保留全部预设。

设计约束：
- 每张卡对应的预设键来自 ``presets.QUALITY_PRESETS`` (单一数据源)；
- 卡面 encoder 文案由 **预设 -> ENCODERS 反查** 生成（如 "H.264 · libx264"），
  不在本文件硬编码任何编码器名称；
- 点击卡片等价于把现有 ``preset_combo`` 切到对应预设，随后由页面的
  ``_on_preset_changed`` 完成全部联动（本组件不重复实现联动逻辑）。
"""

from dataclasses import dataclass

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QSizePolicy, QVBoxLayout,
)

from ..presets import ENCODERS, QUALITY_PRESETS
from .base_tab import repolish, set_label_kind
from .widgets import WheelGuardComboBox

TITLE = "视频输出策略"
MORE_PRESETS_LABEL = "更多预设"
CUSTOM_PRESET = "自定义 (Custom)"
HARDWARE_CAPABILITY_PENDING = "待能力检测"
HARDWARE_CAPABILITY_AVAILABLE = "NVENC 可用"
HARDWARE_CAPABILITY_UNAVAILABLE = "NVENC 不可用"
CUSTOM_BADGE = "自定义参数"


@dataclass(frozen=True)
class PlanTarget:
    """一张目标卡的静态定义。"""

    key: str            # 稳定标识 (测试/日志用)
    title: str          # 卡面标题
    preset_name: str    # QUALITY_PRESETS 中的实际键
    hardware: bool = False  # 是否依赖硬件编码能力 (暂无能力探测)


# 5 张目标卡 -> 现有预设。顺序即展示顺序。
PLAN_TARGETS = (
    PlanTarget(
        key="balanced_h264",
        title="均衡 H.264",
        preset_name="【均衡画质】x264 常用导出 (CRF18)",
    ),
    PlanTarget(
        key="quality_h264",
        title="高质量 H.264",
        preset_name="【极致画质】x264 4K/高动态/AMV (CRF16)",
    ),
    PlanTarget(
        key="hevc_compress",
        title="HEVC 高压缩",
        preset_name="【均衡画质】x265/HEVC 高效压缩 (CRF20)",
    ),
    PlanTarget(
        key="hardware_fast",
        title="硬件极速",
        preset_name="【速度优先】NVIDIA 显卡加速",
        hardware=True,
    ),
    PlanTarget(
        key="custom",
        title="自定义",
        preset_name=CUSTOM_PRESET,
    ),
)


def encoder_badge(
    preset_name: str,
    quality_presets: dict = None,
    encoders: dict = None,
) -> str:
    """由预设反查 ENCODERS 生成卡面 encoder 文案。

    例: "【均衡画质】x264 常用导出 (CRF18)" -> "H.264 · libx264 · CRF 18"
    自定义预设 (encoder 为 None) -> "自定义参数"
    """
    presets = QUALITY_PRESETS if quality_presets is None else quality_presets
    enc_map = ENCODERS if encoders is None else encoders
    preset = presets.get(preset_name) or {}
    encoder = preset.get("encoder")
    if not encoder:
        return CUSTOM_BADGE

    display_name = next(
        (name for name, value in enc_map.items() if value == encoder), encoder
    )
    # "H.264 (CPU - libx264)" -> "H.264"
    codec = display_name.split("(")[0].strip() or display_name
    parts = [codec, encoder]
    if preset.get("crf") is not None:
        parts.append(f"CRF {preset['crf']}")
    elif preset.get("cq") is not None:
        parts.append(f"CQ {preset['cq']}")
    return " · ".join(parts)


class PlanCard(QFrame):
    """单张可点击的目标卡。"""

    clicked = pyqtSignal(str)  # preset_name

    def __init__(self, target: PlanTarget, quality_presets: dict = None,
                 parent=None):
        super().__init__(parent)
        self.target = target
        self.preset_name = target.preset_name
        self._selected = False
        self._hardware_blocked = False

        self.setObjectName("plan_card")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(target.preset_name)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(6)

        self.title_label = QLabel(target.title)
        self.title_label.setWordWrap(True)
        set_label_kind(self.title_label, "strong")
        header.addWidget(self.title_label, 1)

        # 选中标记: 右上角圆形对勾徽标 (替代整块填充色)
        self.check_badge = QLabel("✓")
        self.check_badge.setObjectName("plan_check_badge")
        self.check_badge.setFixedSize(18, 18)
        self.check_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.check_badge.setVisible(False)
        header.addWidget(self.check_badge, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        self.badge_label = QLabel(
            encoder_badge(target.preset_name, quality_presets=quality_presets)
        )
        self.badge_label.setObjectName("accent_label")
        self.badge_label.setWordWrap(True)
        layout.addWidget(self.badge_label)

        presets = quality_presets if quality_presets is not None else QUALITY_PRESETS
        preset = presets.get(target.preset_name) or {}
        description = preset.get("description") or target.title
        self.desc_label = QLabel(description)
        self.desc_label.setObjectName("muted_label")
        self.desc_label.setWordWrap(True)
        layout.addWidget(self.desc_label)
        layout.addStretch(1)

        self.capability_label = QLabel(HARDWARE_CAPABILITY_PENDING)
        self.capability_label.setObjectName("muted_label")
        self.capability_label.setVisible(target.hardware)
        layout.addWidget(self.capability_label)

        self.set_selected(False)

    # ----------------------------------------------------------------
    def is_selected(self) -> bool:
        return self._selected

    def is_hardware_blocked(self) -> bool:
        """硬件卡是否因能力不足被禁用。"""
        return self._hardware_blocked

    def set_hardware_available(self, available) -> None:
        """硬件卡三态（仅对 ``target.hardware`` 卡片生效）。

        Args:
            available: None=待能力检测（卡片仍可选）、True=可用、
                False=不可用（卡片禁用且点击不触发切换）。
        """
        if not self.target.hardware:
            return
        self._hardware_blocked = available is False
        if available is None:
            self.capability_label.setText(HARDWARE_CAPABILITY_PENDING)
        elif available:
            self.capability_label.setText(HARDWARE_CAPABILITY_AVAILABLE)
        else:
            self.capability_label.setText(HARDWARE_CAPABILITY_UNAVAILABLE)
        self.capability_label.setVisible(True)
        self.setEnabled(not self._hardware_blocked)
        if self._hardware_blocked:
            self.setCursor(Qt.CursorShape.ForbiddenCursor)
            self.setToolTip(
                f"{self.target.preset_name}（未检测到该硬件编码器）")
        else:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setToolTip(self.target.preset_name)

    def set_selected(self, selected: bool) -> None:
        self._selected = bool(selected)
        self.setProperty("selected", self._selected)
        set_label_kind(self.title_label, "accent" if self._selected else "strong")
        self.title_label.setText(self.target.title)
        self.check_badge.setVisible(self._selected)
        repolish(self)

    def click(self) -> None:
        """程序化点击（测试/键盘触发）；禁用卡不触发切换。"""
        if not self.isEnabled():
            return
        self.clicked.emit(self.preset_name)

    def mouseReleaseEvent(self, event):
        if (
            self.isEnabled()
            and event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.click()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class OutputPlanCard(QGroupBox):
    """视频输出策略：5 张目标卡 + "更多预设" 下拉 + 视频基础参数表单。"""

    def __init__(self, presets: dict = None, current: str = None, parent=None):
        super().__init__(TITLE, parent)
        self.setObjectName("output_plan_card")
        self.presets = dict(QUALITY_PRESETS if presets is None else presets)
        #: 硬件卡能力状态: None=待检测 / True=可用 / False=不可用
        self.hardware_available = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        intro = QLabel(
            "先选一个目标，参数会自动套用；卡面编码器信息由质量预设实时反查。"
        )
        intro.setObjectName("group_desc")
        intro.setWordWrap(True)
        outer.addWidget(intro)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        self.cards = []
        for index, target in enumerate(PLAN_TARGETS):
            card = PlanCard(target, quality_presets=self.presets)
            card.clicked.connect(self._on_card_clicked)
            grid.addWidget(card, 0, index)
            self.cards.append(card)
        for index in range(len(self.cards)):
            grid.setColumnStretch(index, 1)
        outer.addLayout(grid)

        combo_row = QHBoxLayout()
        combo_row.setSpacing(8)
        combo_label = QLabel(MORE_PRESETS_LABEL)
        combo_label.setObjectName("muted_label")
        self.preset_combo = WheelGuardComboBox()
        self.preset_combo.addItems(list(self.presets.keys()))
        self.preset_combo.setToolTip(
            f"完整预设列表（共 {len(self.presets)} 项）"
        )
        if current and current in self.presets:
            self.preset_combo.setCurrentText(current)
        self.preset_combo.currentTextChanged.connect(self._sync_selection)
        combo_row.addWidget(combo_label)
        combo_row.addWidget(self.preset_combo, 1)
        outer.addLayout(combo_row)

        hint = QLabel("点击上方目标卡会同步切换此下拉；全部预设始终可在此选择。")
        hint.setObjectName("group_desc")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        self._sync_selection(self.preset_combo.currentText())

    # ----------------------------------------------------------------
    # 基础参数表单 (视频压制页把输出格式/分辨率等加进来)
    # ----------------------------------------------------------------

    def param_form(self):
        """返回方案卡下方的基础参数表单 (惰性创建, 由页面填充)。"""
        form = getattr(self, "_param_form", None)
        if form is None:
            form = QFormLayout()
            form.setLabelAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
            form.setHorizontalSpacing(14)
            form.setVerticalSpacing(10)
            self._param_form = form
            separator = QLabel("视频编码参数")
            separator.setObjectName("accent_label")
            self.layout().addWidget(separator)
            self.layout().addLayout(form)
        return form

    # ----------------------------------------------------------------
    # 能力联动
    # ----------------------------------------------------------------

    def set_hardware_preset(self, preset_name: str, label: str) -> None:
        """硬件卡共享平台对应的预设与状态文案。"""
        card = next(card for card in self.cards if card.target.hardware)
        card.preset_name = preset_name
        card.setToolTip(preset_name)
        card.badge_label.setText(encoder_badge(preset_name, self.presets))
        card.desc_label.setText(self.presets[preset_name].get("description", ""))
        if self.hardware_available is not None:
            card.capability_label.setText(f"{label} {'可用' if self.hardware_available else '不可用'}")
        self._sync_selection(self.selected_preset)

    def set_hardware_available(self, available) -> None:
        """硬件目标卡三态: None=待能力检测 / True=可用 / False=不可用(禁用)。"""
        self.hardware_available = available
        for card in self.cards:
            if card.target.hardware:
                card.set_hardware_available(available)

    # ----------------------------------------------------------------
    # 选择联动
    # ----------------------------------------------------------------

    def _on_card_clicked(self, preset_name: str) -> None:
        if preset_name in self.presets and (
            self.preset_combo.currentText() != preset_name
        ):
            self.preset_combo.setCurrentText(preset_name)
        self._sync_selection(self.preset_combo.currentText())

    def _sync_selection(self, preset_name: str) -> None:
        for card in self.cards:
            card.set_selected(card.preset_name == preset_name)

    # ----------------------------------------------------------------
    # 查询辅助
    # ----------------------------------------------------------------

    @property
    def selected_preset(self) -> str:
        return self.preset_combo.currentText()

    def card_for_preset(self, preset_name: str):
        for card in self.cards:
            if card.preset_name == preset_name:
                return card
        return None

    def selected_card(self):
        return self.card_for_preset(self.selected_preset)
