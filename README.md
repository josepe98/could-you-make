# Could You Make

A self-hosted ticket management app for solo developers and small teams who maintain several apps and want one place to collect bug reports and feature requests from users — without making those users sign up for anything.

Named after the way people naturally phrase change requests: *"Could you make..."*

## What it does

You run one instance of Could You Make and point each of your apps at it. Each app gets a stable submit URL (`/submit?app=<name>`) you can link to from a help menu, footer, or "Report a problem" button.

**For your users:**
- Click the link, fill out a short form (title, description, type, urgency, email)
- Get back a private status URL they can bookmark to check on their ticket later, and receive a confirmation email with the ticket ID
- No account, no login, no password
- They never see anyone else's tickets — status pages are reachable only via a 256-bit random token. Can reply to admin messages in-app and via email.
- Get notified when the ticket is resolved with a summary of the conversation

**For you (the admin):**
- One dashboard at `/admin` shows every ticket from every app
- Two view modes: table (sortable/filterable, with separate Active/Done sections) and kanban board (drag cards between status columns)
- Inline status editing, drag-to-resize columns in table mode (persisted per browser)
- Activity chart showing tickets opened and closed per week over the last 12 weeks
- Per-app ticket ID prefixes (e.g. `BLOG-001`, `STORE-014`) so you can reference tickets unambiguously
- Automated effort estimation: on submission, Sonnet 4.6 drafts a summary and assigns an effort level (Small/Medium/Large/Unknown)
- In-app messaging: reply to submitters directly from the ticket drawer; conversations surface in confirmation and resolution emails
- Confirmation and status-change emails to submitters via Resend

The full spec lives in [`REQUIREMENTS.md`](./REQUIREMENTS.md).

## Stack

- **Backend**: Python 3.12 / FastAPI / SQLAlchemy / PostgreSQL
  - slowapi for rate limiting
  - Resend HTTPS API for confirmation emails (any host that allows outbound HTTPS — including PaaS that block outbound SMTP)
- **Frontend**: React 18 / Vite / React Router
- **Build / deploy**: multi-stage Dockerfile (Node builds the frontend, Python slim serves the FastAPI app + built bundle from a single container)

## Configuring your apps

Apps are managed in the database, not in code. Open the admin dashboard, click **Manage apps**, and add a row with:

- **Slug** — the URL identifier, e.g. `my-app`. Permanent; choose carefully (lowercase, digits, and hyphens only).
- **Label** — human-readable name shown in the dashboard and submit form
- **Prefix** — the 2–8 character tag embedded in ticket IDs (e.g. `MYA` → tickets display as `MYA-001`)
- **Order** — sort key for dropdowns (lower values appear first)

Then link to `https://your-instance.example.com/submit?app=<your-app-slug>` from each app.

Prefix and label can be edited later. Slugs cannot be changed after creation — delete and re-create if you need a different slug (and only after reassigning any tickets). Apps that have tickets cannot be deleted.

First-run seed: if the `apps` table is empty on boot, it's populated from the hardcoded list in `backend/models.py:SEED_APPS`. After that, the table is the source of truth.

## Local development

Backend:

```sh
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Required env vars:
export DATABASE_URL="postgresql://user:pass@localhost/cym"
export ADMIN_PASSWORD="change-me-on-first-login"

# Optional — only needed if you want confirmation emails:
export RESEND_API_KEY=re_...
export FROM_EMAIL=tickets@your-verified-domain.com
# Optional: set Reply-To to an inbox you actually read
# export REPLY_TO=you@example.com

# Optional — only needed for automated effort estimation on submission:
# export ANTHROPIC_API_KEY=sk-ant-...

uvicorn backend.main:app --reload --port 8001
```

The first time the backend starts it seeds the admin password from `ADMIN_PASSWORD` and runs schema migrations. Change the password from the dashboard immediately after first login — `ADMIN_PASSWORD` is only the bootstrap value.

Frontend (Vite dev server with HMR, proxies `/api` to port 8001):

```sh
cd frontend
npm install
npm run dev          # http://localhost:5175
```

Or build the bundle and let FastAPI serve everything from one port:

```sh
cd frontend && npm run build
# now visit http://localhost:8001
```

## Deploying

The included `Dockerfile` builds a single container that serves both the API and the built frontend. Any host that can run a Dockerfile and provide a Postgres URL will work — Railway, Fly.io, Render, a VPS with Docker, etc.

Required runtime env vars:

