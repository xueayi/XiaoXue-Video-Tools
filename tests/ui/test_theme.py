# -*- coding: utf-8 -*-
"""theme.py 单元测试: 令牌、亮暗主题切换、持久化、QPalette。"""

import os

import pytest

from src.ui import theme


@pytest.fixture(autouse=True)
def light_theme():
    theme.set_theme("light")
    theme.set_reduced_motion(False)
    yield
    theme.set_theme("light")
    theme.set_reduced_motion(False)


def test_palettes_have_identical_tokens():
    light = theme.PALETTES["light"]
    dark = theme.PALETTES["dark"]
    assert set(light.keys()) == set(dark.keys())


def test_default_theme_is_light():
    assert theme.get_theme() == "light"


def test_set_and_get_theme():
    theme.set_theme("dark")
    assert theme.get_theme() == "dark"
    theme.set_theme("light")
    assert theme.get_theme() == "light"


def test_set_theme_ignores_invalid():
    theme.set_theme("blue")
    assert theme.get_theme() == "light"


def test_corrupted_theme_in_settings_falls_back():
    theme._settings().setValue(theme._KEY_THEME, "solarized")
    assert theme.get_theme() == "light"


def test_reduced_motion_roundtrip():
    assert theme.reduced_motion() is False
    theme.set_reduced_motion(True)
    assert theme.reduced_motion() is True
    theme.set_reduced_motion(False)
    assert theme.reduced_motion() is False


def test_stylesheet_matches_theme():
    light = theme.get_stylesheet("light")
    dark = theme.get_stylesheet("dark")
    assert light != dark
    assert theme.PALETTES["light"]["window_bg"] in light
    assert theme.PALETTES["dark"]["window_bg"] in dark


def test_get_stylesheet_uses_current_theme():
    theme.set_theme("dark")
    assert theme.PALETTES["dark"]["window_bg"] in theme.get_stylesheet()


def test_color_token():
    assert theme.color("accent", "light") == theme.PALETTES["light"]["accent"]
    theme.set_theme("dark")
    assert theme.color("accent") == theme.PALETTES["dark"]["accent"]


def test_color_invalid_token_raises():
    with pytest.raises(KeyError):
        theme.color("not_a_token")


def test_logo_path_exists():
    path = theme.logo_path("light")
    assert path and os.path.exists(path)
    dark_path = theme.logo_path("dark")
    assert dark_path and os.path.exists(dark_path)


def test_logo_path_missing_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(theme, "get_internal_dir", lambda: str(tmp_path / "internal"))
    monkeypatch.setattr(theme, "get_base_dir", lambda: str(tmp_path / "exe"))
    assert theme.logo_path("light") is None


def test_logo_path_prefers_internal_resource_dir(monkeypatch, tmp_path):
    """冻结 onedir 时 datas 位于 _internal/image, 必须优先命中。"""
    internal = tmp_path / "internal"
    logo_dir = internal / "image"
    logo_dir.mkdir(parents=True)
    logo = logo_dir / theme._LOGO_FILES["light"]
    logo.write_bytes(b"png")
    monkeypatch.setattr(theme, "get_internal_dir", lambda: str(internal))
    monkeypatch.setattr(theme, "get_base_dir", lambda: str(tmp_path / "exe"))
    assert theme.logo_path("light") == str(logo)


def test_logo_path_falls_back_to_exe_dir(monkeypatch, tmp_path):
    """便携布局: 资源未打进 _internal 时回退 exe 同级 image/。"""
    exe = tmp_path / "exe"
    logo_dir = exe / "image"
    logo_dir.mkdir(parents=True)
    logo = logo_dir / theme._LOGO_FILES["dark"]
    logo.write_bytes(b"png")
    monkeypatch.setattr(theme, "get_internal_dir", lambda: str(tmp_path / "none"))
    monkeypatch.setattr(theme, "get_base_dir", lambda: str(exe))
    assert theme.logo_path("dark") == str(logo)


def test_logo_path_falls_back_to_flat_exe_logo(monkeypatch, tmp_path):
    """兼容旧版便携布局: logo 直接散放在 exe 同级目录。"""
    exe = tmp_path / "exe"
    exe.mkdir()
    logo = exe / theme._LOGO_FILES["light"]
    logo.write_bytes(b"png")
    monkeypatch.setattr(theme, "get_internal_dir", lambda: str(tmp_path / "none"))
    monkeypatch.setattr(theme, "get_base_dir", lambda: str(exe))
    assert theme.logo_path("light") == str(logo)


def test_apply_theme_sets_palette_and_stylesheet(qapp):
    theme.apply_theme(qapp, "dark")
    assert theme.PALETTES["dark"]["window_bg"] in qapp.styleSheet()
    assert qapp.palette().color(qapp.palette().ColorRole.Window).name().lower() \
        == theme.PALETTES["dark"]["window_bg"].lower()
    theme.apply_theme(qapp, "light")
    assert qapp.palette().color(qapp.palette().ColorRole.Window).name().lower() \
        == theme.PALETTES["light"]["window_bg"].lower()


def test_apply_theme_uses_current_when_none(qapp):
    theme.set_theme("dark")
    theme.apply_theme(qapp)
    assert theme.PALETTES["dark"]["window_bg"] in qapp.styleSheet()


def test_toggle_theme():
    assert theme.toggle_theme() == "dark"
    assert theme.get_theme() == "dark"
    assert theme.toggle_theme() == "light"


def _css_block(css: str, selector: str) -> str:
    """返回 stylesheet 中某个选择器的第一条规则块 (含选择器行)。"""
    start = css.index(selector)
    end = css.index("}", start)
    return css[start:end + 1]


def test_scrollbar_width_is_10px():
    """滚动条从 6px 加宽到 10px (横/纵向), handle 圆角与最小尺寸同步。"""
    css = theme.get_stylesheet("light")
    vertical = _css_block(css, "QScrollBar:vertical {")
    assert "width: 10px;" in vertical
    assert "min-height: 40px;" in _css_block(css, "QScrollBar::handle:vertical {")
    horizontal = _css_block(css, "QScrollBar:horizontal {")
    assert "height: 10px;" in horizontal
    assert "min-width: 40px;" in _css_block(
        css, "QScrollBar::handle:horizontal {")
    assert "border-radius: 4px;" in _css_block(
        css, "QScrollBar::handle:vertical {")


def test_scrollbar_hover_does_not_resize_handle():
    """hover 只提亮颜色, 不再用无效的 handle width 变化。"""
    css = theme.get_stylesheet("light")
    hover = _css_block(css, "QScrollBar::handle:vertical:hover {")
    assert "width:" not in hover
    assert "background:" in hover


def test_native_combo_arrow_disabled():
    """原生下拉箭头关闭 (由 WheelGuardComboBox 自绘三角)。"""
    css = theme.get_stylesheet("light")
    arrow = _css_block(css, "QComboBox::down-arrow {")
    assert "image: none;" in arrow
    assert "border-left" not in arrow
    assert "border-top" not in arrow


def test_hint_spacing_tightened():
    """注释框 margin/padding 收紧 (单控件行后不再有大段留白)。"""
    css = theme.get_stylesheet("light")
    info = _css_block(css, "QLabel#hint_info {")
    assert "margin: 0;" in info
    assert "padding: 0 2px;" in info
    warn = _css_block(css, "QLabel#hint_warning {")
    assert "padding: 6px 10px;" in warn
    assert "margin: 2px 0;" in warn
    tip = _css_block(css, "QLabel#hint_tip {")
    assert "padding: 6px 10px;" in tip
    assert "margin: 2px 0;" in tip
