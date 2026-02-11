#!/usr/bin/env bash
set -euo pipefail

export ALG_API_KEY="${ALG_API_KEY:-local_dummy}"
export VENDOR_WEBHOOK_SECRET="${VENDOR_WEBHOOK_SECRET:-secret}"
export DATABASE_URL="${DATABASE_URL:-sqlite+aiosqlite:///./dev.db}"

if ! uv run pytest -q tests/test_stage6c_openapi.py; then
  echo "❌ Stage 6C OpenAPI pytest suite failed"
  exit 1
fi

echo "🎯 RESULT: Stage 6C OpenAPI ✅ PASSED"
