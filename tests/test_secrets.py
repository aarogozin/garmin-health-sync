import keyring
from cryptography.fernet import Fernet

from garmin_sync.secrets import (
    EncryptedFileRenphoStore,
    EncryptedFileSecretStore,
    EncryptedFileTokenStore,
    MacOSKeychainRenphoStore,
    MacOSKeychainTokenStore,
    configured_stores,
)


def test_keychain_round_trip(monkeypatch) -> None:
    saved: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(
        keyring,
        "set_password",
        lambda service, account, value: saved.__setitem__((service, account), value),
    )
    monkeypatch.setattr(
        keyring, "get_password", lambda service, account: saved.get((service, account))
    )
    monkeypatch.setattr(
        keyring, "delete_password", lambda service, account: saved.pop((service, account))
    )
    store = MacOSKeychainTokenStore()
    store.save("oauth-token")
    assert store.load() == "oauth-token"
    assert store.delete()
    assert store.load() is None


def test_renpho_keychain_round_trip(monkeypatch) -> None:
    saved: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(
        keyring,
        "set_password",
        lambda service, account, value: saved.__setitem__((service, account), value),
    )
    monkeypatch.setattr(
        keyring, "get_password", lambda service, account: saved.get((service, account))
    )
    monkeypatch.setattr(
        keyring, "delete_password", lambda service, account: saved.pop((service, account))
    )
    store = MacOSKeychainRenphoStore()
    store.save("me@example.com", "secret")
    assert store.load() == ("me@example.com", "secret")
    assert store.delete()
    assert store.load() is None


def test_encrypted_file_store_round_trip(tmp_path) -> None:
    key = tmp_path / "key"
    key.write_bytes(Fernet.generate_key())
    backend = EncryptedFileSecretStore(tmp_path / "credentials.enc", key)
    token_store = EncryptedFileTokenStore(backend)
    renpho_store = EncryptedFileRenphoStore(backend)

    token_store.save("private-token")
    renpho_store.save("me@example.com", "private-password")

    raw = (tmp_path / "credentials.enc").read_bytes()
    assert b"private-token" not in raw
    assert b"private-password" not in raw
    assert token_store.load() == "private-token"
    assert renpho_store.load() == ("me@example.com", "private-password")
    assert token_store.delete()
    assert renpho_store.load() == ("me@example.com", "private-password")


def test_configured_stores_use_encrypted_backend(monkeypatch, tmp_path) -> None:
    key = tmp_path / "key"
    key.write_bytes(Fernet.generate_key())
    monkeypatch.setenv("GARMIN_SYNC_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GARMIN_SYNC_SECRET_KEY_FILE", str(key))
    token_store, renpho_store = configured_stores()
    token_store.save("token")
    renpho_store.save("email", "password")
    assert token_store.load() == "token"
    assert renpho_store.load() == ("email", "password")
