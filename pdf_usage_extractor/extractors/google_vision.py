from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Optional

import fitz  # type: ignore
from google.cloud import vision

from ..schemas import UsageRecord
from .base import BaseExtractor


class GoogleVisionExtractor(BaseExtractor):
    """Extractor using Google Cloud Vision API for OCR."""

    name = "google_vision"
    priority = 200  # Higher priority when selected via hint

    def score(self, *, text: str, provider_hint: Optional[str]) -> float:
        """Score is 1.0 if explicitly requested, else 0."""
        if provider_hint and provider_hint.lower() == "google":
            return 1.0
        return 0.0

    def extract(
        self,
        *,
        path: Path,
        text: str,
        debug: bool,
        logger: logging.Logger,
    ) -> Optional[UsageRecord]:
        """Convert PDF to images and extract text using Google Vision."""
        try:
            client = vision.ImageAnnotatorClient()
        except Exception as exc:
            logger.error(
                "Failed to initialize Google Vision client",
                extra={"context": {"error": str(exc)}},
            )
            return None

        # Convert PDF pages to images
        extracted_text = []
        try:
            with fitz.open(path) as doc:
                for page_num, page in enumerate(doc):
                    # Render page to image (pixmap)
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for better OCR
                    img_bytes = pix.tobytes("png")

                    image = vision.Image(content=img_bytes)
                    response = client.text_detection(image=image)
                    
                    if response.error.message:
                         logger.error(
                            f"Google Vision API error on page {page_num}",
                            extra={"context": {"error": response.error.message}},
                        )
                         continue

                    # Get full text annotation
                    texts = response.text_annotations
                    if texts:
                        extracted_text.append(texts[0].description)

        except Exception as exc:
             logger.error(
                "Failed to process PDF with Google Vision",
                extra={"context": {"error": str(exc)}},
            )
             return None

        full_text = "\n".join(extracted_text)
        
        # Return a generic record with the extracted text
        # Since this is a raw OCR extractor, we might want to structure it better
        # For now, we return a generic record
        return UsageRecord(
            provider="Google Vision OCR",
            sensor_id="N/A",
            total_usage=0.0,  # Placeholder
            timestamp=None,
            confidence=1.0 if full_text else 0.0,
            raw_text=full_text
        )
