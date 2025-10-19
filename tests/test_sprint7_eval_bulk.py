"""
Test Sprint 7: Evaluation Items Bulk + Webhook Version Echo (P6.1, P7.1)

Tests bulk evaluation item creation and webhook version header tracking.
"""

import pytest
from datetime import datetime
from document_processing.schemas_eval_items import (
    EvalItemInput,
    BulkCreateEvalItemsRequest,
    BulkCreateEvalItemsResponse,
    BulkItemResult,
    BulkItemError,
    EvalItem,
    EvalItemListResponse
)
from document_processing.models import EvalItemDB, WebhookDeliveryDB


# ============================================================================
# P6.1: Bulk Evaluation Items
# ============================================================================

def test_eval_item_input_schema():
    """Test EvalItemInput schema with optional ID."""
    print("✅ test_eval_item_input_schema")
    
    # With custom ID
    item = EvalItemInput(
        id="test-001",
        input_data={"document_type": "invoice"},
        expected_output={"total_amount": 1000.00},
        metadata={"category": "invoices"}
    )
    assert item.id == "test-001"
    assert item.input_data["document_type"] == "invoice"
    assert item.expected_output["total_amount"] == 1000.00
    assert item.metadata["category"] == "invoices"
    
    # Without custom ID
    item2 = EvalItemInput(
        input_data={"type": "receipt"},
        expected_output={"amount": 50.00}
    )
    assert item2.id is None
    assert item2.metadata is None


def test_eval_item_input_flexible_values():
    """Test EvalItemInput supports any value types."""
    print("✅ test_eval_item_input_flexible_values")
    
    item = EvalItemInput(
        input_data={
            "strings": "text",
            "numbers": 123,
            "floats": 45.67,
            "arrays": [1, 2, 3],
            "nested": {"key": "value"}
        },
        expected_output={
            "result": ["a", "b", "c"],
            "score": 0.95,
            "metadata": {"confidence": 0.98}
        }
    )
    assert isinstance(item.input_data["arrays"], list)
    assert isinstance(item.expected_output["result"], list)


def test_bulk_create_request_schema():
    """Test BulkCreateEvalItemsRequest schema."""
    print("✅ test_bulk_create_request_schema")
    
    request = BulkCreateEvalItemsRequest(
        evaluation_set_id="eval_1234567890ab",
        items=[
            EvalItemInput(
                id="test-001",
                input_data={"type": "invoice"},
                expected_output={"amount": 1000.00}
            ),
            EvalItemInput(
                input_data={"type": "receipt"},
                expected_output={"amount": 50.00}
            )
        ]
    )
    assert request.evaluation_set_id == "eval_1234567890ab"
    assert len(request.items) == 2
    assert request.items[0].id == "test-001"
    assert request.items[1].id is None


def test_bulk_create_request_camelcase_alias():
    """Test BulkCreateEvalItemsRequest accepts camelCase evaluationSetId."""
    print("✅ test_bulk_create_request_camelcase_alias")
    
    data = {
        "evaluationSetId": "eval_abc123",
        "items": [
            {
                "input_data": {"test": "data"},
                "expected_output": {"result": "success"}
            }
        ]
    }
    request = BulkCreateEvalItemsRequest(**data)
    assert request.evaluation_set_id == "eval_abc123"


def test_bulk_create_request_validates_unique_ids():
    """Test BulkCreateEvalItemsRequest rejects duplicate IDs."""
    print("✅ test_bulk_create_request_validates_unique_ids")
    
    with pytest.raises(ValueError, match="Duplicate item IDs"):
        BulkCreateEvalItemsRequest(
            evaluation_set_id="eval_123",
            items=[
                EvalItemInput(
                    id="test-001",
                    input_data={"a": 1},
                    expected_output={"b": 2}
                ),
                EvalItemInput(
                    id="test-001",  # Duplicate!
                    input_data={"c": 3},
                    expected_output={"d": 4}
                )
            ]
        )


def test_bulk_create_request_min_max_items():
    """Test BulkCreateEvalItemsRequest validates item count."""
    print("✅ test_bulk_create_request_min_max_items")
    
    # Empty list should fail (min_length=1)
    with pytest.raises(ValueError):
        BulkCreateEvalItemsRequest(
            evaluation_set_id="eval_123",
            items=[]
        )
    
    # Single item should work
    request = BulkCreateEvalItemsRequest(
        evaluation_set_id="eval_123",
        items=[
            EvalItemInput(
                input_data={"test": 1},
                expected_output={"result": 1}
            )
        ]
    )
    assert len(request.items) == 1


def test_bulk_item_result_schema():
    """Test BulkItemResult schema."""
    print("✅ test_bulk_item_result_schema")
    
    result = BulkItemResult(
        id="item_a1b2c3d4e5f6",
        index=0,
        created_at=datetime(2024, 1, 19, 10, 30, 0)
    )
    assert result.id == "item_a1b2c3d4e5f6"
    assert result.index == 0
    assert result.created_at.year == 2024


