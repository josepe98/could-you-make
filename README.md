# Could You Make

A private ticket management app for collecting bug reports and enhancement requests across Erik's personal and client apps. Named after the way people naturally phrase change requests ("Could you make...?").

Live at **[couldyoumake.app](https://couldyoumake.app)**.

## What it is

Each app Erik maintains links to `couldyoumake.app/submit?app=<name>`. End users fill out a short form (title, description, type, urgency, optional email) and get back a private status link they can use to check on their ticket. Erik triages everything from a single admin dashboard at `/admin`.

Submitters never see anyone else's tickets — status pages are reachable only via a 256-bit random `lookup_token` that's emailed/displayed once on submission.

See [`REQUIREMENTS.md`](./REQUIREMENTS.md) for the full spec.

## Stack

- **Backend**: Python 3.12 / FastAPI / SQLAlchemy / PostgreSQL, slowapi rate limiting, aiosmtplib (Fastmail) for confirmation emails
- **Frontend**: React 18 / Vite / React Router
- **Hosting**: Railway (single instance), Cloudflare in front
- **Build**: multi-stage Dockerfile (Node → `vite build`, then Python slim serving the built bundle)

## Local development

Backend:

```sh
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# requires DATABASE_URL and ADMIN_PASSWORD env vars; optional SMTP_* for email
uvicorn backend.main:app --reload --port 8001
```

Frontend (Vite dev server with HMR, proxies `/api` to `:8001`):

```sh
cd frontend
npm install
npm run dev   # http://localhost:5175
```

Or build the bundle and have FastAPI serve it directly from `frontend/dist/`:

```sh
cd frontend && npm run build
# then visit http://localhost:8001
```

## Deploy

Push to `main` on `github.com/josepe98/could-you-make`. Railway auto-builds the Dockerfile and redeploys. Schema changes are applied at startup via `_run_ddl_migrations()` in `backend/main.py` (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` — there is no Alembic).

## Security highlights

- Admin password hashed with pbkdf2-hmac (sha256, 100k iterations) + per-account salt; sessions stored in DB with 7-day expiry
- Public status URLs use unguessable random tokens, not sequential IDs
- Rate limiting: 2/min ticket creation, 30/min status lookup, 10/min admin login — keyed on `CF-Connecting-IP` so users behind Cloudflare aren't grouped together
- Security headers middleware (HSTS, CSP, X-Frame-Options, etc.); API docs endpoints disabled in production
