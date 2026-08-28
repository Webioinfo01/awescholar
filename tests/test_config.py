"""Tests for CLI config loading."""

import json

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
from pathlib import Path

import pytest

from awescholar import __version__
from awescholar.config import load_config, resolve_agent_config


def test_load_config_defaults_data_json_path_to_none():
    config = load_config(None)

    assert config["data_json_path"] is None


def test_load_config_reads_pipeline_data_json_path(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"pipeline": {"data_json_path": "data/data.json"}}),
        encoding="utf-8",
    )

    config = load_config(str(config_path))

    assert config["data_json_path"] == "data/data.json"


def test_load_config_fails_fast_for_missing_file(tmp_path):
    missing_path = tmp_path / "missing.json"

    with pytest.raises(FileNotFoundError, match="Config file not found"):
        load_config(str(missing_path))


def test_resolve_agent_config_prefixes_agent_model_names():
    config = {
        "model": "openai/global-model",
        "api_key": "global-key",
        "base_url": "https://global.example",
        "model_profiles": {
            "glm": {
                "api_key": "profile-key",
                "base_url": "https://profile.example",
            }
        },
        "agent_models": {
            "reporter": {
                "profile": "glm",
                "name": "glm-5.1",
            }
        },
    }

    model, api_key, base_url = resolve_agent_config(config, "reporter")

    assert model == "openai/glm-5.1"
    assert api_key == "profile-key"
    assert base_url == "https://profile.example"


def test_version_constant_matches_package_metadata():
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    metadata = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    assert __version__ == metadata["project"]["version"]
