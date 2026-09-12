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
    monkeypatch.setattr(theme, "get_base_dir", lambda: str(tmp_path))
    assert theme.logo_path("light") is None


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
