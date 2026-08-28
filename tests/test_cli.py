"""Tests for CLI user-facing behavior."""

import subprocess
import sys
import tomllib
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
