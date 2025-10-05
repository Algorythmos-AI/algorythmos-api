#!/usr/bin/env bash
set -euo pipefail

# --- config ---
DEFAULT_PORT="${PORT:-8080}"
MAX_TRIES=20
READY_TIMEOUT=25
# Do NOT pass --root-path; app may already set root_path="/api"
UV_CMD_BASE="uv run uvicorn app:app --host 127.0.0.1"

# --- pick a free port (8080 then fallbacks) ---
pick_port() {
  local p="$DEFAULT_PORT"
  for try in $(seq 0 20); do
    local CANDIDATE=$((p + try))
    if ! lsof -iTCP -sTCP:LISTEN -nP 2>/dev/null | grep -q ":${CANDIDATE} "; then
      echo "${CANDIDATE}"
      return 0
    fi
  done
  echo "No free port near ${DEFAULT_PORT}" >&2
  return 1
}

PORT="$(pick_port)"
echo ">> Using PORT=${PORT}"

# --- start server in background ---
# Ensure ALG_API_KEY presence doesn't block dev; fail-fast happens only in prod per your settings.
ALG_API_KEY="${ALG_API_KEY:-local_dummy}"
export ALG_API_KEY

set +e
${UV_CMD_BASE} --port "${PORT}" > /tmp/uvicorn.stage2.log 2>&1 &
SRV_PID=$!
set -e
trap 'kill ${SRV_PID} 2>/dev/null || true' EXIT

# --- wait for readiness & detect root path (/api vs root) ---
BASE_A="http://localhost:${PORT}/api"
BASE_B="http://localhost:${PORT}"
SELECTED_BASE=""
echo ">> Probing ${BASE_A}/version and ${BASE_B}/version for readiness..."

for i in $(seq 1 ${MAX_TRIES}); do
  code_a=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_A}/version" || true)
  code_b=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_B}/version" || true)
  if [[ "$code_a" == "200" ]]; then SELECTED_BASE="$BASE_A"; break; fi
  if [[ "$code_b" == "200" ]]; then SELECTED_BASE="$BASE_B"; break; fi
  sleep 1
done

if [[ -z "${SELECTED_BASE}" ]]; then
  echo "!! Server not ready within ${READY_TIMEOUT}s (neither /api/version nor /version returned 200)"
  echo "---- uvicorn logs ----"
  tail -n 200 /tmp/uvicorn.stage2.log || true
  exit 2
fi

export API_BASE="${SELECTED_BASE}"
echo ">> Server ready. API_BASE=${API_BASE}"
echo ">> Running smokes."

# --- pytest smoke (fast + p95 stable) ---
uv run pytest -q tests/test_smoke_vendor_health.py || {
  echo "❌ Pytest smoke failed"
  echo "---- uvicorn logs ----"
  tail -n 200 /tmp/uvicorn.stage2.log || true
  exit 3
}

# --- curl smoke (single-hit speed & status semantics) ---
chmod +x ./scripts/smoke_vendor_health.sh
API_BASE="${API_BASE}" ./scripts/smoke_vendor_health.sh || {
  echo "❌ Curl smoke failed"
  echo "---- uvicorn logs ----"
  tail -n 200 /tmp/uvicorn.stage2.log || true
  exit 4
}

echo "🎯 RESULT: Stage 2 Vendor Health SMOKE ✅ PASSED"
