from __future__ import annotations

import fcntl
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Protocol

import keyring
from cryptography.fernet import Fernet, InvalidToken
from keyring.errors import KeyringError

SERVICE = "garmin-health-sync"
# These are Keychain account labels, not embedded credentials.
TOKEN_ACCOUNT = "oauth-session"  # nosec B105
RENPHO_EMAIL_ACCOUNT = "renpho-email"
RENPHO_PASSWORD_ACCOUNT = "renpho-password"  # nosec B105


class SecretStoreError(RuntimeError):
    """The system secret store could not be used."""


class TokenStore(Protocol):
    def load(self) -> str | None: ...
    def save(self, token: str) -> None: ...
    def delete(self) -> bool: ...


class RenphoStore(Protocol):
    def load(self) -> tuple[str, str] | None: ...
    def save(self, email: str, password: str) -> None: ...
    def delete(self) -> bool: ...


class MacOSKeychainTokenStore:
    """Store only the serialized Garmin OAuth session in macOS Keychain."""

    def load(self) -> str | None:
        try:
            return keyring.get_password(SERVICE, TOKEN_ACCOUNT)
        except KeyringError as exc:
            raise SecretStoreError("Could not read the Garmin session from macOS Keychain") from exc

    def save(self, token: str) -> None:
        try:
            keyring.set_password(SERVICE, TOKEN_ACCOUNT, token)
        except KeyringError as exc:
            raise SecretStoreError("Could not save the Garmin session to macOS Keychain") from exc

    def delete(self) -> bool:
        try:
            if keyring.get_password(SERVICE, TOKEN_ACCOUNT) is None:
                return False
            keyring.delete_password(SERVICE, TOKEN_ACCOUNT)
            return True
        except KeyringError as exc:
            raise SecretStoreError(
                "Could not remove the Garmin session from macOS Keychain"
            ) from exc


class MacOSKeychainRenphoStore:
    """Store RENPHO credentials in macOS Keychain, never in project files."""

    def load(self) -> tuple[str, str] | None:
        try:
            email = keyring.get_password(SERVICE, RENPHO_EMAIL_ACCOUNT)
            password = keyring.get_password(SERVICE, RENPHO_PASSWORD_ACCOUNT)
        except KeyringError as exc:
            raise SecretStoreError("Could not read RENPHO credentials from Keychain") from exc
        return (email, password) if email and password else None

    def save(self, email: str, password: str) -> None:
        try:
            keyring.set_password(SERVICE, RENPHO_EMAIL_ACCOUNT, email)
            keyring.set_password(SERVICE, RENPHO_PASSWORD_ACCOUNT, password)
        except KeyringError as exc:
            raise SecretStoreError("Could not save RENPHO credentials to Keychain") from exc

    def delete(self) -> bool:
        removed = False
        try:
            for account in (RENPHO_EMAIL_ACCOUNT, RENPHO_PASSWORD_ACCOUNT):
                if keyring.get_password(SERVICE, account) is not None:
                    keyring.delete_password(SERVICE, account)
                    removed = True
        except KeyringError as exc:
            raise SecretStoreError("Could not remove RENPHO credentials from Keychain") from exc
        return removed


class EncryptedFileSecretStore:
    """Container-friendly encrypted store; the encryption key is mounted separately."""

    def __init__(self, path: Path, key_path: Path) -> None:
        self.path = path
        try:
            self._cipher = Fernet(key_path.read_bytes().strip())
        except (OSError, ValueError) as exc:
            raise SecretStoreError(
                "Could not read a valid container secret key; see the Docker setup in README.md"
            ) from exc

    def _read(self) -> dict[str, str]:
        try:
            encrypted = self.path.read_bytes()
        except FileNotFoundError:
            return {}
        except OSError as exc:
            raise SecretStoreError("Could not read the encrypted credential store") from exc
        try:
            value = json.loads(self._cipher.decrypt(encrypted))
        except (InvalidToken, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise SecretStoreError(
                "The encrypted credential store is invalid or has the wrong key"
            ) from exc
        if not isinstance(value, dict):
            return {}
        return {str(key): str(item) for key, item in value.items()}

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        """Serialize local credential updates independently of the cloud-upload lock."""
        descriptor: int | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            lock_path = self.path.with_name(f"{self.path.name}.lock")
            descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
            os.fchmod(descriptor, 0o600)
            # Lock a stable sidecar inode: the encrypted document is replaced atomically.
            # Keep this critical section local; no vendor calls or MFA occur inside it.
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        except OSError as exc:
            raise SecretStoreError("Could not lock the encrypted credential store") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def _write(self, values: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._cipher.encrypt(json.dumps(values).encode())
        fd, temporary = tempfile.mkstemp(prefix="credentials-", dir=self.path.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
            os.replace(temporary, self.path)
        except Exception as exc:
            with suppress(OSError):
                os.unlink(temporary)
            raise SecretStoreError("Could not update the encrypted credential store") from exc

    def load_token(self) -> str | None:
        return self._read().get("garmin_token")

    def save_token(self, token: str) -> None:
        """Replace the encrypted Garmin token while retaining other stored credential fields."""
        with self._transaction():
            values = self._read()
            values["garmin_token"] = token
            self._write(values)

    def load_renpho(self) -> tuple[str, str] | None:
        values = self._read()
        email, password = values.get("renpho_email"), values.get("renpho_password")
        return (email, password) if email and password else None

    def save_renpho(self, email: str, password: str) -> None:
        """Replace the RENPHO credential pair within the shared encrypted document."""
        with self._transaction():
            values = self._read()
            values.update(renpho_email=email, renpho_password=password)
            self._write(values)

    def delete_keys(self, *keys: str) -> bool:
        """Remove only the requested credential fields and report whether any existed."""
        with self._transaction():
            values = self._read()
            removed = any(key in values for key in keys)
            for key in keys:
                values.pop(key, None)
            if removed:
                self._write(values)
            return removed


class EncryptedFileTokenStore:
    def __init__(self, backend: EncryptedFileSecretStore) -> None:
        self.backend = backend

    def load(self) -> str | None:
        return self.backend.load_token()

    def save(self, token: str) -> None:
        self.backend.save_token(token)

    def delete(self) -> bool:
        return self.backend.delete_keys("garmin_token")


class EncryptedFileRenphoStore:
    def __init__(self, backend: EncryptedFileSecretStore) -> None:
        self.backend = backend

    def load(self) -> tuple[str, str] | None:
        return self.backend.load_renpho()

    def save(self, email: str, password: str) -> None:
        self.backend.save_renpho(email, password)

    def delete(self) -> bool:
        return self.backend.delete_keys("renpho_email", "renpho_password")


def configured_stores() -> tuple[TokenStore, RenphoStore]:
    """Select Keychain natively and encrypted storage only when explicitly configured."""
    data_dir = os.environ.get("GARMIN_SYNC_DATA_DIR")
    key_file = os.environ.get("GARMIN_SYNC_SECRET_KEY_FILE")
    if bool(data_dir) != bool(key_file):
        raise SecretStoreError(
            "GARMIN_SYNC_DATA_DIR and GARMIN_SYNC_SECRET_KEY_FILE must be configured together"
        )
    if data_dir and key_file:
        backend = EncryptedFileSecretStore(Path(data_dir) / "credentials.enc", Path(key_file))
        return EncryptedFileTokenStore(backend), EncryptedFileRenphoStore(backend)
    return MacOSKeychainTokenStore(), MacOSKeychainRenphoStore()
