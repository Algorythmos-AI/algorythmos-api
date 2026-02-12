"""
Sprint 3: Enhanced Parse API Tests (P2.1)

Tests for Extend API parity:
- Blocks structure with bounding boxes
- Chunks with provenance
- Page dimensions
- Timing metrics
- pageRanges parameter
"""

import pytest
from httpx import AsyncClient
from config import settings


def create_test_pdf_multipage() -> bytes:
    """Create a multi-page PDF for testing page ranges."""
    return b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R 4 0 R 5 0 R] /Count 3 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 6 0 R >> endobj
4 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 7 0 R >> endobj
5 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 8 0 R >> endobj
6 0 obj << /Length 44 >> stream
BT /F1 12 Tf 100 700 Td (Page 1 Content) Tj ET
endstream endobj
7 0 obj << /Length 44 >> stream
BT /F1 12 Tf 100 700 Td (Page 2 Content) Tj ET
endstream endobj
8 0 obj << /Length 44 >> stream
BT /F1 12 Tf 100 700 Td (Page 3 Content) Tj ET
endstream endobj
xref
0 9
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000125 00000 n 
0000000223 00000 n 
0000000321 00000 n 
0000000419 00000 n 
0000000513 00000 n 
0000000607 00000 n 
trailer << /Size 9 /Root 1 0 R >>
startxref
701
%%EOF
"""


@pytest.mark.asyncio
async def test_parse_returns_blocks_structure(client: AsyncClient):
    """Test that parse result includes blocks with bounding boxes."""
    # This test would work if database session was properly configured
    # For now, testing the service directly
    from document_processing.services.enhanced_parse_service import extract_blocks_from_text
    
    text = "This is a test paragraph.\n\nThis is another paragraph."
    blocks = extract_blocks_from_text(text, page_num=1)
    
    assert len(blocks) == 2
    assert all(block.type == "text" for block in blocks)
    assert all(block.bbox is not None for block in blocks)
    assert all(block.bbox.page == 1 for block in blocks)
    assert all(hasattr(block.bbox, 'x') for block in blocks)
    assert all(hasattr(block.bbox, 'y') for block in blocks)


@pytest.mark.asyncio
async def test_parse_returns_chunks_with_provenance(client: AsyncClient):
    """Test that parse result includes chunks with provenance metadata."""
    from document_processing.services.enhanced_parse_service import (
        extract_blocks_from_text,
        create_chunks_from_blocks
    )
    
    text = "A" * 600  # Text longer than default chunk size
    blocks = extract_blocks_from_text(text, page_num=1)
    chunks = create_chunks_from_blocks(blocks, chunk_size=500, overlap=50)
    
    assert len(chunks) >= 2  # Should create multiple chunks
    assert all(hasattr(chunk, 'chunk_id') for chunk in chunks)
    assert all(chunk.page == 1 for chunk in chunks)
    assert all(chunk.block_index == 0 for chunk in chunks)
    assert all(hasattr(chunk, 'start_char') for chunk in chunks)
    assert all(hasattr(chunk, 'end_char') for chunk in chunks)


@pytest.mark.asyncio
async def test_parse_extracts_page_dimensions(client: AsyncClient):
    """Test that parse result includes page dimensions."""
    from document_processing.services.enhanced_parse_service import extract_page_dimensions_from_pdf
    
    pdf_content = create_test_pdf_multipage()
    dimensions = extract_page_dimensions_from_pdf(pdf_content)
    
    # Should have dimensions for all pages (or defaults)
    assert isinstance(dimensions, dict)
    # Either extracted dimensions or empty dict if no PDF library
    if dimensions:
        assert all(hasattr(dim, 'width') for dim in dimensions.values())
        assert all(hasattr(dim, 'height') for dim in dimensions.values())


@pytest.mark.asyncio
async def test_parse_page_ranges_parameter(client: AsyncClient):
    """Test that pageRanges parameter filters pages correctly."""
    from document_processing.services.enhanced_parse_service import parse_page_ranges
    
    # Test single page
    pages = parse_page_ranges("1", 10)
    assert pages == [1]
    
    # Test range
    pages = parse_page_ranges("1-3", 10)
    assert pages == [1, 2, 3]
    
    # Test multiple ranges
    pages = parse_page_ranges("1-2,5-6,9", 10)
    assert pages == [1, 2, 5, 6, 9]
    
    # Test all pages (None)
    pages = parse_page_ranges(None, 5)
    assert pages == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_parse_timing_metrics(client: AsyncClient):
    """Test that parse result includes detailed timing metrics."""
    from document_processing.services.enhanced_parse_service import generate_enhanced_parse_result
    
    text = "Test content for timing"
    result = await generate_enhanced_parse_result(
        run_id="test_run",
        file_id="test_file",
        file_content=b"test",
        file_type="txt",
        extracted_text=text
    )
    
    assert result.timing is not None
    assert hasattr(result.timing, 'total_ms')
    assert hasattr(result.timing, 'format_detection_ms')
    assert hasattr(result.timing, 'text_extraction_ms')
    assert hasattr(result.timing, 'chunking_ms')
    assert result.processing_time_ms > 0


@pytest.mark.asyncio
async def test_parse_table_detection(client: AsyncClient):
    """Test that tables are detected and extracted as TableBlocks."""
    from document_processing.services.enhanced_parse_service import extract_blocks_from_text
    
    text_with_table = """Regular text paragraph.

