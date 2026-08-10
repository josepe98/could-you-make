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

# fastapi >= 0.141 includes routers lazily (_IncludedRouter), so app.routes no
# longer yields flattened objects with .path/.methods; the OpenAPI schema is the
# stable public view of registered routes on both old and new fastapi.
registered = {
    (method.upper(), path)
    for path, ops in app.openapi().get("paths", {}).items()
    for method in ops
    if method.lower() in {"get", "post", "put", "patch", "delete", "head", "options"}
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
