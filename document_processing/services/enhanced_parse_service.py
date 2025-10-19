"""
Sprint 3: Enhanced Parse Service (P2.1)

Generates Extend API-compatible parse results with:
- Blocks structure (text/table/figure)
- Bounding boxes
- Chunks with provenance
- Page dimensions
- Detailed timing
"""

import re
import time
import uuid
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from document_processing.schemas_parse import (
    EnhancedParseResult,
    TextBlock,
    TableBlock,
    FigureBlock,
    ContentBlock,
    Chunk,
    BoundingBox,
    PageDimensions,
    ParseTiming
)


def parse_page_ranges(page_ranges: Optional[str], total_pages: int) -> List[int]:
    """
    Parse page range string into list of page numbers.
    
    Examples:
        "1-5" -> [1, 2, 3, 4, 5]
        "1,3,5" -> [1, 3, 5]
        "1-3,7-9" -> [1, 2, 3, 7, 8, 9]
    
    Args:
        page_ranges: Range string (e.g., "1-5,7,9-12")
        total_pages: Total pages in document
        
    Returns:
        List of 1-indexed page numbers to process
    """
    if not page_ranges:
        return list(range(1, total_pages + 1))
    
    pages = set()
    for part in page_ranges.split(','):
        part = part.strip()
        if '-' in part:
            start, end = part.split('-')
            start_page = max(1, int(start.strip()))
            end_page = min(total_pages, int(end.strip()))
            pages.update(range(start_page, end_page + 1))
        else:
            page_num = int(part.strip())
            if 1 <= page_num <= total_pages:
                pages.add(page_num)
    
    return sorted(pages)


def extract_blocks_from_text(
    text: str,
    page_num: int,
    page_width: float = 612,
    page_height: float = 792
) -> List[ContentBlock]:
    """
    Extract content blocks from plain text.
    
    For Sprint 3, implements basic text block extraction.
    Future: Add table/figure detection with ML models.
    
    Args:
        text: Extracted text content
        page_num: Page number (1-indexed)
        page_width: Page width in points
        page_height: Page height in points
        
    Returns:
        List of content blocks
    """
    blocks = []
    
    # Split into paragraphs
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    
    # Estimate vertical position (simple layout)
    y_position = 72  # Start 1 inch from top
    line_height = 14  # Approximate line height
    
    for para in paragraphs:
        # Detect tables (simple heuristic: lines with | or tabs)
        if '|' in para or '\t' in para:
            # Parse as table
            rows = []
            for line in para.split('\n'):
                if '|' in line:
                    cells = [c.strip() for c in line.split('|') if c.strip()]
                    if cells:
                        rows.append(cells)
                elif '\t' in line:
                    cells = [c.strip() for c in line.split('\t') if c.strip()]
                    if cells:
                        rows.append(cells)
            
            if rows:
                # Estimate table height
                table_height = len(rows) * line_height
                
                blocks.append(TableBlock(
                    type="table",
                    rows=rows,
                    bbox=BoundingBox(
                        x=72,
                        y=y_position,
                        width=page_width - 144,  # 1 inch margins
                        height=table_height,
                        page=page_num
                    ),
                    confidence=0.85,
                    metadata={"row_count": len(rows), "col_count": len(rows[0]) if rows else 0}
                ))
                
                y_position += table_height + line_height
        
        else:
            # Regular text block
            num_lines = len(para.split('\n'))
            block_height = num_lines * line_height
            
            blocks.append(TextBlock(
                type="text",
                text=para,
                bbox=BoundingBox(
                    x=72,
                    y=y_position,
                    width=page_width - 144,
                    height=block_height,
                    page=page_num
                ),
                confidence=0.95,
                metadata={"char_count": len(para), "line_count": num_lines}
            ))
            
            y_position += block_height + line_height
    
    return blocks


def create_chunks_from_blocks(
    blocks: List[ContentBlock],
    chunk_size: int = 500,
    overlap: int = 50
) -> List[Chunk]:
    """
    Create text chunks from content blocks.
    
    Args:
        blocks: Content blocks to chunk
        chunk_size: Target chunk size in characters
        overlap: Character overlap between chunks
        
    Returns:
        List of text chunks with provenance
    """
    chunks = []
    
    for block_idx, block in enumerate(blocks):
        # Extract text from block
        if isinstance(block, TextBlock):
            text = block.text
            page = block.bbox.page if block.bbox else None
        elif isinstance(block, TableBlock):
            # Convert table to text
            text = '\n'.join(['\t'.join(row) for row in block.rows])
            page = block.bbox.page if block.bbox else None
        else:
            # Skip figures for now
            continue
        
        # Create chunks with overlap
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk_text = text[start:end].strip()
            
            if chunk_text:
                chunk = Chunk(
                    chunk_id=f"chunk_{uuid.uuid4().hex[:8]}",
                    text=chunk_text,
                    page=page,
                    block_index=block_idx,
                    start_char=start,
                    end_char=end,
                    metadata={
                        "block_type": block.type,
                        "length": len(chunk_text)
                    }
                )
                chunks.append(chunk)
            
            # Move forward with overlap
            start = end - overlap if end < len(text) else end
    
    return chunks


