"""Exercise launcher lifecycle without Docker, browser access, or real user directories."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

LAUNCHER = Path(__file__).resolve().parents[1] / "health-sync"


@pytest.fixture
def runtime(tmp_path: Path) -> tuple[dict[str, str], Path, Path]:
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for name, body in {
        "docker": '#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_DOCKER_CALLS"\n',
        "curl": "#!/bin/sh\nexit 0\n",
        "uname": "#!/bin/sh\necho Linux\n",
    }.items():
        executable = binaries / name
        executable.write_text(body)
        executable.chmod(0o700)
    private = tmp_path / "runtime"
    archive = tmp_path / "Health notes"
    environment = {
        **os.environ,
        "PATH": f"{binaries}:{os.environ['PATH']}",
        "GARMIN_SYNC_RUNTIME_DIR": str(private),
        "GARMIN_SYNC_ARCHIVE_HOST_DIR": str(archive),
        "TEST_DOCKER_CALLS": str(tmp_path / "docker-calls"),
    }
    return environment, private, archive


def invoke(environment: dict[str, str], *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(LAUNCHER), *arguments], env=environment, capture_output=True, text=True, timeout=10
    )


def test_status_does_not_initialize_a_new_key(runtime: tuple[dict[str, str], Path, Path]) -> None:
    environment, private, _ = runtime
    result = invoke(environment, "status")
    assert result.returncode != 0
    assert "start" in result.stderr
    assert not private.exists()


def test_commands_preserve_running_bridge_configuration(
    runtime: tuple[dict[str, str], Path, Path],
) -> None:
    environment, private, archive = runtime
    assert invoke(environment, "start").returncode == 0
    config = private / "compose.env"
    config.write_text(
        config.read_text()
        + "GARMIN_SYNC_HOST_BRIDGE_URL=http://host.docker.internal:12345\n"
        + "GARMIN_SYNC_HOST_BRIDGE_TOKEN=synthetic-test-capability\n"
    )
    before = config.read_bytes()
    key = (private / "secret.key").read_bytes()
    for args in [
        ("status",),
        ("logs",),
        ("sync", "daily"),
        ("archive", "status"),
        ("schedule", "status"),
    ]:
        result = invoke(environment, *args)
        assert result.returncode == 0, result.stderr
        assert config.read_bytes() == before
        assert (private / "secret.key").read_bytes() == key
    assert private.stat().st_mode & 0o777 == 0o700
    assert archive.stat().st_mode & 0o777 == 0o700
    assert (private / "secret.key").stat().st_mode & 0o777 == 0o600
    assert config.stat().st_mode & 0o777 == 0o600
    assert invoke(environment, "update").returncode == 0
    assert (private / "secret.key").read_bytes() == key


def test_invalid_schedule_time_is_rejected_before_request(
    runtime: tuple[dict[str, str], Path, Path],
) -> None:
    environment, _, _ = runtime
    assert invoke(environment, "start").returncode == 0
    result = invoke(environment, "schedule", "install", "24", "0")
    assert result.returncode != 0
    assert "0-23" in result.stderr


def test_start_does_not_replace_a_lost_credential_key(
    runtime: tuple[dict[str, str], Path, Path],
) -> None:
    environment, private, _ = runtime
    assert invoke(environment, "start").returncode == 0
    (private / "secret.key").unlink()
    result = invoke(environment, "start")
    assert result.returncode != 0
    assert "restore" in result.stderr
    assert not (private / "secret.key").exists()
