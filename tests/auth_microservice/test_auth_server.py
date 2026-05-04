"""
Tests for authentication helpers and lightweight endpoint validation paths.
"""

import base64
import os
import pytest
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

import auth_server

# This file contains unit tests for the functions and features defined in auth_server.py


def make_stored_password(plain_password: str) -> str:
    """
    Build a PBKDF2 stored password string in the salt:hash format.
    """

    salt = os.urandom(16)  # Generate a random 16-byte salt
    salt_b64 = base64.urlsafe_b64encode(
        salt
    ).decode()  # Encode salt to base64 for storage

    # Create a KDF instance
    kdf = PBKDF2HMAC(  # Use the same settings used by auth_server
        algorithm=auth_server.PBKDF2HMAC_SETTINGS["algorithm"],
        length=auth_server.PBKDF2HMAC_SETTINGS["length"],
        salt=salt,
        iterations=auth_server.PBKDF2HMAC_SETTINGS["iterations"],
        backend=auth_server.PBKDF2HMAC_SETTINGS["backend"],
    )

    # Derive the hash from the plain password using the KDF and encode it to base64 for storage
    hash_bytes = kdf.derive(plain_password.encode("utf-8"))
    hash_b64 = base64.urlsafe_b64encode(hash_bytes).decode()

    return f"{salt_b64}:{hash_b64}"  # Store as "salt:hash"


def test_verify_password_success_and_failure():
    """
    verify_password should accept valid credentials and reject invalid ones.
    """

    pwd = "mysecret"  # Arbitrary test password
    stored = make_stored_password(pwd)  # Create stored password format
    assert (
        auth_server.verify_password(stored, pwd) is True
    )  # Correct password should return True
    assert (
        auth_server.verify_password(stored, "wrong") is False
    )  # Incorrect password should return False


def test_is_input_safe_auth():
    """
    is_input_safe should classify straightforward safe/unsafe payloads.
    """

    # Safe inputs
    assert auth_server.is_input_safe("hello") is True  # Simple safe string
    assert auth_server.is_input_safe(["a", "b"]) is True  # List of safe strings
    assert auth_server.is_input_safe({"k": "v"}) is True  # Dictionary of safe strings

    # Basic SQL keywords
    assert auth_server.is_input_safe("SELECT * FROM users") is False
    assert auth_server.is_input_safe("INSERT INTO accounts VALUES (1, 'hack')") is False
    assert auth_server.is_input_safe("UPDATE users SET admin=1") is False
    assert auth_server.is_input_safe("DELETE FROM logs") is False
    assert auth_server.is_input_safe("TRUNCATE TABLE sessions") is False
    assert auth_server.is_input_safe("ALTER TABLE users ADD COLUMN pwned INT") is False
    assert auth_server.is_input_safe("DROP DATABASE main") is False
    assert auth_server.is_input_safe("EXEC xp_cmdshell") is False
    assert auth_server.is_input_safe("DROP TABLE users") is False
    assert auth_server.is_input_safe(["safe", "DROP TABLE users"]) is False
    assert auth_server.is_input_safe({"k": "DROP TABLE users"}) is False
    assert auth_server.is_input_safe("'; DELETE FROM users; --") is False
    assert auth_server.is_input_safe({"email": "'; DROP TABLE users; --"}) is False

    # Comment-based injections
    assert auth_server.is_input_safe("admin' --") is False
    assert auth_server.is_input_safe("admin' #") is False
    assert auth_server.is_input_safe("admin' /*") is False
    assert auth_server.is_input_safe("admin'--") is False

    # Boolean-based injections
    assert auth_server.is_input_safe("1' OR 1=1 --") is False
    assert auth_server.is_input_safe("' OR 'a'='a") is False
    assert auth_server.is_input_safe("admin' OR '1'='1' --") is False
    assert auth_server.is_input_safe("1' OR '1'='1") is False

    # UNION-based injections
    assert (
        auth_server.is_input_safe("' UNION SELECT username, password FROM admin --")
        is False
    )
    assert auth_server.is_input_safe("1 UNION ALL SELECT NULL, NULL, NULL --") is False
    assert auth_server.is_input_safe("' UNION SELECT * FROM passwords --") is False

    # Time-based blind injections
    assert auth_server.is_input_safe("' OR SLEEP(5) --") is False
    assert auth_server.is_input_safe("admin'; WAITFOR DELAY '00:00:05' --") is False

    # Stacked queries
    assert auth_server.is_input_safe("'; DROP TABLE users; --") is False
    assert auth_server.is_input_safe("admin'; DELETE FROM sessions; --") is False

    # Case variations
    assert auth_server.is_input_safe("select * from users") is False
    assert auth_server.is_input_safe("SeLeCt * FrOm users") is False
    assert auth_server.is_input_safe("drop table users") is False

    # Nested in data structures
    assert auth_server.is_input_safe(["admin", "' OR '1'='1"]) is False
    assert (
        auth_server.is_input_safe({"username": "admin' --", "password": "any"}) is False
    )
    assert auth_server.is_input_safe({"user": {"name": "SELECT * FROM users"}}) is False


def test_health_check():
    """
    Health endpoint should return a success status payload.
    """

    # Use Flask test client to call the health check endpoint
    client = auth_server.auth_api.test_client()
    r = client.get("/health")  # Call health check endpoint

    assert r.status_code == auth_server.STATUS_CODES["ok"]  # Check for 200 status code
    assert r.get_json() == {"status": "ok"}  # Check response content


def test_verify_password_rejects_malformed_storage():
    """
    Malformed stored password data should fail verification safely.
    """

    assert auth_server.verify_password("not-a-valid-format", "secret") is False


def test_is_input_safe_raises_for_unsupported_types():
    """
    Unexpected payload types should raise TypeError as documented.
    """

    with pytest.raises(TypeError):
        auth_server.is_input_safe(123)


def test_login_rejects_empty_json_payload():
    """
    Login endpoint should reject empty JSON bodies before DB lookups.
    """

    client = auth_server.auth_api.test_client()
    response = client.post(
        f"/auth/{auth_server.AUTH_API_VERSION}/login",
        json={},
    )
    assert response.status_code == auth_server.STATUS_CODES["bad_request"]
    assert "error" in response.get_json()


def test_login_rejects_non_json_content_type():
    """
    Login endpoint should require application/json content type.
    """

    client = auth_server.auth_api.test_client()
    response = client.post(
        f"/auth/{auth_server.AUTH_API_VERSION}/login",
        data="email=u@x.com&password=p",
        content_type="application/x-www-form-urlencoded",
    )
    assert response.status_code == auth_server.STATUS_CODES["bad_request"]
