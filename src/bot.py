"""Orchestrator: pick topic -> write post -> make image -> publish -> save state.

Run:
  python -m src.bot                 # generate + publish one post
  python -m src.bot --dry-run       # generate + save locally, do NOT publish
  python -m src.bot --login         # browser backend: log in once, save session
  python -m src.bot --backend browser
  python -m src.bot --image-mode card
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import logging
import os
import sys

from .config import Config, ConfigError
from .content import assemble, generate_post
from .images import generate_image
from .linkedin import LinkedInAuthError, LinkedInClient, LinkedInError
from .state import State
from .topics import select_topic

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "out")
LOG_DIR = os.path.join(ROOT, "logs")


def _setup_logging() -> logging.Logger:
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger("bot")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    fh = logging.FileHandler(os.path.join(LOG_DIR, "bot.log"))
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="LinkedIn technical auto-poster")
    p.add_argument("--dry-run", action="store_true", help="Generate but do not publish.")
    p.add_argument("--image-mode", choices=["mix", "card", "ai"], help="Override IMAGE_MODE.")
    p.add_argument("--no-image", action="store_true", help="Publish a text-only post.")
    p.add_argument("--backend", choices=["api", "browser"], help="Override POST_BACKEND.")
    p.add_argument(
        "--login",
        action="store_true",
        help="Browser backend only: open a window to log in once and save the session.",
    )
    p.add_argument("--from-file", help="Post from a pre-written queue JSON instead of generating.")
    p.add_argument("--index", type=int, help="Queue entry to post (0-based). Omit to use the rotating pointer.")
    p.add_argument("--publish", action="store_true", help="Force live publishing for this run (overrides DRY_RUN).")
    return p.parse_args(argv)


def _load_queue(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    posts = data["posts"] if isinstance(data, dict) else data
    if not isinstance(posts, list) or not posts:
        raise ValueError(f"Content queue {path} is empty or malformed.")
    return posts


def _entry_key(entry: dict) -> str:
    """Stable identifier for a queue entry, for no-repeat tracking."""
    if entry.get("id"):
        return str(entry["id"])
    return hashlib.sha1(str(entry.get("body", "")).encode("utf-8")).hexdigest()[:12]


def _publish(cfg: Config, log: logging.Logger, content, image) -> str:
    """Publish via the configured backend. Returns a post id/marker. Raises on failure."""
    if cfg.post_backend == "browser":
        from .browser import BrowserPoster

        poster = BrowserPoster(headless=cfg.browser_headless, channel=cfg.browser_channel)
        poster.post(content.post_text, image.path if image else None)
        return "browser-post"

    client = LinkedInClient(cfg.linkedin_access_token, cfg.linkedin_author_urn)
    if image:
        # Alt text must describe what's actually shown: the AI illustration gets
        # its own description; the branded card gets its title.
        alt = content.illustration_alt if image.mode == "ai" else content.card_alt
        return client.create_image_post(
            content.post_text,
            image.path,
            title=content.card_title,
            alt=alt,
            visibility=cfg.post_visibility,
        )
    return client.create_text_post(content.post_text, visibility=cfg.post_visibility)


def run(argv: list[str] | None = None) -> int:
    log = _setup_logging()
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    cfg = Config.load()
    if args.image_mode:
        cfg.image_mode = args.image_mode
    if args.backend:
        cfg.post_backend = args.backend

    # One-time browser login (no content/keys needed).
    if args.login:
        if cfg.post_backend != "browser":
            log.warning("--login only applies to the browser backend; proceeding to log in anyway.")
        from .browser import BrowserPostError, login

        try:
            login(channel=cfg.browser_channel)
            return 0
        except BrowserPostError as exc:
            log.error(str(exc))
            return 1

    dry_run = cfg.dry_run or args.dry_run
    if args.publish:
        dry_run = False
    if not dry_run:
        log.warning("LIVE publishing is enabled — this run will post to your real LinkedIn profile.")

    state = State.load()

    # Choose content source: a pre-written queue, or live generation via Claude.
    queue_path = args.from_file or os.path.join(ROOT, cfg.content_queue)
    use_queue = bool(args.from_file) or (not cfg.anthropic_api_key and os.path.exists(queue_path))

    topic_key = None     # set only when live-generating (drives rotation memory)
    posted_key = None    # set when consuming the queue automatically (marks no-repeat)

    if use_queue:
        try:
            posts = _load_queue(queue_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            log.error("Cannot read content queue %s: %s", queue_path, exc)
            return 2

        if args.index is not None:
            # Manual: post a specific entry (does not affect the no-repeat set).
            entry = posts[args.index % len(posts)]
        else:
            # Automatic: first entry not already published; stop when exhausted.
            already = set(state.posted_keys)
            entry = next((e for e in posts if _entry_key(e) not in already), None)
            if entry is None:
                log.info("All %d queued posts have already been published. Nothing to post.", len(posts))
                return 0
            posted_key = _entry_key(entry)

        try:
            content = assemble(
                body=entry.get("body", ""),
                hashtags=entry.get("hashtags"),
                card_title=entry.get("card_title", ""),
                card_subtitle=entry.get("card_subtitle", ""),
                image_alt=entry.get("image_alt", ""),
                theme=entry.get("theme", ""),
                angle=entry.get("angle", ""),
            )
        except ValueError as exc:
            log.error("Queue entry %r is invalid: %s", entry.get("id"), exc)
            return 1
        log.info(
            "Queue post %s (%d/%d published) | dry_run=%s",
            entry.get("id"), len(state.posted_keys), len(posts), dry_run,
        )
    else:
        try:
            cfg.require_for_content()
        except ConfigError as exc:
            log.error(str(exc))
            return 2
        topic = select_topic(state.recent_topic_keys, state.post_count)
        topic_key = topic.key
        log.info("Topic: %s | Angle: %s | dry_run=%s", topic.theme, topic.angle, dry_run)
        try:
            content = generate_post(cfg, topic)
        except Exception as exc:  # noqa: BLE001
            log.error("Content generation failed: %s", exc)
            return 1

    log.info("Prepared post (%d chars, %d hashtags).", len(content.post_text), len(content.hashtags))

    # 2) Image (optional; failure degrades to text-only, never aborts).
    image = None
    if not args.no_image:
        try:
            image = generate_image(cfg, content, state.image_counter, OUT_DIR)
            log.info("Image ready: %s (%s)", image.path, image.mode)
        except Exception as exc:  # noqa: BLE001
            log.warning("Image step failed entirely (%s); posting text-only.", exc)

    # Always save a local copy of what we generated (useful for review/debug).
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "last_post.txt"), "w", encoding="utf-8") as fh:
        fh.write(content.post_text)

    if dry_run:
        log.info("DRY RUN — not publishing. Preview saved to out/last_post.txt")
        print("\n" + "=" * 70 + "\n" + content.post_text + "\n" + "=" * 70)
        if image:
            print(f"[image: {image.path} ({image.mode})]")
        return 0

    # 3) Publish via the configured backend.
    try:
        cfg.require_for_posting()
    except ConfigError as exc:
        log.error(str(exc))
        return 2

    try:
        post_id = _publish(cfg, log, content, image)
    except LinkedInAuthError as exc:
        log.error(str(exc))
        return 2
    except LinkedInError as exc:
        log.error("Publishing failed: %s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001 - browser backend raises its own error types
        from .browser import NotLoggedInError

        if isinstance(exc, NotLoggedInError):
            log.error(str(exc))  # session needs a re-login
            return 2
        log.error("Publishing failed: %s", exc)
        return 1

    log.info("Published successfully via %s backend. Post ref: %s", cfg.post_backend, post_id)

    # 4) Persist state (only after a real publish).
    state.post_count += 1
    state.image_counter += 1
    if topic_key is not None:
        state.mark_topic_used(topic_key)
    if posted_key is not None:
        state.mark_posted(posted_key)   # never re-post this queue entry
        state.queue_index = len(state.posted_keys)
    state.last_post_id = post_id
    state.last_run_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    state.save()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
