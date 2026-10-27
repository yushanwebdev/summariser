# Summariser

Paste a URL. Firecrawl turns it into markdown, a crewAI crew summarises it, and you can chat with the source.

- **Scrape:** Firecrawl v2 `/scrape` (markdown, main content only)
- **Crew:** `Editorial Summariser` (`scaledown/summarize`) gets the full scraped markdown, as-is, and writes an overview plus key points sized to the article. Falls back to a direct ScaleDown call if the crew fails.
- **Chat:** `google/gemma-4-31b-it:free` over the summary plus source text, with short-term history per session. If it is rate-limited or returns nothing, the request automatically retries the next free model in `CHAT_FALLBACK_MODELS` and reports which one answered.
- **Groundedness badge:** after each answer, `baseten/mammoth-1:free` returns a probability that the source supports the answer via OpenRouter's Decision API.

## Why mammoth doesn't write the chat

`baseten/mammoth-1:free` is a **decision model**, not a text model. It accepts a `state` plus typed `questions` (`noul`, `choice`, `score`) at `POST https://openrouter.ai/api/alpha/decisions` and returns calibrated probabilities with no generated prose. Asking it to answer a chat message would fail, so it is used for what it is for: scoring whether each answer is grounded in the source. Set `MAMMOTH_CONFIDENCE=0` to skip that call.

## Setup

Requires Python 3.10–3.13 and [uv](https://docs.astral.sh/uv/).

```sh
cp .env.example .env      # add your keys
uv sync --python 3.13
uv run uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000.

You need:

- `OPENROUTER_API_KEY` — https://openrouter.ai/keys
- `FIRECRAWL_API_KEY` — https://firecrawl.dev/app/api-keys

`scaledown/summarize` bills at $0.04/M input tokens; the Gemma chat model and mammoth-1 are free tiers.

## Configuration

| Variable | Default | Notes |
| --- | --- | --- |
| `SUMMARISER_MODEL` | `scaledown/summarize` | crewAI summariser agent |
| `CHAT_MODEL` | `google/gemma-4-31b-it:free` | primary chat model |
| `CHAT_FALLBACK_MODELS` | `poolside/laguna-s-2.1:free,dots-studio/dots-3-note-preview:free,recursive/flint-v1.0:free,cohere/north-mini-code:free,openrouter/free` | comma-separated fallbacks |
| `MAMMOTH_MODEL` | `baseten/mammoth-1:free` | groundedness decisions |
| `MAMMOTH_CONFIDENCE` | `1` | `0` disables the badge |
| `MAX_SOURCE_CHARS` | `200000` | scrape truncation |
| `CHAT_CONTEXT_CHARS` | `120000` | source text sent to chat |
| `SESSION_TTL_MINUTES` | `180` | in-memory session lifetime |

## API

- `POST /api/ingest` — `{"url": "https://..."}` → `{session_id, title, url, summary, markdown, mode}`
- `POST /api/chat` — `{"session_id": "...", "message": "..."}` → `{answer, grounded, model}`
- `GET /api/session/{id}` — reload a session
- `GET /api/health` — key and model status

## Deploy

Pushing to `main` runs the tests and then deploys with GitHub Actions:
rsync to `/srv/summariser`, `docker compose up -d --build`, health check on
`http://localhost:8011/api/health`. Required repository secrets:

- `DEPLOY_HOST` — public IP of the Hetzner box
- `DEPLOY_USER` — `yushan`
- `DEPLOY_SSH_KEY` — private deploy key
- `DEPLOY_KNOWN_HOSTS` — `ssh-keyscan` output for the host

The server keeps its own `.env` (excluded from sync). The container binds to
loopback and is exposed only inside the tailnet by `tailscale serve` on HTTPS
port 8443.

## Notes

Sessions are in-memory, so a restart or a second uvicorn worker loses them. For a real deployment, put the session store in Redis/SQLite and add auth and rate limiting on `/api/ingest` (each call spends Firecrawl and ScaleDown credits).

## Tests

```sh
uv run pytest
```
