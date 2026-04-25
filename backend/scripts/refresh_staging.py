"""Refresh the staging DB from a sanitized, recent copy of production.

Reads prod read-only, scrubs PII/tokens, wipes staging's `tickets` and
`apps` tables, then re-inserts the sanitized rows. Does NOT touch
`admin_password` or `admin_sessions` — staging's own admin login stays
intact across refreshes.

Required environment variables:
  PROD_DATABASE_URL      Connection string for production (read-only use).
  STAGING_DATABASE_URL   Connection string for staging. If unset, falls
                         back to DATABASE_URL.

Typical invocation (from laptop, with Railway CLI linked to staging):
  railway run --environment staging \\
    python -m backend.scripts.refresh_staging

Flags:
  --dry-run   Read prod + sanitize, print counts, write nothing.
  --days N    Copy tickets created in the last N days (default: 90).
  --yes       Skip the interactive 'type refresh to proceed' prompt.
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import psycopg2
from psycopg2.extras import RealDictCursor


EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+\.[\w.\-]+")
BEARER_RE = re.compile(r"Bearer\s+[\w.\-]{10,}", re.IGNORECASE)
STRIPE_KEY_RE = re.compile(r"\b(?:sk|pk|rk)_(?:test|live)?_?[A-Za-z0-9]{16,}\b")
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9._\-]{20,}\b")
GITHUB_TOKEN_RE = re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b")


def scrub_text(text: str | None) -> str | None:
    if not text:
        return text
    t = EMAIL_RE.sub("[redacted-email]", text)
    t = BEARER_RE.sub("[redacted-bearer]", t)
    t = STRIPE_KEY_RE.sub("[redacted-key]", t)
    t = JWT_RE.sub("[redacted-jwt]", t)
    t = GITHUB_TOKEN_RE.sub("[redacted-gh-token]", t)
    return t


def fake_email(ticket_id: int) -> str:
    return f"user{ticket_id}@example.com"


def host(url: str) -> str:
    p = urlparse(url)
    if not p.hostname:
        return "?"
    return f"{p.hostname}:{p.port}" if p.port else p.hostname


def get_urls() -> tuple[str, str]:
    prod = os.environ.get("PROD_DATABASE_URL")
    staging = os.environ.get("STAGING_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not prod:
        sys.exit("ERROR: PROD_DATABASE_URL is not set.")
    if not staging:
        sys.exit("ERROR: STAGING_DATABASE_URL (or DATABASE_URL) is not set.")
    if prod == staging:
        sys.exit("ERROR: prod and staging URLs are identical — refusing to proceed.")
    return prod, staging


def confirm(prod_url: str, staging_url: str, days: int) -> None:
    print(f"Source (prod, read-only):    {host(prod_url)}")
    print(f"Target (staging, will wipe): {host(staging_url)}")
    print(f"Copying tickets from the last {days} days, sanitizing PII/tokens.")
    print("Staging's admin_password and admin_sessions will NOT be touched.")
    answer = input("Type 'refresh' to proceed: ").strip()
    if answer != "refresh":
        sys.exit("Aborted.")


def fetch_prod(prod_url: str, days: int) -> tuple[list[dict], list[dict]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    conn = psycopg2.connect(prod_url)
    try:
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT slug, prefix, label, display_order, created_at FROM apps ORDER BY slug")
            apps = [dict(r) for r in cur.fetchall()]
            cur.execute(
                """
                SELECT id, app, type, title, description, submitter_urgency,
                       admin_priority, status, submitter_email, lookup_token,
                       clarifying_notes, created_at, updated_at
                FROM tickets
                WHERE created_at >= %s
                ORDER BY id
                """,
                (cutoff,),
            )
            tickets = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
    return apps, tickets


def sanitize(tickets: list[dict]) -> tuple[int, int]:
    emails = 0
    tokens = 0
    for t in tickets:
        if t["submitter_email"]:
            t["submitter_email"] = fake_email(t["id"])
            emails += 1
        if t["lookup_token"]:
            t["lookup_token"] = secrets.token_urlsafe(32)
            tokens += 1
        t["description"] = scrub_text(t["description"])
        t["clarifying_notes"] = scrub_text(t["clarifying_notes"])
    return emails, tokens


def wipe_and_load(staging_url: str, apps: list[dict], tickets: list[dict]) -> None:
    conn = psycopg2.connect(staging_url)
    try:
        with conn.cursor() as cur:
            # One transaction: if anything fails, staging keeps its prior state.
            cur.execute("DELETE FROM tickets")
            cur.execute("DELETE FROM apps")
            for a in apps:
                cur.execute(
                    "INSERT INTO apps (slug, prefix, label, display_order, created_at) VALUES (%s, %s, %s, %s, %s)",
                    (a["slug"], a["prefix"], a["label"], a["display_order"], a["created_at"]),
                )
            for t in tickets:
                cur.execute(
                    """
                    INSERT INTO tickets (
                        id, app, type, title, description, submitter_urgency,
                        admin_priority, status, submitter_email, lookup_token,
                        clarifying_notes, created_at, updated_at
                    ) VALUES (
                        %(id)s, %(app)s, %(type)s, %(title)s, %(description)s,
                        %(submitter_urgency)s, %(admin_priority)s, %(status)s,
                        %(submitter_email)s, %(lookup_token)s, %(clarifying_notes)s,
                        %(created_at)s, %(updated_at)s
                    )
                    """,
                    t,
                )
            # Advance the id sequence so new tickets get ids after the copied ones.
            cur.execute(
                "SELECT setval(pg_get_serial_sequence('tickets', 'id'), "
                "COALESCE((SELECT MAX(id) FROM tickets), 0) + 1, false)"
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Refresh staging DB from a sanitized copy of production.",
    )
    p.add_argument("--dry-run", action="store_true", help="Read + sanitize, write nothing.")
    p.add_argument("--days", type=int, default=90, help="Days of ticket history to copy (default 90).")
    p.add_argument("--yes", action="store_true", help="Skip interactive confirmation.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    prod_url, staging_url = get_urls()

    if not args.dry_run and not args.yes:
        confirm(prod_url, staging_url, args.days)

    print(f"Reading prod ({host(prod_url)})…")
    apps, tickets = fetch_prod(prod_url, args.days)
    print(f"  apps:    {len(apps)}")
    print(f"  tickets: {len(tickets)} (last {args.days} days)")

    emails, tokens = sanitize(tickets)
    print(f"Sanitized: {emails} emails replaced, {tokens} lookup tokens rotated.")

    if args.dry_run:
        print("[dry-run] no writes performed.")
        return

    print(f"Loading staging ({host(staging_url)})…")
    wipe_and_load(staging_url, apps, tickets)
    print("Done.")


if __name__ == "__main__":
    main()
