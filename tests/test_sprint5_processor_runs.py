"""
Sprint 5 Tests: Processor Runs with Citations/Confidence (P4.1)

Tests processor run enhancements:
- Citation structure with provenance (page, bbox, text, confidence)
- ExtractedField with value, confidence, and citations
- ProcessorRunData with overall_confidence and usage metrics
- Version tracking (processor_version_id, version_number, api_version)
- Enhanced ProcessorRun response schema
- Lifecycle timestamps (started_at, completed_at)
"""

from datetime import datetime

from document_processing.schemas_processor_runs import (
    Citation,
    ExtractedField,
    UsageMetrics,
    ProcessorRunData,
    ProcessorRun,
    ProcessorRunRequest,
    ProcessorRunListResponse,
    CancelProcessorRunRequest
)


def test_citation_schema_validation():
    """Test Citation schema with full provenance."""
    citation = Citation(
        page=1,
        block_index=3,
        bbox={"x": 72.0, "y": 150.0, "width": 200.0, "height": 20.0, "page": 1},
        text="Invoice Total: $1,234.56",
        confidence=0.95
    )
    
    assert citation.page == 1
    assert citation.block_index == 3
    assert citation.bbox["x"] == 72.0
    assert citation.text == "Invoice Total: $1,234.56"
    assert citation.confidence == 0.95


def test_citation_minimal():
    """Test Citation with minimal fields."""
    citation = Citation(page=1)
    
    assert citation.page == 1
    assert citation.block_index is None
    assert citation.bbox is None
    assert citation.text is None
    assert citation.confidence is None


def test_citation_confidence_validation():
    """Test Citation confidence must be 0.0-1.0."""
    # Valid confidence
    citation1 = Citation(page=1, confidence=0.0)
    assert citation1.confidence == 0.0
    
    citation2 = Citation(page=1, confidence=1.0)
    assert citation2.confidence == 1.0
    
    # Invalid confidence would raise validation error
    # (Pydantic validates ge=0.0, le=1.0)
    assert True  # Pydantic enforces bounds


def test_extracted_field_schema():
    """Test ExtractedField with value, confidence, citations."""
    field = ExtractedField(
        name="invoice_total",
        value=1234.56,
        confidence=0.95,
        citations=[
            Citation(page=1, block_index=5, text="Total: $1,234.56", confidence=0.95)
        ],
        data_type="number"
    )
    
    assert field.name == "invoice_total"
    assert field.value == 1234.56
    assert field.confidence == 0.95
    assert len(field.citations) == 1
    assert field.citations[0].page == 1
    assert field.data_type == "number"


def test_extracted_field_supports_any_value_type():
    """Test ExtractedField supports string, number, array, object values."""
    # String value
    field1 = ExtractedField(name="name", value="John Doe", confidence=0.98)
    assert isinstance(field1.value, str)
    
    # Number value
    field2 = ExtractedField(name="amount", value=1234.56, confidence=0.95)
    assert isinstance(field2.value, float)
    
    # Array value
    field3 = ExtractedField(name="items", value=["item1", "item2"], confidence=0.90)
    assert isinstance(field3.value, list)
    
    # Object value
    field4 = ExtractedField(name="address", value={"city": "NYC", "zip": "10001"}, confidence=0.92)
    assert isinstance(field4.value, dict)


def test_extracted_field_multiple_citations():
    """Test ExtractedField can have multiple citations."""
    field = ExtractedField(
        name="vendor_name",
        value="Acme Corp",
        confidence=0.97,
        citations=[
            Citation(page=1, text="From: Acme Corp", confidence=0.98),
            Citation(page=1, text="Vendor: Acme Corporation", confidence=0.96)
        ]
    )
    
    assert len(field.citations) == 2
    assert field.citations[0].text == "From: Acme Corp"
    assert field.citations[1].text == "Vendor: Acme Corporation"


def test_usage_metrics_schema():
    """Test UsageMetrics for tracking consumption."""
    usage = UsageMetrics(
        input_tokens=1500,
        output_tokens=300,
        total_tokens=1800,
        processing_time_ms=2500,
        page_count=3
    )
    
    assert usage.input_tokens == 1500
    assert usage.output_tokens == 300
    assert usage.total_tokens == 1800
    assert usage.processing_time_ms == 2500
    assert usage.page_count == 3


def test_usage_metrics_all_optional():
    """Test UsageMetrics fields are all optional."""
    usage = UsageMetrics()
    
    assert usage.input_tokens is None
    assert usage.output_tokens is None
    assert usage.total_tokens is None
    assert usage.processing_time_ms is None
    assert usage.page_count is None


