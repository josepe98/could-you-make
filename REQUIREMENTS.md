# Could You Make — Requirements

## Overview

A self-hosted, single-tenant ticket management app for collecting bug reports and enhancement requests across multiple apps maintained by one developer or small team. Named after the natural language pattern used when requesting changes ("Could you make...?").

Stack: FastAPI + PostgreSQL backend, React + Vite frontend, packaged as a single Docker container.

The submitter experience is intentionally minimal — users submit a ticket and optionally track its status via a private link. They cannot see anyone else's tickets. There is exactly one administrator account.

---

## Apps Served

The set of apps is managed as rows in the `apps` database table and edited through the admin UI at `/admin/apps`. On first boot, the table is seeded from `SEED_APPS` in `backend/models.py`; after that, the table is the source of truth. Each app row has:

- `slug` (primary key) — short URL identifier (e.g. `?app=blog`). Lowercase alphanumeric + hyphens. **Permanent once created.**
- `prefix` — 2-8 uppercase characters that become part of every ticket's display ID (e.g. `BLOG-001`). Unique. Editable, with a warning (changes existing tickets' display IDs).
- `label` — human-readable name shown in the dashboard, submit form, and confirmation emails. Editable.
- `display_order` — sort key for dropdown ordering.

Frontend pages fetch `/api/apps` via `AppsContext` on mount; there are no hardcoded app lists in frontend code.

---

## User Roles

### Submitter (end user)
- Accesses the submit form via a link/button in their app
- Fills out and submits a ticket
- Optionally provides their email to receive a confirmation with ticket ID and a private status link
- Can look up the status of their specific ticket via the private link (not guessable)
- Cannot see any other tickets

### Administrator
- Accesses the admin dashboard at `/admin` (password-protected). There is exactly one admin account per instance.
- Sees all tickets across all apps
- Can sort and filter by app, date, type, urgency, priority, and status
- Can set priority and update status inline or via the detail drawer
- Can change admin password from within the dashboard
- Has full read/write/delete access to all tickets

---

## Ticket Data Model

| Field | Type | Notes |
|-------|------|-------|
| `id` | Auto-increment | Display format is app-specific, e.g. `BLOG-001`, `STORE-014` |
| `lookup_token` | String (64) | Random URL-safe token; used for public status URL — not guessable |
| `app` | String (FK → `apps.slug`) | Must match an existing row in the `apps` table |
| `type` | Enum | Bug, Enhancement, Question |
| `title` | String | Short summary, required |
| `description` | Text | Full detail, required |
| `submitter_urgency` | Enum | Low, Medium, High — set by submitter |
| `admin_priority` | Enum | Low, Medium, High, Critical — set by admin, null until triaged |
| `status` | Enum | Open, In Progress, Done, Won't Fix — default Open |
| `clarifying_notes` | Text | Optional admin-only notes for triage/context |
| `submitter_email` | String | Optional; used only for confirmation email |
| `created_at` | Timestamp | Set on creation |
| `updated_at` | Timestamp | Updated on any change |
| `resolved_at` | Timestamp | Set when status transitions to Done or Won't Fix; cleared on reopen |

---

## Submit Form (`/submit`)

- URL parameter `app` pre-populates and locks the app field (e.g. `/submit?app=blog`)
- Fields: Title, Description, Type, Urgency, Email (optional)
- On submit:
  - Ticket is created with an app-specific display ID (e.g. `BLOG-007`) and a random `lookup_token`
  - If email provided: confirmation email sent via Resend with ticket ID and a link to `/ticket/{lookup_token}`
  - Submitter sees a confirmation screen with the display ID and a "Track status" link
- No login required
- Rate limited to 2 submissions per minute per IP. The IP is keyed on `CF-Connecting-IP` (Cloudflare), falling back to `X-Forwarded-For`, then to the connection IP — see `backend/limiter.py` and the README's "Behind a reverse proxy / CDN" section for the trust model.

---

## Status Page (`/ticket/:token`)

- Publicly accessible but not linked or indexed — only reachable via the `lookup_token` in the confirmation email or success screen
- Token is random and non-guessable; sequential ticket IDs cannot be enumerated
- Shows: ticket ID, title, type, app, date submitted, current status
- Does not show: priority, description, admin notes, submitter email, or any other tickets
- If token not found: generic not-found message

---

## Admin Dashboard (`/admin`)

