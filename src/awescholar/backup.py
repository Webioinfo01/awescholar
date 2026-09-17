"""Pre-edit backups that skip files git already protects.

Every mutating command snapshots the archive before writing. Outside git
that copy is the only undo; inside a git repo, a committed-and-unmodified
file is already recoverable from history, so the timestamped copy is litter
— the archive gets a fresh backup file on every run and none of them ever
pays for itself. ``backup_file`` copies only when the working tree differs
from what git holds (or when there is no git repo at all).
"""

import os
import shutil
import subprocess
from datetime import datetime


def _git_clean(path: str) -> bool:
    """True when git holds the file's current bytes: tracked and unmodified.

    Untracked files return False — git holds nothing for them. Outside any
    git repository, False as well.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    name = os.path.basename(path)
    try:
        tracked = subprocess.run(
            ["git", "-C", directory, "ls-files", "--error-unmatch", name],
            capture_output=True,
        )
        if tracked.returncode != 0:
            return False
        unmodified = subprocess.run(
            ["git", "-C", directory, "diff", "--quiet", "--", name],
            capture_output=True,
        )
        return unmodified.returncode == 0
    except OSError:
        return False


def backup_file(path: str, no_backup: bool = False) -> str | None:
    """Snapshot ``path`` to ``<path>.<timestamp>.bak`` unless unnecessary.

    Returns the backup path, or None when nothing was copied (no_backup,
    or the file is git-clean so history already holds it).
    """
    if no_backup:
        return None
    if _git_clean(path):
        return None
    ts = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{path}.{ts}.bak"
    shutil.copy2(path, backup_path)
    return backup_path
