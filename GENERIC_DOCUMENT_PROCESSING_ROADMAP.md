# Generic Document Processing Roadmap

## 🎯 Goal
Transform `api.algorythmos.fr` from a specialized telecom invoice extractor into a **full-featured document processing platform** supporting:

- Custom extraction schemas
- Document splitting
- Document classification
- Generic parsing
- Configurable extractors/classifiers/splitters

---

## 📊 Current State Analysis

### ✅ What You Already Have
1. **Strong Foundation:**
   - FastAPI with lifespan management ✅
   - Database with SQLAlchemy (async) ✅
   - Background job processing ✅
   - Webhook notifications ✅
   - Idempotency & retry logic ✅
   - Prometheus metrics ✅
   - Authentication (API keys) ✅
   - Pagination (cursor-based) ✅
   - Production deployment (Vercel) ✅

2. **Extensible Architecture:**
   - `BaseExtractor` abstract class
   - Router pattern for multiple extractors
   - Provider-specific implementations (Orange, GenericTelco)
   - PDF text extraction (`load_text()`)
   - Scoring/detection system

3. **Fixed Schema:**
   - `UsageRecord` (provider, dates, internet_gb, currency, etc.)
   - Pre-defined field types

### ❌ What's Missing for Generic Processing

1. **Custom Schemas** - Users can't define their own extraction fields
2. **Document Splitting** - Can't split multi-section documents
3. **Generic Classification** - Limited to telco invoice detection
4. **Configurable Extractors** - Can't create custom extractors via API
5. **Multiple Output Formats** - Only JSON, no CSV/XML/etc.
6. **Advanced Parsing** - No table extraction, no layout analysis
7. **Multi-format Support** - Only PDFs, no Word/Excel/Images
8. **LLM Integration** - No GPT/Claude for complex extraction

---

## 🗺️ Implementation Phases

### **Phase 1: Foundation (2-3 weeks)**
**Goal:** Enable custom schemas and configurable extractors

#### 1.1 Custom Schema System
```python
# New models in schemas.py
class FieldDefinition(BaseModel):
    name: str
    type: Literal["string", "number", "date", "boolean", "array", "object"]
    description: Optional[str] = None
    required: bool = False
    default: Optional[Any] = None

class ExtractionSchema(BaseModel):
    schema_id: str
    name: str
    description: str
    fields: List[FieldDefinition]
    created_at: datetime
    updated_at: datetime

# Database table
class SchemaDefinition(Base):
    __tablename__ = "extraction_schemas"
    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    definition = Column(JSON, nullable=False)  # FieldDefinition list
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
```

#### 1.2 Configurable Extractor API
```python
# New endpoints
POST   /extractors                    # Create custom extractor
GET    /extractors                    # List all extractors
GET    /extractors/{extractor_id}     # Get extractor details
PATCH  /extractors/{extractor_id}     # Update extractor config
DELETE /extractors/{extractor_id}     # Delete extractor

# Extractor configuration
class ExtractorConfig(BaseModel):
    extractor_id: str
    name: str
    type: Literal["regex", "llm", "template", "ml"]
    schema_id: str  # References ExtractionSchema
    rules: Dict[str, Any]  # Type-specific extraction rules
    enabled: bool = True
```

#### 1.3 Database Migration
```bash
# Create new tables
alembic revision -m "add_extraction_schemas_and_extractors"
# Tables: extraction_schemas, extractors, extractor_rules
```

---

### **Phase 2: Document Splitting (1-2 weeks)**
**Goal:** Split documents by page, section, or pattern

#### 2.1 Splitter Interface
```python
class BaseSplitter(ABC):
    """Base class for document splitters."""
    
    @abstractmethod
    def split(
        self, 
        document: bytes,
        config: SplitterConfig
    ) -> List[DocumentChunk]:
        """Split document into chunks."""

class PageSplitter(BaseSplitter):
    """Split PDF by pages (1-3, 4-6, etc.)"""

class SectionSplitter(BaseSplitter):
    """Split by headings/markers (e.g., 'Invoice Summary', 'Details')"""

class PatternSplitter(BaseSplitter):
    """Split by regex patterns"""
```

