"""Topic + angle library and rotation logic.

The bot picks a (theme, angle) pair each run, avoiding recently used pairs so
the feed stays varied across Test Automation / SDET / QA / scraping / AI topics.
Selection is deterministic given the state (no randomness), which keeps CI runs
reproducible and easy to debug.
"""
from __future__ import annotations

from dataclasses import dataclass

# Core themes requested by the user.
THEMES = [
    "Test Automation",
    "SDET engineering",
    "QA automation strategy",
    "Web scraping & data extraction",
    "Using AI for QA Ops",
    "AI-driven development",
    "CI/CD & test infrastructure",
    "API & contract testing",
]

# Angles applied across themes to keep posts fresh and concrete.
ANGLES = [
    "a practical how-to with a concrete code-level example",
    "a common pitfall and how to avoid it",
    "a tooling deep-dive comparing two popular options",
    "a hard-won lesson / mini case study from real projects",
    "an opinionated 'stop doing X, do Y instead' take",
    "a metrics & ROI angle (what to measure and why)",
    "a 2026 trend and what it means for practitioners",
    "a step-by-step checklist readers can apply today",
    "debugging a flaky/non-deterministic failure",
    "scaling from a small suite to a large, fast one",
]


@dataclass
class Topic:
    theme: str
    angle: str

    @property
    def key(self) -> str:
        # Stable identifier used for de-duplication in state.
        return f"{THEMES.index(self.theme)}:{ANGLES.index(self.angle)}"


def select_topic(recent_keys: list[str], post_count: int) -> Topic:
    """Pick the next (theme, angle) pair.

    Strategy: advance BOTH the theme index and the angle index by one each post.
    Because len(THEMES) and len(ANGLES) differ, consecutive posts get a different
    theme *and* a different angle — maximizing variety across topic areas instead
    of exhausting one theme before moving on. We skip any pair whose key is in the
    recent set (exact-repeat de-duplication), falling back to the base pair if all
    candidates are somehow recent.
    """
    recent = set(recent_keys)
    nt, na = len(THEMES), len(ANGLES)
    for i in range(nt * na):
        c = post_count + i
        candidate = Topic(THEMES[c % nt], ANGLES[c % na])
        if candidate.key not in recent:
            return candidate
    return Topic(THEMES[post_count % nt], ANGLES[post_count % na])
