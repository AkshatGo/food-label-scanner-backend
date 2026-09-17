"""Auth service tests."""

import pytest

from app.database import store
from app.services.auth_service import (
    AuthError,
    login,
    signup,
    update_conditions,
    user_from_token,
)


@pytest.fixture(autouse=True)
def isolate_users(monkeypatch):
    """Fresh in-memory users collection per test."""
    backup = store.users
    store.users = store.InMemoryCollection()
    yield
    store.users = backup


def test_signup_and_login_roundtrip():
    result = signup("user@example.com", "password123")
    assert result["user_id"]
    assert result["token"]

    login_result = login("user@example.com", "password123")
    assert login_result["user_id"] == result["user_id"]


def test_signup_duplicate_email_conflict():
    signup("user@example.com", "password123")
    with pytest.raises(AuthError) as excinfo:
        signup("user@example.com", "otherpass456")
    assert excinfo.value.http_status == 409


def test_signup_short_password_rejected():
    with pytest.raises(AuthError) as excinfo:
        signup("user@example.com", "short")
    assert excinfo.value.http_status == 400


def test_signup_invalid_email_rejected():
    with pytest.raises(AuthError):
        signup("not-an-email", "password123")


def test_login_wrong_password_unauthorized():
    signup("user@example.com", "password123")
    with pytest.raises(AuthError) as excinfo:
        login("user@example.com", "wrongpassword")
    assert excinfo.value.http_status == 401


def test_login_unknown_user_unauthorized():
    with pytest.raises(AuthError) as excinfo:
        login("ghost@example.com", "password123")
    assert excinfo.value.http_status == 401


def test_token_resolves_user():
    result = signup("user@example.com", "password123")
    user = user_from_token(result["token"])
    assert user["email"] == "user@example.com"


def test_invalid_token_rejected():
    with pytest.raises(AuthError):
        user_from_token("garbage.token.value")


def test_conditions_accept_only_supported():
    result = signup("user@example.com", "password123")
    user_id = result["user_id"]
    updated = update_conditions(user_id, ["diabetes", "migraine"])
    assert updated["conditions"] == ["diabetes", "migraine"]

    with pytest.raises(AuthError) as excinfo:
        update_conditions(user_id, ["diabetes", "common cold"])
    assert excinfo.value.http_status == 422
    assert excinfo.value.code == "INVALID_CONDITION"
