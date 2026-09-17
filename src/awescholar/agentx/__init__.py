"""AgentX registry support: the agentx-hub snapshot (data/agents-snapshot.json).

Two orientations, one tool — awesome-list projects are paper-oriented (the
archive is a category dict of paper records), the AgentX hub is
project-oriented (the snapshot is a slug-sorted agent list keyed by GitHub
repo). This package ports the former agentx-cli (TypeScript) so awescholar
owns both sides: intake (`updater add --agentx`), the metrics+lifecycle
refresh (`updater enrich --agentx`), paper-meta backfill
(`updater backfill --agentx --fields paper-meta`), and the offline
writer-invariants gate (`verify --agentx`).

Modules:
- policy      — categories, lifecycle constants, tag registry + policy
- transform   — status/retirement/license lifecycle rules (pure)
- papers      — paper clue extraction and S2 title matching (pure)
- snapshot    — snapshot I/O, slugify, merge (sorted, counts, no timestamps)
- validate    — offline snapshot invariants (the CI gate)
- intake      — `updater add --agentx`: single record + --from-json batches
- papers_fill — `updater backfill --agentx`: paperMeta + citation backfill
"""
