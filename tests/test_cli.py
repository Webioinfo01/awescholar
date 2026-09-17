"""Tests for CLI user-facing behavior."""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import tomllib
import urllib.request
from pathlib import Path


def _run_config() -> dict:
    """A load_config() result with every key cmd_run/cmd_digest touch."""
    return {
        "model": "openai/test-model", "api_key": None, "base_url": None,
        "ss_api_key": None, "model_profiles": {}, "agent_models": None,
        "search_query": None, "publication_date": None, "fields_of_study": None,
        "limit_search": 50, "limit_filter": 10, "include_abstracts": True,
        "categories": None, "db_path": "output", "report_filename": None,
        "skip_search": False, "use_updater_json": False, "use_filtered_json": False,
        "existing_json_path": None, "merge_new_to_old": False, "data_json_path": None,
        "research_interests": None,
    }


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


def test_crawler_run_month_derives_dates_output_dir_and_report_name(tmp_path, monkeypatch):
    from awescholar import cli, pipeline

    monkeypatch.chdir(tmp_path)
    captured = {}

    def fake_run_pipeline(**kwargs):
        captured.update(kwargs)
        return {}, "# Report"

    monkeypatch.setattr(pipeline, "run_pipeline", fake_run_pipeline)

    args = argparse.Namespace(
        query="AI agent", month="2026-05", date=None,
        limit_search=None, limit_filter=None, output=None,
    )
    assert cli.cmd_run(args, _run_config()) is None

    assert captured["publication_date_or_year"] == "2026-05-01:2026-05-31"
    assert captured["db_path"] == "month_reports/2605"
    report = tmp_path / "month_reports" / "2605" / "report.md"
    assert report.read_text(encoding="utf-8") == "# Report"


def test_crawler_run_rejects_invalid_month(tmp_path, capsys):
    from awescholar import cli

    args = argparse.Namespace(
        query="AI agent", month="2026-13", date=None,
        limit_search=None, limit_filter=None, output=None,
    )
    assert cli.cmd_run(args, _run_config()) == 1
    assert "invalid month" in capsys.readouterr().err


def test_updater_digest_writes_default_month_path(tmp_path, monkeypatch):
    from awescholar import cli

    monkeypatch.chdir(tmp_path)
    archive = tmp_path / "data.json"
    archive.write_text(
        json.dumps({"AI Agents": [{"doi": "10.1/a", "title": "Alpha", "year": "2026.05"}]}),
        encoding="utf-8",
    )

    args = argparse.Namespace(archive=str(archive), month="2026-05", output=None, no_llm=True)
    assert cli.cmd_digest(args, _run_config()) is None

    out = tmp_path / "month_reports" / "2605" / "digest.md"
    assert "Monthly Research Digest — 2026-05" in out.read_text(encoding="utf-8")


def test_updater_digest_fails_actionably_when_month_has_no_papers(tmp_path, capsys):
    from awescholar import cli

    archive = tmp_path / "data.json"
    archive.write_text(
        json.dumps({"AI Agents": [{"doi": "10.1/a", "title": "Alpha", "year": "2026.04"}]}),
        encoding="utf-8",
    )

    args = argparse.Namespace(archive=str(archive), month="2026-05", output=None, no_llm=True)
    assert cli.cmd_digest(args, _run_config()) == 1
    assert "no papers with year 2026.05" in capsys.readouterr().err


def test_updater_help_lists_only_data_mutation_commands():
    result = _run_cli("updater", "--help")
    combined = result.stdout + result.stderr
    assert result.returncode == 0
    for name in ("search", "add", "update", "dedupe", "enrich", "backfill"):
        assert name in combined
    for gone in ("readme", "counts", "rss", "digest", "export-agentx", "citations"):
        assert gone not in combined


def test_render_help_lists_artifact_commands():
    result = _run_cli("render", "--help")
    combined = result.stdout + result.stderr
    assert result.returncode == 0
    for name in ("readme", "counts", "rss", "digest", "agentx"):
        assert name in combined


def test_backfill_fields_scope_dispatch(tmp_path, monkeypatch):
    from awescholar import backfill as bf
    from awescholar import cli

    archive = tmp_path / "data.json"
    archive.write_text("{}", encoding="utf-8")
    calls = []

    monkeypatch.setattr(bf, "backfill_affiliations",
                        lambda **kw: calls.append("affiliation"))
    monkeypatch.setattr(bf, "backfill_citations",
                        lambda **kw: calls.append("citations") or {"filled_citations": 0, "candidates": 0})

    args = argparse.Namespace(archive=str(archive), fields=["citations"],
                               only=None, no_backup=True)
    cli.cmd_backfill(args, {"ss_api_key": None})
    assert calls == ["citations"]

    args.fields = None
    cli.cmd_backfill(args, {"ss_api_key": None})
    assert calls == ["citations", "affiliation", "citations"]


# ── AgentX mode: updater add --agentx / backfill --agentx / verify --agentx ──

def _agentx_snapshot(path, agents):
    path.write_text(json.dumps(
        {"agents": agents, "counts": {"total": len(agents), "gone": 0}}),
        encoding="utf-8")


def _agentx_args(tmp_path, **kw):
    base = {"archive": str(tmp_path / "data" / "agents-snapshot.json"),
            "agentx": True, "repo": None, "from_json": None, "category": None,
            "name": None, "tags": None, "paper": None, "homepage": None,
            "description": None}
    base.update(kw)
    return argparse.Namespace(**base)


