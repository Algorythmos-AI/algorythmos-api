"""
Sprint 2: Multi-Format File Validation Service

Implements comprehensive format detection and validation for all Extend API supported types:
- PDF: application/pdf
- Images: image/png, image/jpeg, image/tiff, image/svg+xml, image/heic, image/heif
- Word: application/msword, application/vnd.openxmlformats-officedocument.wordprocessingml.document
- Excel: application/vnd.ms-excel, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
"""

import io
import mimetypes
from pathlib import Path
from typing import Dict, Optional, Tuple, List


# Extend API supported file types
SUPPORTED_EXTENSIONS = {
    # Documents
    "pdf": "application/pdf",
    
    # Images
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "tiff": "image/tiff",
    "tif": "image/tiff",
    "svg": "image/svg+xml",
    "heic": "image/heic",
    "heif": "image/heif",
    
    # Word documents
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    
    # Excel spreadsheets
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


# MIME type to normalized type mapping
MIME_TO_NORMALIZED = {
    "application/pdf": "pdf",
    
    "image/png": "png",
    "image/jpeg": "jpeg",
    "image/jpg": "jpeg",
    "image/tiff": "tiff",
    "image/tif": "tiff",
    "image/svg+xml": "svg",
    "image/heic": "heic",
    "image/heif": "heif",
    
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
}


# Magic bytes for format detection (first few bytes of file)
MAGIC_BYTES = {
    "pdf": [b"%PDF"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpeg": [b"\xff\xd8\xff"],
    "tiff": [b"II\x2a\x00", b"MM\x00\x2a"],  # Little-endian and big-endian
    "gif": [b"GIF87a", b"GIF89a"],
    "zip": [b"PK\x03\x04"],  # Used by DOCX, XLSX
    "heic": [b"ftypheic", b"ftypheix"],  # At offset 4
    "heif": [b"ftypmif1"],  # At offset 4
}


class FormatValidationError(Exception):
    """Exception raised when file format validation fails."""
    pass


class FormatValidator:
    """Validates and normalizes file formats for Extend API compatibility."""
    
    def __init__(self):
        # Initialize mimetypes with custom mappings
        mimetypes.init()
        mimetypes.add_type("image/heic", ".heic")
        mimetypes.add_type("image/heif", ".heif")
    
    def validate_and_normalize(
        self,
        content: bytes,
        filename: str,
        declared_content_type: Optional[str] = None
    ) -> Tuple[str, str, Dict[str, any]]:
        """
        Validate file format and return normalized information.
        
        Args:
            content: File content as bytes
            filename: Original filename
            declared_content_type: Content-Type from upload (optional)
            
        Returns:
            Tuple of (normalized_type, mime_type, metadata)
            
        Raises:
            FormatValidationError: If format is unsupported or invalid
        """
        # Step 1: Detect format from magic bytes (most reliable)
        detected_type = self._detect_from_magic_bytes(content)
        
        # Step 2: Get extension from filename
        ext = Path(filename).suffix.lower().lstrip(".")
        ext_type = ext if ext in SUPPORTED_EXTENSIONS else None
        
        # Step 3: Parse declared content type
        declared_type = None
        if declared_content_type:
            declared_type = MIME_TO_NORMALIZED.get(declared_content_type)
        
        # Step 4: Determine final type (magic bytes > extension > declared)
        final_type = detected_type or ext_type or declared_type
        
        if not final_type:
            raise FormatValidationError(
                f"Could not determine file type for '{filename}'. "
                f"Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS.keys()))}"
            )
        
        if final_type not in SUPPORTED_EXTENSIONS.values() and final_type not in SUPPORTED_EXTENSIONS:
            raise FormatValidationError(
                f"Unsupported file type: {final_type}. "
                f"Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS.keys()))}"
            )
        
        # Normalize to extension-based type if it's a MIME type
        if "/"  in final_type:
            final_type = MIME_TO_NORMALIZED.get(final_type, final_type)
        
        # Get proper MIME type
        if final_type in SUPPORTED_EXTENSIONS:
            mime_type = SUPPORTED_EXTENSIONS[final_type]
        else:
            mime_type = final_type
        
        # Extract basic metadata
        metadata = self._extract_basic_metadata(content, final_type, filename)
        
        return final_type, mime_type, metadata
    
    def _detect_from_magic_bytes(self, content: bytes) -> Optional[str]:
        """
        Detect file type from magic bytes.
        
        Returns:
            Detected type or None if not detected
        """
        if len(content) < 12:
            return None
        
        # Check PDF
        if content.startswith(b"%PDF"):
            return "pdf"
        
        # Check PNG
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            return "png"
        
        # Check JPEG
        if content.startswith(b"\xff\xd8\xff"):
            return "jpeg"
        
        # Check TIFF
        if content.startswith(b"II\x2a\x00") or content.startswith(b"MM\x00\x2a"):
            return "tiff"
        
        # Check HEIC/HEIF (magic at offset 4-11)
        if len(content) >= 12:
            ftyp = content[4:12]
            if b"ftypheic" in ftyp or b"ftypheix" in ftyp:
                return "heic"
            if b"ftypmif1" in ftyp or b"ftypheif" in ftyp:
                return "heif"
        
        # Check ZIP-based formats (DOCX, XLSX)
        if content.startswith(b"PK\x03\x04"):
            # Need to inspect ZIP contents to distinguish DOCX vs XLSX
            return self._detect_office_format(content)
        
        # Check SVG (XML-based)
        if b"<svg" in content[:1024] or b"<?xml" in content[:100]:
            if b"<svg" in content[:2048]:
                return "svg"
        
        return None
    
    def _detect_office_format(self, content: bytes) -> Optional[str]:
        """
        Detect DOCX vs XLSX from ZIP content.
        
        Both are ZIP files, need to check internal structure.
        """
        try:
            import zipfile
            
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                filenames = zf.namelist()
                
                # DOCX has word/ directory
                if any(f.startswith("word/") for f in filenames):
                    return "docx"
                
                # XLSX has xl/ directory
                if any(f.startswith("xl/") for f in filenames):
                    return "xlsx"
                
                # Check content types
                if "[Content_Types].xml" in filenames:
                    content_types = zf.read("[Content_Types].xml").decode("utf-8", errors="ignore")
                    if "wordprocessingml" in content_types:
                        return "docx"
                    if "spreadsheetml" in content_types:
                        return "xlsx"
        
        except Exception:
            pass
        
        return None
    
    def _extract_basic_metadata(
        self,
        content: bytes,
        file_type: str,
        filename: str
    ) -> Dict[str, any]:
        """
        Extract basic metadata from file content.
        
        Returns:
            Dictionary with format-specific metadata
        """
        metadata = {
            "size_bytes": len(content),
            "format": file_type,
            "filename": filename,
        }
        
        # Add format-specific metadata
        if file_type in ["png", "jpeg", "tiff", "heic", "heif"]:
            metadata.update(self._extract_image_metadata(content, file_type))
        elif file_type == "pdf":
            metadata.update(self._extract_pdf_metadata(content))
        elif file_type in ["docx", "doc"]:
            metadata.update(self._extract_word_metadata(content, file_type))
        elif file_type in ["xlsx", "xls"]:
            metadata.update(self._extract_excel_metadata(content, file_type))
        
        return metadata
    
    def _extract_image_metadata(self, content: bytes, file_type: str) -> Dict[str, any]:
        """Extract metadata from image files."""
        metadata = {"type": "image"}
        
        try:
            from PIL import Image
            
            img = Image.open(io.BytesIO(content))
            metadata["width"] = img.width
            metadata["height"] = img.height
            metadata["mode"] = img.mode
            metadata["format"] = img.format
            
            # Extract EXIF data if available
            if hasattr(img, "_getexif") and img._getexif():
                exif = img._getexif()
                if exif:
                    metadata["has_exif"] = True
        
        except ImportError:
            metadata["note"] = "PIL not available for detailed image analysis"
        except Exception as e:
            metadata["extraction_error"] = str(e)
        
        return metadata
    
    def _extract_pdf_metadata(self, content: bytes) -> Dict[str, any]:
        """Extract metadata from PDF files."""
        metadata = {"type": "pdf"}
        
        try:
            import pdfplumber
            
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                metadata["page_count"] = len(pdf.pages)
                metadata["pdf_info"] = pdf.metadata or {}
        
        except ImportError:
            try:
                import fitz  # pymupdf
                
                doc = fitz.open(stream=content, filetype="pdf")
                metadata["page_count"] = doc.page_count
                metadata["pdf_info"] = doc.metadata or {}
                doc.close()
            
            except ImportError:
                metadata["note"] = "No PDF library available"
        
        except Exception as e:
            metadata["extraction_error"] = str(e)
        
        return metadata
    
    def _extract_word_metadata(self, content: bytes, file_type: str) -> Dict[str, any]:
        """Extract metadata from Word documents."""
        metadata = {"type": "word", "format": file_type}
        
        if file_type == "docx":
            try:
                import zipfile
                from xml.etree import ElementTree as ET
                
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    # Count pages (approximate from XML)
                    if "docProps/app.xml" in zf.namelist():
                        app_xml = zf.read("docProps/app.xml")
                        root = ET.fromstring(app_xml)
                        pages = root.find(".//{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}Pages")
                        if pages is not None and pages.text:
                            metadata["page_count"] = int(pages.text)
            
            except Exception as e:
                metadata["extraction_error"] = str(e)
        
        return metadata
    
    def _extract_excel_metadata(self, content: bytes, file_type: str) -> Dict[str, any]:
        """Extract metadata from Excel spreadsheets."""
        metadata = {"type": "excel", "format": file_type}
        
        if file_type == "xlsx":
            try:
                import zipfile
                from xml.etree import ElementTree as ET
                
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    # Count sheets
                    if "xl/workbook.xml" in zf.namelist():
                        workbook_xml = zf.read("xl/workbook.xml")
                        root = ET.fromstring(workbook_xml)
                        sheets = root.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet")
                        metadata["sheet_count"] = len(sheets)
            
            except Exception as e:
                metadata["extraction_error"] = str(e)
        
        return metadata
    
    def is_supported_format(self, filename: str) -> bool:
        """
        Check if filename has a supported extension.
        
        Args:
            filename: Filename to check
            
        Returns:
            True if supported, False otherwise
        """
        ext = Path(filename).suffix.lower().lstrip(".")
        return ext in SUPPORTED_EXTENSIONS
    
    def get_supported_formats(self) -> List[str]:
        """
        Get list of all supported file formats.
        
        Returns:
            List of supported extensions
        """
        return sorted(SUPPORTED_EXTENSIONS.keys())
    
    def get_mime_type(self, extension: str) -> Optional[str]:
        """
        Get MIME type for a given extension.
        
        Args:
            extension: File extension (with or without dot)
            
        Returns:
            MIME type or None if unsupported
        """
        ext = extension.lower().lstrip(".")
        return SUPPORTED_EXTENSIONS.get(ext)


# Global instance
format_validator = FormatValidator()
