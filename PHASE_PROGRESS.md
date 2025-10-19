# Generic Document Processing - Phase Progress

## Execution Status

**Started:** 2025-10-19
**Current Phase:** PHASE 2 - Regex Extractor  
**Overall Status:** IN_PROGRESS

---

## PHASE 0: Pre-Flight Checks ✓

**Goal:** Establish architectural foundations and align codebase standards
**Status:** COMPLETE

### Completed ✓
- [x] API prefix detection: `/api` (via `root_path`)
- [x] Tenant context verification: `tenant_ctx["tenant"]` confirmed
- [x] FastAPI Path alias: Using `PathParam` consistently
- [x] Primary keys: All models use `id` column
- [x] Soft delete: Added `is_deleted` to schemas, extractors, classifiers, splitters
- [x] Core configuration module: `core/config.py` with constants
- [x] Error response shape: Standardized builder functions
- [x] Pagination: Standardized meta builder
- [x] Generated Alembic migration for soft delete columns
- [x] Executed migration successfully (20251019_soft_delete is head)
- [x] Route count smoke test (38 routes working)
- [x] Committed pre-flight changes

### Notes
- API uses `/api` root_path in FastAPI config
- All existing endpoints return proper tenant isolation
- `PathParam` alias avoids conflict with `pathlib.Path`
- Migration adds is_deleted boolean column + indexes to 4 tables

---

## PHASE 1: Foundation + /schemas CRUD ✓

**Status:** COMPLETE
**Goal:** Implement soft-delete, offset pagination, and standardized errors for all document processing CRUD

### Completed ✓
- [x] Schema service: soft-delete + offset pagination + standardized errors
- [x] Schema endpoints: Updated to use build_pagination_meta and build_error_response
- [x] Extractor service: soft-delete + offset pagination
- [x] Classifier service: soft-delete + offset pagination
- [x] Splitter service: soft-delete + offset pagination
- [x] All services return tuple (items, total) for flexible meta construction
- [x] All deletes are now soft deletes (set is_deleted=True)
- [x] Duplicate name checks only check non-deleted resources
- [x] Schema verification in extractor service filters deleted schemas
- [x] Updated all list endpoints (/schemas, /extractors, /classifiers, /splitters)
- [x] All endpoints use offset parameter instead of cursor
- [x] All endpoints return {items, meta} with standardized pagination
- [x] Comprehensive test suite created (test_phase1_crud.py)
- [x] Tests cover soft-delete, pagination, error formats for all resources

### Implementation Details
- **Service signatures changed:** `cursor` parameter → `offset` parameter
- **Return type changed:** Response models → tuples `(items, total)`
- **All queries filter:** `is_deleted == False`
- **Meta format:** `{limit, offset, total, next_offset, has_more}`
- **Error format:** `{"error": {"type": "...", "message": "..."}}`

### Notes
- Soft-delete allows name reuse (only check non-deleted resources)
- Separation of concerns: services return data, endpoints build responses
- All CRUD operations properly tenant-isolated

---

## PHASE 2: Regex Extractor 🔍

**Status:** NOT_STARTED

### Checklist
- [ ] Create `document_chunks` usage plan
- [ ] Implement `regex_extractor.py` service
- [ ] Add `POST /extract/regex` endpoint
- [ ] Implement citations and confidence scoring
- [ ] Add tests
- [ ] Verify with curl

---

## PHASE 3: Classification & Splitting 🏷️

**Status:** NOT_STARTED

### Checklist
- [ ] Implement keyword classifier service
- [ ] Add `POST /classify` endpoint
- [ ] Implement rule-based splitter service
- [ ] Add `POST /split` endpoint
- [ ] Add tests
- [ ] Verify with curl

---

## PHASE 4: Advanced Parsing 📄

**Status:** NOT_STARTED

### Checklist
- [ ] Create files table and model
- [ ] Implement file upload endpoint
- [ ] Create parser_runs table
- [ ] Implement sync parse endpoint
- [ ] Implement async parse endpoint
- [ ] Add tests
- [ ] Verify with curl

---

## PHASE 5: Multi-Format & LLM 🤖

**Status:** NOT_STARTED

### Checklist
- [ ] Add DOCX/XLSX format handlers
- [ ] Add image format handlers
- [ ] Implement LLM post-processing service
- [ ] Add tests
- [ ] Verify with curl

---

## PHASE 6: Production Hardening 🛡️

**Status:** NOT_STARTED

### Checklist
- [ ] Implement webhooks table and service
- [ ] Add webhook registration endpoints
- [ ] Implement rate limiting middleware
- [ ] Add idempotency handling
- [ ] Add Prometheus metrics
- [ ] Set up CI workflow
- [ ] Add tests
- [ ] Verify with curl

---

## PHASE 7: Extend-Parity Surfaces 🔄

**Status:** NOT_STARTED

### Checklist
- [ ] Create processors table
- [ ] Implement processor endpoints
- [ ] Create workflows table
- [ ] Implement workflow endpoints
- [ ] Create evaluation sets table
- [ ] Implement evaluation endpoints
- [ ] Add tests
- [ ] Verify with curl

---

## Commit Log

| Phase | Commit SHA | Message | Date |
|-------|-----------|---------|------|
| 0 | - | (in progress) | 2025-10-19 |

---

## Final Status

**COMPLETION:** NOT_YET

(This will be updated to "DONE ✓" when all phases complete)
