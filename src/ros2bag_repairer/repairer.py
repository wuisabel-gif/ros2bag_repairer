"""Repair an incomplete or corrupt rosbag2 (sqlite3) bag."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from . import db
from .metadata import build_metadata, write_metadata


@dataclass
class RepairReport:
    bag_dir: Path
    db_files: List[str] = field(default_factory=list)
    wal_checkpointed: List[str] = field(default_factory=list)
    recovered: List[str] = field(default_factory=list)
    metadata_written: Optional[Path] = None
    message_count: int = 0
    notes: List[str] = field(default_factory=list)


def find_db_files(path: Path):
    """Resolve ``path`` to (bag_dir, [db3, ...])."""
    if path.is_file() and path.suffix == ".db3":
        return path.parent, [path]
    if path.is_dir():
        return path, sorted(path.glob("*.db3"))
    raise FileNotFoundError(f"no bag directory or .db3 file at {path}")


def repair(
    path,
    output=None,
    force_recover: bool = False,
) -> RepairReport:
    """Repair the bag at ``path``.

    Steps, per ``.db3``: checkpoint a leftover WAL, run an integrity check, and
    salvage with sqlite ``.recover`` if it fails (or if ``force_recover``).
    Then rebuild ``metadata.yaml`` from the (recovered) databases.

    With ``output`` set, the repaired bag is written there and the originals are
    left untouched. In place (default), a database that needs recovery is backed
    up to ``<name>.db3.bak`` before being replaced.
    """
    path = Path(path).expanduser().resolve()
    bag_dir, db_files = find_db_files(path)
    if not db_files:
        raise FileNotFoundError(f"no .db3 files found in {bag_dir}")

    in_place = output is None
    out_dir = bag_dir if in_place else Path(output).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    report = RepairReport(bag_dir=bag_dir)
    out_dbs: List[Path] = []

    for src in db_files:
        report.db_files.append(src.name)

        try:
            if db.checkpoint_wal(src):
                report.wal_checkpointed.append(src.name)
        except Exception as exc:  # WAL merge is best-effort
            report.notes.append(f"{src.name}: WAL checkpoint failed: {exc}")

        dst = out_dir / src.name
        if force_recover or not db.integrity_ok(src):
            if dst.resolve() == src.resolve():
                backup = src.with_suffix(".db3.bak")
                if not backup.exists():
                    shutil.copy2(src, backup)
                    report.notes.append(
                        f"{src.name}: backed up original to {backup.name}"
                    )
                tmp = out_dir / (src.name + ".recovered")
                db.recover(src, tmp)
                os.replace(tmp, dst)
            else:
                db.recover(src, dst)
            report.recovered.append(src.name)
        elif dst.resolve() != src.resolve():
            shutil.copy2(src, dst)

        out_dbs.append(dst)

    metadata = build_metadata(out_dbs)
    report.message_count = metadata["rosbag2_bagfile_information"]["message_count"]
    meta_path = out_dir / "metadata.yaml"
    write_metadata(metadata, meta_path)
    report.metadata_written = meta_path
    return report
