"""Rebuild a rosbag2 ``metadata.yaml`` from the messages in the ``.db3`` file(s).

rosbag2's metadata is fully derivable from the database: the ``topics`` table
gives every topic's name/type/serialization/QoS, and the ``messages`` table
gives the counts and timestamps. We recompute all of it so a bag that lost its
``metadata.yaml`` becomes playable again.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

# Matches the metadata schema written by rosbag2 (Humble) for sqlite3 bags.
METADATA_VERSION = 5


@dataclass
class TopicInfo:
    name: str
    type: str
    serialization_format: str
    offered_qos_profiles: str
    count: int = 0


@dataclass
class FileInfo:
    path: str
    count: int
    start_ns: Optional[int]
    end_ns: Optional[int]


def read_db(db_path: Path):
    """Return (topics_by_id, total_count, start_ns, end_ns) for one ``.db3``."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        topic_columns = {row[1] for row in conn.execute("PRAGMA table_info(topics)")}
        has_qos = "offered_qos_profiles" in topic_columns

        topics: dict[int, TopicInfo] = {}
        for row in conn.execute("SELECT * FROM topics"):
            qos = row["offered_qos_profiles"] if has_qos else ""
            topics[row["id"]] = TopicInfo(
                name=row["name"],
                type=row["type"],
                serialization_format=row["serialization_format"],
                offered_qos_profiles=qos or "",
            )

        total = 0
        start_ns: Optional[int] = None
        end_ns: Optional[int] = None
        for row in conn.execute(
            "SELECT topic_id, COUNT(*) AS c, MIN(timestamp) AS mn, "
            "MAX(timestamp) AS mx FROM messages GROUP BY topic_id"
        ):
            if row["topic_id"] in topics:
                topics[row["topic_id"]].count = row["c"]
            total += row["c"]
            if row["mn"] is not None:
                start_ns = row["mn"] if start_ns is None else min(start_ns, row["mn"])
            if row["mx"] is not None:
                end_ns = row["mx"] if end_ns is None else max(end_ns, row["mx"])

        return topics, total, start_ns, end_ns
    finally:
        conn.close()


def build_metadata(db_files: list[Path], storage_id: str = "sqlite3") -> dict:
    """Build the metadata dict for one or more (split) ``.db3`` files."""
    merged: dict[str, TopicInfo] = {}
    files: list[FileInfo] = []
    total = 0
    start_ns: Optional[int] = None
    end_ns: Optional[int] = None

    for db_path in sorted(db_files):
        topics, file_total, file_start, file_end = read_db(db_path)
        total += file_total
        if file_start is not None:
            start_ns = file_start if start_ns is None else min(start_ns, file_start)
        if file_end is not None:
            end_ns = file_end if end_ns is None else max(end_ns, file_end)
        for info in topics.values():
            if info.name not in merged:
                merged[info.name] = TopicInfo(
                    info.name,
                    info.type,
                    info.serialization_format,
                    info.offered_qos_profiles,
                    0,
                )
            merged[info.name].count += info.count
        files.append(FileInfo(db_path.name, file_total, file_start, file_end))

    start = start_ns or 0
    duration = (end_ns - start_ns) if (start_ns is not None and end_ns is not None) else 0

    return {
        "rosbag2_bagfile_information": {
            "version": METADATA_VERSION,
            "storage_identifier": storage_id,
            "duration": {"nanoseconds": int(duration)},
            "starting_time": {"nanoseconds_since_epoch": int(start)},
            "message_count": int(total),
            "topics_with_message_count": [
                {
                    "topic_metadata": {
                        "name": t.name,
                        "type": t.type,
                        "serialization_format": t.serialization_format,
                        "offered_qos_profiles": t.offered_qos_profiles,
                    },
                    "message_count": int(t.count),
                }
                for t in merged.values()
            ],
            "compression_format": "",
            "compression_mode": "",
            "relative_file_paths": [f.path for f in files],
            "files": [
                {
                    "path": f.path,
                    "starting_time": {
                        "nanoseconds_since_epoch": int(f.start_ns or 0)
                    },
                    "duration": {
                        "nanoseconds": int(
                            (f.end_ns - f.start_ns)
                            if (f.start_ns is not None and f.end_ns is not None)
                            else 0
                        )
                    },
                    "message_count": int(f.count),
                }
                for f in files
            ],
        }
    }


def write_metadata(metadata: dict, out_path: Path) -> None:
    with out_path.open("w") as stream:
        yaml.safe_dump(metadata, stream, default_flow_style=False, sort_keys=False)