#### 2.2 Splitter API
```python
POST   /splitters                     # Create splitter configuration
GET    /splitters                     # List all splitters
POST   /documents/{doc_id}/split      # Split a document
```

#### 2.3 Output Types
```python
class DocumentChunk(BaseModel):
    chunk_id: str
    parent_document_id: str
    chunk_index: int
    page_range: Optional[Tuple[int, int]]
    content: bytes  # The actual split content
    metadata: Dict[str, Any]
```

---

### **Phase 3: Document Classification (1-2 weeks)**
**Goal:** Classify documents into categories

#### 3.1 Classifier Interface
```python
class BaseClassifier(ABC):
    """Base class for document classifiers."""
    
    @abstractmethod
    def classify(
        self,
        text: str,
        metadata: Dict[str, Any]
    ) -> ClassificationResult:
        """Classify document and return category + confidence."""

class KeywordClassifier(BaseClassifier):
    """Classify based on keyword presence."""

class MLClassifier(BaseClassifier):
    """Classify using trained ML model."""

class LLMClassifier(BaseClassifier):
    """Classify using GPT/Claude."""
```

#### 3.2 Classifier API
```python
POST   /classifiers                   # Create classifier
GET    /classifiers                   # List classifiers
POST   /documents/{doc_id}/classify   # Classify document

# Classification result
class ClassificationResult(BaseModel):
    category: str
    confidence: float
    subcategories: Optional[List[str]]
    metadata: Dict[str, Any]
```

---

### **Phase 4: Advanced Parsing (2-3 weeks)**
**Goal:** Extract tables, layouts, complex structures

#### 4.1 Table Extraction
```python
# Using libraries like pdfplumber, camelot, or tabula
class TableExtractor:
    def extract_tables(
        self,
        pdf_path: Path,
        page_numbers: Optional[List[int]] = None
    ) -> List[Table]:
        """Extract tables from PDF."""

class Table(BaseModel):
    table_id: str
    page: int
    rows: List[List[str]]
    headers: Optional[List[str]]
    bbox: Optional[Tuple[float, float, float, float]]
```

#### 4.2 Layout Analysis
```python
# Using libraries like pdfminer.six or PyMuPDF
class LayoutAnalyzer:
    def analyze(self, pdf_path: Path) -> DocumentLayout:
        """Analyze document layout (columns, headers, footers)."""

class DocumentLayout(BaseModel):
    page_layouts: List[PageLayout]
    has_multi_column: bool
    header_region: Optional[BoundingBox]
    footer_region: Optional[BoundingBox]
```

---

### **Phase 5: Multi-Format Support (2-3 weeks)**
**Goal:** Support Word, Excel, Images, HTML

#### 5.1 Format Handlers
```python
class BaseFormatHandler(ABC):
    supported_formats: List[str]
    
    @abstractmethod
    def extract_text(self, file_path: Path) -> str:
        """Extract text from document."""
    
    @abstractmethod
    def extract_structure(self, file_path: Path) -> DocumentStructure:
        """Extract structured data."""

# Implementations
class WordHandler(BaseFormatHandler):  # python-docx
class ExcelHandler(BaseFormatHandler):  # openpyxl
class ImageHandler(BaseFormatHandler):  # pytesseract (OCR)
class HTMLHandler(BaseFormatHandler):  # beautifulsoup4
```

#### 5.2 File Type Detection
```python
import magic  # python-magic

def detect_file_type(file_path: Path) -> str:
    """Detect MIME type."""
    mime = magic.from_file(str(file_path), mime=True)
    return mime
```

---

### **Phase 6: LLM Integration (1-2 weeks)**
**Goal:** Use GPT/Claude for complex extraction

