# LinkedIn Technical Auto-Poster

Automatically writes and publishes a polished, technical LinkedIn post — on
topics like **Test Automation, SDET, QA automation, web scraping, AI for QA Ops,
and AI-driven development** — with a generated **image** (branded title card or
AI illustration) and relevant **hashtags**.

- ✍️ Posts written by Claude (Anthropic API) — specific, professional, no fluff.
- 🖼️ Images: free branded title cards (Pillow) + optional AI illustrations (OpenAI). `mix` alternates them.
- 🔁 Topic/angle rotation so posts don't repeat.
- 🗓️ Runs **once per day** by default (configurable). Schedule via **macOS launchd** *or* **free GitHub Actions**.
- 🔌 Two posting backends, selected with `POST_BACKEND`:
  - **`api`** — LinkedIn's official API (`w_member_social`). Compliant, cloud-friendly.
  - **`browser`** — Playwright driving a real browser with a session you log into once.

> ⚠️ It posts **autonomously** (no review step), as you chose. Start with
> `DRY_RUN=true` until you're happy with the output, then flip it to `false`.

> 🚨 **Browser backend caveat.** Browser automation violates LinkedIn's User
> Agreement and can get your account restricted or banned. The session-reuse
> design (you log in by hand once; no password stored) lowers the risk but does
> not remove it. Use it **locally only** (launchd) — never on GitHub Actions,
> because the browser profile holds live session cookies that must never leave
> your machine. For cloud/always-on, use `POST_BACKEND=api`.

---

## How it works

```
topics.py → content.py (Claude) → images.py (card | AI) → publish → state.json
                                                            ├─ linkedin.py  (api backend)
                                                            └─ browser.py   (browser backend)
```

`src/bot.py` orchestrates one cycle. The scheduler (launchd or GitHub Actions)
invokes it on a cadence.

---

## Setup

### 0. Install dependencies

```bash
cd linkedin-autopost-bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Then pick a backend in `.env` via `POST_BACKEND`. The browser backend needs
steps **A1–A2** below; the API backend needs steps **1–2**.

---

## Backend A — browser (`POST_BACKEND=browser`)

Reuses a session you log into once. No password is stored.

### A1. Install the browser binary (one-time)

```bash
playwright install chromium
```

### A2. Log in once and save the session

```bash
python -m src.bot --login
```

A Chromium window opens on LinkedIn. Sign in by hand (do any 2FA/CAPTCHA). When
you land on your feed, the window closes and the session is saved to
`browser_profile/` (git-ignored). Re-run this whenever the session expires (the
bot will log a clear "run --login" message when that happens).

Then test without posting, and go live:

```bash
python -m src.bot --dry-run          # writes out/last_post.txt, no posting
# happy? set DRY_RUN=false in .env, then:
python -m src.bot
```

> Tip: if a post fails, set `BROWSER_HEADLESS=false` to watch it run, and check
> `logs/browser_fail.png` (a screenshot saved on failure).

---

## Backend B — official API (`POST_BACKEND=api`)

### 1. Create a LinkedIn Developer app (one-time, free)

1. Go to <https://www.linkedin.com/developers/apps> → **Create app**.
   (You'll need a LinkedIn **Company Page** to associate — creating one is free.)
2. On the app's **Products** tab, request/add:
   - **Sign In with LinkedIn using OpenID Connect**
   - **Share on LinkedIn**  ← this grants the `w_member_social` posting scope
3. On the **Auth** tab:
   - Copy the **Client ID** and **Client Secret** into `.env`.
   - Under **Authorized redirect URLs**, add: `http://localhost:8000/callback`

### 2. Get your access token + author URN

```bash
python scripts/get_linkedin_token.py
```

This opens your browser, you approve, and it writes `LINKEDIN_ACCESS_TOKEN` and
`LINKEDIN_AUTHOR_URN` directly into your `.env` (the token is not printed to the
terminal, and `.env` is locked to `600`).

> Tokens last ~60 days. Re-run this script to renew (you'll get a clear error in
> the logs when it expires).

### 3. Add your API keys to `.env`

- `ANTHROPIC_API_KEY` — required (writes the posts) — <https://console.anthropic.com/>
- `OPENAI_API_KEY` — only if you keep `IMAGE_MODE=mix` or `ai`.
  Set `IMAGE_MODE=card` to skip it entirely (free, no image API).

### 4. Test without posting

```bash
python -m src.bot --dry-run
```

Prints the generated post and saves it to `out/last_post.txt` plus an image in
`out/`. Nothing is published. Inspect both.

### 5. Publish for real

