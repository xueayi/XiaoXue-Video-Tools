# -*- coding: utf-8 -*-
"""error_card.py 测试: 8 类错误归类 (委托 src.ffmpeg.errors)、日志尾部、卡片渲染与信号。"""

import pytest

from PyQt6.QtWidgets import QLabel

import src.ui.error_card as error_card_module
from src.ffmpeg.errors import ErrorCategory as DomainCategory
from src.ffmpeg.errors import UserFacingError
from src.ffmpeg.errors import classify as domain_classify
from src.ui.error_card import (
    ErrorCard,
    ErrorCategory,
    ErrorInfo,
    classify_log_text,
    error_info_from_user,
)

# (日志文本, 期望分类)
_CLASSIFY_CASES = [
    # 硬件编码器 (迁自 core.py 的 NVENC / QSV / AMF 关键词)
    ("[h264_nvenc @ 000001f4] No NVENC capable devices found",
     ErrorCategory.ENCODER_UNAVAILABLE),
    ("Error initializing an MFX session", ErrorCategory.ENCODER_UNAVAILABLE),
    ("CreateComponent failed", ErrorCategory.ENCODER_UNAVAILABLE),
    ("[h264_nvenc @ 0000] Failed to init NVENC", ErrorCategory.ENCODER_UNAVAILABLE),
    ("Unknown encoder 'h264_qsv'", ErrorCategory.ENCODER_UNAVAILABLE),
    # 输入 / 权限
    ("[in#0] Error opening input: No such file or directory",
     ErrorCategory.INPUT_NOT_FOUND),
    ("Invalid data found when processing input", ErrorCategory.INPUT_NOT_FOUND),
    ("[out#0/mp4] Error opening output: Permission denied",
     ErrorCategory.OUTPUT_PERMISSION_DENIED),
    ("Access is denied", ErrorCategory.OUTPUT_PERMISSION_DENIED),
    # 字幕滤镜
    ("No such filter: 'subtitles'", ErrorCategory.SUBTITLE_FILTER_ERROR),
    ("Error applying subtitles filter", ErrorCategory.SUBTITLE_FILTER_ERROR),
    # 容器 (迁自 remux_tab.py 容器规则)
    ("Could not find tag for codec vp9 in stream #0, codec not currently "
     "supported in container", ErrorCategory.CONTAINER_INCOMPATIBLE),
    ("容器不兼容，建议改用 MKV", ErrorCategory.CONTAINER_INCOMPATIBLE),
    # FFmpeg 本体缺失 / 取消 / 未知
    ("ffmpeg: not found", ErrorCategory.FFMPEG_NOT_FOUND),
    ("任务已停止", ErrorCategory.PROCESS_CANCELLED),
    ("Exiting normally, received signal 2.", ErrorCategory.PROCESS_CANCELLED),
    ("something totally unexpected happened", ErrorCategory.UNKNOWN_FFMPEG_ERROR),
]


def test_error_category_has_eight_members():
    assert len(ErrorCategory) == 8
    assert len({category.value for category in ErrorCategory}) == 8


def test_error_category_is_domain_enum():
    """M2.5: UI 重新导出领域枚举, 不存在两套分类值。"""
    assert ErrorCategory is DomainCategory


def test_classify_log_text_delegates_to_domain_module(monkeypatch):
    """classify_log_text 必须委托 src.ffmpeg.errors.classify (不再自带规则)。"""
    calls = []

    def fake_classify(stderr_tail="", exit_code=None, cancelled=False):
        calls.append((stderr_tail, exit_code, cancelled))
        return UserFacingError(
            title="委托标题",
            category=DomainCategory.FFMPEG_NOT_FOUND,
            causes=("原因",),
            actions=("操作",),
            log_tail="tail",
        )

    monkeypatch.setattr(error_card_module, "classify", fake_classify)
    info = classify_log_text("some log")

    assert calls == [("some log", None, False)]
    assert isinstance(info, ErrorInfo)
    assert info.title == "委托标题"
    assert info.category is DomainCategory.FFMPEG_NOT_FOUND
    assert info.causes == ["原因"]
    assert info.actions == ["操作"]
    assert info.log_tail == "tail"