#### 6.1 LLM Extractor
```python
class LLMExtractor(BaseExtractor):
    """Use LLM for extraction when rules-based fails."""
    
    def __init__(self, model: str = "gpt-4", api_key: str = None):
        self.client = OpenAI(api_key=api_key)
        self.model = model
    
    def extract(
        self,
        text: str,
        schema: ExtractionSchema
    ) -> Dict[str, Any]:
        """Extract fields using LLM."""
        prompt = self._build_prompt(text, schema)
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
```

#### 6.2 Configuration
```python
# Environment variables
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
LLM_PROVIDER=openai  # or anthropic, azure, etc.
LLM_MODEL=gpt-4-turbo-preview
```

---

### **Phase 7: Citation & Confidence (1 week)**
**Goal:** Track where data came from and how confident we are

#### 7.1 Citation System
```python
class Citation(BaseModel):
    field_name: str
    source_page: int
    source_text: str  # The actual text that was extracted
    bbox: Optional[Tuple[float, float, float, float]]
    extraction_method: Literal["regex", "llm", "template", "manual"]

class ExtractedField(BaseModel):
    name: str
    value: Any
    confidence: float
    citations: List[Citation]
```

#### 7.2 Confidence Scoring
```python
def calculate_confidence(
    extraction_method: str,
    match_quality: float,
    field_type: str
) -> float:
    """Calculate confidence score 0-1."""
    base_scores = {
        "exact_match": 0.95,
        "regex": 0.85,
        "fuzzy_match": 0.70,
        "llm": 0.80,
        "template": 0.90
    }
    return base_scores.get(extraction_method, 0.5) * match_quality
```

---

## 🏗️ Architectural Changes

### Database Schema Updates
```sql
-- New tables needed
CREATE TABLE extraction_schemas (
    id VARCHAR PRIMARY KEY,
    tenant_id VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    definition JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE extractors (
    id VARCHAR PRIMARY KEY,
    tenant_id VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    type VARCHAR NOT NULL,
    schema_id VARCHAR REFERENCES extraction_schemas(id),
    config JSONB NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE classifiers (
    id VARCHAR PRIMARY KEY,
    tenant_id VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    type VARCHAR NOT NULL,
    config JSONB NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE splitters (
    id VARCHAR PRIMARY KEY,
    tenant_id VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    type VARCHAR NOT NULL,
    config JSONB NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE document_chunks (
    id VARCHAR PRIMARY KEY,
    parent_document_id VARCHAR NOT NULL,
    chunk_index INTEGER NOT NULL,
    content BYTEA,
    metadata JSONB,
    created_at TIMESTAMP NOT NULL
);
```

### API Structure Reorganization
```
/api
├── /schemas                 # Manage extraction schemas
├── /extractors              # Manage custom extractors
├── /classifiers             # Manage classifiers
├── /splitters               # Manage splitters
├── /documents               # Document operations
│   ├── POST /upload
│   ├── POST /{id}/extract
│   ├── POST /{id}/classify
│   ├── POST /{id}/split
│   └── GET  /{id}/chunks
├── /processors              # (existing)
├── /jobs                    # (existing)
└── /webhooks                # (existing)
```

---

## 📦 New Dependencies

```toml
# pyproject.toml additions
[project.dependencies]
# Multi-format support
python-docx = ">=1.1.0"       # Word documents
openpyxl = ">=3.1.0"          # Excel files
python-pptx = ">=0.6.23"      # PowerPoint
pytesseract = ">=0.3.10"      # OCR for images
Pillow = ">=10.0.0"           # Image processing
python-magic = ">=0.4.27"     # File type detection

# Table extraction
pdfplumber = ">=0.10.0"       # Advanced PDF parsing
camelot-py = ">=0.11.0"       # Table extraction
tabula-py = ">=2.8.0"         # Alternative table extraction

# LLM integration
openai = ">=1.0.0"            # OpenAI GPT
anthropic = ">=0.7.0"         # Claude
tiktoken = ">=0.5.0"          # Token counting

# NLP & ML
spacy = ">=3.7.0"             # NLP processing
scikit-learn = ">=1.3.0"      # ML classifiers
transformers = ">=4.35.0"     # Hugging Face models (optional)

# Advanced PDF
PyMuPDF = ">=1.23.0"          # Layout analysis
pdfminer.six = ">=20220524"   # Alternative PDF parser
```

