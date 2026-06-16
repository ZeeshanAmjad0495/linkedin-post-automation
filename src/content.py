"""Post generation using the Claude API (Anthropic SDK).

Returns a structured object containing the post body, hashtags, an image prompt
(for AI illustrations) and a title/subtitle (for branded cards).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

import anthropic

from .config import Config
from .topics import Topic

AUDIENCE = (
    "QA engineers, SDETs, automation engineers, engineering managers and "
    "developers who care about quality, testing and AI-assisted engineering"
)

# Cached system prompt (large, stable) -> cheap on repeat runs via prompt caching.
# The anti-AI-tell rules below are derived from the "humanizer" guidance so posts
# read like a real engineer wrote them, not a model.
SYSTEM_PROMPT = """You are a senior SDET and QA automation engineer writing your own \
LinkedIn posts. You are not a marketer and not a chatbot. You write the way an \
experienced engineer talks when they actually have something specific and useful to say.

What good looks like:
- A real point of view. React to things, take a position, admit trade-offs and \
uncertainty. First person ("I", "we") is good when it fits.
- Specific and correct. Name real tools (Playwright, Selenium, pytest, Cypress, \
Appium, Postman/Newman, Pact, k6, Locust, Scrapy, requests, Great Expectations, \
GitHub Actions, etc.) and use precise terminology. Never invent APIs, benchmarks, \
or statistics. If you cite a number, keep it modest and clearly framed as typical.
- Concrete. Where it helps, include a SHORT code snippet or a compact before/after \
as plain text (LinkedIn has no code blocks: use indentation and line breaks).
- Varied rhythm. Mix short, punchy sentences with longer ones. Do not make every \
sentence the same shape.

Hard rules. The post must NOT read as AI-generated:
- NO emojis anywhere. None.
- NO em dashes. Use commas, periods, or parentheses.
- NO "AI vocabulary": delve, tapestry, testament, underscore, showcase, pivotal, \
landscape (figurative), vibrant, crucial, seamless, robust (as filler), leverage \
(as a verb), realm, foster, garner, intricate, elevate, unlock, harness, empower, \
game-changer, deep dive, navigate (figurative).
- NO negative-parallelism slogans ("it's not just X, it's Y") and NO tailing \
fragments ("no guessing", "no flaky tests").
- NO forced rule-of-three lists ("faster, cleaner, smarter").
- NO copula avoidance ("serves as", "stands as", "boasts"). Use is / are / has.
- NO superficial "-ing" tails ("...ensuring reliability", "...highlighting the importance").
- NO signposting ("let's dive in", "here's what you need to know") and NO generic \
upbeat conclusions ("the future is bright").
- NO promotional fluff, NO sycophancy. Use straight quotes only, never curly quotes.

