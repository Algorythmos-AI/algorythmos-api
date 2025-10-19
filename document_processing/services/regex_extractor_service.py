"""
Regex-based extraction service for PHASE 2.

This service implements basic regex pattern matching for field extraction
from text documents using extraction schemas.
"""

import re
from typing import Dict, List, Optional, Any
from datetime import datetime

from document_processing.models import ExtractionSchemaDB, ExtractorDB
from document_processing.schemas import FieldDefinition
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_


class ExtractionResult:
    """Result of a field extraction."""
    def __init__(
        self,
        field_name: str,
        value: Any,
        confidence: float = 1.0,
        citation: Optional[Dict[str, Any]] = None
    ):
        self.field_name = field_name
        self.value = value
        self.confidence = confidence
        self.citation = citation or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return {
            "field_name": self.field_name,
            "value": self.value,
            "confidence": self.confidence,
            "citation": self.citation
        }


class RegexExtractor:
    """
    Regex-based field extractor.
    
    Extracts structured data from text using regex patterns defined in extraction schemas.
    """
    
    def __init__(self, schema: ExtractionSchemaDB, extractor: Optional[ExtractorDB] = None):
        """
        Initialize the regex extractor.
        
        Args:
            schema: The extraction schema defining fields to extract
            extractor: Optional extractor configuration with custom rules
        """
        self.schema = schema
        self.extractor = extractor
        self.rules = extractor.rules if extractor else {}
    
    def extract(self, text: str) -> List[ExtractionResult]:
        """
        Extract fields from text using regex patterns.
        
        Args:
            text: The input text to extract from
        
        Returns:
            List of extraction results for each field
        """
        results = []
        
        for field in self.schema.fields:
            field_name = field["name"]
            field_type = field["type"]
            
            # Get regex pattern for this field (from extractor rules or default)
            pattern = self._get_pattern_for_field(field_name, field)
            
            if not pattern:
                # No pattern available, skip this field
                continue
            
            # Perform extraction
            value, confidence, citation = self._extract_field(
                text, pattern, field_type
            )
            
            if value is not None:
                results.append(ExtractionResult(
                    field_name=field_name,
                    value=value,
                    confidence=confidence,
                    citation=citation
                ))
        
        return results
    
    def _get_pattern_for_field(self, field_name: str, field: Dict) -> Optional[str]:
        """
        Get the regex pattern for a field.
        
        Checks extractor rules first, then falls back to field metadata.
        
        Args:
            field_name: Name of the field
            field: Field definition dictionary
        
        Returns:
            Regex pattern string or None
        """
        # Check extractor rules
        if self.rules and "patterns" in self.rules:
            if field_name in self.rules["patterns"]:
                return self.rules["patterns"][field_name]
        
        # Check field metadata for pattern
        if "pattern" in field:
            return field["pattern"]
        
        # Check field description for common patterns
        description = field.get("description", "").lower()
        
        # Auto-detect common patterns based on field name and description
        if "email" in field_name.lower() or "email" in description:
            return r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        
        if "phone" in field_name.lower() or "phone" in description:
            return r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'
        
        if "date" in field_name.lower() or "date" in description:
            return r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b'
        
        if "amount" in field_name.lower() or "price" in field_name.lower():
            return r'\$?\d+(?:,\d{3})*(?:\.\d{2})?'
        
        if "invoice" in field_name.lower() and "number" in field_name.lower():
            return r'(?:INV|Invoice)[-\s]?#?\s*([A-Z0-9-]+)'
        
        return None
    
    def _extract_field(
        self, text: str, pattern: str, field_type: str
    ) -> tuple[Any, float, Dict[str, Any]]:
        """
        Extract a single field using regex pattern.
        
        Args:
            text: Input text
            pattern: Regex pattern
            field_type: Expected field type (string, number, etc.)
        
        Returns:
            Tuple of (value, confidence, citation)
        """
        try:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            
            if not match:
                return None, 0.0, {}
            
            # Extract the value
            if match.groups():
                raw_value = match.group(1)  # First capture group
            else:
                raw_value = match.group(0)  # Full match
            
            # Convert to appropriate type
            value = self._convert_value(raw_value, field_type)
            
            # Calculate confidence (basic heuristic)
            confidence = self._calculate_confidence(match, text)
            
            # Create citation
            citation = {
                "start_pos": match.start(),
                "end_pos": match.end(),
                "matched_text": match.group(0),
                "pattern": pattern
            }
            
            return value, confidence, citation
            
        except Exception as e:
            # Pattern matching failed
            return None, 0.0, {"error": str(e)}
    
    def _convert_value(self, raw_value: str, field_type: str) -> Any:
        """
        Convert extracted string to the appropriate type.
        
        Args:
            raw_value: Raw extracted string
            field_type: Target field type
        
        Returns:
            Converted value
        """
        raw_value = raw_value.strip()
        
        if field_type == "number":
            # Remove currency symbols and commas
            cleaned = re.sub(r'[$,]', '', raw_value)
            try:
                if '.' in cleaned:
                    return float(cleaned)
                return int(cleaned)
            except ValueError:
                return raw_value
        
        elif field_type == "boolean":
            return raw_value.lower() in ("yes", "true", "1", "y")
        
        elif field_type == "array":
            # Split on commas
            return [item.strip() for item in raw_value.split(',')]
        
        # Default: return as string
        return raw_value
    
    def _calculate_confidence(self, match: re.Match, text: str) -> float:
        """
        Calculate confidence score for an extraction.
        
        Uses simple heuristics:
        - Match quality (exact vs partial)
        - Match position (earlier in text = higher confidence)
        - Match length
        
        Args:
            match: Regex match object
            text: Full input text
        
        Returns:
            Confidence score between 0.0 and 1.0
        """
        base_confidence = 0.8  # Base confidence for any match
        
        # Bonus for exact match with word boundaries
        matched_text = match.group(0)
        if len(matched_text) > 3:  # Meaningful length
            base_confidence += 0.1
        
        # Penalty for matches near the end of text (might be less relevant)
        position_ratio = match.start() / len(text) if len(text) > 0 else 0
        if position_ratio > 0.8:
            base_confidence -= 0.1
        
        # Cap at 1.0
        return min(base_confidence, 1.0)


