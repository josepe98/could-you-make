"""CI smoke test (CYM-127).

Importing backend.main runs the DDL migrations and seeds against whatever
DATABASE_URL points at — in CI that's a throwaway Postgres service container,
so a clean import proves three things at once: the app imports without
crashing, _run_ddl_migrations() executes valid SQL on Postgres, and the seed
functions run. After import we assert key routes are registered to catch
accidental router-include regressions.

Run as: python -m backend.scripts.ci_smoke
Needs DATABASE_URL (Postgres) and ADMIN_PASSWORD in the environment.
"""
import sys

from backend.main import app  # import side effects ARE the migration check

EXPECTED_ROUTES = {
    ("POST", "/api/tickets"),
    ("GET", "/api/tickets/{lookup_token}"),
    ("GET", "/api/tickets/{lookup_token}/messages"),
    ("POST", "/api/admin/login"),
    ("GET", "/api/admin/tickets"),
    ("PATCH", "/api/admin/tickets/{ticket_id}"),
    ("POST", "/api/admin/tickets/{ticket_id}/messages"),
    ("GET", "/api/apps"),
    ("POST", "/api/admin/apps"),
}

registered = {
    (method, route.path)
    for route in app.routes
    for method in getattr(route, "methods", set())
}

missing = EXPECTED_ROUTES - registered
if missing:
    print("FAIL: expected routes not registered:")
    for method, path in sorted(missing):
        print(f"  {method} {path}")
    sys.exit(1)

print(
    f"OK: app imported, migrations ran clean, "
    f"{len(registered)} routes registered, all {len(EXPECTED_ROUTES)} expected routes present"
)
