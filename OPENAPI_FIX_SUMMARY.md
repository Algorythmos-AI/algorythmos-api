# OpenAPI Schema Generation Fix - Summary

## Problem
The `/docs` endpoint was failing to load because the `/api/openapi.json` endpoint was returning HTTP 500 errors. The Swagger UI could not fetch the OpenAPI schema.

## Root Causes Identified

### 1. **Indentation Error (Critical)**
**Location:** `app.py` line 547

The middleware initialization code was incorrectly indented inside the `custom_openapi()` function:

```python
@app.get("/openapi.json", include_in_schema=False)
async def custom_openapi():
    ...
    return {...}

    # Add middleware... ← This was INSIDE the function! ❌
origins = settings.get_cors_origins()
```

**Impact:** This broke the entire FastAPI app initialization, causing the middleware to never be added to the app.

**Fix:** Unindented the middleware code to be at module level:

```python
@app.get("/openapi.json", include_in_schema=False)
async def custom_openapi():
    ...
    return {...}

# Add middleware... ← Now at correct indentation ✅
origins = settings.get_cors_origins()
```

### 2. **Pydantic Model Forward References (Critical)**
**Location:** `app.py` lines 46-79

**Error Message:**
```
pydantic.errors.PydanticUserError: `TypeAdapter[typing.Annotated[_app_entrypoint.PathRequest, Body(PydanticUndefined)]]` is not fully defined
```

**Problem:** Pydantic models (`PathRequest`, `JobCreate`, `JobRecord`) that reference other models (like `ExtractResponse`) were not being rebuilt after all imports completed. This caused FastAPI's OpenAPI schema generator to fail when trying to introspect these models.

**Fix:** Added `model_rebuild()` calls after all model definitions:

```python
class PathRequest(BaseModel):
    ...

class JobCreate(BaseModel):
    ...

class JobRecord(BaseModel):
    result: Optional[ExtractResponse] = None  # Forward reference
    ...

# Rebuild models to ensure all forward references are resolved
PathRequest.model_rebuild()
JobCreate.model_rebuild()
JobRecord.model_rebuild()
```

### 3. **Test Import Errors (Non-Critical)**
**Location:** `tests/test_smoke.py`, `tests/test_uploads.py`

Tests were importing non-existent `build_api` function after we migrated to using the `app` object directly with lifespan context manager.

**Fix:** Updated test imports:
```python
# Before ❌
from app import build_api
app = build_api()

# After ✅
from app import app
```

## Verification

### Local Testing
```bash
✅ App imports successfully
✅ OpenAPI schema generated with 12 paths
✅ /docs endpoint loads Swagger UI properly
✅ All smoke tests pass (7/7)
✅ All production safety tests pass (3/3)
```

### Production Testing (After Deployment)
```bash
# Test OpenAPI endpoint
curl https://api.algorythmos.com/api/openapi.json
# Should return valid JSON with OpenAPI 3.1.0 schema

# Test Swagger UI
open https://api.algorythmos.com/docs
# Should load interactive API documentation
```

## Commits

1. **b020309** - `fix(openapi): fix indentation and rebuild Pydantic models`
   - Fixed critical indentation error in middleware initialization
   - Added model_rebuild() calls for all Pydantic models
   - Resolves PydanticUserError during schema generation

2. **801c8da** - `fix(tests): update imports after removing build_api function`
   - Updated test fixtures to use `app` directly
   - Fixed import errors in test_smoke.py and test_uploads.py

## Lessons Learned

1. **Python Indentation Matters:** Even a small indentation error can completely break app initialization
2. **Pydantic Forward References:** Always call `model_rebuild()` on models with forward references
3. **Test Coverage:** Having smoke tests helped quickly verify the fix worked
4. **Local Testing First:** Always test OpenAPI schema generation locally before deploying

## Related Issues

- FastAPI Lifespan Migration (commit a4f0f43)
- Vercel Module Import Conflict (commit c9c15d0)
- Missing Dependencies (commit db45a0d)

## Documentation

See also:
- [Pydantic Model Rebuild Documentation](https://docs.pydantic.dev/latest/concepts/models/#rebuilding-model-schema)
- [FastAPI OpenAPI Schema Customization](https://fastapi.tiangolo.com/how-to/custom-docs-ui-assets/)
