"""Unit tests for app.core.security."""
from datetime import timedelta

import pytest
from jose import jwt

from app.config.settings import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_csrf_token,
    hash_password,
    safe_str_compare,
    verify_password,
)
from tests.conftest import TEST_SETTINGS


# ─── Password hashing ─────────────────────────────────────────────────────────

def test_hash_password_produces_bcrypt_hash():
    h = hash_password("hunter2")
    assert h.startswith("$2b$")


def test_verify_password_correct():
    h = hash_password("correct-horse")
    assert verify_password("correct-horse", h) is True


def test_verify_password_wrong():
    h = hash_password("correct-horse")
    assert verify_password("wrong-password", h) is False


def test_hash_is_non_deterministic():
    """bcrypt should produce different hashes for the same input."""
    assert hash_password("same") != hash_password("same")


# ─── JWT ──────────────────────────────────────────────────────────────────────

def test_create_and_decode_access_token():
    token = create_access_token(
        {"sub": "user-123", "username": "alice"},
        settings=TEST_SETTINGS,
    )
    payload = decode_token(token, settings=TEST_SETTINGS)
    assert payload["sub"] == "user-123"
    assert payload["username"] == "alice"
    assert payload["type"] == "access"


def test_create_and_decode_refresh_token():
    token = create_refresh_token(
        {"sub": "user-456"},
        settings=TEST_SETTINGS,
    )
    payload = decode_token(token, settings=TEST_SETTINGS)
    assert payload["sub"] == "user-456"
    assert payload["type"] == "refresh"


def test_expired_token_raises():
    token = create_access_token(
        {"sub": "x"},
        expires_delta=timedelta(seconds=-1),
        settings=TEST_SETTINGS,
    )
    from app.core.errors import AuthError
    with pytest.raises(AuthError):
        decode_token(token, settings=TEST_SETTINGS)


def test_tampered_token_raises():
    token = create_access_token({"sub": "x"}, settings=TEST_SETTINGS)
    bad = token[:-4] + "xxxx"
    from app.core.errors import AuthError
    with pytest.raises(AuthError):
        decode_token(bad, settings=TEST_SETTINGS)


# ─── CSRF ─────────────────────────────────────────────────────────────────────

def test_generate_csrf_token_is_url_safe_string():
    token = generate_csrf_token()
    assert isinstance(token, str)
    assert len(token) >= 32
    assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" for c in token)


def test_generate_csrf_token_unique():
    assert generate_csrf_token() != generate_csrf_token()


# ─── safe_str_compare ─────────────────────────────────────────────────────────

def test_safe_str_compare_equal():
    assert safe_str_compare("abc", "abc") is True


def test_safe_str_compare_not_equal():
    assert safe_str_compare("abc", "xyz") is False


def test_safe_str_compare_empty():
    assert safe_str_compare("", "") is True
    assert safe_str_compare("a", "") is False
