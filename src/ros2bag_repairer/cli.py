"""Command-line entry point: ``ros2bag-repair``."""
from __future__ import annotations

import argparse
import sys

from .repairer import repair


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="ros2bag-repair",
        description=(
            "Repair an incomplete or corrupt rosbag2 (sqlite3) bag: checkpoint a "
            "leftover write-ahead log, recover a malformed .db3, and rebuild "
            "metadata.yaml from the recorded messages."
        ),
    )
    parser.add_argument("bag", help="bag directory, or a single .db3 file")
    parser.add_argument(
        "-o",
        "--output",
        help="write the repaired bag to this directory instead of repairing in place",
    )
    parser.add_argument(
        "--force-recover",
        action="store_true",
        help="run sqlite .recover even if the integrity check passes",
    )
    args = parser.parse_args(argv)

    try:
        report = repair(args.bag, output=args.output, force_recover=args.force_recover)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"repaired bag: {report.bag_dir}")
    print(f"  db files:         {', '.join(report.db_files)}")
    if report.wal_checkpointed:
        print(f"  wal checkpointed: {', '.join(report.wal_checkpointed)}")
    if report.recovered:
        print(f"  recovered:        {', '.join(report.recovered)}")
    print(f"  message count:    {report.message_count}")
    print(f"  metadata:         {report.metadata_written}")
    for note in report.notes:
        print(f"  note: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