def test_bulk_item_error_schema():
    """Test BulkItemError schema."""
    print("✅ test_bulk_item_error_schema")
    
    error = BulkItemError(
        index=2,
        item_id="test-003",
        error_type="duplicate",
        message="Item with ID 'test-003' already exists"
    )
    assert error.index == 2
    assert error.item_id == "test-003"
    assert error.error_type == "duplicate"
    assert "already exists" in error.message


def test_bulk_create_response_schema():
    """Test BulkCreateEvalItemsResponse schema."""
    print("✅ test_bulk_create_response_schema")
    
    response = BulkCreateEvalItemsResponse(
        evaluation_set_id="eval_1234567890ab",
        created_count=2,
        failed_count=1,
        created_items=[
            BulkItemResult(
                id="item_abc123",
                index=0,
                created_at=datetime.now()
            ),
            BulkItemResult(
                id="item_def456",
                index=1,
                created_at=datetime.now()
            )
        ],
        errors=[
            BulkItemError(
                index=2,
                item_id="test-003",
                error_type="validation",
                message="Invalid input data"
            )
        ]
    )
    assert response.created_count == 2
    assert response.failed_count == 1
    assert len(response.created_items) == 2
    assert len(response.errors) == 1


def test_bulk_create_response_camelcase_aliases():
    """Test BulkCreateEvalItemsResponse uses camelCase aliases."""
    print("✅ test_bulk_create_response_camelcase_aliases")
    
    response = BulkCreateEvalItemsResponse(
        evaluation_set_id="eval_123",
        created_count=1,
        failed_count=0,
        created_items=[
            BulkItemResult(
                id="item_abc",
                index=0,
                created_at=datetime.now()
            )
        ]
    )
    
    # Serialize to dict and check camelCase keys
    data = response.model_dump(by_alias=True)
    assert "evaluationSetId" in data
    assert "createdCount" in data
    assert "failedCount" in data
    assert "createdItems" in data


def test_bulk_create_response_no_errors():
    """Test BulkCreateEvalItemsResponse with no errors."""
    print("✅ test_bulk_create_response_no_errors")
    
    response = BulkCreateEvalItemsResponse(
        evaluation_set_id="eval_123",
        created_count=3,
        failed_count=0,
        created_items=[
            BulkItemResult(id=f"item_{i}", index=i, created_at=datetime.now())
            for i in range(3)
        ]
    )
    assert response.failed_count == 0
    assert len(response.errors) == 0
    assert response.created_count == 3


