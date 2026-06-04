import os
import stat

from recetario.infrastructure.security import TokenCipher


def test_roundtrip_and_persistence(tmp_path):
    key = tmp_path / "token.key"
    cipher = TokenCipher(key)

    token = cipher.encrypt("super-secret-refresh-token")
    assert token != "super-secret-refresh-token"

    # A fresh cipher using the same key file decrypts it.
    assert TokenCipher(key).decrypt(token) == "super-secret-refresh-token"


def test_key_file_created_with_owner_only_perms(tmp_path):
    key = tmp_path / "nested" / "token.key"
    TokenCipher(key)
    assert key.exists()
    assert stat.S_IMODE(os.stat(key).st_mode) == 0o600


def test_distinct_keys_cannot_decrypt(tmp_path):
    from cryptography.fernet import InvalidToken

    token = TokenCipher(tmp_path / "a.key").encrypt("x")
    try:
        TokenCipher(tmp_path / "b.key").decrypt(token)
        raised = False
    except InvalidToken:
        raised = True
    assert raised
