"""
Document splitting service for PHASE 3.

Implements rule-based document splitting using splitter configurations.
"""

import re
from typing import Dict, List, Optional, Any
from datetime import datetime

from document_processing.models import SplitterDB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_


class DocumentChunk:
    """A chunk of split document."""
    
    def __init__(
        self,
        content: str,
        chunk_index: int,
        start_pos: int,
        end_pos: int,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.content = content
        self.chunk_index = chunk_index
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return {
            "content": self.content,
            "chunk_index": self.chunk_index,
            "start_pos": self.start_pos,
            "end_pos": self.end_pos,
            "content_length": len(self.content),
            "metadata": self.metadata
        }


class RuleBasedSplitter:
    """
    Rule-based document splitter.
    
    Splits documents using patterns and rules defined in splitter configurations.
    """
    
    def __init__(self, splitter: SplitterDB):
        """
        Initialize the splitter.
        
        Args:
            splitter: The splitter configuration
        """
        self.splitter = splitter
        self.rules = splitter.rules or {}
    
    def split(self, text: str) -> List[DocumentChunk]:
        """
        Split text into chunks based on rules.
        
        Args:
            text: The input text to split
        
        Returns:
            List of document chunks
        """
        split_strategy = self.rules.get("strategy", "delimiter")
        
        if split_strategy == "delimiter":
            return self._split_by_delimiter(text)
        elif split_strategy == "pattern":
            return self._split_by_pattern(text)
        elif split_strategy == "fixed_size":
            return self._split_by_size(text)
        elif split_strategy == "paragraph":
            return self._split_by_paragraph(text)
        else:
            # Default: treat entire text as one chunk
            return [DocumentChunk(
                content=text,
                chunk_index=0,
                start_pos=0,
                end_pos=len(text)
            )]
    
    def _split_by_delimiter(self, text: str) -> List[DocumentChunk]:
        """Split by delimiter string."""
        delimiter = self.rules.get("delimiter", "\n\n")
        parts = text.split(delimiter)
        
        chunks = []
        current_pos = 0
        
        for index, part in enumerate(parts):
            if part.strip():  # Skip empty chunks
                chunk = DocumentChunk(
                    content=part,
                    chunk_index=index,
                    start_pos=current_pos,
                    end_pos=current_pos + len(part),
                    metadata={"split_type": "delimiter", "delimiter": delimiter}
                )
                chunks.append(chunk)
            
            current_pos += len(part) + len(delimiter)
        
        return chunks
    
    def _split_by_pattern(self, text: str) -> List[DocumentChunk]:
        """Split by regex pattern."""
        pattern = self.rules.get("pattern", r"\n\s*\n")
        
        # Find all split positions
        splits = list(re.finditer(pattern, text))
        
        if not splits:
            # No matches, return entire text
            return [DocumentChunk(
                content=text,
                chunk_index=0,
                start_pos=0,
                end_pos=len(text)
            )]
        
        chunks = []
        current_pos = 0
        
        for index, match in enumerate(splits):
            # Get text before this split
            chunk_text = text[current_pos:match.start()]
            
            if chunk_text.strip():
                chunk = DocumentChunk(
                    content=chunk_text,
                    chunk_index=index,
                    start_pos=current_pos,
                    end_pos=match.start(),
                    metadata={"split_type": "pattern", "pattern": pattern}
                )
                chunks.append(chunk)
            
            current_pos = match.end()
        
        # Add remaining text
        if current_pos < len(text):
            remaining = text[current_pos:]
            if remaining.strip():
                chunks.append(DocumentChunk(
                    content=remaining,
                    chunk_index=len(chunks),
                    start_pos=current_pos,
                    end_pos=len(text),
                    metadata={"split_type": "pattern", "pattern": pattern}
                ))
        
        return chunks
    
    def _split_by_size(self, text: str) -> List[DocumentChunk]:
        """Split into fixed-size chunks."""
        chunk_size = self.rules.get("chunk_size", 1000)
        overlap = self.rules.get("overlap", 0)
        
        chunks = []
        index = 0
        current_pos = 0
        
        while current_pos < len(text):
            end_pos = min(current_pos + chunk_size, len(text))
            chunk_text = text[current_pos:end_pos]
            
            chunk = DocumentChunk(
                content=chunk_text,
                chunk_index=index,
                start_pos=current_pos,
                end_pos=end_pos,
                metadata={
                    "split_type": "fixed_size",
                    "chunk_size": chunk_size,
                    "overlap": overlap
                }
            )
            chunks.append(chunk)
            
            # Move to next chunk with overlap
            current_pos += chunk_size - overlap
            index += 1
        
        return chunks
    
    def _split_by_paragraph(self, text: str) -> List[DocumentChunk]:
        """Split by paragraph (double newlines)."""
        # Split on double newlines or more
        paragraphs = re.split(r'\n\s*\n+', text)
        
        chunks = []
        current_pos = 0
        
        for index, paragraph in enumerate(paragraphs):
            if paragraph.strip():
                chunk = DocumentChunk(
                    content=paragraph.strip(),
                    chunk_index=index,
                    start_pos=current_pos,
                    end_pos=current_pos + len(paragraph),
                    metadata={"split_type": "paragraph"}
                )
                chunks.append(chunk)
            
            # Approximate position (this is simplified)
            current_pos += len(paragraph) + 2
        
        return chunks


async def split_document(
    db: AsyncSession,
    tenant_id: str,
    text: str,
    splitter_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Split a document using rule-based splitting.
    
    Args:
        db: Database session
        tenant_id: Tenant identifier
        text: Text content to split
        splitter_id: Optional specific splitter to use
    
    Returns:
        Dictionary with splitting results
    
    Raises:
        ValueError: If splitter not found
    """
    # Build query for splitters
    query = select(SplitterDB).where(
        and_(
            SplitterDB.tenant_id == tenant_id,
            SplitterDB.is_deleted == False,
            SplitterDB.enabled == True
        )
    )
    
    if splitter_id:
        query = query.where(SplitterDB.id == splitter_id)
    else:
        # Use the first enabled splitter
        query = query.order_by(SplitterDB.created_at.desc()).limit(1)
    
    result = await db.execute(query)
    splitter = result.scalar_one_or_none()
    
    if not splitter:
        if splitter_id:
            raise ValueError(f"Splitter '{splitter_id}' not found or not enabled")
        else:
            raise ValueError("No enabled splitters found for this tenant")
    
    # Perform splitting
    rule_splitter = RuleBasedSplitter(splitter)
    chunks = rule_splitter.split(text)
    
    return {
        "splitter_id": splitter.id,
        "splitter_name": splitter.name,
        "split_strategy": splitter.rules.get("strategy", "delimiter"),
        "original_length": len(text),
        "chunk_count": len(chunks),
        "chunks": [chunk.to_dict() for chunk in chunks],
        "split_time": datetime.utcnow().isoformat()
    }
