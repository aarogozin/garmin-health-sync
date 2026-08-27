import json

from garmin_sync.state import SyncState


def test_sync_state_round_trip_and_deduplicates(tmp_path) -> None:
    path = tmp_path / "state.json"
    state = SyncState(path)
    assert state.synced_ids() == set()
    state.mark_synced("a")
    state.mark_synced("a")
    state.mark_synced("b")
    assert state.synced_ids() == {"a", "b"}
    assert json.loads(path.read_text())["renpho_synced_ids"] == ["a", "b"]
    assert path.stat().st_mode & 0o777 == 0o600


def test_activity_state_stores_only_hash(tmp_path) -> None:
    path = tmp_path / "state.json"
    state = SyncState(path)
    state.mark_activity_synced("123456")
    assert state.activity_synced("123456")
    assert "123456" not in path.read_text()
