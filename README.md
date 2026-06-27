# ros2bag-repairer

[![PyPI version](https://img.shields.io/pypi/v/ros2bag-repairer.svg)](https://pypi.org/project/ros2bag-repairer/)
[![Python versions](https://img.shields.io/pypi/pyversions/ros2bag-repairer.svg)](https://pypi.org/project/ros2bag-repairer/)
[![License](https://img.shields.io/pypi/l/ros2bag-repairer.svg)](LICENSE)

Repair **incomplete or corrupted rosbag2 (sqlite3 `.db3`) recordings** — the
kind of logs left behind when a robot crashes, loses power, or is interrupted
before the recorder can shut down cleanly. Instead of treating those partially
written bags as lost data, this tool reconstructs and recovers what it can
directly from the database using only the Python standard library and the
`sqlite3` CLI, with no ROS 2 installation required.

## What it fixes

| Symptom | What happened | Repair |
| --- | --- | --- |
| `ros2 bag play` can't open the bag | recorder died before writing `metadata.yaml` | rebuild `metadata.yaml` from the messages in the `.db3` |
| messages missing / bag truncated | a `<bag>_0.db3-wal` was never checkpointed | fold the WAL back into the database |
| "database disk image is malformed" | the `.db3` is partially corrupt | salvage with sqlite `.recover` (falls back to `.dump`), backing up the original |

`metadata.yaml` is fully derivable from the database: the `topics` table holds
every topic's name/type/serialization/QoS, and the `messages` table holds the
counts and timestamps. The tool recomputes all of it (version 5, sqlite3),
which is exactly what makes a metadata-less bag playable again.

## Install

```bash
pip install -e .          # from this directory
# or run without installing:
python -m ros2bag_repairer.cli <bag>   # with src/ on PYTHONPATH
```

Requires Python ≥ 3.8, PyYAML, and the `sqlite3` command-line tool (only needed
for the corrupt-database recovery path).

## Use

```bash
# Repair in place (rebuilds metadata.yaml; backs up any db it has to recover):
ros2bag-repair /data/recordings/zed_20260621_225845

# Or a single .db3 file:
ros2bag-repair /data/recordings/zed_20260621_225845/zed_20260621_225845_0.db3

# Write the repaired bag elsewhere, leaving the original untouched:
ros2bag-repair <bag> --output ~/bag_repair/zed_20260621_225845

# Force sqlite .recover even if the integrity check passes:
ros2bag-repair <bag> --force-recover
```

Then play it as usual:

```bash
ros2 bag play /data/recordings/zed_20260621_225845
```

## Library API

```python
from ros2bag_repairer import repair

report = repair("/data/recordings/zed_20260621_225845")
print(report.message_count, report.recovered, report.metadata_written)
```

## How it works

1. `db.checkpoint_wal` — merges a leftover `-wal` into the database.
2. `db.integrity_ok` / `db.recover` — integrity-checks the `.db3` and, if it
   fails, rebuilds it with sqlite `.recover`.
3. `metadata.build_metadata` — reads `topics` + `messages` and recomputes the
   per-topic counts, the start time, and the duration.
4. `repairer.repair` — orchestrates the above and writes `metadata.yaml`.

## Test

```bash
python -m pytest -q          # or: python tests/test_repair.py via pytest
```

## License

Apache-2.0.
