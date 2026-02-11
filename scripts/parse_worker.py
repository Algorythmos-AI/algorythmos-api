"""CLI wrapper to run the durable parser async worker."""

from __future__ import annotations

from document_processing.workers.parse_worker import main


if __name__ == "__main__":
    raise SystemExit(main())
