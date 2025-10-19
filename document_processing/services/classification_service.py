"""
Document classification service for PHASE 3.

Implements keyword-based document classification using classifier configurations.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime

from document_processing.models import ClassifierDB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_


class ClassificationResult:
    """Result of document classification."""
    
    def __init__(
        self,
        category: str,
        confidence: float,
        matched_keywords: List[str],
        classifier_id: Optional[str] = None
    ):
        self.category = category
        self.confidence = confidence
        self.matched_keywords = matched_keywords
        self.classifier_id = classifier_id
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return {
            "category": self.category,
            "confidence": self.confidence,
            "matched_keywords": self.matched_keywords,
            "classifier_id": self.classifier_id
        }


class KeywordClassifier:
    """
    Keyword-based document classifier.
    
    Classifies documents by matching keywords and rules defined in classifier configurations.
    """
    
    def __init__(self, classifier: ClassifierDB):
        """
        Initialize the classifier.
        
        Args:
            classifier: The classifier configuration
        """
        self.classifier = classifier
        self.categories = classifier.categories or []
        self.rules = classifier.rules or {}
    
    def classify(self, text: str) -> List[ClassificationResult]:
        """
        Classify text into categories based on keyword matching.
        
        Args:
            text: The input text to classify
        
        Returns:
            List of classification results ordered by confidence
        """
        text_lower = text.lower()
        results = []
        
        # Get keyword rules for each category
        keyword_rules = self.rules.get("keywords", {})
        
        for category in self.categories:
            # Get keywords for this category
            keywords = keyword_rules.get(category, [])
            
            if not keywords:
                # No keywords defined for this category
                continue
            
            # Find matching keywords
            matched = []
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    matched.append(keyword)
            
            # Calculate confidence based on match ratio
            if matched:
                confidence = len(matched) / len(keywords)
                
                # Boost confidence if multiple keywords match
                if len(matched) > 1:
                    confidence = min(confidence + 0.1 * (len(matched) - 1), 1.0)
                
                results.append(ClassificationResult(
                    category=category,
                    confidence=confidence,
                    matched_keywords=matched,
                    classifier_id=self.classifier.id
                ))
        
        # Sort by confidence (highest first)
        results.sort(key=lambda r: r.confidence, reverse=True)
        
        return results


async def classify_document(
    db: AsyncSession,
    tenant_id: str,
    text: str,
    classifier_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Classify a document using keyword-based classification.
    
    Args:
        db: Database session
        tenant_id: Tenant identifier
        text: Text content to classify
        classifier_id: Optional specific classifier to use
    
    Returns:
        Dictionary with classification results
    
    Raises:
        ValueError: If classifier not found
    """
    # Build query for classifiers
    query = select(ClassifierDB).where(
        and_(
            ClassifierDB.tenant_id == tenant_id,
            ClassifierDB.is_deleted == False,
            ClassifierDB.enabled == True
        )
    )
    
    if classifier_id:
        query = query.where(ClassifierDB.id == classifier_id)
    else:
        # Use all enabled classifiers, ordered by priority (if available)
        query = query.order_by(ClassifierDB.created_at.desc())
    
    result = await db.execute(query)
    classifiers = result.scalars().all()
    
    if not classifiers:
        if classifier_id:
            raise ValueError(f"Classifier '{classifier_id}' not found or not enabled")
        else:
            raise ValueError("No enabled classifiers found for this tenant")
    
    # Run classification with each classifier
    all_results = []
    for classifier in classifiers:
        keyword_classifier = KeywordClassifier(classifier)
        results = keyword_classifier.classify(text)
        all_results.extend(results)
    
    # Sort all results by confidence
    all_results.sort(key=lambda r: r.confidence, reverse=True)
    
    # Get top category
    top_category = all_results[0].category if all_results else None
    
    return {
        "text_length": len(text),
        "classifiers_used": len(classifiers),
        "classifications": [r.to_dict() for r in all_results],
        "top_category": top_category,
        "classification_time": datetime.utcnow().isoformat()
    }
