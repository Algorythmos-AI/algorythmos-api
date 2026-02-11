from __future__ import annotations

"""Expose the FastAPI application when importing the ``app`` package."""

from importlib import util
from pathlib import Path
from types import ModuleType
from typing import Any

_APP_MODULE_NAME = "_app_entrypoint"
_APP_PATH = Path(__file__).resolve().parent.parent / "app.py"


def _load_entrypoint() -> ModuleType:
    if _APP_MODULE_NAME in globals():  # pragma: no cover
        return globals()[_APP_MODULE_NAME]  # type: ignore[index]

    if not _APP_PATH.is_file():  # pragma: no cover
        raise RuntimeError(f"Expected application entrypoint at {_APP_PATH!s}")

    spec = util.spec_from_file_location(_APP_MODULE_NAME, _APP_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError("Unable to load application entrypoint")

    module = util.module_from_spec(spec)
    loader = spec.loader
    assert loader is not None
    loader.exec_module(module)  # type: ignore[attr-defined]
    globals()[_APP_MODULE_NAME] = module
    return module


_app_entry: ModuleType = _load_entrypoint()
app: Any = getattr(_app_entry, "app", None)

if app is None:  # pragma: no cover
    raise RuntimeError("Top-level app.py does not expose an 'app' attribute")

# Expose Stage 3+ constants for tests
RUN_MAX_FILE_BYTES: int = getattr(_app_entry, "RUN_MAX_FILE_BYTES", 10 * 1024 * 1024)
RUN_MAX_FILES: int = getattr(_app_entry, "RUN_MAX_FILES", 50)
WEBHOOK_REPLAY_TTL_S: int = getattr(_app_entry, "WEBHOOK_REPLAY_TTL_S", 300)
WEBHOOK_REPLAY_WINDOW_S: int = getattr(_app_entry, "WEBHOOK_REPLAY_WINDOW_S", 60)
_processor_runs: Any = getattr(_app_entry, "_processor_runs", {})

__all__ = [
    "app",
    "RUN_MAX_FILE_BYTES",
    "RUN_MAX_FILES",
    "WEBHOOK_REPLAY_TTL_S",
    "WEBHOOK_REPLAY_WINDOW_S",
    "_processor_runs",
]
