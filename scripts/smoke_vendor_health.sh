#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-https://api.algorythmos.fr}"   # set to http://localhost:8080/api for local
URL="${API_BASE%/}/vendor/healthz"
THRESHOLD="${VENDOR_HEALTH_FAST_SEC:-1.0}"

# One quick probe
code=$(curl -s -o /dev/null -w "%{http_code}" "$URL")
time_total=$(curl -s -o /dev/null -w "%{time_total}" "$URL")

echo "vendor health: code=$code, time=${time_total}s"
if [[ "$code" != "204" && "$code" != "502" ]]; then
  echo "Unexpected status code: $code"
  exit 1
fi
awk -v t="$THRESHOLD" -v x="$time_total" 'BEGIN{ if (x>t) { printf "Too slow: %.3fs > %.3fs\n", x, t; exit 2 } }'
echo "OK: fast (<= ${THRESHOLD}s)"
