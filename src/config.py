"""Configuration loading and validation.

All secrets and tunables come from environment variables (loaded from a local
.env file in development). Nothing here is ever logged.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # python-dotenv not installed yet; env may still be set by the shell/CI
    pass


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _norm_person_urn(value: str | None) -> str:
    """Accept either a bare member id or a full URN and return a full person URN."""
    if not value:
        return ""
    value = value.strip()
    if not value:
        return ""
    if value.startswith("urn:li:person:"):
        return value
    return f"urn:li:person:{value}"


@dataclass
class Config:
    # Posting backend: "api" (official API) or "browser" (Playwright session)
    post_backend: str
    browser_headless: bool
    browser_channel: str | None

    # Pre-written content queue (used when no Anthropic key is configured)
    content_queue: str

    # LinkedIn
    linkedin_access_token: str
    linkedin_author_urn: str
    linkedin_client_id: str | None
    linkedin_client_secret: str | None
    linkedin_redirect_uri: str
    post_visibility: str

    # Anthropic (content generation)
    anthropic_api_key: str
    anthropic_model: str

    # Image generation
    image_provider: str
    image_mode: str
    openai_api_key: str | None
    openai_image_model: str

    # Branding / behavior
    brand_name: str
    brand_handle: str
    dry_run: bool

    @staticmethod
    def load() -> "Config":
        return Config(
            post_backend=(os.getenv("POST_BACKEND") or "api").strip().lower(),
            browser_headless=_bool(os.getenv("BROWSER_HEADLESS"), True),
            browser_channel=(os.getenv("BROWSER_CHANNEL") or "").strip() or None,
            content_queue=(os.getenv("CONTENT_QUEUE") or "content/month_posts.json").strip(),
            linkedin_access_token=(os.getenv("LINKEDIN_ACCESS_TOKEN") or "").strip(),
            linkedin_author_urn=_norm_person_urn(os.getenv("LINKEDIN_AUTHOR_URN")),
            linkedin_client_id=(os.getenv("LINKEDIN_CLIENT_ID") or "").strip() or None,
            linkedin_client_secret=(os.getenv("LINKEDIN_CLIENT_SECRET") or "").strip() or None,
            linkedin_redirect_uri=(os.getenv("LINKEDIN_REDIRECT_URI") or "http://localhost:8000/callback").strip(),
            post_visibility=(os.getenv("POST_VISIBILITY") or "PUBLIC").strip().upper(),
            anthropic_api_key=(os.getenv("ANTHROPIC_API_KEY") or "").strip(),
            anthropic_model=(os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-4-6").strip(),
            image_provider=(os.getenv("IMAGE_PROVIDER") or "openai").strip().lower(),
            image_mode=(os.getenv("IMAGE_MODE") or "mix").strip().lower(),
            openai_api_key=(os.getenv("OPENAI_API_KEY") or "").strip() or None,
            openai_image_model=(os.getenv("OPENAI_IMAGE_MODEL") or "gpt-image-1").strip(),
            brand_name=(os.getenv("BRAND_NAME") or "").strip(),
            brand_handle=(os.getenv("BRAND_HANDLE") or "").strip(),
            # Fail safe: if DRY_RUN is unset, do NOT publish. Live posting must be
            # an explicit opt-in (DRY_RUN=false), so a missing/blank env never
            # results in an accidental irreversible post to a real profile.
            dry_run=_bool(os.getenv("DRY_RUN"), True),
        )

    # --- validation helpers -------------------------------------------------
    def require_for_content(self) -> None:
        if not self.anthropic_api_key:
            raise ConfigError(
                "ANTHROPIC_API_KEY is not set. Add it to your .env file "
                "(get one at https://console.anthropic.com/)."
            )

    def require_for_posting(self) -> None:
        if self.post_backend == "browser":
            # The browser backend authenticates via a saved session, not API
            # creds. Session presence is validated when the browser launches.
            return
        if self.post_backend != "api":
            raise ConfigError("POST_BACKEND must be 'api' or 'browser'.")
        missing = []
        if not self.linkedin_access_token:
            missing.append("LINKEDIN_ACCESS_TOKEN")
        if not self.linkedin_author_urn or self.linkedin_author_urn == "urn:li:person:":
            missing.append("LINKEDIN_AUTHOR_URN")
        if missing:
            raise ConfigError(
                "Missing required LinkedIn settings: "
                + ", ".join(missing)
                + ". Run `python scripts/get_linkedin_token.py` to obtain them, "
                "then add them to .env."
            )
        if self.post_visibility not in ("PUBLIC", "CONNECTIONS"):
            raise ConfigError("POST_VISIBILITY must be PUBLIC or CONNECTIONS.")

    @property
    def wants_ai_images(self) -> bool:
        return self.image_mode in ("mix", "ai")
