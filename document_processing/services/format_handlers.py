"""
Format handlers for different document types.

Supports extraction of text from various formats:
- PDF (using pdfplumber or pymupdf)
- DOCX (Microsoft Word)
- XLSX (Excel)
- Images (OCR with placeholder for Tesseract/cloud OCR)
- Plain text
"""

import io
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re


class FormatHandler:
    """Base class for document format handlers."""
    
    def can_handle(self, content_type: str, filename: str) -> bool:
        """Check if this handler can process the given file."""
        raise NotImplementedError
    
    def extract_text(self, content: bytes, filename: str) -> str:
        """Extract text from document content."""
        raise NotImplementedError
    
    def extract_metadata(self, content: bytes, filename: str) -> Dict[str, any]:
        """Extract metadata from document."""
        return {}


class TextHandler(FormatHandler):
    """Handler for plain text files."""
    
    def can_handle(self, content_type: str, filename: str) -> bool:
        return content_type in [
            "text/plain",
            "text/csv",
            "text/markdown",
            "application/json",
            "application/xml"
        ]
    
    def extract_text(self, content: bytes, filename: str) -> str:
        """Decode text content."""
        # Try different encodings
        for encoding in ["utf-8", "utf-16", "latin-1", "cp1252"]:
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        
        # Fallback: decode with errors ignored
        return content.decode("utf-8", errors="ignore")
    
    def extract_metadata(self, content: bytes, filename: str) -> Dict[str, any]:
        text = self.extract_text(content, filename)
        return {
            "character_count": len(text),
            "line_count": text.count("\n") + 1,
            "word_count": len(text.split())
        }


class PDFHandler(FormatHandler):
    """Handler for PDF files."""
    
    def can_handle(self, content_type: str, filename: str) -> bool:
        return (
            content_type in ["application/pdf", "application/x-pdf"] or
            filename.lower().endswith(".pdf")
        )
    
    def extract_text(self, content: bytes, filename: str) -> str:
        """Extract text from PDF using pdfplumber."""
        try:
            import pdfplumber
            
            text_parts = []
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
            
            return "\n\n".join(text_parts)
        
        except ImportError:
            # Fallback to pymupdf if pdfplumber not available
            return self._extract_with_pymupdf(content)
        except Exception as e:
            raise ValueError(f"Failed to extract text from PDF: {str(e)}")
    
    def _extract_with_pymupdf(self, content: bytes) -> str:
        """Fallback extraction using pymupdf."""
        try:
            import fitz  # pymupdf
            
            text_parts = []
            doc = fitz.open(stream=content, filetype="pdf")
            
            for page in doc:
                text_parts.append(page.get_text())
            
            doc.close()
            return "\n\n".join(text_parts)
        
        except ImportError:
            raise ValueError("No PDF library available (install pdfplumber or pymupdf)")
        except Exception as e:
            raise ValueError(f"Failed to extract text from PDF: {str(e)}")
    
    def extract_metadata(self, content: bytes, filename: str) -> Dict[str, any]:
        """Extract PDF metadata."""
        try:
            import pdfplumber
            
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                metadata = pdf.metadata or {}
                return {
                    "page_count": len(pdf.pages),
                    "title": metadata.get("Title"),
                    "author": metadata.get("Author"),
                    "subject": metadata.get("Subject"),
                    "creator": metadata.get("Creator"),
                    "producer": metadata.get("Producer"),
                    "creation_date": metadata.get("CreationDate"),
                }
        except Exception:
            return {"page_count": 0}


class DOCXHandler(FormatHandler):
    """Handler for Microsoft Word documents."""
    
    def can_handle(self, content_type: str, filename: str) -> bool:
        return (
            content_type in [
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/msword"
            ] or
            filename.lower().endswith((".docx", ".doc"))
        )
    
    def extract_text(self, content: bytes, filename: str) -> str:
        """Extract text from DOCX file."""
        try:
            import docx
            
            doc = docx.Document(io.BytesIO(content))
            
            text_parts = []
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    text_parts.append(paragraph.text)
            
            # Also extract text from tables
            for table in doc.tables:
                for row in table.rows:
                    row_text = " | ".join(cell.text.strip() for cell in row.cells)
                    if row_text.strip():
                        text_parts.append(row_text)
            
            return "\n\n".join(text_parts)
        
        except ImportError:
            raise ValueError("python-docx not installed (install with: pip install python-docx)")
        except Exception as e:
            raise ValueError(f"Failed to extract text from DOCX: {str(e)}")
    
    def extract_metadata(self, content: bytes, filename: str) -> Dict[str, any]:
        """Extract DOCX metadata."""
        try:
            import docx
            
            doc = docx.Document(io.BytesIO(content))
            core_props = doc.core_properties
            
            return {
                "paragraph_count": len(doc.paragraphs),
                "table_count": len(doc.tables),
                "title": core_props.title,
                "author": core_props.author,
                "subject": core_props.subject,
                "keywords": core_props.keywords,
                "created": core_props.created.isoformat() if core_props.created else None,
                "modified": core_props.modified.isoformat() if core_props.modified else None,
            }
        except Exception:
            return {}


