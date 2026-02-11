from __future__ import annotations

import json
import logging
import time
from typing import Any

from fastapi import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, REGISTRY, generate_latest

runs_started = Counter("runs_started_total", "Runs started", ["processor"])
runs_succeeded = Counter("runs_succeeded_total", "Runs succeeded", ["processor"])
runs_failed = Counter("runs_failed_total", "Runs failed", ["processor"])

vendor_latency = Histogram(
    "vendor_request_latency_seconds",
    "Latency for upstream vendor requests",
    ["method", "endpoint", "status_code"],
    buckets=(0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0, 1.5, 2.5, 5.0, 10.0),
)


def jlog(level: str = "info", **fields: Any) -> None:
    fields.setdefault("ts", time.time())
    message = json.dumps(fields, separators=(",", ":"))
    getattr(logging, level if hasattr(logging, level) else "info")(message)


def metrics_app():
    async def handler() -> Response:
        data = generate_latest(REGISTRY)
        return Response(content=data, media_type=CONTENT_TYPE_LATEST)

    return handler
