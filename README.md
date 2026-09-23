# Affiliate AI Platform

AI-powered affiliate marketing automation platform. Foundation scaffold:
FastAPI + PostgreSQL + Redis backend, Next.js + TypeScript + Tailwind frontend,
orchestrated with Docker Compose. All timestamps use `Asia/Jakarta`.

## Structure

```
backend/   FastAPI API, SQLAlchemy models, Alembic migrations, Redis worker,
           Telegram bot runtime
frontend/  Next.js App Router dashboard
```

## Setup

```bash
cp .env.example .env   # fill in secrets
docker compose up --build
```

- API: http://localhost:8000
- API docs: http://localhost:8000/docs
- Dashboard: http://localhost:3000

## Migrations

```bash
docker compose exec backend alembic upgrade head
```

## Endpoints (v1)

| Method | Path                                | Purpose                        |
| ------ | ----------------------------------- | ------------------------------ |
| GET    | /api/v1/health                      | Liveness + timezone            |
| GET    | /api/v1/health/ready                | DB / Redis readiness           |
| GET    | /api/v1/products                    | List products                  |
| POST   | /api/v1/products                    | Create product                 |
| PATCH  | /api/v1/products/{id}               | Update product                 |
| DELETE | /api/v1/products/{id}               | Delete product                 |
| GET    | /api/v1/content                     | List content queue             |
| POST   | /api/v1/content/generate            | Enqueue legacy content job     |
| GET    | /api/v1/analytics/summary           | Platform counters              |
| POST   | /api/v1/ai/generate                 | Create AI generation (202)     |
| GET    | /api/v1/ai/generations              | List generations               |
| GET    | /api/v1/ai/generations/{id}         | Get one generation             |
| POST   | /api/v1/ai/generations/{id}/retry   | Re-queue a failed generation   |

## AI text generation pipeline

```
POST /api/v1/ai/generate
  -> AIGeneration row (status=queued) + Job row
  -> Redis list "affiliate:jobs:default"
  -> worker: status=processing -> AIProvider -> validate -> result
  -> status=completed (or failed + error_message, with bounded retries)
```

### Provider configuration

Selected by `AI_PROVIDER`. OpenAI-compatible providers (`openai`, `deepseek`,
`groq`, `openrouter`, `together`, `ollama`, `lmstudio`, `custom`) use
`AI_API_KEY` + `AI_MODEL` + `AI_BASE_URL`.

Set `AI_PROVIDER=mock` to run the entire pipeline locally with no external
API call — useful for development and the end-to-end smoke test.

Retries are bounded by `AI_MAX_RETRIES` (default 3). Configuration errors fail
fast without retrying.

### Content types and platforms

Content types: `caption`, `hook`, `short_video_script`, `product_description`,
`cta`. Platforms: `tiktok`, `instagram`, `facebook`, `threads`, `x`.
Each maps to a versioned prompt template in
`backend/app/services/prompt_templates.py`.

### Dashboard

- `/dashboard/ai` — create a generation, poll status, view/copy variations,
  regenerate.
- `/dashboard/queue` — all generations with status badges, created/completed
  times, View and Retry actions.

Polling (2-3s) is used instead of websockets.

## Tests

```bash
docker compose up -d postgres redis
docker compose run --rm backend pytest
```

179 tests cover API creation/validation/retrieval, queue job creation, worker
success/failure/retry/exhaustion, provider selection and failure modes, output
parsing, prompt templates, and the Telegram bot (commands, authorization,
`/add` conversation, media upload/validation, AI triggering, invalid input,
keyboard/callback delivery resilience).

### Live end-to-end check

`backend/scripts/e2e_telegram_live.py` drives the real handlers against the real
PostgreSQL, Redis queue, worker and AI provider, and sends every bot reply to the
real admin chat through the Bot API:

```bash
docker compose exec -T backend python scripts/e2e_telegram_live.py
```

It asserts product + media persistence, dashboard visibility, the queued job
reaching `succeeded`, the completion notification being drained by the bot,
authorization, restart-safe conversation state, and that no token appears in the
OpenAPI schema or in any bot reply. Only the inbound direction is synthesized —
Telegram is the only party that can deliver an update to `getUpdates`, so update
payloads (and the media bytes behind a fake `file_id`) are built locally.

## Telegram bot

The bot runs as its own service and starts with `docker compose up -d`.

```
Telegram /add
  -> step-by-step product fields (optional ones can be /skip'd)
  -> photo / video uploads (validated + stored with generated filenames)
  -> PostgreSQL (Product + ProductMedia)
  -> dashboard /products
  -> [Analyze with AI] / [Generate Content] buttons
  -> existing queue -> existing worker -> completed generation
```

### Configuration

| Variable | Purpose |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Bot token (never hardcoded) |
| `TELEGRAM_ADMIN_USER_ID` | Comma-separated allow-list of user IDs |
| `TELEGRAM_ADMIN_CHAT_ID` | Comma-separated allow-list of chat IDs |
| `FRONTEND_BASE_URL` | Base URL for the "Open Dashboard" button. **Must be publicly reachable**: Telegram rejects the whole message if an inline-keyboard URL is not a valid public HTTP URL, so `localhost` disables the button (the text is still delivered). |
| `MEDIA_MAX_FILE_SIZE_MB` | Per-file upload cap (default 20) |

### Dashboard API address

The dashboard reads the API at `NEXT_PUBLIC_API_BASE_URL`, which is evaluated in
two different places:

- **Server components** render inside the frontend container, where the API is
  reachable as `http://backend:8000`. Set `API_INTERNAL_BASE_URL` to that; it
  falls back to `NEXT_PUBLIC_API_BASE_URL` when unset.
- **Browser code** (client components) runs on the user's machine, so
  `NEXT_PUBLIC_API_BASE_URL` must be the address *the user's browser* can reach
  (e.g. `http://<host>:8000`), and that origin must be in `CORS_ORIGINS`.

Pointing both at `localhost` makes the dashboard render an empty shell: the
frontend container cannot reach the host's `localhost`.

**Authorization is secure by default:** if no allow-list is configured, every
user is rejected.

### Commands

| Command | Purpose |
| --- | --- |
| `/start` | Welcome + command list |
| `/help` | Detailed help |
| `/add` | Step-by-step product creation |
| `/products` | Last 10 products |
| `/stats` | Product / media / generation counts |
| `/skip` | Skip an optional field |
| `/done` | Finish media collection |
| `/cancel` | Abort the conversation |

### Conversation state

State is stored in **Redis** (`telegram:state:<user_id>`) with a TTL, so an
in-progress `/add` survives a bot restart. No conversation state lives in
process memory.

### Media safety

- size validated before download (declared) and during download (actual)
- MIME type checked against an allow-list
- filenames are always generated (UUID); Telegram filenames are never used as
  paths, only stored as a display label with path components stripped
- failed uploads keep the product and expose a **Retry Media** button

### Health

The `telegram-bot` service writes a heartbeat file every 5s; the container
healthcheck fails if the heartbeat is older than 30s.

## Status

Implemented: project foundation, data models, API surface, queue plumbing,
Docker Compose, dashboard shell, complete AI text generation vertical slice,
**and the Telegram bot runtime** (commands, guided `/add` flow, media upload,
AI actions, persistent state, authorization, healthcheck).

Stubbed (later phases): AI image/video generation, social media publishing,
real analytics ingestion.
