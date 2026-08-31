"""Tests for CLI user-facing behavior."""

import os
import socket
import subprocess
import sys
import time
import tomllib
import urllib.request
from pathlib import Path


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "awescholar.cli", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_help_does_not_load_litellm():
    result = _run_cli("--help")

    combined = result.stdout + result.stderr
    assert result.returncode == 0
    assert "LiteLLM" not in combined
    assert "usage: awescholar" in combined


def test_version_uses_package_version_without_litellm_warning():
    result = _run_cli("-v")
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    metadata = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    combined = result.stdout + result.stderr
    assert result.returncode == 0
    assert combined.strip() == f"awescholar {metadata['project']['version']}"
    assert "LiteLLM" not in combined


def test_init_help_does_not_load_litellm():
    result = _run_cli("init", "--help")

    combined = result.stdout + result.stderr
    assert result.returncode == 0
    assert "LiteLLM" not in combined
    assert "--template" in combined


def test_init_scaffolds_into_target_directory(tmp_path):
    target = tmp_path / "repo"
    result = subprocess.run(
        [sys.executable, "-m", "awescholar.cli", "init", str(target), "--no-serve"],
        capture_output=True, text=True, check=False, cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert (target / "readme.md").exists()
    assert (target / "docs" / "data.json").exists()
    assert "127.0.0.1" not in result.stdout


def test_init_serves_docs_over_http(tmp_path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    target = tmp_path / "repo"
    proc = subprocess.Popen(
        [sys.executable, "-m", "awescholar.cli", "init", str(target), "--port", str(port)],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, cwd=tmp_path,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    try:
        url = None
        for line in proc.stdout:
            if "Local preview: " in line:
                url = line.split("Local preview: ", 1)[1].strip().split()[0]
                break
        assert url, "init output never announced a preview URL"
        for _ in range(50):
            try:
                with urllib.request.urlopen(url, timeout=2) as resp:
                    body = resp.read().decode("utf-8", "replace")
                assert "<html" in body.lower()
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise AssertionError("preview server did not respond")
    finally:
        proc.terminate()
        proc.wait(timeout=15)
    assert (target / "docs" / "index.html").exists()


def test_bind_preview_server_falls_forward_to_next_free_port(tmp_path):
    from awescholar.cli import _bind_preview_server

    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        busy_port = blocker.getsockname()[1]
        server = _bind_preview_server(str(tmp_path), busy_port)
        try:
            assert server.server_address[1] == busy_port + 1
        finally:
            server.server_close()


def test_serve_preview_warns_and_skips_when_all_ports_busy(tmp_path, capsys):
    from awescholar.cli import serve_preview

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        base_port = probe.getsockname()[1]
    blockers = []
    try:
        for candidate in range(base_port, base_port + 10):
            blocker = socket.socket()
            blocker.bind(("127.0.0.1", candidate))
            blocker.listen(1)
            blockers.append(blocker)
        serve_preview(str(tmp_path), port=base_port)
    finally:
        for blocker in blockers:
            blocker.close()
    assert "skipping local preview" in capsys.readouterr().out