| Variable | Notes |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `ADMIN_PASSWORD` | Bootstrap password for first login. Change immediately. |
| `RESEND_API_KEY` | Optional, for confirmation emails. Sign up at [resend.com](https://resend.com), verify your sending domain, create an API key. |
| `FROM_EMAIL` | Required if emails are enabled. Must be on a domain you've verified in Resend (e.g. `tickets@yourdomain.com`). |
| `FROM_NAME` | Optional. Display name shown in the From field (e.g. `Could You Make`). If unset, the bare address is used. |
| `REPLY_TO` | Optional. Sets Reply-To on confirmation emails, e.g. an inbox you actually read. |
| `BASE_URL` | Public URL of your instance (used in confirmation email links). Defaults to the production URL. |
| `ANTHROPIC_API_KEY` | Optional, for post-submission effort estimation. When set, Sonnet 4.6 drafts a summary and assigns an effort level. If unset, a warning is logged but submission proceeds normally. |
| `API_KEY` | Optional. When set, admin endpoints accept `Authorization: Bearer <key>` in addition to the session cookie — used by the MCP server and other programmatic callers. Leave empty to disable bearer-token auth. |

Schema changes are applied at startup via `_run_ddl_migrations()` in `backend/main.py` using `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. There is no Alembic — when you add a new model column, also add a matching `ALTER TABLE` line in that function.

### Programmatic access (API key)

Set `API_KEY` to a long random string and admin endpoints will accept `Authorization: Bearer <key>` as well as the session cookie. Use this for scripts, the MCP server, or any automation that works tickets without logging in through the browser.

Generate a key locally:

```sh
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Set it in Railway (or wherever you run CYM) and in `backend/.env` for local dev. Never commit the key. If the key leaks, rotate it — a new value invalidates the old one immediately because there is only one active key at a time.

Endpoints that accept the key (admin-only):

- `GET /api/admin/tickets` (filters: `app`, `type`, `status`, `sort_by`, `sort_dir`)
- `GET /api/admin/tickets/{id}`
- `PATCH /api/admin/tickets/{id}` (body: `admin_priority`, `status`, `type`, `title`, `description`, `clarifying_notes`)
- `DELETE /api/admin/tickets/{id}`
- `POST /api/admin/apps`
- `PATCH /api/admin/apps/{slug}`
- `DELETE /api/admin/apps/{slug}`

Deliberately **session-cookie only** (no bearer-token path):

- `POST /api/admin/login`, `POST /api/admin/logout`
- `POST /api/admin/change-password`

Public (no auth required):

- `POST /api/tickets`, `GET /api/tickets/{lookup_token}`, `GET /api/apps`

### Behind a reverse proxy / CDN

If you put Cloudflare (or any reverse proxy) in front, the rate limiter needs to see the real client IP, not the proxy's. The bundled `client_ip_key()` in `backend/limiter.py` reads `CF-Connecting-IP` first, then falls back to `X-Forwarded-For`, then to the connection IP. **Trusting these headers is only safe if your origin isn't directly reachable from the public internet** — otherwise an attacker can spoof them. If you deploy without a proxy, replace `client_ip_key` with slowapi's `get_remote_address`.

## Security highlights

- Admin password hashed with pbkdf2-hmac (sha256, 100k iterations) + per-account salt
- Sessions stored in the database with 7-day expiry, HTTP-only / Secure / SameSite=Lax cookies
- Public status URLs use 256-bit random tokens, not sequential IDs
- Rate limiting: 2/min ticket creation, 30/min status lookup, 10/min admin login (per real client IP)
- Security headers middleware: HSTS, CSP, X-Frame-Options: DENY, X-Content-Type-Options: nosniff, Referrer-Policy, Permissions-Policy
- RFC 9116 `/.well-known/security.txt` endpoint for vulnerability disclosure
- API docs (`/docs`, `/redoc`, `/openapi.json`) disabled in production
- `Cache-Control: no-store` on all non-static responses

## Caveats / non-goals

- **Single tenant.** One admin user, one set of apps. There's no multi-tenancy and no plans for it.
- **Single instance.** Rate limiting and sessions are storage-backed but rate-limit counters are in process memory. If you scale horizontally you'll need to move slowapi to a Redis backend (`storage_uri="redis://..."`).
- **No file attachments.** Submissions are text only. By design — keeps the threat surface and the storage story simple.
- **No status-change emails.** Submitters get one confirmation email on creation; they have to revisit their status URL to see updates.
- **No real migration system.** See the deploy section above. Fine for a small project; replace with Alembic if you want anything more sophisticated.
