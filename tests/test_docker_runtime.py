from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_compose_separates_private_data_and_visible_archive() -> None:
    compose = (ROOT / "compose.yaml").read_text()
    assert "garmin-sync-data:/data" in compose
    assert "target: /archive" in compose
    assert "GARMIN_SYNC_ARCHIVE_DIR: /archive" in compose
    assert "/var/run/docker.sock" not in compose
    assert '"127.0.0.1:8080:8080"' in compose
    assert "read_only: true" in compose


def test_launcher_uses_private_runtime_and_docker_first_contract() -> None:
    launcher = ROOT / "health-sync"
    content = launcher.read_text()
    assert launcher.stat().st_mode & 0o111
    assert "Garmin Health Sync Docker" in content
    assert "Documents/Garmin Health Sync" in content
    assert "docker compose" in content
    assert "GARMIN_SYNC_ARCHIVE_HOST_DIR" in content
    assert "shasum -a 256" in content
    for command in ("start)", "stop)", "status)", "logs)", "update)", "sync|archive)", "schedule)"):
        assert command in content


def test_host_helper_is_built_outside_the_runtime_image() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "AS host-helper" in dockerfile
    assert "FROM scratch AS host-helper-export" in dockerfile
    runtime = dockerfile[dockerfile.index("FROM python") :]
    assert "golang" not in runtime
