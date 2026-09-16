"""Tests for CLI config loading."""

import json

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
from pathlib import Path

import pytest

from awescholar import __version__
from awescholar.config import (
    load_config,
    resolve_agent_config,
    ss_env_api_key,
    warn_missing_ss_key,
)


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


def test_ss_env_api_key_prefers_underscored_name(monkeypatch):
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "key-with-underscore")
    monkeypatch.setenv("SEMANTICSCHOLAR_API_KEY", "key-without-underscore")

    assert ss_env_api_key() == "key-with-underscore"


def test_ss_env_api_key_falls_back_to_legacy_name(monkeypatch):
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    monkeypatch.setenv("SEMANTICSCHOLAR_API_KEY", "legacy-key")

    assert ss_env_api_key() == "legacy-key"


def test_ss_env_api_key_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    monkeypatch.delenv("SEMANTICSCHOLAR_API_KEY", raising=False)

    assert ss_env_api_key() is None


def test_load_config_reads_ss_api_key_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "env-key")
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({}), encoding="utf-8")

    config = load_config(str(config_path))

    assert config["ss_api_key"] == "env-key"


def test_load_config_config_value_beats_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "env-key")
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"semantic_scholar": {"api_key": "config-key"}}),
        encoding="utf-8",
    )

    config = load_config(str(config_path))

    assert config["ss_api_key"] == "config-key"


def test_load_config_reads_ss_api_key_from_user_dotenv(monkeypatch, tmp_path):
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    monkeypatch.delenv("SEMANTICSCHOLAR_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    user_dotenv = tmp_path / ".config" / "awescholar" / ".env"
    user_dotenv.parent.mkdir(parents=True)
    user_dotenv.write_text("SEMANTIC_SCHOLAR_API_KEY=user-key\n", encoding="utf-8")

    config = load_config(None)

    assert config["ss_api_key"] == "user-key"


def test_load_config_project_dotenv_beats_user_dotenv(monkeypatch, tmp_path):
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    monkeypatch.delenv("SEMANTICSCHOLAR_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    (project_dir / ".env").write_text("SEMANTIC_SCHOLAR_API_KEY=project-key\n", encoding="utf-8")
    user_dotenv = tmp_path / "home" / ".config" / "awescholar" / ".env"
    user_dotenv.parent.mkdir(parents=True)
    user_dotenv.write_text("SEMANTIC_SCHOLAR_API_KEY=user-key\n", encoding="utf-8")

    config = load_config(None)

    assert config["ss_api_key"] == "project-key"


def test_load_config_environment_beats_dotenv_files(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "environment-key")
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("SEMANTIC_SCHOLAR_API_KEY=project-key\n", encoding="utf-8")
    user_dotenv = tmp_path / ".config" / "awescholar" / ".env"
    user_dotenv.parent.mkdir(parents=True)
    user_dotenv.write_text("SEMANTIC_SCHOLAR_API_KEY=user-key\n", encoding="utf-8")

    config = load_config(None)

    assert config["ss_api_key"] == "environment-key"


def test_load_config_config_value_beats_dotenv_files(monkeypatch, tmp_path):
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    monkeypatch.delenv("SEMANTICSCHOLAR_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    user_dotenv = tmp_path / ".config" / "awescholar" / ".env"
    user_dotenv.parent.mkdir(parents=True)
    user_dotenv.write_text("SEMANTIC_SCHOLAR_API_KEY=user-key\n", encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"semantic_scholar": {"api_key": "config-key"}}),
        encoding="utf-8",
    )

    config = load_config(str(config_path))

    assert config["ss_api_key"] == "config-key"


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


def test_warn_missing_ss_key_writes_actionable_hint_to_stderr(capsys):
    warn_missing_ss_key()

    err = capsys.readouterr().err
    assert "no Semantic Scholar API key" in err
    assert "anonymous free tier" in err
    assert "SEMANTIC_SCHOLAR_API_KEY" in err


def test_load_config_reads_aweseries_dotenv(monkeypatch, tmp_path):
    """~/.config/aweseries/.env is loaded as the series-wide keyring."""
    home = tmp_path / "home"
    (home / ".config" / "aweseries").mkdir(parents=True)
    (home / ".config" / "aweseries" / ".env").write_text(
        "GITHUB_TOKEN=from-aweseries\nSEMANTIC_SCHOLAR_API_KEY=ss-aweseries\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    config = load_config(None)
    assert config["github_token"] == "from-aweseries"
    assert config["ss_api_key"] == "ss-aweseries"
