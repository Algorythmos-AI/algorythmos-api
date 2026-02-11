#!/usr/bin/env bash
set -euo pipefail

echo "== Stage 8: Runs index =="

ALG_API_KEY="${ALG_API_KEY:-local_dummy}"
VENDOR_WEBHOOK_SECRET="${VENDOR_WEBHOOK_SECRET:-secret}"
export ALG_API_KEY
export VENDOR_WEBHOOK_SECRET

DEFAULT_PORT="${PORT:-8080}"
MAX_TRIES=40
LOG_FILE="$(mktemp -t stage8-uvicorn.XXXXXX)"

pick_port() {
  local base="$DEFAULT_PORT"
  for try in $(seq 0 20); do
    local candidate=$((base + try))
    if ! lsof -iTCP -sTCP:LISTEN -nP 2>/dev/null | grep -q ":${candidate} "; then
      echo "${candidate}"
      return 0
    fi
  done
  echo "Failed to find free port near ${DEFAULT_PORT}" >&2
  return 1
}

PORT="$(pick_port)"
echo "Using PORT=${PORT}"

set +e
uv run python - "${PORT}" >"${LOG_FILE}" 2>&1 <<'PY' &
import importlib.util
import pathlib
import sys
import uvicorn

port = int(sys.argv[1])
spec = importlib.util.spec_from_file_location("stage8_app", pathlib.Path("app.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

uvicorn.run(module.app, host="127.0.0.1", port=port)
PY
SERVER_PID=$!
set -e
trap 'kill ${SERVER_PID} 2>/dev/null || true; rm -f "${LOG_FILE}"' EXIT

BASE_API="http://127.0.0.1:${PORT}/api"
BASE_ROOT="http://127.0.0.1:${PORT}"
API_BASE=""

for _ in $(seq 1 ${MAX_TRIES}); do
  if curl -sf "${BASE_API}/version" >/dev/null; then
    API_BASE="${BASE_API}"
    break
  fi
  if curl -sf "${BASE_ROOT}/version" >/dev/null; then
    API_BASE="${BASE_ROOT}"
    break
  fi
  sleep 0.25
done

if [[ -z "${API_BASE}" ]]; then
  echo "❌ Server did not become ready"
  tail -n 200 "${LOG_FILE}" || true
  exit 1
fi

echo "API_BASE=${API_BASE}"
echo "Running Stage-8 pytest suite..."

if ! uv run pytest -q tests/test_stage8_runs_index.py; then
  echo "❌ Stage 8 tests failed"
  tail -n 200 "${LOG_FILE}" || true
  exit 2
fi

echo "🎯 Stage 8 ✅ PASSED"
