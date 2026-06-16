"""Minimal LinkedIn posting client using the official UGC Posts + Assets API.

Requires an OAuth 2.0 access token with the `w_member_social` scope (obtained
via scripts/get_linkedin_token.py). This is the only LinkedIn-sanctioned way to
post on a member's behalf. No scraping or browser automation.

Image flow (LinkedIn "Vector Asset" / register-upload):
  1. POST /v2/assets?action=registerUpload  -> returns an upload URL + asset URN
  2. Upload the image binary to that URL
  3. POST /v2/ugcPosts referencing the asset URN
"""
from __future__ import annotations

import logging

import requests

log = logging.getLogger("bot.linkedin")

BASE = "https://api.linkedin.com/v2"
TIMEOUT = 30


class LinkedInError(RuntimeError):
    pass


class LinkedInAuthError(LinkedInError):
    """401/403 — token expired or missing scope; user must re-authorize."""


class LinkedInClient:
    def __init__(self, access_token: str, author_urn: str):
        self.token = access_token
        self.author_urn = author_urn

    # --- internals ----------------------------------------------------------
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _raise_for(resp: requests.Response, what: str) -> None:
        if resp.status_code in (200, 201):
            return
        snippet = resp.text[:400]
        if resp.status_code in (401, 403):
            raise LinkedInAuthError(
                f"{what} failed ({resp.status_code}). Your access token is likely "
                f"expired or missing the w_member_social scope. Re-run "
                f"scripts/get_linkedin_token.py and update LINKEDIN_ACCESS_TOKEN. "
                f"Details: {snippet}"
            )
        raise LinkedInError(f"{what} failed ({resp.status_code}): {snippet}")

    def _register_upload(self) -> tuple[str, str]:
        body = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": self.author_urn,
                "serviceRelationships": [
                    {"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}
                ],
            }
        }
        resp = requests.post(
            f"{BASE}/assets?action=registerUpload",
            headers=self._headers(),
            json=body,
            timeout=TIMEOUT,
        )
        self._raise_for(resp, "registerUpload")
        value = resp.json()["value"]
        asset = value["asset"]
        upload_url = value["uploadMechanism"][
            "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"
        ]["uploadUrl"]
        return asset, upload_url

    def _upload_binary(self, upload_url: str, data: bytes, mime: str) -> None:
        # The register-upload URL is single-use. Upload the binary with one PUT
        # (LinkedIn's documented `--upload-file` flow). Never retry with a
        # different verb against the same consumed URL — only retry the SAME
        # idempotent PUT, and only on transient 5xx.
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": mime}
        resp: requests.Response | None = None
        for attempt in range(3):
            resp = requests.put(upload_url, headers=headers, data=data, timeout=120)
            if resp.status_code in (200, 201):
                return
            if resp.status_code < 500:
                break  # 4xx won't fix itself; surface it immediately
            log.warning("Image upload got %s (attempt %d/3); retrying.", resp.status_code, attempt + 1)
        assert resp is not None
        self._raise_for(resp, "image upload")

    # --- public API ---------------------------------------------------------
    def create_text_post(self, text: str, visibility: str = "PUBLIC") -> str:
        body = {
            "author": self.author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": visibility},
        }
        resp = requests.post(f"{BASE}/ugcPosts", headers=self._headers(), json=body, timeout=TIMEOUT)
        self._raise_for(resp, "create text post")
        return resp.headers.get("x-restli-id") or resp.json().get("id", "")

    def create_image_post(
        self,
        text: str,
        image_path: str,
        title: str = "",
        alt: str = "",
        visibility: str = "PUBLIC",
    ) -> str:
        asset, upload_url = self._register_upload()
        mime = "image/png" if image_path.lower().endswith(".png") else "image/jpeg"
        with open(image_path, "rb") as fh:
            self._upload_binary(upload_url, fh.read(), mime)

        media_entry = {
            "status": "READY",
            "media": asset,
            "description": {"text": (alt or title)[:200]},
            "title": {"text": (title or "")[:200]},
        }
        body = {
            "author": self.author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "IMAGE",
                    "media": [media_entry],
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": visibility},
        }
        resp = requests.post(f"{BASE}/ugcPosts", headers=self._headers(), json=body, timeout=TIMEOUT)
        self._raise_for(resp, "create image post")
        return resp.headers.get("x-restli-id") or resp.json().get("id", "")