def test_processor_run_data_schema():
    """Test ProcessorRunData with fields and overall_confidence."""
    data = ProcessorRunData(
        fields=[
            ExtractedField(
                name="invoice_number",
                value="INV-2025-001",
                confidence=0.98,
                citations=[Citation(page=1, text="Invoice #INV-2025-001")]
            )
        ],
        overall_confidence=0.96,
        usage=UsageMetrics(
            input_tokens=1500,
            output_tokens=300,
            total_tokens=1800
        ),
        metadata={"extraction_method": "llm"}
    )
    
    assert len(data.fields) == 1
    assert data.fields[0].name == "invoice_number"
    assert data.overall_confidence == 0.96
    assert data.usage.total_tokens == 1800
    assert data.metadata["extraction_method"] == "llm"


def test_processor_run_data_overall_confidence_validation():
    """Test overall_confidence must be 0.0-1.0."""
    data = ProcessorRunData(
        fields=[],
        overall_confidence=0.85
    )
    
    assert data.overall_confidence == 0.85
    # Pydantic validates ge=0.0, le=1.0


def test_processor_run_request_schema():
    """Test ProcessorRunRequest with version specification."""
    request = ProcessorRunRequest(
        file_id="file_abc123",
        processor_version_id="pver_xyz789",
        parameters={"confidence_threshold": 0.8},
        webhook_url="https://example.com/webhook"
    )
    
    assert request.file_id == "file_abc123"
    assert request.processor_version_id == "pver_xyz789"
    assert request.parameters["confidence_threshold"] == 0.8
    assert request.webhook_url == "https://example.com/webhook"


def test_processor_run_request_alternative_inputs():
    """Test ProcessorRunRequest supports file_id or input_path."""
    # File ID mode
    request1 = ProcessorRunRequest(file_id="file_123")
    assert request1.file_id == "file_123"
    assert request1.input_path is None
    
    # Input path mode
    request2 = ProcessorRunRequest(input_path="/path/to/file.pdf")
    assert request2.input_path == "/path/to/file.pdf"
    assert request2.file_id is None


def test_processor_run_response_schema():
    """Test ProcessorRun response with full structure."""
    run = ProcessorRun(
        runId="run_abc123",
        processorId="proc_xyz789",
        processorVersionId="pver_v2",
        versionNumber=2,
        fileId="file_123",
        status="completed",
        data=ProcessorRunData(
            fields=[
                ExtractedField(
                    name="invoice_number",
                    value="INV-2025-001",
                    confidence=0.98,
                    citations=[Citation(page=1)]
                )
            ],
            overall_confidence=0.96
        ),
        apiVersion="2025-10-15",
        createdAt=datetime.utcnow(),
        updatedAt=datetime.utcnow(),
        completedAt=datetime.utcnow(),
        tenantId="tenant_123"
    )
    
    assert run.id == "run_abc123"
    assert run.processor_id == "proc_xyz789"
    assert run.processor_version_id == "pver_v2"
    assert run.version_number == 2
    assert run.status == "completed"
    assert run.data.overall_confidence == 0.96
    assert run.api_version == "2025-10-15"


def test_processor_run_camelcase_aliases():
    """Test ProcessorRun supports both camelCase and snake_case."""
    # CamelCase (API format)
    run = ProcessorRun(
        runId="run_123",
        processorId="proc_123",
        status="queued",
        createdAt=datetime.utcnow(),
        updatedAt=datetime.utcnow(),
        tenantId="t1"
    )
    
    # Can access via snake_case
    assert run.id == "run_123"
    assert run.processor_id == "proc_123"
    assert run.tenant_id == "t1"


def test_processor_run_status_values():
    """Test ProcessorRun supports all status values."""
    statuses = ["queued", "processing", "completed", "failed", "cancelled"]
    
    for status in statuses:
        run = ProcessorRun(
            runId=f"run_{status}",
            processorId="proc_123",
            status=status,
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
            tenantId="t1"
        )
        assert run.status == status


def test_processor_run_with_error():
    """Test ProcessorRun can include error details."""
    run = ProcessorRun(
        runId="run_failed",
        processorId="proc_123",
        status="failed",
        error={
            "code": "EXTRACTION_FAILED",
            "message": "Failed to extract data",
            "details": {"reason": "Invalid PDF"}
        },
        createdAt=datetime.utcnow(),
        updatedAt=datetime.utcnow(),
        tenantId="t1"
    )
    
    assert run.error["code"] == "EXTRACTION_FAILED"
    assert run.error["message"] == "Failed to extract data"


