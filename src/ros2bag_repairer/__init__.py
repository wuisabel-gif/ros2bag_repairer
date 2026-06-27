"""Repair incomplete or corrupt rosbag2 (sqlite3) bags.

The two common failures after a recording crashes:

* the ``metadata.yaml`` was never written, so ``ros2 bag play`` can't open the
  bag even though the ``.db3`` holds all the messages;
* the ``.db3`` was left with an un-checkpointed write-ahead log, or is
  partially corrupt.

This package rebuilds ``metadata.yaml`` straight from the messages in the
``.db3`` and, when needed, folds the WAL back in or salvages a malformed
database with sqlite's ``.recover``. It needs no ROS 2 installation.
"""
from .repairer import RepairReport, repair

__all__ = ["repair", "RepairReport"]
__version__ = "0.1.0"
