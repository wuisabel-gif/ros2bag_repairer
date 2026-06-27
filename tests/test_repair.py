"""Tests for ros2bag_repairer.

Covers the common case (a bag that lost its metadata.yaml) and the WAL-leftover
case, by building tiny rosbag2-shaped sqlite databases in a temp dir.
"""
import shutil
import sqlite3
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ros2bag_repairer.repairer import repair  # noqa: E402


def _make_bag(tmp_path, name="mybag"):
    bag = tmp_path / name
    bag.mkdir()
    db_path = bag / f"{name}_0.db3"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE topics(
            id INTEGER PRIMARY KEY, name TEXT, type TEXT,
            serialization_format TEXT, offered_qos_profiles TEXT);
        CREATE TABLE messages(
            id INTEGER PRIMARY KEY, topic_id INTEGER, timestamp INTEGER, data BLOB);
        """
    )
    conn.execute(
        "INSERT INTO topics VALUES (1, '/imu', 'sensor_msgs/msg/Imu', 'cdr', '')"
    )
    conn.execute(
        "INSERT INTO topics VALUES (2, '/odom', 'nav_msgs/msg/Odometry', 'cdr', '')"
    )
    for i in range(10):  # /imu timestamps 1000..1900
        conn.execute(
            "INSERT INTO messages(topic_id, timestamp, data) VALUES (1, ?, ?)",
            (1000 + i * 100, b"x"),
        )
    for i in range(5):  # /odom timestamps 1050..1450
        conn.execute(
            "INSERT INTO messages(topic_id, timestamp, data) VALUES (2, ?, ?)",
            (1050 + i * 100, b"y"),
        )
    conn.commit()
    conn.close()
    return bag


def _info(bag):
    meta = yaml.safe_load((bag / "metadata.yaml").read_text())
    return meta["rosbag2_bagfile_information"]


def test_rebuilds_missing_metadata(tmp_path):
    bag = _make_bag(tmp_path)
    assert not (bag / "metadata.yaml").exists()

    report = repair(bag)

    info = _info(bag)
    assert info["version"] == 5
    assert info["storage_identifier"] == "sqlite3"
    assert info["message_count"] == 15
    assert info["starting_time"]["nanoseconds_since_epoch"] == 1000
    assert info["duration"]["nanoseconds"] == 900  # 1900 - 1000
    assert info["relative_file_paths"] == ["mybag_0.db3"]
    counts = {
        t["topic_metadata"]["name"]: t["message_count"]
        for t in info["topics_with_message_count"]
    }
    assert counts == {"/imu": 10, "/odom": 5}
    assert report.message_count == 15


def test_output_dir_leaves_original_untouched(tmp_path):
    bag = _make_bag(tmp_path)
    out = tmp_path / "fixed"

    repair(bag, output=out)

    assert (out / "metadata.yaml").exists()
    assert (out / "mybag_0.db3").exists()
    assert not (bag / "metadata.yaml").exists()  # original dir untouched


def test_checkpoints_leftover_wal(tmp_path):
    src = _make_bag(tmp_path, name="src")
    src_db = src / "src_0.db3"
    # Put the db in WAL mode (autocheckpoint off) and write an extra row, so the
    # 16th message lives only in the -wal.
    conn = sqlite3.connect(str(src_db))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA wal_autocheckpoint=0")
    conn.execute(
        "INSERT INTO messages(topic_id, timestamp, data) VALUES (1, 2000, 'z')"
    )
    conn.commit()

    # While the connection is still open (WAL not checkpointed), copy the files
    # out — this is what a recorder killed mid-write leaves on disk.
    crashed = tmp_path / "crashed"
    crashed.mkdir()
    dst_db = crashed / "crashed_0.db3"
    shutil.copy(str(src_db), str(dst_db))
    for suffix in ("-wal", "-shm"):
        side = Path(str(src_db) + suffix)
        if side.exists():
            shutil.copy(str(side), str(dst_db) + suffix)
    conn.close()

    assert Path(str(dst_db) + "-wal").exists()  # leftover WAL present

    report = repair(crashed)

    assert "crashed_0.db3" in report.wal_checkpointed
    assert _info(crashed)["message_count"] == 16
