"""
Tests for the unified API route structure.

Verifies that:
  1. The main app router imports without errors.
  2. No duplicate method+path combinations are registered.
  3. Every route has a non-empty tags list.
  4. Every route has a non-empty summary.
  5. All expected top-level API prefixes are present.
  6. The six originally-stray route files are now under api/routes/, not api/.
"""

import importlib
import sys
from collections import Counter

# ── 1. App imports cleanly ────────────────────────────────────────────────────


def test_app_imports_without_error():
    """Importing the FastAPI application raises no errors."""
    from app.main import app

    assert app is not None


def test_api_router_imports_without_error():
    """Importing the top-level api_router succeeds."""
    from app.api import api_router

    assert api_router is not None


# ── 2. No duplicate routes ────────────────────────────────────────────────────


def test_no_duplicate_routes():
    """
    No two registered routes share the same HTTP method + path.

    Duplicate routes cause silent shadowing: the first registered route wins
    and the second is unreachable. This catches accidental double-registration
    caused by leftover files in the old api/ location.
    """
    from app.main import app

    combos = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods or []:
                combos.append((method, route.path))

    counts = Counter(combos)
    dupes = {k: v for k, v in counts.items() if v > 1}
    assert not dupes, f"Duplicate routes found: {dupes}"


# ── 3. Every route has non-empty tags ────────────────────────────────────────


def test_every_openapi_route_has_tags():
    """Every endpoint in the OpenAPI schema has at least one tag."""
    from app.main import app

    schema = app.openapi()
    missing = []
    for path, methods in schema.get("paths", {}).items():
        for method, op in methods.items():
            if method in ("get", "post", "put", "patch", "delete"):
                if not op.get("tags"):
                    missing.append(f"{method.upper()} {path}")

    assert not missing, "Routes missing tags:\n" + "\n".join(f"  {r}" for r in missing)


# ── 4. Every route has a non-empty summary ───────────────────────────────────


def test_every_openapi_route_has_summary():
    """Every endpoint in the OpenAPI schema has a non-empty summary."""
    from app.main import app

    schema = app.openapi()
    missing = []
    for path, methods in schema.get("paths", {}).items():
        for method, op in methods.items():
            if method in ("get", "post", "put", "patch", "delete"):
                if not op.get("summary"):
                    missing.append(f"{method.upper()} {path}")

    assert not missing, "Routes missing summary:\n" + "\n".join(f"  {r}" for r in missing)


# ── 5. Expected top-level prefixes are present ───────────────────────────────


def test_expected_prefixes_present():
    """
    All top-level API prefixes expected by the frontend and documented APIs exist.

    Checks for the /api/v1/... prefix form used in production.
    """
    from app.main import app
    from app.core.config import get_settings

    settings = get_settings()
    prefix = settings.API_V1_PREFIX  # e.g. "/api/v1"

    # FastAPI 0.141+ preserves included routers as nested route objects instead
    # of flattening every path into app.routes. OpenAPI remains the canonical
    # representation of the externally exposed API across FastAPI versions.
    all_paths = set(app.openapi().get("paths", {}))

    expected_prefixes = [
        f"{prefix}/health",
        f"{prefix}/costs",
        f"{prefix}/auth",
        f"{prefix}/teams",
        f"{prefix}/jobs",
        f"{prefix}/usage",
        f"{prefix}/analytics",
        f"{prefix}/integrations",
        f"{prefix}/billing",
        f"{prefix}/budgets",
        f"{prefix}/forecast",
        f"{prefix}/anomalies",
        f"{prefix}/optimize",
        f"{prefix}/reports",
    ]

    for expected in expected_prefixes:
        matches = [p for p in all_paths if p.startswith(expected)]
        assert matches, f"No routes found under prefix: {expected}"


# ── 6. Old api/ files are gone; routes are in api/routes/ ────────────────────


def test_stray_route_files_removed_from_api_root():
    """
    The six originally-stray route files (auth, costs, jobs, teams, usage, analytics)
    are no longer importable from app.api directly.

    Importing app.api.auth etc. must raise ModuleNotFoundError — the files should
    only exist under app.api.routes.
    """
    stale_modules = [
        "app.api.auth",
        "app.api.costs",
        "app.api.jobs",
        "app.api.teams",
        "app.api.usage",
        "app.api.analytics",
    ]
    for mod_name in stale_modules:
        # Remove from cache so a fresh import is attempted
        sys.modules.pop(mod_name, None)

    import importlib

    for mod_name in stale_modules:
        try:
            importlib.import_module(mod_name)
            # If we reach here, the file still exists at the old location
            assert False, f"{mod_name} still importable from old location — file not removed"
        except ModuleNotFoundError:
            pass  # expected


def test_migrated_routes_importable_from_routes():
    """The six migrated files are importable from their new app.api.routes location."""
    migrated = [
        "app.api.routes.auth",
        "app.api.routes.costs",
        "app.api.routes.jobs",
        "app.api.routes.teams",
        "app.api.routes.usage",
        "app.api.routes.analytics",
    ]
    for mod_name in migrated:
        mod = importlib.import_module(mod_name)
        assert hasattr(mod, "router"), f"{mod_name} has no 'router' attribute"
