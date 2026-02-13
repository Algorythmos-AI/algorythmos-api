#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_ENV_FILE="${BACKEND_ENV_FILE:-${ROOT_DIR}/.env}"
FRONTEND_ENV_FILE="${FRONTEND_ENV_FILE:-${ROOT_DIR}/frontend/.env.local}"

read_var_from_file() {
  local var_name="$1"
  local file_path="$2"
  local line

  [[ -f "$file_path" ]] || return 1

  line="$(grep -E "^[[:space:]]*${var_name}[[:space:]]*=" "$file_path" | tail -n 1 || true)"
  [[ -n "$line" ]] || return 1

  line="${line#*=}"
  line="${line%%#*}"
  line="${line%$'\r'}"
  line="$(echo "$line" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
  line="${line%\"}"
  line="${line#\"}"
  [[ -n "$line" ]] || return 1

  printf '%s' "$line"
}

resolve_var() {
  local var_name="$1"
  local file_path="$2"
  local env_val="${!var_name:-}"

  if [[ -n "$env_val" ]]; then
    printf '%s' "$env_val"
    return 0
  fi

  read_var_from_file "$var_name" "$file_path"
}

missing=()

audit_required_var() {
  local var_name="$1"
  local file_path="$2"
  if ! resolve_var "$var_name" "$file_path" >/dev/null 2>&1; then
    missing+=("${var_name} (expected in env or ${file_path})")
  fi
}

audit_required_var "ALG_API_KEY" "$BACKEND_ENV_FILE"
audit_required_var "ALG_TENANT_ID" "$BACKEND_ENV_FILE"
audit_required_var "ENV" "$BACKEND_ENV_FILE"

env_value="$(resolve_var "ENV" "$BACKEND_ENV_FILE" 2>/dev/null || true)"
cors_value="$(resolve_var "CORS_ORIGINS" "$BACKEND_ENV_FILE" 2>/dev/null || true)"
env_value_lower="$(printf '%s' "$env_value" | tr '[:upper:]' '[:lower:]')"

if [[ "$env_value_lower" == "prod" || "$env_value_lower" == "production" ]]; then
  if [[ -z "$cors_value" || "$cors_value" == "*" ]]; then
    missing+=("CORS_ORIGINS (must be explicit and not '*' in production)")
  fi

  audit_required_var "REDIS_URL" "$BACKEND_ENV_FILE"
  audit_required_var "GOOGLE_CLIENT_ID" "$BACKEND_ENV_FILE"
fi

api_base="$(resolve_var "NEXT_PUBLIC_API_BASE_URL" "$FRONTEND_ENV_FILE" 2>/dev/null || true)"
legacy_api_base="$(resolve_var "NEXT_PUBLIC_API_URL" "$FRONTEND_ENV_FILE" 2>/dev/null || true)"

if [[ -z "$api_base" && -z "$legacy_api_base" ]]; then
  missing+=("NEXT_PUBLIC_API_BASE_URL or NEXT_PUBLIC_API_URL (expected in env or ${FRONTEND_ENV_FILE})")
fi

if ((${#missing[@]} > 0)); then
  echo "Environment contract verification failed. Missing or invalid values:"
  for item in "${missing[@]}"; do
    echo "- ${item}"
  done
  exit 1
fi

echo "Environment contract verification passed."
if [[ -n "$api_base" ]]; then
  echo "- Frontend API base source: NEXT_PUBLIC_API_BASE_URL"
else
  echo "- Frontend API base source: NEXT_PUBLIC_API_URL (legacy fallback)"
fi
