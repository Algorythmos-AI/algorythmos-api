#!/usr/bin/env bash
set -euo pipefail

echo "== Stage 7: pytest + respx suite =="
export ALG_API_KEY="${ALG_API_KEY:-local_dummy}"
export VENDOR_WEBHOOK_SECRET="${VENDOR_WEBHOOK_SECRET:-secret}"
export API_BASE="${API_BASE:-https://vendor.test}"

echo "Running pytest (Stage 7)..."
uv run pytest -q tests/test_stage7_*.py && echo "🎯 Stage 7 ✅ PASSED"
