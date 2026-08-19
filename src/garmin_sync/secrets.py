from __future__ import annotations

from typing import Protocol

import keyring
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
