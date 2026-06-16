"""Browser posting backend (Playwright), using a reused logged-in session.

Design choice (safer than scripting the password):
  - You log in ONCE by hand with `python -m src.bot --login`. A real browser
    opens; you sign in (handling any 2FA/CAPTCHA yourself). The session is saved
    in a persistent browser profile on disk (browser_profile/).
  - Every scheduled run launches that same profile, already logged in, and posts.
    No password is stored anywhere, and LinkedIn sees a consistent "remembered"
    device instead of a fresh scripted login.

Note: any browser automation is against LinkedIn's User Agreement and carries
account risk. This backend is intended for LOCAL use (launchd). Do NOT use it on
GitHub Actions: the profile holds live session cookies that must never be
committed. Use POST_BACKEND=api for cloud.

LinkedIn's DOM changes often, so selectors below are defensive with fallbacks and
a screenshot is dumped to logs/ on failure for debugging.
"""
from __future__ import annotations

import logging
import os
import re

log = logging.getLogger("bot.browser")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE_DIR = os.path.join(ROOT, "browser_profile")
FAIL_SHOT = os.path.join(ROOT, "logs", "browser_fail.png")
PROOF_SHOT = os.path.join(ROOT, "out", "last_post_proof.png")

LINKEDIN_FEED = "https://www.linkedin.com/feed/"
LINKEDIN_LOGIN = "https://www.linkedin.com/login"
LOGGED_OUT_MARKERS = ("/login", "/authwall", "/checkpoint", "uas/login", "/signup")


class BrowserPostError(RuntimeError):
    pass


class NotLoggedInError(BrowserPostError):
    """The saved session is missing/expired; the user must run --login again."""


def _launch_context(p, headless: bool, channel: str | None):
    os.makedirs(PROFILE_DIR, exist_ok=True)
    return p.chromium.launch_persistent_context(
        PROFILE_DIR,
        headless=headless,
        channel=channel or None,  # "" -> bundled chromium; "chrome" -> system Chrome
        viewport={"width": 1280, "height": 900},
        args=["--disable-blink-features=AutomationControlled"],
    )


def login(channel: str | None = None) -> None:
    """Open a headed browser so the user can sign in once; persist the session."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = _launch_context(p, headless=False, channel=channel)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(LINKEDIN_LOGIN)
        print(
            "\nA browser window opened. Log in to LinkedIn there (including any 2FA "
            "or CAPTCHA).\nWaiting up to 5 minutes for you to reach your feed..."
        )
        try:
            page.wait_for_url("**/feed/**", timeout=300_000)
        except Exception:
            ctx.close()
            raise BrowserPostError(
                "Did not detect the LinkedIn feed within 5 minutes. Re-run --login and "
                "finish signing in."
            )
        page.wait_for_timeout(2000)  # let cookies settle
        ctx.close()
    print("Login captured. Session saved to browser_profile/. You can post now.")


class BrowserPoster:
    def __init__(self, headless: bool = True, channel: str | None = None):
        self.headless = headless
        self.channel = channel

    def post(self, text: str, image_path: str | None = None) -> None:
        from playwright.sync_api import sync_playwright

        if not os.path.isdir(PROFILE_DIR) or not os.listdir(PROFILE_DIR):
            raise NotLoggedInError(
                "No saved browser session found. Run `python -m src.bot --login` first."
            )

        with sync_playwright() as p:
            ctx = _launch_context(p, headless=self.headless, channel=self.channel)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.goto(LINKEDIN_FEED, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(2500)
                self._ensure_logged_in(page)
                self._open_composer(page)
                self._write(page, text)
                if image_path:
                    self._attach(page, image_path)
                self._submit(page)
                page.wait_for_timeout(4000)  # let the post commit
                try:
                    os.makedirs(os.path.dirname(PROOF_SHOT), exist_ok=True)
                    page.screenshot(path=PROOF_SHOT)
                    log.info("Saved post confirmation screenshot -> %s", PROOF_SHOT)
                except Exception:
                    pass
                log.info("Browser post submitted.")
            except Exception:
                self._dump(page)
                raise
            finally:
                ctx.close()

    # --- steps ---------------------------------------------------------------
    @staticmethod
    def _ensure_logged_in(page) -> None:
        if any(marker in page.url for marker in LOGGED_OUT_MARKERS):
            raise NotLoggedInError(
                "LinkedIn session is logged out or challenged. Run "
                "`python -m src.bot --login` to refresh it."
            )

    def _open_composer(self, page) -> None:
        opened = self._click_first(
            page,
            [
                "button.share-box-feed-entry__trigger",
                "[aria-label='Start a post']",
                "button:has-text('Start a post')",
            ],
            required=False,
        )
        if not opened:
            page.get_by_role("button", name=re.compile("start a post", re.I)).first.click(timeout=8000)
        page.wait_for_selector(
            "div.ql-editor[contenteditable='true'], div[role='textbox'][contenteditable='true']",
            timeout=20_000,
        )

    def _write(self, page, text: str) -> None:
        editor = page.locator(
            "div.ql-editor[contenteditable='true'], div[role='textbox'][contenteditable='true']"
        ).first
        editor.click()
        # insert_text writes the text (with newlines/unicode) without firing the
        # key handlers that can hijack characters in a rich editor.
        page.keyboard.insert_text(text)
        page.wait_for_timeout(800)

    def _attach(self, page, image_path: str) -> None:
        inp = page.locator("input[type='file']")
        if not inp.count():
            self._click_first(
                page,
                [
                    "button[aria-label*='photo' i]",
                    "button[aria-label*='media' i]",
                    "button:has-text('Add media')",
                ],
                required=False,
            )
            page.wait_for_selector("input[type='file']", timeout=15_000)
            inp = page.locator("input[type='file']")
        inp.first.set_input_files(image_path)
        page.wait_for_timeout(2500)
        # The media preview shows a Next/Done step before returning to the composer.
        self._click_first(
            page,
            ["button:has-text('Next')", "button:has-text('Done')", "button[aria-label='Continue']"],
            required=False,
        )
        page.wait_for_timeout(1500)

    def _submit(self, page) -> None:
        clicked = self._click_first(
            page,
            [
                "button.share-actions__primary-action",
                "div.share-box_actions button.artdeco-button--primary",
                "button.artdeco-button--primary:has-text('Post')",
            ],
            required=False,
        )
        if not clicked:
            page.get_by_role("button", name=re.compile(r"^post$", re.I)).first.click(timeout=8000)

    # --- helpers -------------------------------------------------------------
    @staticmethod
    def _click_first(page, selectors: list[str], required: bool = True, timeout: int = 8000) -> bool:
        for sel in selectors:
            loc = page.locator(sel).first
            try:
                if loc.count() and loc.is_visible():
                    loc.click(timeout=timeout)
                    return True
            except Exception:
                continue
        if required:
            raise BrowserPostError(f"Could not find/click any of: {selectors}")
        return False

    @staticmethod
    def _dump(page) -> None:
        try:
            os.makedirs(os.path.dirname(FAIL_SHOT), exist_ok=True)
            page.screenshot(path=FAIL_SHOT, full_page=True)
            log.error("Saved failure screenshot -> %s (url: %s)", FAIL_SHOT, page.url)
        except Exception:
            pass
