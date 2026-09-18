"""The agentx entry is a pure alias: these tests pin the argv mapping and the
unknown-command behavior — the underlying commands are covered by their own
tests."""

import sys
from unittest import mock

from awescholar import agentx_cli


def test_build_argv_maps_each_command():
    assert agentx_cli.build_argv(
        ["add", "owner/repo", "--category", "bio-omics", "--tags", "Stanford"]
    ) == ["updater", "add", "--agentx", "owner/repo", "--category", "bio-omics",
          "--tags", "Stanford"]
    assert agentx_cli.build_argv(["add", "--from-json", "c.json"]) == [
        "updater", "add", "--agentx", "--from-json", "c.json"]
    assert agentx_cli.build_argv(["enrich"]) == ["updater", "enrich", "--agentx"]
    assert agentx_cli.build_argv(["backfill", "--fields", "citations"]) == [
        "updater", "backfill", "--agentx", "--fields", "citations"]
    assert agentx_cli.build_argv(["validate"]) == ["verify", "--agentx"]


def test_build_argv_rejects_unknown_and_empty():
    assert agentx_cli.build_argv(["snapshot"]) is None
    assert agentx_cli.build_argv([]) is None


def test_main_delegates_with_agentx_prog():
    with mock.patch.object(agentx_cli, "awescholar_main", return_value=0) as run, \
            mock.patch.object(sys, "argv", ["agentx", "validate"]):
        assert agentx_cli.main() == 0
    run.assert_called_once_with(["verify", "--agentx"], prog="agentx")


def test_main_version_passthrough():
    with mock.patch.object(agentx_cli, "awescholar_main", return_value=0) as run, \
            mock.patch.object(sys, "argv", ["agentx", "-v"]):
        assert agentx_cli.main() == 0
    run.assert_called_once_with(["--version"], prog="agentx")


def test_main_usage_and_nonzero_on_unknown_command(capsys):
    with mock.patch.object(sys, "argv", ["agentx", "snapshot"]):
        assert agentx_cli.main() == 2
    assert "snapshot -> enrich" in capsys.readouterr().err
