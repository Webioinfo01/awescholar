"""agentx — short-command front end for the AgentX hub registry.

Installing this package provides two console scripts: ``awescholar`` and
``agentx``. This one is a pure argv alias over the AgentX modes of the
awescholar CLI — every command maps onto an existing subcommand, so flags,
defaults and validation are inherited and nothing is re-implemented here.

Command map (vs the deprecated npm ``agentx-hub-cli``)::

    agentx add owner/repo --category <slug> [...]  == awescholar updater add --agentx [...]
    agentx enrich                                  == awescholar updater enrich --agentx
    agentx backfill [--fields ...]                 == awescholar updater backfill --agentx
    agentx validate                                == awescholar verify --agentx

Renames: the old ``snapshot`` became ``enrich`` (it refreshes metrics and
lifecycle, not the file), and ``enrich-papers``/``refresh-citations`` merged
into ``backfill`` fields.
"""

import sys

from .cli import main as awescholar_main

_COMMANDS: dict[str, list[str]] = {
    "add": ["updater", "add", "--agentx"],
    "enrich": ["updater", "enrich", "--agentx"],
    "backfill": ["updater", "backfill", "--agentx"],
    "validate": ["verify", "--agentx"],
}

_USAGE = """\
usage: agentx <command> [options]

commands (run inside an AgentX repo; every flag of the underlying
awescholar command is accepted — agentx <command> --help lists them):
  add owner/repo --category <slug> [--tags "A,B"] [--paper URL]   register an agent
  add --from-json candidates.json                                  batch intake (all-or-nothing)
  enrich                                                           refresh GitHub metrics + lifecycle
  backfill [--fields paper-meta,venue-tags,citations]              paper metadata from Semantic Scholar
  validate                                                         offline snapshot-invariant gate

renamed from the deprecated npm agentx-hub-cli:
snapshot -> enrich, enrich-papers / refresh-citations -> backfill.
The full toolkit (crawler, reader, render, ...) stays under `awescholar --help`.
"""


def build_argv(argv: list[str]) -> list[str] | None:
    """Map an agentx invocation to its awescholar argv, or None if unknown."""
    if argv and argv[0] in _COMMANDS:
        return _COMMANDS[argv[0]] + argv[1:]
    return None


def main() -> int:
    argv = sys.argv[1:]
    mapped = build_argv(argv)
    if mapped is not None:
        return awescholar_main(mapped, prog="agentx")
    if argv and argv[0] in ("-v", "--version"):
        return awescholar_main(["--version"], prog="agentx")
    if argv and argv[0] in ("-h", "--help"):
        print(_USAGE, end="")
        return 0
    print(_USAGE, file=sys.stderr, end="")
    return 2
