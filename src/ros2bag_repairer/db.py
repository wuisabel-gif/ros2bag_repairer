"""SQLite-level recovery helpers for rosbag2 ``.db3`` files."""
from __future__ import annotations

import shutil
import sqlite3
import subprocess
from pathlib import Path


def checkpoint_wal(db_path: Path) -> bool:
    """Fold a leftover ``-wal`` file back into the database.

    A recorder killed mid-write can leave a ``<bag>_0.db3-wal`` next to the
    database; the committed messages live there until checkpointed. Returns
    True if a WAL was present and merged.
    """
    wal = db_path.with_name(db_path.name + "-wal")
    if not wal.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.commit()
    finally:
        conn.close()
    return True


def integrity_ok(db_path: Path) -> bool:
    """Return True if the database opens and passes ``PRAGMA integrity_check``."""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return False
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        return bool(row) and row[0] == "ok"
    except sqlite3.DatabaseError:
        return False
    finally:
        conn.close()


def recover(db_path: Path, out_path: Path) -> None:
    """Salvage a corrupt ``.db3`` into ``out_path`` using the sqlite3 CLI.

    Tries ``.recover`` first (rebuilds from b-tree leaves, tolerant of
    corruption) and falls back to ``.dump``. Raises if neither produces a
    database that passes an integrity check.
    """
    sqlite_cli = shutil.which("sqlite3")
    if sqlite_cli is None:
        raise RuntimeError(
            "the sqlite3 command-line tool is required to recover a corrupt .db3"
        )
    last_error = ""
    for command in (".recover", ".dump"):
        try:
            dump = subprocess.run(
                [sqlite_cli, str(db_path), command],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        except subprocess.CalledProcessError as exc:
            last_error = exc.stderr or str(exc)
            continue
        if not dump.strip():
            continue
        if out_path.exists():
            out_path.unlink()
        load = subprocess.run(
            [sqlite_cli, str(out_path)],
            input=dump,
            text=True,
            capture_output=True,
        )
        if load.returncode == 0 and integrity_ok(out_path):
            return
        last_error = load.stderr or last_error
    raise RuntimeError(f"could not recover {db_path.name}: {last_error}".strip())
