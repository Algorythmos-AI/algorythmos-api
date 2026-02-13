#!/bin/bash
# Simple smoke test for deployment validation

set -e

API_BASE=${API_BASE:-"https://api.algorythmos.com"}

echo "🔍 Testing API endpoints..."

# Test version endpoint
echo "Testing /version..."
VERSION_RESPONSE=$(curl -s "${API_BASE}/version")
if echo "$VERSION_RESPONSE" | grep -q "api-algorythmos"; then
    echo "✅ /version endpoint working"
else
    echo "❌ /version endpoint failed"
    exit 1
fi

# Test vendor health endpoint (should be fast)
echo "Testing /vendor/healthz..."
START_TIME=$(date +%s%N)
HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${API_BASE}/vendor/healthz")
END_TIME=$(date +%s%N)
DURATION_MS=$(( (END_TIME - START_TIME) / 1000000 ))

if [[ "$HEALTH_STATUS" == "502" ]] && [[ $DURATION_MS -lt 2000 ]]; then
    echo "✅ /vendor/healthz working (${HEALTH_STATUS}, ${DURATION_MS}ms)"
else
    echo "❌ /vendor/healthz failed (${HEALTH_STATUS}, ${DURATION_MS}ms)"
    exit 1
fi

echo "🎉 All smoke tests passed!"