- Redirects to `/admin/login` if not authenticated
- Login page includes a link back to the submit form
- Password stored hashed (pbkdf2, 100k iterations) in the database; falls back to env var on first run
- Session persisted via a secure HTTP-only cookie (7-day expiry); sessions stored in DB and survive restarts
- Expired sessions are cleaned up on each login
- **Ticket list view:**
  - Two view modes: **Table** and **Board**. View preference persists per browser.
  - **Table mode:** Split into two tables: **Active** (any status other than Done) on top, **Done** below. Rows animate between the two tables via the View Transitions API when status is toggled across the Done boundary. Columns: ID, App, Type, Title, Urgency (submitter), Priority (admin, inline — currently hidden via `SHOW_PRIORITY_COLUMN` flag in `AdminDashboard.jsx`), Status (inline), Date. Column widths are user-resizable (drag the column edge); widths persist per browser via `localStorage`. Sortable by: Date, Urgency, Priority, Status. Filterable by: App, Type, Status. Title column wraps (not truncated).
  - **Board mode:** Kanban-style view with columns for each status (Open, In Progress, Done, Won't Fix). Cards can be dragged between columns to change status. Filterable by: App, Type.
- **Ticket detail drawer** (click any row):
  - Full description
  - All fields editable: title, type, description, clarifying_notes, priority, status
  - Read-only metadata: app, submitter urgency, email, timestamps
  - Save and Delete buttons
- **Change password** (inline form in dashboard header):
  - Requires current password, new password, confirmation
  - Minimum 8 characters enforced both client- and server-side
  - Persisted to DB; takes effect immediately
- **Activity chart** (modal, triggered from dashboard header):
  - Bar chart showing tickets opened and closed per week over the last 12 weeks
  - Built from `resolved_at` timestamps; computed client-side from already-loaded tickets

---

## Email (Resend HTTPS API)

- Trigger: ticket submission where submitter provides an email address
- Configured via `RESEND_API_KEY` and `FROM_EMAIL` env vars. Optional `REPLY_TO` sets the Reply-To header.
- Uses Resend's HTTPS API rather than SMTP, because most PaaS providers (notably Railway) block outbound SMTP on every port. HTTPS always works.
- Sent as a FastAPI `BackgroundTask` so the HTTP response returns immediately, with a 15-second timeout.
- `FROM_EMAIL` must be on a domain verified in Resend; the address itself does not need to be a real mailbox.
- Content:
  - Subject: `Your ticket BLOG-007 has been submitted`
  - Body: ticket display ID, title, type, app, urgency, and a link to `/ticket/{lookup_token}`
- No status-change notification emails (v1)

---

## Entry Points in Each App

Each integrating app displays a small, unobtrusive link or icon (e.g. a speech bubble or wrench icon in the corner or menu bar) that opens `<your-instance>/submit?app=<appname>` in a new tab. Native apps can open the same URL in the system default browser.

---

## Tech Stack

- **Backend**: Python / FastAPI, PostgreSQL, SQLAlchemy, slowapi (rate limiting)
- **Frontend**: React 18, Vite, React Router
- **Email**: Resend HTTPS API (via the `resend` Python SDK)
- **Packaging**: multi-stage Dockerfile (single container serves API + built frontend)

---

## Security

- Admin password hashed with pbkdf2_hmac (sha256, 100k iterations) + random salt
- Sessions stored in DB with expiry; not held in memory
- Public ticket status URLs use random tokens, not guessable sequential IDs
- Rate limiting (slowapi, in-memory): ticket creation 2/min/IP, ticket lookup 30/min/IP, admin login 10/min/IP. IP keyed on `CF-Connecting-IP` so users behind the Cloudflare proxy aren't grouped into one bucket.
- Session cookie: httponly, secure, samesite=lax
- Pydantic validation on all inputs; SQLAlchemy ORM (no SQL injection risk)
- Security headers middleware on all responses: HSTS, X-Frame-Options: DENY, X-Content-Type-Options: nosniff, Referrer-Policy, Permissions-Policy, Content-Security-Policy
- Cache-Control: no-store on all non-static-asset responses
- API docs endpoints disabled (no /api/docs, /redoc, /openapi.json)

---

## Out of Scope (v1)

- Status-change notification emails
- Submitter accounts or login
- Public-facing ticket boards or voting
- Attachments or screenshots
- Multiple admin users