Structure:
- Open with a strong, concrete first line that states the actual point, not a teaser.
- Short paragraphs. A tight list with plain dashes is fine when it genuinely helps.
- Body length 900-1700 characters (LinkedIn's hard limit is 3000 including hashtags).

Return ONLY a single JSON object, no prose around it, with EXACTLY these keys:
{
  "post": "the full post body WITHOUT hashtags. Real line breaks. No emojis. Straight quotes only.",
  "hashtags": ["#PascalCaseTag", "..."],   // 3-5 relevant tags, no spaces, no emojis
  "image_prompt": "a specific prompt for a clean, modern, professional tech illustration: flat/editorial style, no text, no logos",
  "image_alt": "a literal, concrete description of what that illustration shows, for screen readers, <= 120 chars, no marketing language",
  "card_title": "a plain, punchy title <= 55 characters, no emojis",
  "card_subtitle": "a one-line supporting subtitle <= 90 characters, no emojis"
}
"""


LINKEDIN_MAX_CHARS = 3000
MIN_BODY_CHARS = 400  # below this, treat the model output as a stub/refusal

# Broad emoji / pictograph / dingbat / variation-selector ranges.
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF"
    "\U00002190-\U000021FF\U00002300-\U000023FF\U0000FE00-\U0000FE0F"
    "\U0001F1E6-\U0001F1FF\U00002000-\U0000200D\U0000203C\U00002049]",
    flags=re.UNICODE,
)

# Curly quotes -> straight; em/en dashes -> comma+space (both are AI tells).
_QUOTE_MAP = {
    "“": '"', "”": '"', "‘": "'", "’": "'",
    "—": ", ", "–": ", ", "…": "...",
}


def _humanize(text: str) -> str:
    """Strip emojis and normalize AI-tell punctuation. Hard guarantee on top of the prompt."""
    if not text:
        return text
    for src, dst in _QUOTE_MAP.items():
        text = text.replace(src, dst)
    text = _EMOJI_RE.sub("", text)
    text = re.sub(r"[ \t]{2,}", " ", text)        # collapse spaces left by removals
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)  # no space before punctuation
    text = re.sub(r" +\n", "\n", text)             # trailing spaces before newlines
    text = re.sub(r"\n{3,}", "\n\n", text)         # cap blank-line runs
    return text.strip()


@dataclass
class PostContent:
    post_text: str          # body + hashtags, ready to publish
    body: str               # body only
    hashtags: list[str]
    image_prompt: str
    card_title: str
    card_subtitle: str
    card_alt: str           # alt text for a branded card (= the title on the card)
    illustration_alt: str   # alt text describing an AI illustration's content
    theme: str
    angle: str


def _extract_json(text: str) -> dict:
    """Best-effort extraction of the JSON object from the model's reply."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9]*\n", "", text)
        text = re.sub(r"\n```\s*$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    # strict=False tolerates the raw newlines the model puts inside the "post"
    # string (we explicitly ask for real line breaks), which strict JSON rejects.
    return json.loads(text, strict=False)


def _clean_hashtags(tags) -> list[str]:
    out: list[str] = []
    seen = set()
    for tag in tags or []:
        # LinkedIn only keeps [A-Za-z0-9_] after '#' and truncates at the first
        # other character, so "#CI/CD" -> "#CI". Strip everything else up front.
        body = re.sub(r"[^0-9A-Za-z_]", "", str(tag).lstrip("#"))
        if not body or body.isdigit():  # all-numeric tags are ignored by LinkedIn
            continue
        tag = "#" + body
        key = tag.lower()
        if key not in seen:
            seen.add(key)
            out.append(tag)
    return out[:6]


def generate_post(cfg: Config, topic: Topic) -> PostContent:
    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)

    user_prompt = (
        f"Write today's LinkedIn post.\n"
        f"Theme: {topic.theme}\n"
        f"Angle: {topic.angle}\n"
        f"Audience: {AUDIENCE}\n\n"
        f"Make it genuinely useful and specific. Return only the JSON object."
    )

    resp = client.messages.create(
        model=cfg.anthropic_model,
        max_tokens=1800,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw = "".join(block.text for block in resp.content if block.type == "text")
    data = _extract_json(raw)

    return assemble(
        body=data.get("post", ""),
        hashtags=data.get("hashtags"),
        card_title=data.get("card_title", topic.theme),
        card_subtitle=data.get("card_subtitle", ""),
        image_prompt=data.get("image_prompt", ""),
        image_alt=data.get("image_alt", ""),
        theme=topic.theme,
        angle=topic.angle,
    )


def assemble(
    *,
    body: str,
    hashtags=None,
    card_title: str = "",
    card_subtitle: str = "",
    image_prompt: str = "",
    image_alt: str = "",
    theme: str = "",
    angle: str = "",
) -> PostContent:
    """Build a validated, humanized PostContent from raw fields.

    Shared by the live generator and the pre-written queue, so both get the same
    emoji-stripping, hashtag sanitization, length floor, and 3000-char ceiling.
    """
    body = _humanize(str(body))
    if not body:
        raise ValueError("Empty post body.")
    # Quality floor: never autonomously publish a stub or a refusal.
    if len(body) < MIN_BODY_CHARS:
        raise ValueError(
            f"Post body is suspiciously short ({len(body)} chars < {MIN_BODY_CHARS}); refusing to publish."
        )

    tags = _clean_hashtags(hashtags)
    post_text = body if not tags else f"{body}\n\n{' '.join(tags)}"

    # Enforce LinkedIn's hard limit: drop hashtags first, then trim the body.
    if len(post_text) > LINKEDIN_MAX_CHARS:
        if len(body) <= LINKEDIN_MAX_CHARS:
            post_text = body
        else:
            cut = body[: LINKEDIN_MAX_CHARS - 1].rsplit(" ", 1)[0].rstrip()
            post_text = cut + "..."

    ct = _humanize(str(card_title or theme))[:60]
    cs = _humanize(str(card_subtitle))[:100]
    alt = _humanize(str(image_alt))[:200]

    return PostContent(
        post_text=post_text,
        body=body,
        hashtags=tags,
        image_prompt=str(image_prompt).strip(),
        card_title=ct,
        card_subtitle=cs,
        card_alt=ct or theme,
        illustration_alt=alt or ct or theme,
        theme=theme,
        angle=angle,
    )