def test_updater_add_agentx_registers_repo(tmp_path, monkeypatch):
    from awescholar import cli
    from awescholar.agentx import intake

    snap = tmp_path / "data" / "agents-snapshot.json"
    snap.parent.mkdir(parents=True)
    _agentx_snapshot(snap, [])
    calls = {}

    def fake_add(archive, repo, **kw):
        calls.update(archive=archive, repo=repo, category=kw.get("category"))
        return {"slug": "x", "repo": repo}

    monkeypatch.setattr(intake, "add_agent", fake_add)
    args = _agentx_args(tmp_path, repo="owner/repo", category="benchmarks",
                        tags="Stanford, NeurIPS")
    assert cli.cmd_add(args, {"github_token": None}) == 0
    assert calls["repo"] == "owner/repo"
    assert calls["category"] == "benchmarks"
    assert calls["archive"] == str(snap)


def test_updater_add_agentx_from_json_dispatch(tmp_path, monkeypatch, capsys):
    from awescholar import cli
    from awescholar.agentx import intake

    snap = tmp_path / "data" / "agents-snapshot.json"
    snap.parent.mkdir(parents=True)
    _agentx_snapshot(snap, [])
    calls = {}
    monkeypatch.setattr(intake, "add_from_json",
                        lambda archive, path, **kw: calls.update(archive=archive) or 0)
    candidate = tmp_path / "candidates.json"
    candidate.write_text('{"agents": []}', encoding="utf-8")
    args = _agentx_args(tmp_path, from_json=str(candidate))
    assert cli.cmd_add(args, {"github_token": None}) == 0
    assert calls["archive"] == str(snap)


def test_updater_add_agentx_requires_repo_or_from_json(tmp_path):
    from awescholar import cli

    args = _agentx_args(tmp_path)
    assert cli.cmd_add(args, {"github_token": None}) == 1


def test_updater_add_paper_mode_still_interactive(tmp_path, monkeypatch):
    from awescholar import cli, record

    called = {}
    monkeypatch.setattr(record, "add_interactive",
                        lambda **kw: called.update(kw))
    args = _agentx_args(tmp_path, agentx=False,
                        archive=str(tmp_path / "data.json"))
    cli.cmd_add(args, {})
    assert called["archive_path"] == str(tmp_path / "data.json")


def test_backfill_agentx_dispatches_paper_meta_and_citations(tmp_path, monkeypatch):
    from awescholar import cli
    from awescholar.agentx import papers_fill

    calls = []
    monkeypatch.setattr(papers_fill, "enrich_papers",
                        lambda *a, **kw: calls.append(("enrich", kw.get("force"))))
    monkeypatch.setattr(papers_fill, "refresh_citations",
                        lambda *a, **kw: calls.append(("refresh", None)))

    args = argparse.Namespace(archive=str(tmp_path / "snap.json"), agentx=True,
                              fields=["paper-meta"], only=["bio"], refresh=True,
                              no_backup=True)
    cli.cmd_backfill(args, {"ss_api_key": None})
    assert calls == [("enrich", True)]

    calls.clear()
    args.fields = ["citations"]
    cli.cmd_backfill(args, {"ss_api_key": None})
    assert calls == [("refresh", None)]

    calls.clear()
    args.fields = None  # default: paper-meta + citations
    args.refresh = False
    cli.cmd_backfill(args, {"ss_api_key": None})
    assert calls == [("enrich", False), ("refresh", None)]


def test_backfill_agentx_rejects_affiliation_field(tmp_path, capsys):
    from awescholar import cli

    args = argparse.Namespace(archive=str(tmp_path / "snap.json"), agentx=True,
                              fields=["affiliation"], only=None, refresh=False,
                              no_backup=True)
    assert cli.cmd_backfill(args, {"ss_api_key": None}) == 1
    assert "affiliation" in capsys.readouterr().err


def test_verify_agentx_passes_clean_snapshot(tmp_path, capsys):
    from awescholar import cli

    snap = tmp_path / "agents-snapshot.json"
    _agentx_snapshot(snap, [{
        "slug": "alpha-agent", "name": "Alpha Agent", "repo": "example/alpha-agent",
        "githubUrl": "https://github.com/example/alpha-agent", "homepage": None,
        "paper": None, "category": "benchmarks", "tags": [],
        "language": "Python", "stars": 1, "pushedAt": "2026-09-01T00:00:00Z",
        "openIssues": 0, "license": "MIT", "description": "d", "status": "active",
        "source": "manual", "sourceUrl": None,
    }])
    args = argparse.Namespace(agentx=True, archive=str(snap))
    assert cli.cmd_verify(args, {}) == 0
    assert "Snapshot OK: 1 agents" in capsys.readouterr().out


def test_verify_agentx_reports_problems_and_exit_code(tmp_path, capsys):
    from awescholar import cli

    snap = tmp_path / "agents-snapshot.json"
    _agentx_snapshot(snap, [{
        "slug": "alpha-agent", "name": "Alpha Agent", "repo": "example/alpha-agent",
        "githubUrl": "https://github.com/example/alpha-agent", "homepage": None,
        "paper": None, "category": "not-a-category", "tags": [],
        "language": "Python", "stars": -1, "pushedAt": None,
        "openIssues": 0, "license": None, "description": None, "status": "active",
    }])
    args = argparse.Namespace(agentx=True, archive=str(snap))
    assert cli.cmd_verify(args, {}) == 1
    out = capsys.readouterr().out
    assert "problem(s)" in out and "unknown category" in out


def test_verify_agentx_requires_flag(tmp_path, capsys):
    from awescholar import cli

    args = argparse.Namespace(agentx=False, archive=str(tmp_path / "x.json"))
    assert cli.cmd_verify(args, {}) == 1
    assert "--agentx" in capsys.readouterr().err


def test_cli_help_lists_verify_command():
    result = _run_cli("--help")
    combined = result.stdout + result.stderr
    assert result.returncode == 0
    assert "verify" in combined