Set `DRY_RUN=false` in `.env`, then:

```bash
python -m src.bot
```

---

## Content source: pre-written queue or live generation

The bot gets each post from one of two places:

- **Pre-written queue** (`content/month_posts.json`) — used automatically whenever
  no `ANTHROPIC_API_KEY` is set. A month of posts is shipped in this file, so the
  bot needs **no API key at runtime**. Each run publishes the first entry that
  hasn't been posted yet and records its `id` in `state/state.json`, so **a post
  is never repeated**. When every entry has been published, a run simply logs
  "nothing to post" and exits cleanly.
- **Live generation** (Claude) — used when `ANTHROPIC_API_KEY` is set.

Useful commands:

```bash
python -m src.bot --from-file content/month_posts.json --dry-run   # preview next post
python -m src.bot --from-file content/month_posts.json --index 4   # post a specific entry
```

Regenerate or extend the queue any time by editing `content/month_posts.json`
(each entry needs `id`, `theme`, `body`, `hashtags`, `card_title`, `card_subtitle`,
`image_alt`). New `id`s are treated as new posts.

## Scheduling

### Option A — macOS (launchd) — your machine

```bash
bash scripts/install_launchd.sh
```

Runs daily at **09:30 local**. Edit the time (or switch to every-6-hours) in
`launchd/com.zeeshan.linkedin-autopost.plist`, then re-run the installer.
Caveat: only fires while your Mac is **awake and online**.

### Option B — GitHub Actions — FREE, always-on

Best if you want it to run even with your Mac off.

1. Create a **private** GitHub repo and push this folder to it.
2. Repo → **Settings → Secrets and variables → Actions → New repository secret**, add:
   `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_AUTHOR_URN`, `ANTHROPIC_API_KEY`, and
   (if using AI images) `OPENAI_API_KEY`.
3. Optionally add **Variables**: `IMAGE_MODE`, `BRAND_NAME`, `POST_VISIBILITY`.
4. The workflow in `.github/workflows/post.yml` runs daily and commits the
   rotation state back. **It does NOT post live until you opt in:** every run is
   a dry run until you add the repository **Variable** `LIVE_POSTING=true`.
   So trigger a first run from the **Actions** tab (**Run workflow**), open the
   run log, read the generated post it prints, and only then set
   `LIVE_POSTING=true` to enable real publishing.

GitHub's free tier (2,000 Actions minutes/month on private repos) is far more
than a daily ~1-minute job needs.

---

## Cost — can this be $0?

| Piece | Cost |
|---|---|
| **Scheduling** (launchd or GitHub Actions) | **Free** |
| **Branded title-card images** (`IMAGE_MODE=card`) | **Free** |
| **Post text** (Claude) | A few cents/month at 1 post/day (cheap, not free) |
| **AI illustrations** (OpenAI, `mix`/`ai`) | ~$0.01–0.04 per image |

**Truly $0 path:** set `IMAGE_MODE=card` (free images) and run on GitHub Actions
(free compute). The only remaining cost is Claude text generation — pennies per
month. New Anthropic accounts include some starter credit. If you want literally
zero spend, swap the text model for a free-tier LLM provider — ask and I'll wire
it in (the content layer is isolated in `src/content.py`).

---

## Configuration reference (`.env`)

| Variable | Purpose |
|---|---|
| `LINKEDIN_ACCESS_TOKEN` | OAuth token with `w_member_social` |
| `LINKEDIN_AUTHOR_URN` | `urn:li:person:...` (the helper prints it) |
| `POST_VISIBILITY` | `PUBLIC` or `CONNECTIONS` |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | Claude content generation |
| `IMAGE_MODE` | `mix` / `card` / `ai` |
| `OPENAI_API_KEY` / `OPENAI_IMAGE_MODEL` | AI illustrations |
| `BRAND_NAME` / `BRAND_HANDLE` | Footer text on title cards |
| `DRY_RUN` | `true` = generate but don't publish |

## CLI flags

```bash
python -m src.bot --dry-run            # don't publish
python -m src.bot --image-mode card    # force a branded card this run
python -m src.bot --no-image           # text-only post
```

## Troubleshooting

- **401/403 on publish** → token expired or missing scope. Re-run
  `scripts/get_linkedin_token.py`, update `.env`.
- **Card looks plain / wrong font** → set `FONT_BOLD_PATH` / `FONT_REGULAR_PATH`
  in `.env` to a `.ttf` on your system.
- **Posting too often hurts reach** → 1/day is intentional. Don't set it below
  that on a real profile.

Logs: `logs/bot.log`.