async def extract_with_schema(
    db: AsyncSession,
    tenant_id: str,
    schema_id: str,
    text: str,
    extractor_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Extract structured data from text using a schema.
    
    Args:
        db: Database session
        tenant_id: Tenant identifier
        schema_id: ID of the extraction schema to use
        text: Input text to extract from
        extractor_id: Optional specific extractor to use
    
    Returns:
        Dictionary with extraction results
    
    Raises:
        ValueError: If schema or extractor not found
    """
    # Load schema
    schema_result = await db.execute(
        select(ExtractionSchemaDB).where(
            and_(
                ExtractionSchemaDB.id == schema_id,
                ExtractionSchemaDB.tenant_id == tenant_id,
                ExtractionSchemaDB.is_deleted == False
            )
        )
    )
    schema = schema_result.scalar_one_or_none()
    
    if not schema:
        raise ValueError(f"Schema '{schema_id}' not found for this tenant")
    
    # Load extractor if specified
    extractor = None
    if extractor_id:
        extractor_result = await db.execute(
            select(ExtractorDB).where(
                and_(
                    ExtractorDB.id == extractor_id,
                    ExtractorDB.tenant_id == tenant_id,
                    ExtractorDB.schema_id == schema_id,
                    ExtractorDB.is_deleted == False,
                    ExtractorDB.enabled == True
                )
            )
        )
        extractor = extractor_result.scalar_one_or_none()
        
        if not extractor:
            raise ValueError(f"Extractor '{extractor_id}' not found or not enabled")
    
    # Perform extraction
    regex_extractor = RegexExtractor(schema=schema, extractor=extractor)
    results = regex_extractor.extract(text)
    
    # Build response
    return {
        "schema_id": schema_id,
        "schema_name": schema.name,
        "extractor_id": extractor.id if extractor else None,
        "extracted_fields": [r.to_dict() for r in results],
        "total_fields": len(schema.fields),
        "extracted_count": len(results),
        "extraction_time": datetime.utcnow().isoformat()
    }
