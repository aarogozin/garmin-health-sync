import multiprocessing
import stat

import keyring
from cryptography.fernet import Fernet

from garmin_sync.operation_lock import write_lock
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


def _save_paused_token(path, key, read_started, release) -> None:
    """Hold the first process between reading and publishing its token update."""
    class PausedStore(EncryptedFileSecretStore):
        def _read(self):
            values = super()._read()
            read_started.set()
            if not release.wait(15):
                raise RuntimeError("test transaction was not released")
            return values

    PausedStore(path, key).save_token("test-token")


def _save_competing_renpho(path, key, started, finished) -> None:
    store = EncryptedFileSecretStore(path, key)
    started.set()
    store.save_renpho("test@example.com", "test-password")
    finished.set()


def test_encrypted_updates_are_serialized_between_processes(tmp_path) -> None:
    key = tmp_path / "key"
    key.write_bytes(Fernet.generate_key())
    path = tmp_path / "credentials.enc"
    # Spawn exercises separate descriptors and interpreters on both Darwin and Linux.
    context = multiprocessing.get_context("spawn")
    read_started, release = context.Event(), context.Event()
    competing_started, competing_finished = context.Event(), context.Event()
    first = context.Process(target=_save_paused_token, args=(path, key, read_started, release))
    second = context.Process(
        target=_save_competing_renpho,
        args=(path, key, competing_started, competing_finished),
    )
    first.start()
    try:
        assert read_started.wait(10)
        second.start()
        assert competing_started.wait(10)
        # Without a transaction lock, process two writes its RENPHO credentials
        # while process one holds a stale document, and process one erases them.
        assert not competing_finished.wait(0.5)
    finally:
        release.set()
        for process in (first, second):
            if process.pid is not None:
                process.join(10)
                if process.is_alive():
                    process.terminate()
                    process.join(5)
    assert first.exitcode == second.exitcode == 0
    backend = EncryptedFileSecretStore(path, key)
    assert backend.load_token() == "test-token"
    assert backend.load_renpho() == ("test@example.com", "test-password")
    lock = path.with_name("credentials.enc.lock")
    assert stat.S_IMODE(lock.stat().st_mode) == 0o600
    assert lock.read_bytes() == b""
    assert b"test-token" not in path.read_bytes()
    assert b"test-password" not in path.read_bytes()


def test_credential_lock_is_independent_of_cloud_write_lock(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GARMIN_SYNC_DATA_DIR", str(tmp_path))
    key = tmp_path / "key"
    key.write_bytes(Fernet.generate_key())
    backend = EncryptedFileSecretStore(tmp_path / "credentials.enc", key)
    with write_lock():
        backend.save_token("test-token")
        backend.save_renpho("test@example.com", "test-password")
        assert backend.delete_keys("garmin_token")
    assert backend.load_token() is None
    assert backend.load_renpho() == ("test@example.com", "test-password")