def extract_page_dimensions_from_pdf(content: bytes) -> Dict[int, PageDimensions]:
    """
    Extract page dimensions from PDF content.
    
    Args:
        content: PDF file bytes
        
    Returns:
        Dictionary mapping page numbers to dimensions
    """
    dimensions = {}
    
    try:
        import pdfplumber
        import io
        
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                dimensions[i] = PageDimensions(
                    width=float(page.width),
                    height=float(page.height),
                    unit="pt"
                )
    
    except ImportError:
        try:
            import fitz  # pymupdf
            
            doc = fitz.open(stream=content, filetype="pdf")
            for i in range(doc.page_count):
                page = doc[i]
                rect = page.rect
                dimensions[i + 1] = PageDimensions(
                    width=float(rect.width),
                    height=float(rect.height),
                    unit="pt"
                )
            doc.close()
        
        except ImportError:
            # Default letter size if no PDF library
            pass
    
    except Exception:
        # Fallback to defaults
        pass
    
    return dimensions


async def generate_enhanced_parse_result(
    run_id: str,
    file_id: str,
    file_content: bytes,
    file_type: str,
    extracted_text: str,
    page_ranges: Optional[str] = None,
    api_version: Optional[str] = None,
    legacy_result: Optional[Dict[str, Any]] = None
) -> EnhancedParseResult:
    """
    Generate enhanced parse result with Extend API structure.
    
    Args:
        run_id: Parser run ID
        file_id: File ID
        file_content: Raw file bytes
        file_type: File format (pdf, docx, etc.)
        extracted_text: Extracted text content
        page_ranges: Optional page range filter
        api_version: API version from request
        legacy_result: Optional legacy parse result for backwards compat
        
    Returns:
        Enhanced parse result with blocks/chunks
    """
    timing_start = time.time()
    
    # Format detection timing
    format_start = time.time()
    total_pages = extracted_text.count('\f') + 1 if '\f' in extracted_text else 1
    format_ms = int((time.time() - format_start) * 1000)
    
    # Parse page ranges
    pages_to_process = parse_page_ranges(page_ranges, total_pages)
    
    # Extract page dimensions (for PDFs)
    page_dimensions = {}
    if file_type == "pdf":
        page_dimensions = extract_page_dimensions_from_pdf(file_content)
    else:
        # Default dimensions for non-PDF
        for page_num in pages_to_process:
            page_dimensions[page_num] = PageDimensions(
                width=612, height=792, unit="pt"  # Letter size default
            )
    
    # Text extraction timing
    extract_start = time.time()
    
    # Split text by pages
    page_texts = extracted_text.split('\f') if '\f' in extracted_text else [extracted_text]
    
    # Filter by page ranges
    filtered_texts = [(i+1, page_texts[i]) for i in range(len(page_texts)) if (i+1) in pages_to_process]
    
    extract_ms = int((time.time() - extract_start) * 1000)
    
    # Generate blocks
    all_blocks = []
    for page_num, page_text in filtered_texts:
        page_dims = page_dimensions.get(page_num, PageDimensions(width=612, height=792, unit="pt"))
        blocks = extract_blocks_from_text(page_text, page_num, page_dims.width, page_dims.height)
        all_blocks.extend(blocks)
    
    # Chunking timing
    chunk_start = time.time()
    chunks = create_chunks_from_blocks(all_blocks)
    chunk_ms = int((time.time() - chunk_start) * 1000)
    
    # Total timing
    total_ms = int((time.time() - timing_start) * 1000)
    
    # Build timing object
    timing = ParseTiming(
        total_ms=total_ms,
        format_detection_ms=format_ms,
        text_extraction_ms=extract_ms,
        classification_ms=legacy_result.get("classification_ms") if legacy_result else None,
        chunking_ms=chunk_ms,
        extraction_ms=legacy_result.get("extraction_ms") if legacy_result else None
    )
    
    # Build result
    result = EnhancedParseResult(
        run_id=run_id,
        file_id=file_id,
        status="completed",
        blocks=all_blocks,
        chunks=chunks,
        page_dimensions=page_dimensions,
        pages_processed=len(pages_to_process),
        classification=legacy_result.get("classification") if legacy_result else None,
        extracted=legacy_result.get("extracted") if legacy_result else None,
        confidence=legacy_result.get("confidence", 0.9) if legacy_result else 0.9,
        timing=timing,
        processing_time_ms=total_ms,
        completed_at=datetime.utcnow(),
        api_version=api_version,
        error=None
    )
    
    return result
