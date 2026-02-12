#!/bin/bash

# Configuration
API_URL="http://localhost:8000/api"
API_KEY="test-api-key"
TENANT_ID="test-tenant"
TEST_PDF="frontend/test-files/orange_invoice_001.pdf"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

# Helper function
check_status() {
    if [ "$1" -eq "$2" ]; then
        echo -e "${GREEN}✓ Success ($1)${NC}"
    else
        echo -e "${RED}✗ Failed (Expected $2, got $1)${NC}"
        # exit 1
    fi
}

echo "========================================================"
echo "Algorythmos API Verification Suite"
echo "========================================================"

# 1. Health Check
echo -e "\n1. Testing Health Endpoint..."
status=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/alg/healthz")
check_status "$status" 200

# 2. Auth Check - Missing Headers (Expect 400/401)
echo -e "\n2. Testing Auth (Missing Headers)..."
status=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/schemas")
if [ "$status" -eq 400 ] || [ "$status" -eq 401 ] || [ "$status" -eq 403 ]; then
    echo -e "${GREEN}✓ Success (Rejected with $status)${NC}"
else
    echo -e "${RED}✗ Failed (Should be rejected, got $status)${NC}"
fi

# 3. Auth Check - Valid Headers
echo -e "\n3. Testing Auth (Valid Headers)..."
status=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "X-API-Key: $API_KEY" \
    -H "X-Tenant-ID: $TENANT_ID" \
    "$API_URL/schemas")
check_status "$status" 200

# 4. Create Schema
echo -e "\n4. Creating Schema..."
SCHEMA_ID="test-schema-$(date +%s)"
response=$(curl -s -X POST "$API_URL/schemas" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -d "{
        \"schema_id\": \"$SCHEMA_ID\",
        \"name\": \"Test Invoice Schema\",
        \"fields\": [
            {\"name\": \"total_amount\", \"type\": \"currency\", \"description\": \"Total invoice amount\"},
            {\"name\": \"invoice_date\", \"type\": \"date\", \"description\": \"Invoice date\"}
        ]
    }")
echo "  Response: $(echo "$response" | cut -c 1-100)..."

# 5. Upload & Extract
echo -e "\n5. Testing Upload & Extract..."
if [ -f "$TEST_PDF" ]; then
    status=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "$API_URL/extract/upload?provider_hint=orange" \
        -H "X-API-Key: $API_KEY" \
        -H "X-Tenant-ID: $TENANT_ID" \
        -F "files=@$TEST_PDF")
    check_status "$status" 200
else
    echo -e "${RED}✗ Test PDF not found at $TEST_PDF${NC}"
fi

# 6. File Upload (Direct)
echo -e "\n6. Testing File Upload..."
if [ -f "$TEST_PDF" ]; then
    status=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "$API_URL/files" \
        -H "X-API-Key: $API_KEY" \
        -H "X-Tenant-ID: $TENANT_ID" \
        -F "file=@$TEST_PDF")
    if [ "$status" -eq 200 ] || [ "$status" -eq 201 ]; then
        echo -e "${GREEN}✓ Success ($status)${NC}"
    else
        echo -e "${RED}✗ Failed (Expected 200/201, got $status)${NC}"
    fi
else
    echo -e "${RED}✗ Test PDF not found at $TEST_PDF${NC}"
fi

echo -e "\n========================================================"
echo "Verification Complete"
echo "========================================================"