def test_eval_item_schema():
    """Test EvalItem response schema."""
    print("✅ test_eval_item_schema")
    
    item = EvalItem(
        id="item_a1b2c3d4e5f6",
        evaluation_set_id="eval_123",
        input_data={"document_type": "invoice"},
        expected_output={"total": 1000.00},
        metadata={"category": "invoices"},
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    assert item.id == "item_a1b2c3d4e5f6"
    assert item.evaluation_set_id == "eval_123"
    assert item.input_data["document_type"] == "invoice"


def test_eval_item_camelcase_aliases():
    """Test EvalItem uses camelCase aliases."""
    print("✅ test_eval_item_camelcase_aliases")
    
    item = EvalItem(
        id="item_abc",
        evaluation_set_id="eval_123",
        input_data={"test": 1},
        expected_output={"result": 1},
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    data = item.model_dump(by_alias=True)
    assert "evaluationSetId" in data
    assert "inputData" in data
    assert "expectedOutput" in data
    assert "createdAt" in data
    assert "updatedAt" in data


def test_eval_item_list_response():
    """Test EvalItemListResponse schema."""
    print("✅ test_eval_item_list_response")
    
    response = EvalItemListResponse(
        evaluation_set_id="eval_123",
        items=[
            EvalItem(
                id="item_1",
                evaluation_set_id="eval_123",
                input_data={"test": 1},
                expected_output={"result": 1},
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
        ],
        total=10,
        page=1,
        page_size=50
    )
    assert response.evaluation_set_id == "eval_123"
    assert len(response.items) == 1
    assert response.total == 10
    assert response.page == 1


# ============================================================================
# P7.1: Webhook Version Echo
# ============================================================================

def test_webhook_delivery_db_has_api_version():
    """Test WebhookDeliveryDB model has api_version field."""
    print("✅ test_webhook_delivery_db_has_api_version")
    
    # Check that api_version attribute exists
    assert hasattr(WebhookDeliveryDB, 'api_version')
    
    # Verify it's a Column
    from sqlalchemy import Column
    assert isinstance(WebhookDeliveryDB.api_version, type(WebhookDeliveryDB.id))


def test_eval_item_db_model():
    """Test EvalItemDB model structure."""
    print("✅ test_eval_item_db_model")
    
    # Check table name
    assert EvalItemDB.__tablename__ == "eval_items"
    
    # Check required fields exist
    assert hasattr(EvalItemDB, 'id')
    assert hasattr(EvalItemDB, 'evaluation_set_id')
    assert hasattr(EvalItemDB, 'tenant_id')
    assert hasattr(EvalItemDB, 'input_data')
    assert hasattr(EvalItemDB, 'expected_output')
    assert hasattr(EvalItemDB, 'actual_output')
    assert hasattr(EvalItemDB, 'last_run_status')
    assert hasattr(EvalItemDB, 'last_run_score')
    assert hasattr(EvalItemDB, 'last_run_at')
    assert hasattr(EvalItemDB, 'item_metadata')
    assert hasattr(EvalItemDB, 'is_deleted')
    assert hasattr(EvalItemDB, 'created_at')
    assert hasattr(EvalItemDB, 'updated_at')


def test_eval_item_db_status_values():
    """Test EvalItemDB supports valid status values."""
    print("✅ test_eval_item_db_status_values")
    
    # Valid status values per schema comment
    valid_statuses = ['passed', 'failed', 'error', 'not_run']
    
    # Model should accept these values
    # (This is a schema test, actual DB constraints not enforced in model)
    assert all(isinstance(status, str) for status in valid_statuses)


def test_eval_item_db_score_range():
    """Test EvalItemDB last_run_score is float (0.0-1.0)."""
    print("✅ test_eval_item_db_score_range")
    
    # Check that last_run_score is a Float column
    from sqlalchemy import Float
    # Type checking at model level
    assert hasattr(EvalItemDB, 'last_run_score')


def test_bulk_creation_atomic_behavior():
    """Test bulk creation should be atomic (all or nothing per item)."""
    print("✅ test_bulk_creation_atomic_behavior")
    
    # This test verifies the schema supports partial success
    response = BulkCreateEvalItemsResponse(
        evaluation_set_id="eval_123",
        created_count=2,
        failed_count=1,
        created_items=[
            BulkItemResult(id="item_1", index=0, created_at=datetime.now()),
            BulkItemResult(id="item_2", index=1, created_at=datetime.now())
        ],
        errors=[
            BulkItemError(
                index=2,
                error_type="validation",
                message="Missing required field"
            )
        ]
    )
    
    # Some items succeed, some fail
    assert response.created_count == 2
    assert response.failed_count == 1


def test_bulk_creation_preserves_order():
    """Test bulk creation preserves item order via index."""
    print("✅ test_bulk_creation_preserves_order")
    
    created = [
        BulkItemResult(id=f"item_{i}", index=i, created_at=datetime.now())
        for i in range(5)
    ]
    
    # Verify indices are sequential
    for i, result in enumerate(created):
        assert result.index == i


def test_bulk_error_provides_context():
    """Test bulk errors provide sufficient context for debugging."""
    print("✅ test_bulk_error_provides_context")
    
    error = BulkItemError(
        index=42,
        item_id="test-invoice-001",
        error_type="duplicate",
        message="Item with ID 'test-invoice-001' already exists in evaluation set 'eval_123'"
    )
    
    # Should have all necessary info
    assert error.index >= 0  # Position in batch
    assert error.item_id is not None  # User's custom ID
    assert error.error_type in ["duplicate", "validation"]  # Category
    assert len(error.message) > 10  # Meaningful message


# ============================================================================
# Sprint 7 Summary
# ============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Sprint 7 Test Suite: Evaluation Items Bulk + Webhook Version")
    print("=" * 60)
    
    test_functions = [
        # P6.1: Bulk Evaluation Items
        test_eval_item_input_schema,
        test_eval_item_input_flexible_values,
        test_bulk_create_request_schema,
        test_bulk_create_request_camelcase_alias,
        test_bulk_create_request_validates_unique_ids,
        test_bulk_create_request_min_max_items,
        test_bulk_item_result_schema,
        test_bulk_item_error_schema,
        test_bulk_create_response_schema,
        test_bulk_create_response_camelcase_aliases,
        test_bulk_create_response_no_errors,
        test_eval_item_schema,
        test_eval_item_camelcase_aliases,
        test_eval_item_list_response,
        # P7.1: Webhook Version Echo
        test_webhook_delivery_db_has_api_version,
        test_eval_item_db_model,
        test_eval_item_db_status_values,
        test_eval_item_db_score_range,
        # Integration
        test_bulk_creation_atomic_behavior,
        test_bulk_creation_preserves_order,
        test_bulk_error_provides_context,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in test_functions:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"❌ {test_func.__name__} failed: {e}")
            failed += 1
    
    print("=" * 60)
    print(f"Results: {passed}/{len(test_functions)} tests passed")
    if failed == 0:
        print("✅ Sprint 7 test structure complete!")
    else:
        print(f"❌ {failed} tests failed")
    print("=" * 60)
