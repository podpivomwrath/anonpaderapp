"""Вход на сайте через VK ID (bot/web_auth.py, 2026-10-15)."""

from types import SimpleNamespace

from bot import web_auth


def _settings(secret="s3cret", client="123"):
    return SimpleNamespace(vk_miniapp_secret=secret, vk_id_client_id=client)


def test_token_roundtrip_and_tamper():
    s = _settings()
    token = web_auth.make_token(s, 777, now=1000)
    assert web_auth.verify_token(s, token, now=1001) == 777
    uid, exp, sig = token.split(".")
    assert web_auth.verify_token(s, f"778.{exp}.{sig}", now=1001) is None
    assert web_auth.verify_token(_settings(secret="other"), token, now=1001) is None
    assert web_auth.verify_token(s, token, now=1000 + web_auth.SESSION_TTL_SECONDS + 1) is None
    assert web_auth.verify_token(s, "garbage", now=1001) is None


def test_no_secret_no_sessions():
    token = web_auth.make_token(_settings(), 5, now=1)
    assert web_auth.verify_token(_settings(secret=""), token, now=2) is None
