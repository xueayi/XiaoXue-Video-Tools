# -*- coding: utf-8 -*-
"""版本解析/比较测试 (M4.2, 自 tests/test_updater.py 迁移)。

迁移映射: 旧 ``test_parse_version`` / ``test_is_newer`` /
``test_is_newer_unparseable`` / ``test_is_dev_version`` 原样保留断言。
"""

import pytest

from src.update.version import is_dev_version, is_newer, parse_version


@pytest.mark.parametrize("v, expect", [
    ("2.1.0", (2, 1, 0, 3, 0)),
    ("v2.1.0", (2, 1, 0, 3, 0)),
    ("2.1.0-beta", (2, 1, 0, 1, 0)),
    ("2.1.0-beta.2", (2, 1, 0, 1, 2)),
    ("2.1.0-rc.1", (2, 1, 0, 2, 1)),
    ("2.1.0-alpha.3", (2, 1, 0, 0, 3)),
    (" 垃圾输入 ", None),
    ("", None),
])
def test_parse_version(v, expect):
    assert parse_version(v) == expect


@pytest.mark.parametrize("remote, local, expect", [
    ("2.2.0", "2.1.0", True),
    ("2.1.0", "2.1.0", False),
    ("2.1.0", "2.2.0", False),
    ("2.1.0", "2.1.0-beta", True),
    ("2.1.0-rc.1", "2.1.0-beta.9", True),
    ("10.0.0", "2.9.9", True),
])
def test_is_newer(remote, local, expect):
    assert is_newer(remote, local) is expect


def test_is_newer_unparseable():
    assert is_newer("garbage", "2.1.0") is False
    assert is_newer("2.1.0", "garbage") is False


def test_is_dev_version():
    assert is_dev_version("2.0.0-dev") is True
    assert is_dev_version("2.1.0") is False
