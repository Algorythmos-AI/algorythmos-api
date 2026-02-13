#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
BACKEND_BASE_URL="http://${BACKEND_HOST}:${BACKEND_PORT}"
BACKEND_LOG_FILE="${BACKEND_LOG_FILE:-${ROOT_DIR}/backend_verify.log}"
DEFAULT_PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"

if [[ -x "$DEFAULT_PYTHON_BIN" ]]; then
  PYTHON_BIN="${PYTHON_BIN:-$DEFAULT_PYTHON_BIN}"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1"
    exit 1
  fi
}

require_cmd "$PYTHON_BIN"
require_cmd curl
require_cmd npm

cd "$ROOT_DIR"

"$ROOT_DIR/scripts/verify_env_contract.sh"

export ALG_API_KEY="${ALG_API_KEY:-local-dev-api-key}"
export ALG_TENANT_ID="${ALG_TENANT_ID:-default}"
export ENV="${ENV:-dev}"
export CORS_ORIGINS="${CORS_ORIGINS:-http://localhost:3000,https://app.algorythmos.com}"

if lsof -iTCP:"${BACKEND_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port ${BACKEND_PORT} is already in use. Set BACKEND_PORT to an available port and retry."
  exit 1
fi

"$PYTHON_BIN" -m uvicorn app:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" >"$BACKEND_LOG_FILE" 2>&1 &
backend_pid=$!

cleanup() {
  if kill -0 "$backend_pid" >/dev/null 2>&1; then
    kill "$backend_pid" >/dev/null 2>&1 || true
    wait "$backend_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT

backend_ready=0
for _ in $(seq 1 30); do
  if curl -fsS "${BACKEND_BASE_URL}/alg/healthz" >/dev/null; then
    backend_ready=1
    break
  fi
  sleep 1
done

if [[ "$backend_ready" -ne 1 ]]; then
  echo "Backend failed to become healthy at ${BACKEND_BASE_URL}/alg/healthz"
  echo "Last backend log lines:"
  tail -n 40 "$BACKEND_LOG_FILE" || true
  exit 1
fi

echo "Backend health check passed (${BACKEND_BASE_URL}/alg/healthz)."

if ! curl -fsS "${BACKEND_BASE_URL}/docs" >/dev/null; then
  echo "Backend docs endpoint check failed (${BACKEND_BASE_URL}/docs)."
  exit 1
fi

echo "Backend docs endpoint check passed (${BACKEND_BASE_URL}/docs)."

echo "Running frontend production build..."
npm --prefix frontend run build

echo "Local stack verification passed."
