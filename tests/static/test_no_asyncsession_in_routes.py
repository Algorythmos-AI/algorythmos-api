"""
Test to prevent AsyncSession type annotation regression in route handlers.

This test ensures that SQLAlchemy session types are never used as type annotations
in FastAPI route handler parameters, which would break OpenAPI schema generation
on Vercel due to Pydantic v2 introspecting internal SQLAlchemy types.

BACKGROUND:
- Production outage: /openapi.json returned 500, /docs failed
- Root cause: `db: AsyncSession = Depends(get_session)` caused Pydantic to try
  introspecting SQLAlchemy's _AsyncSessionBind type
- Fix: Remove type annotation, use `db = Depends(get_session)` instead

This test will fail if anyone reintroduces the bug.

NOTE: This test does NOT use the async fixtures from conftest.py.
"""

import inspect
import re
import sys
from pathlib import Path

import pytest


# Patterns that should NEVER appear in route handler signatures
FORBIDDEN_PATTERNS = [
    r":\s*AsyncSession\s*=\s*Depends",
    r":\s*Session\s*=\s*Depends",
    r":\s*Optional\[AsyncSession\]\s*=",
    r":\s*Optional\[Session\]\s*=",
]


# Lazy-load app to avoid fixture conflicts - this function gets the app directly
def _get_app():
    """Get FastAPI app directly without fixtures."""
    ROOT = Path(__file__).resolve().parents[1]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from app import app
    return app


def _get_route_handlers():
    """Extract all route handlers from the FastAPI app."""
    app = _get_app()
    handlers = []
    for route in app.routes:
        if hasattr(route, "endpoint"):
            handlers.append((route.path, route.endpoint))
    return handlers


def _check_handler_source(handler):
    """
    Check if a handler's source contains forbidden SQLAlchemy type patterns.
    
    Returns list of matched forbidden patterns (empty if clean).
    """
    try:
        source = inspect.getsource(handler)
    except (OSError, TypeError):
        # Can't get source for some handlers (builtins, etc.)
        return []
    
    violations = []
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, source):
            violations.append(pattern)
    
    return violations


# Mark this module to skip the autouse reset_state fixture
# by running it with different configuration
pytestmark = [
    pytest.mark.filterwarnings("ignore::DeprecationWarning"),
]


class TestNoAsyncSessionInRoutes:
    """
    Regression test: Ensure no route handler uses AsyncSession type annotations.
    
    Why this matters:
    - Pydantic v2 + FastAPI introspect type annotations for OpenAPI schema
    - SQLAlchemy's AsyncSession has internal types that Pydantic can't resolve
    - This causes /openapi.json to fail with 500 on Vercel (but may work locally)
    
    Correct pattern:
        db = Depends(get_session)  # ✅ No type annotation
    
    Wrong pattern:
        db: AsyncSession = Depends(get_session)  # ❌ NEVER DO THIS
    """

    @pytest.mark.usefixtures()  # Explicitly use no fixtures
    def test_no_asyncsession_type_annotations_in_routes(self):
        """
        Fail if any route handler has AsyncSession/Session type annotation.
        """
        violations = []
        
        for path, handler in _get_route_handlers():
            handler_violations = _check_handler_source(handler)
            if handler_violations:
                func_name = getattr(handler, "__name__", str(handler))
                violations.append(
                    f"Route '{path}' handler '{func_name}' contains forbidden patterns: {handler_violations}"
                )
        
        if violations:
            error_message = (
                "\n\n🚨 REGRESSION DETECTED: SQLAlchemy session type annotations in route handlers!\n\n"
                "This will break OpenAPI schema generation on Vercel.\n\n"
                "VIOLATIONS FOUND:\n" + "\n".join(f"  - {v}" for v in violations) + "\n\n"
                "FIX: Remove the type annotation from the Depends() parameter.\n"
                "  ❌ Wrong: db: AsyncSession = Depends(get_session)\n"
                "  ✅ Correct: db = Depends(get_session)\n\n"
                "See: https://errors.pydantic.dev/2.11/u/class-not-fully-defined\n"
            )
            pytest.fail(error_message)

    @pytest.mark.usefixtures()  # Explicitly use no fixtures
    def test_forbidden_patterns_are_not_empty(self):
        """Sanity check: ensure we're actually checking something."""
        assert len(FORBIDDEN_PATTERNS) > 0
        handlers = _get_route_handlers()
        assert len(handlers) > 0, "No routes found to check"
