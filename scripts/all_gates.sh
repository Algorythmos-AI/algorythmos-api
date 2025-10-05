#!/usr/bin/env bash
set -euo pipefail

export ALG_API_KEY="${ALG_API_KEY:-local_dummy}"
export VENDOR_WEBHOOK_SECRET="${VENDOR_WEBHOOK_SECRET:-secret}"

echo "== Running Stage 2 gate =="
make stage2-gate
echo "== Stage 2 ✅ =="

echo "== Running Stage 3 gate =="
make stage3-gate
echo "== Stage 3 ✅ =="

echo "== Running Stage 4 gate =="
make stage4-gate
echo "== Stage 4 ✅ =="

echo ""
echo "🎉 ALL GATES ✅ PASSED"
