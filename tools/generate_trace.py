#!/usr/bin/env python3
# Copyright 2018 Nico Weber
# Copyright 2024 David Turner
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Converts one (or several) .ninja_log files into chrome's about:tracing format.

Usage:
    ninja -C $BUILDDIR
    generate_trace.py $BUILDDIR/.ninja_log [$BUILDDIR2/.ninja_log...] > trace.json
"""

import json
import os
import argparse
import re
import sys


class Target:
    """Represents a single line read for a .ninja_log file. Start and end times
    are milliseconds."""

    def __init__(self, start, end):
        self.start = start
        self.end = end
        self.targets = []


def read_targets(log, timestamp_delta):
    """Reads all targets from .ninja_log file |log_file|, sorted by start
    time"""
    header = log.readline()
    m = re.search(r"^# ninja log v(\d+)\n$", header)
    assert m, "unrecognized ninja log version %r" % header
    version = int(m.group(1))
    assert 5 <= version <= 6, "unsupported ninja log version %d" % version
    if version == 6:
        # Skip header line
        next(log)

    targets = {}
    for line in log:
        if line.startswith("#"):
            continue
        start, end, _, name, cmdhash = line.strip().split("\t")  # Ignore restat.
        start_ms = int(start) + timestamp_delta
        end_ms = int(end) + timestamp_delta
        targets.setdefault(cmdhash, Target(start_ms, end_ms)).targets.append(name)
    return sorted(targets.values(), key=lambda job: job.start)


class Threads:
    """Tries to reconstruct the parallelism from a .ninja_log"""

    def __init__(self):
        self.workers = []  # Maps thread id to time that thread is occupied for.

    def alloc(self, target):
        """Places target in an available thread, or adds a new thread."""
        for worker in range(len(self.workers)):
            if self.workers[worker] <= target.start:
                self.workers[worker] = target.end
                return worker
        self.workers.append(target.end)
        return len(self.workers) - 1


def log_to_dicts(log, pid, timestamp_delta):
    """Reads a file-like object |log| containing a .ninja_log, and yields one
    about:tracing dict per command found in the log."""
    threads = Threads()
    # Multiply the process number by 1000 to ensure that the recording tids
    # are unique. Otherwise these confuses the trace viewer which sees several
    # threads with overlapping events.
    pid = pid * 1000
    for target in read_targets(log, timestamp_delta):
        tid = pid + threads.alloc(target)
        yield {
            "name": "%0s" % ", ".join(target.targets),
            "cat": "targets",
            "ph": "X",
            "ts": (target.start * 1000),
            "dur": ((target.end - target.start) * 1000),
            "pid": pid,
            "tid": tid,
            "args": {},
        }


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "logs", metavar="NINJA_LOG", nargs="+", help="Path to an input .ninja_log file."
    )

    args = parser.parse_args()

    # Compute the timestamps of all log files.
    log_timestamps = {}
    for log_file in args.logs:
        log_info = os.stat(log_file)
        log_timestamps[log_file] = log_info.st_mtime

    # Compute the minimal log timestamp, which will be used as the base
    # for the final start/end values.
    base_timestamp = min(log_timestamps.values())

    entries = []
    for pid, log_file in enumerate(args.logs):
        timestamp_delta = log_timestamps[log_file] - base_timestamp
        with open(log_file, "r") as log:
            entries += list(log_to_dicts(log, pid, timestamp_delta))
    json.dump(entries, sys.stdout)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