def test_classify_log_text_matches_domain_result():
    text = "[h264_nvenc @ 0000] No NVENC capable devices found"
    info = classify_log_text(text)
    expected = domain_classify(text)
    assert info.title == expected.title
    assert info.category is expected.category
    assert info.causes == list(expected.causes)
    assert info.actions == list(expected.actions)
    assert info.log_tail == expected.log_tail


def test_error_info_from_user_converts_tuples_to_lists():
    error = UserFacingError(
        title="标题",
        category=DomainCategory.INPUT_NOT_FOUND,
        causes=("原因一", "原因二"),
        actions=("操作一",),
        log_tail="tail",
    )
    info = error_info_from_user(error)
    assert info.title == "标题"
    assert info.category is DomainCategory.INPUT_NOT_FOUND
    assert info.causes == ["原因一", "原因二"]
    assert info.actions == ["操作一"]
    assert info.log_tail == "tail"


@pytest.mark.parametrize("text,expected", _CLASSIFY_CASES)
def test_classify_log_text(text, expected):
    info = classify_log_text(text)
    assert info.category is expected
    assert info.title
    assert info.causes
    assert info.actions


def test_classify_empty_text_is_unknown():
    info = classify_log_text("")
    assert info.category is ErrorCategory.UNKNOWN_FFMPEG_ERROR
    assert info.causes and info.actions


def test_classify_none_text_is_unknown():
    info = classify_log_text(None)
    assert info.category is ErrorCategory.UNKNOWN_FFMPEG_ERROR


def test_classify_keeps_log_tail():
    lines = [f"line {i}" for i in range(30)]
    lines.append("No NVENC capable devices found")
    info = classify_log_text("\n".join(lines))
    tail_lines = info.log_tail.splitlines()
    assert len(tail_lines) == 20
    assert tail_lines[-1] == "No NVENC capable devices found"


def test_error_info_defaults():
    info = ErrorInfo(title="标题")
    assert info.causes == []
    assert info.actions == []
    assert info.log_tail == ""
    assert info.category is ErrorCategory.UNKNOWN_FFMPEG_ERROR


# ----------------------------------------------------------------
# ErrorCard
# ----------------------------------------------------------------

def _sample_info():
    return ErrorInfo(
        title="硬件编码器不可用",
        causes=["原因一", "原因二"],
        actions=["改用 CPU 编码", "更新驱动"],
        log_tail="tail line",
        category=ErrorCategory.ENCODER_UNAVAILABLE,
    )


def _cause_labels(card):
    return [
        label for label in card.findChildren(QLabel)
        if label.objectName() == "hint_info"
    ]


def test_error_card_starts_hidden(qapp):
    card = ErrorCard()
    assert card.isHidden() is True
    assert card.error is None


def test_error_card_show(qapp):
    card = ErrorCard()
    info = _sample_info()
    actions, logs = [], []
    card.action_requested.connect(actions.append)
    card.log_requested.connect(lambda: logs.append(True))

    card.show(info)
    assert card.isHidden() is False
    assert card.error is info
    assert card._title_label.text() == "硬件编码器不可用"
    assert [label.text() for label in _cause_labels(card)] == ["•  原因一", "•  原因二"]
    assert [btn.text() for btn in card._action_buttons] == ["改用 CPU 编码", "更新驱动"]

    # 操作按钮 → action_requested(文案)；日志按钮 → log_requested()
    card._action_buttons[1].click()
    assert actions == ["更新驱动"]
    card._log_btn.click()
    assert logs == [True]


def test_error_card_reshow_replaces_content(qapp):
    card = ErrorCard()
    card.show(ErrorInfo(title="旧错误", causes=["旧原因"], actions=["旧操作"]))
    card.show(ErrorInfo(title="新错误", causes=["新原因"], actions=["新操作"]))

    assert card._title_label.text() == "新错误"
    assert [label.text() for label in _cause_labels(card)] == ["•  新原因"]
    assert [btn.text() for btn in card._action_buttons] == ["新操作"]


def test_error_card_show_rejects_non_info(qapp):
    card = ErrorCard()
    with pytest.raises(TypeError):
        card.show("not-an-error-info")


def test_error_card_without_actions(qapp):
    card = ErrorCard()
    card.show(ErrorInfo(title="仅标题"))
    assert card._action_buttons == []
    assert card._action_header.isHidden() is True
    assert card._cause_header.isHidden() is True