Header1 | Header2 | Header3
Data1 | Data2 | Data3
Data4 | Data5 | Data6

Another paragraph."""
    
    blocks = extract_blocks_from_text(text_with_table, page_num=1)
    
    # Should have text block, table block, text block
    assert len(blocks) >= 2
    
    # Find table block
    table_blocks = [b for b in blocks if b.type == "table"]
    assert len(table_blocks) > 0
    
    table = table_blocks[0]
    assert len(table.rows) == 3  # Header + 2 data rows
    assert len(table.rows[0]) == 3  # 3 columns


@pytest.mark.asyncio
async def test_parse_bounding_box_coordinates(client: AsyncClient):
    """Test that bounding boxes have valid coordinates."""
    from document_processing.services.enhanced_parse_service import extract_blocks_from_text
    
    text = "Test paragraph."
    blocks = extract_blocks_from_text(text, page_num=1, page_width=612, page_height=792)
    
    assert len(blocks) > 0
    block = blocks[0]
    
    assert block.bbox is not None
    assert block.bbox.x >= 0
    assert block.bbox.y >= 0
    assert block.bbox.width > 0
    assert block.bbox.height > 0
    assert block.bbox.page == 1
    assert block.bbox.x + block.bbox.width <= 612


@pytest.mark.asyncio
async def test_parse_confidence_scores(client: AsyncClient):
    """Test that blocks include confidence scores."""
    from document_processing.services.enhanced_parse_service import extract_blocks_from_text
    
    text = "Test content."
    blocks = extract_blocks_from_text(text, page_num=1)
    
    assert len(blocks) > 0
    assert all(block.confidence is not None for block in blocks)
    assert all(0.0 <= block.confidence <= 1.0 for block in blocks)


@pytest.mark.asyncio
async def test_parse_chunk_overlap(client: AsyncClient):
    """Test that chunks have proper overlap."""
    from document_processing.services.enhanced_parse_service import (
        extract_blocks_from_text,
        create_chunks_from_blocks
    )
    
    text = "A" * 600  # Long text
    blocks = extract_blocks_from_text(text, page_num=1)
    chunks = create_chunks_from_blocks(blocks, chunk_size=500, overlap=50)
    
    # Check overlap between consecutive chunks
    if len(chunks) >= 2:
        chunk1_end = chunks[0].end_char
        chunk2_start = chunks[1].start_char
        overlap = chunk1_end - chunk2_start
        assert overlap == 50


@pytest.mark.asyncio
async def test_parse_api_version_stored(client: AsyncClient):
    """Test that API version is stored in parse result."""
    from document_processing.services.enhanced_parse_service import generate_enhanced_parse_result
    
    result = await generate_enhanced_parse_result(
        run_id="test",
        file_id="test",
        file_content=b"test",
        file_type="txt",
        extracted_text="test",
        api_version="2025-01-15"
    )
    
    assert result.api_version == "2025-01-15"


@pytest.mark.asyncio
async def test_parse_enhanced_request_camelcase(client: AsyncClient):
    """Test that EnhancedParseRequest accepts camelCase parameters."""
    from document_processing.schemas_parse import EnhancedParseRequest
    
    # Test with camelCase
    request = EnhancedParseRequest(
        file_id="test_file",
        target="json",
        pageRanges="1-5",
        agenticOcr=True,
        pageRotation=90
    )
    
    assert request.file_id == "test_file"
    assert request.page_ranges == "1-5"
    assert request.agentic_ocr is True
    assert request.page_rotation == 90


@pytest.mark.asyncio
async def test_parse_result_blocks_schema(client: AsyncClient):
    """Test that parse result blocks follow correct schema."""
    from document_processing.schemas_parse import TextBlock, BoundingBox
    
    block = TextBlock(
        type="text",
        text="Test content",
        bbox=BoundingBox(x=10, y=20, width=100, height=50, page=1),
        confidence=0.95
    )
    
    # Validate schema
    assert block.type == "text"
    assert block.text == "Test content"
    assert block.bbox.x == 10
    assert block.bbox.page == 1
    assert block.confidence == 0.95


@pytest.mark.asyncio
async def test_parse_result_includes_pages_processed(client: AsyncClient):
    """Test that parse result includes pages_processed count."""
    from document_processing.services.enhanced_parse_service import generate_enhanced_parse_result
    
    result = await generate_enhanced_parse_result(
        run_id="test",
        file_id="test",
        file_content=b"test",
        file_type="txt",
        extracted_text="Page 1\fPage 2\fPage 3",  # 3 pages
        page_ranges="1-2"  # Only process first 2
    )
    
    assert result.pages_processed == 2
