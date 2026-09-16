"""Configuration loading and model resolution."""

import json
import os
import re
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv


def prefix_model(name: str | None) -> str | None:
    """Prepend 'openai/' if no provider prefix is present."""
    if name and "/" not in name:
        return f"openai/{name}"
    return name


def ss_env_api_key() -> str | None:
    """Read the Semantic Scholar API key from the environment.

    SEMANTIC_SCHOLAR_API_KEY matches the config.json placeholder convention;
    SEMANTICSCHOLAR_API_KEY is kept for backward compatibility.
    """
    return os.getenv("SEMANTIC_SCHOLAR_API_KEY") or os.getenv("SEMANTICSCHOLAR_API_KEY")


def warn_missing_ss_key() -> None:
    """Warn on stderr when no Semantic Scholar API key could be resolved."""
    print(
        "Warning: no Semantic Scholar API key found — using anonymous free tier. "
        "Set SEMANTIC_SCHOLAR_API_KEY, add ~/.config/awescholar/.env, or pass --ss-api-key.",
        file=sys.stderr,
    )


def gh_env_token() -> str | None:
    """Read the GitHub API token from the environment."""
    return os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")


def warn_missing_github_token() -> None:
    """Warn on stderr when no GitHub token could be resolved."""
    print(
        "Warning: no GITHUB_TOKEN found — anonymous rate limits are severe "
        "(60 repo reads/hour, 10 searches/minute). Set GITHUB_TOKEN, add "
        "~/.config/awescholar/.env, or pass --github-token.",
        file=sys.stderr,
    )


def _expand_env_vars(value):
    """Replace ${VAR} patterns with environment variable values."""
    if isinstance(value, str):
        def _replace(match):
            return os.environ.get(match.group(1), "")
        return re.sub(r"\$\{(\w+)\}", _replace, value) or None
    if isinstance(value, list):
        return [_expand_env_vars(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    return value


def _load_dotenv_files() -> None:
    """Load project and user dotenv files without replacing existing values."""
    project_dotenv = find_dotenv(usecwd=True)
    if project_dotenv:
        load_dotenv(project_dotenv)
    load_dotenv(Path.home() / ".config" / "awescholar" / ".env")


def load_config(path: str | None) -> dict:
    """Load config from JSON file, expanding ${ENV_VAR} patterns."""
    _load_dotenv_files()
    raw = {}
    if path:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            raw = _expand_env_vars(json.load(f))

    model = raw.get("model", {})
    ss = raw.get("semantic_scholar", {})
    gh = raw.get("github", {})
    search = raw.get("search", {})
    filt = raw.get("filter", {})
    output = raw.get("output", {})
    pipe = raw.get("pipeline", {})
    model_profiles = raw.get("model_profiles") or {}

    profile_name = model.get("profile")
    if profile_name and profile_name in model_profiles:
        profile = model_profiles[profile_name]
        api_key = profile.get("api_key") or model.get("api_key") or os.getenv("AWESCHOLAR_API_KEY")
        base_url = profile.get("base_url") or model.get("base_url") or os.getenv("AWESCHOLAR_BASE_URL")
    else:
        api_key = model.get("api_key") or os.getenv("AWESCHOLAR_API_KEY")
        base_url = model.get("base_url") or os.getenv("AWESCHOLAR_BASE_URL")

    return {
        "model": prefix_model(model.get("name")) or os.getenv("AWESCHOLAR_MODEL", "gpt-4.1-mini"),
        "api_key": api_key,
        "base_url": base_url,
        "model_profiles": model_profiles,
        "agent_models": raw.get("agent_models"),
        "ss_api_key": ss.get("api_key") or ss_env_api_key(),
        "github_token": gh.get("token") or gh_env_token(),
        "search_query": search.get("query"),
        "fields_of_study": search.get("fields_of_study"),
        "publication_date": search.get("publication_date"),
        "limit_search": search.get("limit", 100),
        "include_abstracts": search.get("include_abstracts", True),
        "limit_filter": filt.get("limit", 20),
        "research_interests": filt.get("research_interests"),
        "db_path": output.get("db_path") or os.getenv("AWESCHOLAR_DB_PATH", "output"),
        "report_filename": output.get("report_filename"),
        "skip_search": pipe.get("skip_search", False),
        "use_updater_json": pipe.get("use_updater_json", False),
        "use_filtered_json": pipe.get("use_filtered_json", False),
        "existing_json_path": pipe.get("existing_json_path"),
        "merge_new_to_old": pipe.get("merge_new_to_old", False),
        "data_json_path": pipe.get("data_json_path"),
        "categories": raw.get("categories"),
    }


def resolve_agent_settings(
    agent_models: dict | None,
    agent_name: str,
    fallback_model: str,
    fallback_key: str | None,
    fallback_url: str | None,
    model_profiles: dict | None = None,
) -> tuple[str, str | None, str | None]:
    """Resolve model, api_key, and base_url for an agent."""
    if agent_models and isinstance(agent_models, dict):
        agent = agent_models.get(agent_name)
        if agent and isinstance(agent, dict):
            model_name = prefix_model(agent.get("name")) or fallback_model
            profile_name = agent.get("profile")
            if profile_name and model_profiles:
                profile = model_profiles.get(profile_name, {})
                api_key = profile.get("api_key") or agent.get("api_key") or fallback_key
                base_url = profile.get("base_url") or agent.get("base_url") or fallback_url
            else:
                api_key = agent.get("api_key") or fallback_key
                base_url = agent.get("base_url") or fallback_url
            return model_name, api_key, base_url
    return fallback_model, fallback_key, fallback_url


def resolve_agent_config(config: dict, agent_name: str) -> tuple[str, str | None, str | None]:
    """Resolve model, api_key, and base_url for an agent from loaded config."""
    return resolve_agent_settings(
        config.get("agent_models"),
        agent_name,
        config["model"],
        config["api_key"],
        config["base_url"],
        model_profiles=config.get("model_profiles"),
    )
