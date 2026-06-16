"""Lightweight persistent state so topic/angle/image choices rotate over time.

Stored as a small JSON file. On GitHub Actions the workflow commits this file
back to the repo so rotation survives across runs.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field

STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state")
STATE_PATH = os.path.join(STATE_DIR, "state.json")

# How many recent topic keys to remember (avoid repeating these next).
RECENT_MEMORY = 8


@dataclass
class State:
    post_count: int = 0
    image_counter: int = 0
    queue_index: int = 0  # informational: how many queue posts have been published
    recent_topic_keys: list[str] = field(default_factory=list)
    posted_keys: list[str] = field(default_factory=list)  # queue ids already published (no repeats)
    last_post_id: str | None = None
    last_run_iso: str | None = None

    @staticmethod
    def load() -> "State":
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return State(
                post_count=int(data.get("post_count", 0)),
                image_counter=int(data.get("image_counter", 0)),
                queue_index=int(data.get("queue_index", 0)),
                recent_topic_keys=list(data.get("recent_topic_keys", [])),
                posted_keys=list(data.get("posted_keys", [])),
                last_post_id=data.get("last_post_id"),
                last_run_iso=data.get("last_run_iso"),
            )
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            return State()

    def save(self) -> None:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(asdict(self), fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())  # ensure data hits disk before the rename
        os.replace(tmp, STATE_PATH)  # atomic rename of a fully-written temp file

    def mark_topic_used(self, key: str) -> None:
        self.recent_topic_keys.append(key)
        if len(self.recent_topic_keys) > RECENT_MEMORY:
            self.recent_topic_keys = self.recent_topic_keys[-RECENT_MEMORY:]

    def mark_posted(self, key: str) -> None:
        if key not in self.posted_keys:
            self.posted_keys.append(key)
