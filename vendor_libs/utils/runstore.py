from __future__ import annotations

import threading
import time
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple


class RunStore:
    """Thread-safe in-memory store for run metadata with TTL eviction."""

    def __init__(self, ttl_seconds: float = 86400.0, max_items: int = 10000) -> None:
        self.ttl = ttl_seconds
        self.max = max_items
        self._lock = threading.Lock()
        self._runs: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._vendor_to_run: Dict[str, Tuple[float, str]] = {}

    def _gc(self) -> None:
        now = time.time()
        stale_runs = [run_id for run_id, (ts, _) in self._runs.items() if now - ts > self.ttl]
        for run_id in stale_runs:
            self._runs.pop(run_id, None)

        stale_links = [job_id for job_id, (ts, _) in self._vendor_to_run.items() if now - ts > self.ttl]
        for job_id in stale_links:
            self._vendor_to_run.pop(job_id, None)

        # Basic eviction when exceeding capacity (remove oldest entries)
        if len(self._runs) > self.max:
            excess = len(self._runs) - self.max
            for run_id in list(sorted(self._runs, key=lambda k: self._runs[k][0]))[:excess]:
                self._runs.pop(run_id, None)

        if len(self._vendor_to_run) > self.max:
            excess = len(self._vendor_to_run) - self.max
            for job_id in list(sorted(self._vendor_to_run, key=lambda k: self._vendor_to_run[k][0]))[:excess]:
                self._vendor_to_run.pop(job_id, None)

    def put_run(self, run_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            self._gc()
            stored = deepcopy(payload)
            self._runs[run_id] = (time.time(), stored)
            return deepcopy(stored)

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            self._gc()
            item = self._runs.get(run_id)
            if not item:
                return None
            _, payload = item
            return deepcopy(payload)

    def link_vendor_job(self, vendor_job_id: str, run_id: str) -> None:
        with self._lock:
            self._gc()
            self._vendor_to_run[vendor_job_id] = (time.time(), run_id)

    def find_run_by_vendor_job(self, vendor_job_id: str) -> Optional[str]:
        with self._lock:
            self._gc()
            item = self._vendor_to_run.get(vendor_job_id)
            if not item:
                return None
            _, run_id = item
            return run_id

    def complete_run(
        self,
        run_id: str,
        *,
        status: str,
        output: Optional[Dict[str, Any]] = None,
        error: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            self._gc()
            timestamp = time.time()
            updated_iso = datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
            stored = self._runs.get(run_id)
            if not stored:
                # Create entry if missing for idempotency
                record: Dict[str, Any] = {
                    "id": run_id,
                    "status": status,
                    "output": deepcopy(output) if output is not None else None,
                    "error": deepcopy(error) if error is not None else None,
                    "updated_at": updated_iso,
                }
                self._runs[run_id] = (timestamp, record)
                return deepcopy(record)

            _, payload = stored
            payload["status"] = status
            payload["updated_at"] = updated_iso
            if output is not None:
                payload["output"] = deepcopy(output)
                payload.pop("error", None)
            if error is not None:
                payload["error"] = deepcopy(error)
                payload.pop("output", None)
            self._runs[run_id] = (timestamp, payload)
            return deepcopy(payload)


run_store = RunStore()
