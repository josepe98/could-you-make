# Could You Make

A self-hosted ticket management app for solo developers and small teams who maintain several apps and want one place to collect bug reports and feature requests from users — without making those users sign up for anything.

Named after the way people naturally phrase change requests: *"Could you make..."*

## What it does

You run one instance of Could You Make and point each of your apps at it. Each app gets a stable submit URL (`/submit?app=<name>`) you can link to from a help menu, footer, or "Report a problem" button.

**For your users:**
- Click the link, fill out a short form (title, description, type, urgency, optional email)
- Get back a private status URL they can bookmark to check on their ticket later
- No account, no login, no password
- They never see anyone else's tickets — status pages are reachable only via a 256-bit random token that's emailed and shown once on submission

**For you (the admin):**
- One dashboard at `/admin` shows every ticket from every app in a single sortable, filterable table
- Active and Done tickets render in separate tables; rows animate between them as you triage
- Inline status editing, drag-to-resize columns (persisted per browser)
- Per-app ticket ID prefixes (e.g. `BLOG-001`, `STORE-014`) so you can reference tickets unambiguously
- Optional confirmation emails to submitters via SMTP

The full spec lives in [`REQUIREMENTS.md`](./REQUIREMENTS.md).

## Stack

- **Backend**: Python 3.12 / FastAPI / SQLAlchemy / PostgreSQL
  - slowapi for rate limiting
  - aiosmtplib for confirmation emails (any SMTP provider)
- **Frontend**: React 18 / Vite / React Router
- **Build / deploy**: multi-stage Dockerfile (Node builds the frontend, Python slim serves the FastAPI app + built bundle from a single container)

## Configuring your apps

Add the apps you want to serve to two places:

1. `backend/models.py` — `APP_PREFIXES` dict (maps app slug → ID prefix) and the `AppName` enum
2. `frontend/src/pages/{Submit,AdminDashboard,TicketStatus}.jsx` — the `APPS` / `APP_LABELS` constants for display names

Then link to `https://your-instance.example.com/submit?app=<your-app-slug>` from each app.

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
export SMTP_HOST=smtp.example.com SMTP_PORT=465
export SMTP_USER=... SMTP_PASSWORD=... FROM_EMAIL=...

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
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `FROM_EMAIL` | Optional, for confirmation emails |
| `BASE_URL` | Public URL of your instance (used in confirmation email links). Defaults to the production URL. |

Schema changes are applied at startup via `_run_ddl_migrations()` in `backend/main.py` using `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. There is no Alembic — when you add a new model column, also add a matching `ALTER TABLE` line in that function.

### Behind a reverse proxy / CDN

If you put Cloudflare (or any reverse proxy) in front, the rate limiter needs to see the real client IP, not the proxy's. The bundled `client_ip_key()` in `backend/limiter.py` reads `CF-Connecting-IP` first, then falls back to `X-Forwarded-For`, then to the connection IP. **Trusting these headers is only safe if your origin isn't directly reachable from the public internet** — otherwise an attacker can spoof them. If you deploy without a proxy, replace `client_ip_key` with slowapi's `get_remote_address`.

## Security highlights

- Admin password hashed with pbkdf2-hmac (sha256, 100k iterations) + per-account salt
- Sessions stored in the database with 7-day expiry, HTTP-only / Secure / SameSite=Lax cookies
- Public status URLs use 256-bit random tokens, not sequential IDs
- Rate limiting: 2/min ticket creation, 30/min status lookup, 10/min admin login (per real client IP)
- Security headers middleware: HSTS, CSP, X-Frame-Options: DENY, X-Content-Type-Options: nosniff, Referrer-Policy, Permissions-Policy
- API docs (`/docs`, `/redoc`, `/openapi.json`) disabled in production
- `Cache-Control: no-store` on all non-static responses

## Caveats / non-goals

- **Single tenant.** One admin user, one set of apps. There's no multi-tenancy and no plans for it.
- **Single instance.** Rate limiting and sessions are storage-backed but rate-limit counters are in process memory. If you scale horizontally you'll need to move slowapi to a Redis backend (`storage_uri="redis://..."`).
- **No file attachments.** Submissions are text only. By design — keeps the threat surface and the storage story simple.
- **No status-change emails.** Submitters get one confirmation email on creation; they have to revisit their status URL to see updates.
- **No real migration system.** See the deploy section above. Fine for a small project; replace with Alembic if you want anything more sophisticated.