class XLSXHandler(FormatHandler):
    """Handler for Excel spreadsheets."""
    
    def can_handle(self, content_type: str, filename: str) -> bool:
        return (
            content_type in [
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/vnd.ms-excel"
            ] or
            filename.lower().endswith((".xlsx", ".xls"))
        )
    
    def extract_text(self, content: bytes, filename: str) -> str:
        """Extract text from Excel file."""
        try:
            import openpyxl
            
            workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
            
            text_parts = []
            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                
                text_parts.append(f"=== Sheet: {sheet_name} ===")
                
                for row in sheet.iter_rows(values_only=True):
                    # Filter out None values and convert to strings
                    row_values = [str(cell) for cell in row if cell is not None]
                    if row_values:
                        text_parts.append(" | ".join(row_values))
            
            return "\n\n".join(text_parts)
        
        except ImportError:
            raise ValueError("openpyxl not installed (install with: pip install openpyxl)")
        except Exception as e:
            raise ValueError(f"Failed to extract text from XLSX: {str(e)}")
    
    def extract_metadata(self, content: bytes, filename: str) -> Dict[str, any]:
        """Extract Excel metadata."""
        try:
            import openpyxl
            
            workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
            
            sheet_info = {}
            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                sheet_info[sheet_name] = {
                    "row_count": sheet.max_row,
                    "column_count": sheet.max_column
                }
            
            return {
                "sheet_count": len(workbook.sheetnames),
                "sheet_names": workbook.sheetnames,
                "sheets": sheet_info
            }
        except Exception:
            return {}


class ImageHandler(FormatHandler):
    """Handler for image files with OCR capability."""
    
    def can_handle(self, content_type: str, filename: str) -> bool:
        return (
            content_type in [
                "image/jpeg",
                "image/png",
                "image/tiff",
                "image/bmp",
                "image/gif"
            ] or
            filename.lower().endswith((".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".gif"))
        )
    
    def extract_text(self, content: bytes, filename: str) -> str:
        """Extract text from image using OCR."""
        try:
            from PIL import Image
            import pytesseract
            
            image = Image.open(io.BytesIO(content))
            
            # Perform OCR
            text = pytesseract.image_to_string(image)
            
            return text.strip()
        
        except ImportError as e:
            if "PIL" in str(e):
                raise ValueError("Pillow not installed (install with: pip install Pillow)")
            elif "pytesseract" in str(e):
                raise ValueError("pytesseract not installed (install with: pip install pytesseract)")
            else:
                raise ValueError(f"Missing dependency: {str(e)}")
        except Exception as e:
            # Return placeholder for OCR
            return f"[Image OCR not available: {str(e)}]\n[Placeholder: Image content requires OCR processing]"
    
    def extract_metadata(self, content: bytes, filename: str) -> Dict[str, any]:
        """Extract image metadata."""
        try:
            from PIL import Image
            
            image = Image.open(io.BytesIO(content))
            
            return {
                "format": image.format,
                "mode": image.mode,
                "size": image.size,
                "width": image.width,
                "height": image.height,
            }
        except Exception:
            return {}


class FormatDetector:
    """Detects and routes to appropriate format handler."""
    
    def __init__(self):
        self.handlers: List[FormatHandler] = [
            PDFHandler(),
            DOCXHandler(),
            XLSXHandler(),
            ImageHandler(),
            TextHandler(),  # Fallback handler
        ]
    
    def get_handler(self, content_type: str, filename: str) -> Optional[FormatHandler]:
        """Get appropriate handler for the file."""
        for handler in self.handlers:
            if handler.can_handle(content_type, filename):
                return handler
        return None
    
    def extract_text(self, content: bytes, content_type: str, filename: str) -> str:
        """Extract text using appropriate handler."""
        handler = self.get_handler(content_type, filename)
        
        if not handler:
            raise ValueError(f"No handler available for content type: {content_type}")
        
        return handler.extract_text(content, filename)
    
    def extract_metadata(self, content: bytes, content_type: str, filename: str) -> Dict[str, any]:
        """Extract metadata using appropriate handler."""
        handler = self.get_handler(content_type, filename)
        
        if not handler:
            return {}
        
        return handler.extract_metadata(content, filename)


# Global format detector instance
format_detector = FormatDetector()
