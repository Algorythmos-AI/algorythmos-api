"""
Sprint 2: Multi-Format File Validation Tests

Tests for P1.1: Format validation for all Extend API supported types
"""
import io
import pytest
from httpx import AsyncClient
from config import settings


# Test file creation helpers
def create_test_pdf() -> bytes:
    """Create a minimal valid PDF file."""
    return b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj
4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(Test PDF) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000214 00000 n 
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
308
%%EOF
"""


def create_test_png() -> bytes:
    """Create a minimal valid PNG file (1x1 pixel)."""
    return (
        b'\x89PNG\r\n\x1a\n'
        b'\x00\x00\x00\rIHDR'
        b'\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
        b'\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4'
        b'\x00\x00\x00\x00IEND\xaeB`\x82'
    )


def create_test_jpeg() -> bytes:
    """Create a minimal valid JPEG file."""
    return (
        b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
        b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c'
        b'\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c'
        b'\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x0b\x08\x00'
        b'\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01'
        b'\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07'
        b'\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05'
        b'\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07'
        b'"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18'
        b'\x19\x1a%&\'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86'
        b'\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6'
        b'\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6'
        b'\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5'
        b'\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00'
        b'\x08\x01\x01\x00\x00?\x00\xf6\xfc\xff\xd9'
    )


def create_test_svg() -> bytes:
    """Create a minimal valid SVG file."""
    return b'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
    <circle cx="50" cy="50" r="40" fill="blue" />
</svg>'''


def create_test_docx() -> bytes:
    """Create a minimal valid DOCX file (ZIP-based)."""
    import zipfile
    import io
    
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # [Content_Types].xml
        zf.writestr('[Content_Types].xml', 
            '<?xml version="1.0"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '</Types>')
        
        # word/document.xml
        zf.writestr('word/document.xml',
            '<?xml version="1.0"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>Test Document</w:t></w:r></w:p></w:body>'
            '</w:document>')
    
    buffer.seek(0)
    return buffer.read()


def create_test_xlsx() -> bytes:
    """Create a minimal valid XLSX file (ZIP-based)."""
    import zipfile
    import io
    
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # [Content_Types].xml
        zf.writestr('[Content_Types].xml',
            '<?xml version="1.0"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '</Types>')
        
        # xl/workbook.xml
        zf.writestr('xl/workbook.xml',
            '<?xml version="1.0"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheets><sheet name="Sheet1" sheetId="1" /></sheets>'
            '</workbook>')
    
    buffer.seek(0)
    return buffer.read()


@pytest.mark.asyncio
async def test_upload_pdf_file(client: AsyncClient):
    """Test PDF file upload with format validation."""
    pdf_content = create_test_pdf()
    
    response = await client.post(
        "/files",
        headers={
            "x-api-key": settings.ALG_API_KEY,
            "x-tenant-id": "tenant-format-test"
        },
        files={"file": ("test.pdf", pdf_content, "application/pdf")}
    )
    
    assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
    data = response.json()
    assert data["content_type"] == "application/pdf"
    assert data["metadata"]["format_info"]["format"] == "pdf"
    assert data["metadata"]["normalized_type"] == "pdf"


@pytest.mark.asyncio
async def test_upload_png_file(client: AsyncClient):
    """Test PNG file upload with format validation."""
    png_content = create_test_png()
    
    response = await client.post(
        "/files",
        headers={
            "x-api-key": settings.ALG_API_KEY,
            "x-tenant-id": "tenant-format-test"
        },
        files={"file": ("test.png", png_content, "image/png")}
    )
    
    assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
    data = response.json()
    assert data["content_type"] == "image/png"
    assert data["metadata"]["format_info"]["format"] == "png"


@pytest.mark.asyncio
async def test_upload_jpeg_file(client: AsyncClient):
    """Test JPEG file upload with format validation."""
    jpeg_content = create_test_jpeg()
    
    response = await client.post(
        "/files",
        headers={
            "x-api-key": settings.ALG_API_KEY,
            "x-tenant-id": "tenant-format-test"
        },
        files={"file": ("test.jpg", jpeg_content, "image/jpeg")}
    )
    
    assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
    data = response.json()
    assert data["content_type"] == "image/jpeg"
    assert data["metadata"]["format_info"]["format"] == "jpeg"


@pytest.mark.asyncio
async def test_upload_svg_file(client: AsyncClient):
    """Test SVG file upload with format validation."""
    svg_content = create_test_svg()
    
    response = await client.post(
        "/files",
        headers={
            "x-api-key": settings.ALG_API_KEY,
            "x-tenant-id": "tenant-format-test"
        },
        files={"file": ("test.svg", svg_content, "image/svg+xml")}
    )
    
    assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
    data = response.json()
    assert data["content_type"] == "image/svg+xml"
    assert data["metadata"]["format_info"]["format"] == "svg"


@pytest.mark.asyncio
async def test_upload_docx_file(client: AsyncClient):
    """Test DOCX file upload with format validation."""
    docx_content = create_test_docx()
    
    response = await client.post(
        "/files",
        headers={
            "x-api-key": settings.ALG_API_KEY,
            "x-tenant-id": "tenant-format-test"
        },
        files={"file": ("test.docx", docx_content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    )
    
    assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
    data = response.json()
    assert "wordprocessingml" in data["content_type"] or data["metadata"]["format_info"]["format"] == "docx"


@pytest.mark.asyncio
async def test_upload_xlsx_file(client: AsyncClient):
    """Test XLSX file upload with format validation."""
    xlsx_content = create_test_xlsx()
    
    response = await client.post(
        "/files",
        headers={
            "x-api-key": settings.ALG_API_KEY,
            "x-tenant-id": "tenant-format-test"
        },
        files={"file": ("test.xlsx", xlsx_content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    )
    
    assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
    data = response.json()
    assert "spreadsheetml" in data["content_type"] or data["metadata"]["format_info"]["format"] == "xlsx"


@pytest.mark.asyncio
async def test_upload_unsupported_format(client: AsyncClient):
    """Test that unsupported file formats are rejected."""
    # Create a fake EXE file
    exe_content = b"MZ\x90\x00\x03\x00\x00\x00"  # DOS MZ header
    
    response = await client.post(
        "/files",
        headers={
            "x-api-key": settings.ALG_API_KEY,
            "x-tenant-id": "tenant-format-test"
        },
        files={"file": ("malware.exe", exe_content, "application/x-msdownload")}
    )
    
    assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
    data = response.json()
    assert data["detail"]["code"] == "UNSUPPORTED_FORMAT"
    assert "supported_formats" in data["detail"]


@pytest.mark.asyncio
async def test_format_detection_from_magic_bytes(client: AsyncClient):
    """Test that format is detected from magic bytes even with wrong extension."""
    # Upload PDF with .txt extension
    pdf_content = create_test_pdf()
    
    response = await client.post(
        "/files",
        headers={
            "x-api-key": settings.ALG_API_KEY,
            "x-tenant-id": "tenant-format-test"
        },
        files={"file": ("notapdf.txt", pdf_content, "text/plain")}
    )
    
    # Should detect as PDF from magic bytes
    assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
    data = response.json()
    assert data["metadata"]["format_info"]["format"] == "pdf"


@pytest.mark.asyncio
async def test_format_validation_with_multiple_extensions(client: AsyncClient):
    """Test that both .jpg and .jpeg extensions work."""
    jpeg_content = create_test_jpeg()
    
    # Test .jpg
    response1 = await client.post(
        "/files",
        headers={
            "x-api-key": settings.ALG_API_KEY,
            "x-tenant-id": "tenant-format-test"
        },
        files={"file": ("test.jpg", jpeg_content, "image/jpeg")}
    )
    assert response1.status_code == 201
    
    # Test .jpeg
    response2 = await client.post(
        "/files",
        headers={
            "x-api-key": settings.ALG_API_KEY,
            "x-tenant-id": "tenant-format-test"
        },
        files={"file": ("test.jpeg", jpeg_content, "image/jpeg")}
    )
    assert response2.status_code == 201


@pytest.mark.asyncio
async def test_format_metadata_extraction(client: AsyncClient):
    """Test that format-specific metadata is extracted."""
    pdf_content = create_test_pdf()
    
    response = await client.post(
        "/files",
        headers={
            "x-api-key": settings.ALG_API_KEY,
            "x-tenant-id": "tenant-format-test"
        },
        files={"file": ("test.pdf", pdf_content, "application/pdf")}
    )
    
    assert response.status_code == 201
    data = response.json()
    
    # Check metadata structure
    assert "format_info" in data["metadata"]
    assert "size_bytes" in data["metadata"]["format_info"]
    assert "format" in data["metadata"]["format_info"]
    assert data["metadata"]["format_info"]["type"] == "pdf"


@pytest.mark.asyncio
async def test_supported_formats_list(client: AsyncClient):
    """Test that error response includes supported formats list."""
    response = await client.post(
        "/files",
        headers={
            "x-api-key": settings.ALG_API_KEY,
            "x-tenant-id": "tenant-format-test"
        },
        files={"file": ("test.unknown", b"invalid content", "application/octet-stream")}
    )
    
    assert response.status_code == 400
    data = response.json()
    supported = data["detail"]["supported_formats"]
    
    # Verify all Extend API formats are listed
    expected_formats = ["pdf", "png", "jpg", "jpeg", "tiff", "tif", "svg", "heic", "heif", "doc", "docx", "xls", "xlsx"]
    for fmt in expected_formats:
        assert fmt in supported, f"Missing supported format: {fmt}"
