import keyring

from garmin_sync.secrets import MacOSKeychainRenphoStore, MacOSKeychainTokenStore


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
