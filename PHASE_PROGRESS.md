# Generic Document Processing - Phase Progress

## Execution Status

**Started:** 2025-10-19
**Current Phase:** PHASE 0 - Pre-Flight
**Overall Status:** IN_PROGRESS

---

## PHASE 0: Pre-Flight Checks ⏳

**Goal:** Establish architectural foundations and align codebase standards

### Completed ✓
- [x] API prefix detection: `/api` (via `root_path`)
- [x] Tenant context verification: `tenant_ctx["tenant"]` confirmed
- [x] FastAPI Path alias: Using `PathParam` consistently
- [x] Primary keys: All models use `id` column
- [x] Soft delete: Added `is_deleted` to schemas, extractors, classifiers, splitters
- [x] Core configuration module: `core/config.py` with constants
- [x] Error response shape: Standardized builder functions
- [x] Pagination: Standardized meta builder

### In Progress
- [ ] Generate Alembic migration for soft delete columns
- [ ] Update services to filter by `is_deleted`
- [ ] Route count smoke test
- [ ] Commit pre-flight changes

### Notes
- API uses `/api` root_path in FastAPI config
- All existing endpoints return proper tenant isolation
- `PathParam` alias avoids conflict with `pathlib.Path`

---

## PHASE 1: Foundation + /schemas CRUD 📋

**Status:** NOT_STARTED

### Checklist
- [ ] Verify existing schema DTOs
- [ ] Add soft-delete to schema service
- [ ] Update pagination to use offset-based (not cursor)
- [ ] Add proper error response shapes
- [ ] Update tests for soft-delete behavior
- [ ] Verify with curl tests

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