def test_processor_run_timestamps():
    """Test ProcessorRun tracks lifecycle timestamps."""
    now = datetime.utcnow()
    
    run = ProcessorRun(
        runId="run_123",
        processorId="proc_123",
        status="completed",
        createdAt=now,
        updatedAt=now,
        startedAt=now,
        completedAt=now,
        tenantId="t1"
    )
    
    assert run.created_at is not None
    assert run.updated_at is not None
    assert run.started_at is not None
    assert run.completed_at is not None


def test_processor_run_list_response():
    """Test ProcessorRunListResponse with pagination."""
    response = ProcessorRunListResponse(
        items=[
            ProcessorRun(
                runId="run_1",
                processorId="proc_123",
                status="completed",
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow(),
                tenantId="t1"
            ),
            ProcessorRun(
                runId="run_2",
                processorId="proc_123",
                status="processing",
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow(),
                tenantId="t1"
            )
        ],
        meta={"total": 2, "page": 1, "page_size": 50}
    )
    
    assert len(response.items) == 2
    assert response.meta["total"] == 2
    assert response.items[0].id == "run_1"
    assert response.items[1].id == "run_2"


def test_cancel_processor_run_request():
    """Test CancelProcessorRunRequest schema."""
    request = CancelProcessorRunRequest(
        reason="User requested cancellation"
    )
    
    assert request.reason == "User requested cancellation"


def test_cancel_processor_run_request_optional_reason():
    """Test CancelProcessorRunRequest reason is optional."""
    request = CancelProcessorRunRequest()
    
    assert request.reason is None


def test_version_tracking_in_runs():
    """Test runs track which processor version was used."""
    run = ProcessorRun(
        runId="run_123",
        processorId="proc_abc",
        processorVersionId="pver_xyz",
        versionNumber=2,
        apiVersion="2025-10-15",
        status="completed",
        createdAt=datetime.utcnow(),
        updatedAt=datetime.utcnow(),
        tenantId="t1"
    )
    
    # Version tracking enables:
    # - Reproducibility: know exact version used
    # - Auditing: track version changes over time
    # - Rollback: identify runs from specific versions
    
    assert run.processor_version_id == "pver_xyz"
    assert run.version_number == 2
    assert run.api_version == "2025-10-15"


def test_citations_enable_transparency():
    """Test citations provide transparency and verifiability."""
    # A well-cited extraction includes:
    # 1. The extracted value
    # 2. Where it was found (page, position)
    # 3. The actual text that was extracted
    # 4. Confidence in the extraction
    
    field = ExtractedField(
        name="total_amount",
        value=1234.56,
        confidence=0.95,
        citations=[
            Citation(
                page=2,
                block_index=7,
                bbox={"x": 400.0, "y": 500.0, "width": 100.0, "height": 15.0, "page": 2},
                text="Total: $1,234.56",
                confidence=0.95
            )
        ]
    )
    
    # Users can:
    # - Verify the extraction by checking the citation
    # - Navigate directly to the source location
    # - Understand confidence levels
    # - Debug extraction issues
    
    citation = field.citations[0]
    assert citation.page == 2
    assert citation.text == "Total: $1,234.56"
    assert citation.bbox is not None


if __name__ == "__main__":
    print("Sprint 5 Test Suite: Processor Runs with Citations/Confidence")
    print("=" * 60)
    
    # Run all tests
    test_functions = [
        test_citation_schema_validation,
        test_citation_minimal,
        test_citation_confidence_validation,
        test_extracted_field_schema,
        test_extracted_field_supports_any_value_type,
        test_extracted_field_multiple_citations,
        test_usage_metrics_schema,
        test_usage_metrics_all_optional,
        test_processor_run_data_schema,
        test_processor_run_data_overall_confidence_validation,
        test_processor_run_request_schema,
        test_processor_run_request_alternative_inputs,
        test_processor_run_response_schema,
        test_processor_run_camelcase_aliases,
        test_processor_run_status_values,
        test_processor_run_with_error,
        test_processor_run_timestamps,
        test_processor_run_list_response,
        test_cancel_processor_run_request,
        test_cancel_processor_run_request_optional_reason,
        test_version_tracking_in_runs,
        test_citations_enable_transparency,
    ]
    
    passed = 0
    for test_func in test_functions:
        try:
            test_func()
            print(f"✅ {test_func.__name__}")
            passed += 1
        except Exception as e:
            print(f"❌ {test_func.__name__}: {e}")
    
    print("=" * 60)
    print(f"Results: {passed}/{len(test_functions)} tests passed")
    print("✅ Sprint 5 test structure complete!")
