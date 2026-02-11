from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional, Tuple


class TTLCache:
    def __init__(self, ttl_seconds: float = 600.0, max_items: int = 2000) -> None:
        self.ttl = ttl_seconds
        self.max = max_items
        self._lock = threading.Lock()
        self._store: Dict[str, Tuple[float, Any]] = {}

    def _gc(self) -> None:
        now = time.time()
        dead = [k for k, (ts, _) in self._store.items() if now - ts > self.ttl]
        for k in dead:
            self._store.pop(k, None)
        if len(self._store) > self.max:
            for k in list(self._store.keys())[: len(self._store) - self.max]:
                self._store.pop(k, None)

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            self._gc()
            item = self._store.get(key)
            if not item:
                return None
            ts, val = item
            if time.time() - ts > self.ttl:
                self._store.pop(key, None)
                return None
            return val

    def put(self, key: str, value: Any) -> Any:
        with self._lock:
            self._gc()
            self._store[key] = (time.time(), value)
            return value


idem_cache = TTLCache(ttl_seconds=600.0, max_items=2000)
