"""Desktop notifications (macOS) for unattended runs.

Used so a scheduled (launchd) run that can't post is not silent. The main case
is an expired browser session: the bot fires a "re-login needed" banner so you
know to run `python -m src.bot --login`.

macOS only (uses osascript). No-ops on other platforms or if osascript fails, so
a notification problem never affects the exit status of a run.
"""
from __future__ import annotations

import logging
import platform
import subprocess

log = logging.getLogger("bot.notify")


def desktop(title: str, message: str, sound: str = "Basso") -> None:
    if platform.system() != "Darwin":
        return
    # AppleScript string literals are double-quoted; neutralize embedded quotes.
    t = title.replace('"', "'").replace("\\", "")
    m = message.replace('"', "'").replace("\\", "")
    script = f'display notification "{m}" with title "{t}" sound name "{sound}"'
    try:
        subprocess.run(["osascript", "-e", script], check=False, timeout=10)
    except Exception as exc:  # noqa: BLE001 - never let a banner failure matter
        log.warning("Desktop notification failed: %s", exc)


def relogin_needed(detail: str = "") -> None:
    msg = "LinkedIn session expired. Run:  python -m src.bot --login"
    if detail:
        msg = f"{msg}  ({detail[:80]})"
    desktop("LinkedIn bot: re-login needed", msg)


def post_failed(detail: str) -> None:
    desktop("LinkedIn bot: post failed", detail[:180])
