"""Tests for JWT authentication."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.auth import create_access_token, verify_token


def test_create_and_verify_token():
    token = create_access_token("test-user")
    payload = verify_token(token)
    assert payload["sub"] == "test-user"
    assert "exp" in payload


def test_invalid_token_raises():
    with pytest.raises(HTTPException) as exc_info:
        verify_token("invalid.token.here")
    assert exc_info.value.status_code == 401


def test_default_subject():
    token = create_access_token()
    payload = verify_token(token)
    assert payload["sub"] == "dashboard"
