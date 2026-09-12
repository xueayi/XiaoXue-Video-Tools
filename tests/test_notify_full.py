# -*- coding: utf-8 -*-
"""notify.py 覆盖测试 (mock requests)。"""

import pytest

import src.notify as notify
from src.notify import send_feishu_notification, send_webhook_notification


class FakeResp:
    def __init__(self, status_code=200, payload=None, text="raw"):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


@pytest.fixture
def post_log(monkeypatch):
    calls = []

    def install(response):
        def fake_post(url, **kw):
            calls.append((url, kw))
            return response
        monkeypatch.setattr(notify.requests, "post", fake_post)

    install(FakeResp(200, {"code": 0}))
    return calls


def test_feishu_success(monkeypatch):
    calls = []
    monkeypatch.setattr(notify.requests, "post",
                        lambda url, **kw: calls.append(url) or
                        FakeResp(200, {"code": 0}))
    assert send_feishu_notification("https://hook", "标题", "内容") is True


def test_feishu_empty_url():
    assert send_feishu_notification("", "t", "c") is False


def test_feishu_api_error(monkeypatch):
    monkeypatch.setattr(notify.requests, "post",
                        lambda url, **kw: FakeResp(200, {"code": 19001}))
    assert send_feishu_notification("https://hook", "t", "c") is False


def test_feishu_http_error(monkeypatch):
    monkeypatch.setattr(notify.requests, "post",
                        lambda url, **kw: FakeResp(500, None, "oops"))
    assert send_feishu_notification("https://hook", "t", "c") is False


def test_feishu_timeout(monkeypatch):
    import requests as requests_mod

    def raise_timeout(url, **kw):
        raise requests_mod.exceptions.Timeout()
    monkeypatch.setattr(notify.requests, "post", raise_timeout)
    assert send_feishu_notification("https://hook", "t", "c") is False


def test_feishu_request_exception(monkeypatch):
    import requests as requests_mod

    def raise_err(url, **kw):
        raise requests_mod.exceptions.RequestException("net down")
    monkeypatch.setattr(notify.requests, "post", raise_err)
    assert send_feishu_notification("https://hook", "t", "c") is False


def test_feishu_generic_exception(monkeypatch):
    def raise_err(url, **kw):
        raise RuntimeError("???")
    monkeypatch.setattr(notify.requests, "post", raise_err)
    assert send_feishu_notification("https://hook", "t", "c") is False


def test_webhook_success(monkeypatch):
    monkeypatch.setattr(notify.requests, "post",
                        lambda url, **kw: FakeResp(200, {"ok": 1}))
    assert send_webhook_notification("https://hook",
                                     body_json='{"a": 1}') is True


def test_webhook_empty_url():
    assert send_webhook_notification("") is False


def test_webhook_bad_headers_json():
    assert send_webhook_notification("https://hook",
                                     headers_json="{bad") is False


def test_webhook_bad_body_json():
    assert send_webhook_notification("https://hook",
                                     body_json="{bad") is False


def test_webhook_non_2xx(monkeypatch):
    monkeypatch.setattr(notify.requests, "post",
                        lambda url, **kw: FakeResp(404, None, "nope"))
    assert send_webhook_notification("https://hook", body={"a": 1}) is False


def test_webhook_timeout(monkeypatch):
    import requests as requests_mod

    def raise_timeout(url, **kw):
        raise requests_mod.exceptions.Timeout()
    monkeypatch.setattr(notify.requests, "post", raise_timeout)
    assert send_webhook_notification("https://hook") is False


def test_webhook_request_exception(monkeypatch):
    import requests as requests_mod

    def raise_err(url, **kw):
        raise requests_mod.exceptions.RequestException("x")
    monkeypatch.setattr(notify.requests, "post", raise_err)
    assert send_webhook_notification("https://hook") is False


def test_webhook_generic_exception(monkeypatch):
    def raise_err(url, **kw):
        raise RuntimeError("boom")
    monkeypatch.setattr(notify.requests, "post", raise_err)
    assert send_webhook_notification("https://hook") is False


def test_webhook_default_body_and_headers(monkeypatch):
    calls = []
    monkeypatch.setattr(notify.requests, "post",
                        lambda url, **kw: calls.append(kw) or
                        FakeResp(201, None, "created"))
    assert send_webhook_notification("https://hook") is True
    assert calls[0]["json"] == {}