---

## 🧪 Testing Strategy

### 1. Unit Tests
```python
# tests/test_custom_schemas.py
def test_create_schema()
def test_validate_field_types()
def test_schema_versioning()

# tests/test_splitters.py
def test_page_splitter()
def test_section_splitter()
def test_pattern_splitter()

# tests/test_classifiers.py
def test_keyword_classifier()
def test_ml_classifier()
def test_llm_classifier()
```

### 2. Integration Tests
```python
# tests/integration/test_custom_extraction.py
async def test_create_schema_and_extract()
async def test_split_then_classify()
async def test_llm_extraction_with_custom_schema()
```

### 3. Performance Tests
```python
# tests/performance/test_large_documents.py
def test_1000_page_pdf_splitting()
def test_concurrent_llm_requests()
def test_batch_classification()
```

---

## 📈 Migration Path for Existing Users

### Backward Compatibility
```python
# Keep existing endpoints working
@app.post("/extract/upload")  # Legacy - still works
@app.post("/documents/upload")  # New generic endpoint

# Auto-create "telco_invoice" schema for existing users
async def migrate_existing_tenant(tenant_id: str):
    """Create default schema for legacy tenants."""
    schema = ExtractionSchema(
        schema_id=f"{tenant_id}_telco_invoice",
        name="Telecom Invoice",
        fields=[
            FieldDefinition(name="provider", type="string"),
            FieldDefinition(name="internet_gb", type="number"),
            # ... existing fields
        ]
    )
    await create_schema(schema, tenant_id)
```

---

## 💰 Cost Considerations

### LLM Usage
- OpenAI GPT-4: ~$0.03/1K tokens input, ~$0.06/1K tokens output
- Claude 3: ~$0.015/1K tokens input, ~$0.075/1K tokens output
- **Recommendation:** Implement caching and rate limiting

### Infrastructure
- Larger database (schemas, extractors, chunks)
- More memory for ML models
- Potential GPU for on-premise models

### Development Time
- **Phase 1:** 2-3 weeks (foundation)
- **Phase 2-3:** 2-4 weeks (splitting + classification)
- **Phase 4-5:** 4-6 weeks (parsing + multi-format)
- **Phase 6-7:** 2-3 weeks (LLM + citations)
- **Total:** 10-16 weeks (~3-4 months)

---

## 🚀 Quick Start Option: MVP in 1 Week

If you want to get something working quickly, prioritize:

**Week 1 MVP:**
1. ✅ Custom schema definition API (2 days)
2. ✅ Regex-based configurable extractor (2 days)
3. ✅ Simple page splitter (1 day)
4. ✅ Basic keyword classifier (1 day)
5. ✅ Documentation update (1 day)

This gives you a **functional generic document processor** that you can demo and iterate on.

---

## 🎯 Recommended Next Steps

1. **Review this roadmap** - Prioritize phases based on your needs
2. **Set up development branch** - `git checkout -b feature/generic-document-processing`
3. **Start with Phase 1.1** - Custom schemas (most foundational)
4. **Create first database migration** - Add `extraction_schemas` table
5. **Implement schema CRUD endpoints** - POST/GET/PATCH/DELETE
6. **Write comprehensive tests** - Ensure quality from day 1
7. **Update documentation** - Keep API_REFERENCE.md in sync

**Ready to start? Which phase would you like to tackle first?** 🚀
