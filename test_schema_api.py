#!/usr/bin/env python3
"""Test script for Schema API endpoints."""

import json
import requests

API_BASE = "http://localhost:8080/api"
API_KEY = "algo_dWukMWn8YyFfkdnL4yITRgp8042vYbz1ckk2aY3dv"

headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json",
}

def test_create_schema():
    """Test creating a new extraction schema."""
    payload = {
        "name": "Invoice Extractor",
        "description": "Extract fields from invoices",
        "fields": [
            {
                "name": "invoice_number",
                "type": "string",
                "description": "Invoice number",
                "required": True
            },
            {
                "name": "total_amount",
                "type": "number",
                "description": "Total invoice amount",
                "required": True
            },
            {
                "name": "invoice_date",
                "type": "date",
                "description": "Invoice date",
                "required": False
            },
            {
                "name": "line_items",
                "type": "array",
                "description": "List of line items",
                "required": False
            }
        ],
        "metadata": {
            "industry": "general",
            "version": "1.0"
        }
    }
    
    print("🚀 Creating schema...")
    response = requests.post(
        f"{API_BASE}/schemas",
        headers=headers,
        json=payload
    )
    
    print(f"Status: {response.status_code}")
    if response.status_code == 201:
        data = response.json()
        print("✅ Schema created successfully!")
        print(json.dumps(data, indent=2))
        return data["schema_id"]
    else:
        print(f"❌ Error: {response.text}")
        return None


def test_list_schemas():
    """Test listing schemas."""
    print("\n📋 Listing schemas...")
    response = requests.get(
        f"{API_BASE}/schemas",
        headers=headers,
        params={"limit": 10}
    )
    
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Found {data['total']} schemas")
        print(json.dumps(data, indent=2))
    else:
        print(f"❌ Error: {response.text}")


def test_get_schema(schema_id):
    """Test getting a specific schema."""
    print(f"\n🔍 Getting schema {schema_id}...")
    response = requests.get(
        f"{API_BASE}/schemas/{schema_id}",
        headers=headers
    )
    
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print("✅ Schema retrieved successfully!")
        print(json.dumps(data, indent=2))
    else:
        print(f"❌ Error: {response.text}")


def test_update_schema(schema_id):
    """Test updating a schema."""
    print(f"\n✏️  Updating schema {schema_id}...")
    payload = {
        "description": "Extract fields from invoices (updated)",
        "fields": [
            {
                "name": "invoice_number",
                "type": "string",
                "description": "Invoice number (updated)",
                "required": True
            },
            {
                "name": "total_amount",
                "type": "number",
                "description": "Total invoice amount",
                "required": True
            },
            {
                "name": "customer_name",
                "type": "string",
                "description": "Customer name (new field)",
                "required": False
            }
        ]
    }
    
    response = requests.patch(
        f"{API_BASE}/schemas/{schema_id}",
        headers=headers,
        json=payload
    )
    
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Schema updated! Now version {data['version']}")
        print(json.dumps(data, indent=2))
    else:
        print(f"❌ Error: {response.text}")


def test_delete_schema(schema_id):
    """Test deleting a schema."""
    print(f"\n🗑️  Deleting schema {schema_id}...")
    response = requests.delete(
        f"{API_BASE}/schemas/{schema_id}",
        headers=headers
    )
    
    print(f"Status: {response.status_code}")
    if response.status_code == 204:
        print("✅ Schema deleted successfully!")
    else:
        print(f"❌ Error: {response.text}")


if __name__ == "__main__":
    print("=" * 60)
    print("SCHEMA API TEST SUITE")
    print("=" * 60)
    
    # Create a schema
    schema_id = test_create_schema()
    
    if schema_id:
        # List all schemas
        test_list_schemas()
        
        # Get the specific schema
        test_get_schema(schema_id)
        
        # Update the schema
        test_update_schema(schema_id)
        
        # Delete the schema
        test_delete_schema(schema_id)
        
        # Verify it's gone
        print("\n🔍 Verifying deletion...")
        test_get_schema(schema_id)
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE!")
    print("=" * 60)
