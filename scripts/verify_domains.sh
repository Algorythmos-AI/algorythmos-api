#!/usr/bin/env bash
set -euo pipefail

failures=0

check_2xx_or_3xx() {
  local label="$1"
  local url="$2"
  local code

  code="$(curl -sS -o /dev/null -w "%{http_code}" --max-time 20 "$url" || true)"
  if [[ "$code" =~ ^[23][0-9][0-9]$ ]]; then
    echo "PASS ${label}: ${url} (HTTP ${code})"
  else
    echo "FAIL ${label}: ${url} returned HTTP ${code:-000}"
    failures=$((failures + 1))
  fi
}

check_www_redirect() {
  local url="https://www.algorythmos.com"
  local headers
  local code
  local location

  headers="$(curl -sS -I --max-time 20 "$url" || true)"
  code="$(echo "$headers" | awk 'NR==1 {print $2}')"
  location="$(echo "$headers" | awk -F': ' 'tolower($1)=="location" {print $2}' | tr -d '\r' | tail -n 1)"

  # Permanent redirects are valid as either 301 or 308 depending on edge platform defaults.
  if [[ ( "$code" == "301" || "$code" == "308" ) && "$location" == https://algorythmos.com* ]]; then
    echo "PASS WWW redirect: ${url} -> ${location} (HTTP ${code})"
  else
    echo "FAIL WWW redirect: expected 301 or 308 to https://algorythmos.com*, got code=${code:-000}, location=${location:-<none>}"
    failures=$((failures + 1))
  fi
}

check_api_health() {
  local candidates=(
    "https://api.algorythmos.com/health"
    "https://api.algorythmos.com/alg/healthz"
    "https://api.algorythmos.com/api/health"
    "https://api.algorythmos.com/api/alg/healthz"
    "https://api.algorythmos.com/docs"
    "https://api.algorythmos.com/api/docs"
  )

  local passed=0
  local code

  for url in "${candidates[@]}"; do
    code="$(curl -sS -o /dev/null -w "%{http_code}" --max-time 20 "$url" || true)"
    if [[ "$code" =~ ^[23][0-9][0-9]$ ]]; then
      echo "PASS API probe: ${url} (HTTP ${code})"
      passed=1
      break
    else
      echo "WARN API probe: ${url} returned HTTP ${code:-000}"
    fi
  done

  if [[ "$passed" -ne 1 ]]; then
    echo "FAIL API domain: no accepted health/docs endpoint responded with 2xx/3xx"
    failures=$((failures + 1))
  fi
}

check_2xx_or_3xx "Marketing apex" "https://algorythmos.com"
check_www_redirect
check_2xx_or_3xx "Frontend app" "https://app.algorythmos.com"
check_api_health

if [[ "$failures" -gt 0 ]]; then
  echo "Domain verification failed with ${failures} issue(s)."
  exit 1
fi

echo "Domain verification passed."
