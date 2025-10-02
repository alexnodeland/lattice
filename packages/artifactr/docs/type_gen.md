# Type Generation System

This document describes the unified type generation system that keeps frontend TypeScript types in sync with backend Pydantic models.

## Overview

We use a **unified OpenAPI-based approach** that generates TypeScript types from Pydantic models without requiring the backend server to be running. This ensures type safety and consistency between frontend and backend.

## The Unified Approach

### OpenAPI Schema Generation

**Why this approach:**
- ✅ **Complete coverage** - Includes both Pydantic models AND API endpoints
- ✅ **Industry standard** - OpenAPI is the gold standard for API documentation  
- ✅ **Best tooling** - Excellent TypeScript generation with `openapi-typescript`
- ✅ **Future-proof** - Works with any OpenAPI-compatible system
- ✅ **Single source of truth** - One method, no confusion
- ✅ **Auto-generated exports** - Convenient type exports and utility functions

**How it works:**
1. Imports your FastAPI app statically (no server required)
2. Generates OpenAPI schema using `app.openapi()`
3. Converts schema to TypeScript using `openapi-typescript`
4. **Auto-generates convenient type exports** in `index.ts`

**Output:** 
- `apps/frontend/lib/types/api.ts` (raw OpenAPI types)
- `apps/frontend/lib/types/index.ts` (convenient exports - **auto-generated**)

## Usage

### Quick Start

```bash
# Install dependencies (one-time setup)
make install-deps

# Generate types
make types
```

### Development Workflow

```bash
# During development - clean and regenerate
make dev-types

# Just generate types
make types

# Clean generated files
make clean
```

### Integration with Build Process

Types are automatically generated before building the frontend:

```json
{
  "scripts": {
    "prebuild": "pnpm run types:generate"
  }
}
```

## File Structure

```
scripts/
└── generate-api-schema.py      # OpenAPI schema + index.ts generation

apps/frontend/lib/types/
├── api.ts                      # Generated TypeScript types (from OpenAPI)
├── index.ts                    # Auto-generated convenient exports ⚠️ DO NOT EDIT
└── api-schema.json             # Intermediate OpenAPI schema
```

## Usage in Frontend Code

```typescript
// ✅ RECOMMENDED: Import from the convenient index file
import type { 
  Idea, 
  User, 
  CreateIdeaForm, 
  UpdateUserForm,
  ModelId 
} from '@/lib/types';

// ✅ Also available: Direct imports from generated API types
import type { components, paths } from '@/lib/types/api';

// Use the convenient types
interface Props {
  idea: Idea;
  onUpdate: (data: UpdateIdeaForm) => void;
}

// Use form types for creating/editing
const createIdea = (formData: CreateIdeaForm) => {
  // formData automatically excludes id, created_at, updated_at
};
```

### Available Auto-Generated Types

The `index.ts` file automatically generates:

**Model Types:**
- `Idea`, `User`, `Thread`, etc. (your Pydantic models)

**Form Types:**
- `CreateIdeaForm` - excludes auto-generated fields (id, timestamps)
- `UpdateIdeaForm` - partial with required id

**API Types:**
- `CreateIdeaRequest`, `CreateIdeaResponse` - for API calls
- `ApiPaths`, `ApiOperations` - for advanced usage

**Utility Types:**
- `ModelId` - consistent ID type across models
- `ValidationError`, `HTTPValidationError` - error handling

**Utility Functions:**
- `isModelType()` - type guard function
- `getErrorMessage()` - extract error messages from API responses

## Adding New Models

1. Create your Pydantic model in `src/backend/models/`
2. Use it in your FastAPI endpoints (this makes it appear in OpenAPI schema)
3. Run `make dev-types` to regenerate types

**Example:**
```python
# In your router
@router.post("/documents/")
async def create_document(document: PRD) -> PRD:
    # Your endpoint logic
    return document
```

This automatically includes `PRD` in the generated TypeScript types.

## Troubleshooting

### Import Errors

If you get import errors when running the generation script:

```bash
# Ensure you're in the project root
cd /path/to/your/project

# Run the generation
make types
```

### Missing Dependencies

```bash
# Install all dependencies
make install-deps
```

### Stale Types

```bash
# Clean and regenerate
make dev-types
```

### Types Not Appearing

Make sure your Pydantic models are used in FastAPI endpoints. Only models that appear in your API will be included in the OpenAPI schema.

## Best Practices

1. **Use models in endpoints** - Only Pydantic models used in FastAPI endpoints will appear in generated types
2. **Run after model changes** - Always regenerate types when you modify Pydantic models
3. **Use prebuild hooks** - Types are auto-generated before builds
4. **Version control generated files** - Commit generated types to catch breaking changes in CI
5. **Import from index** - Use `@/lib/types` for convenient imports
6. **Don't edit index.ts** - It's auto-generated and will be overwritten

## CI/CD Integration

Add to your CI pipeline:

```yaml
- name: Generate Types
  run: make types

- name: Check for type changes
  run: git diff --exit-code apps/frontend/lib/types/
```

This ensures types are always in sync and catches breaking changes.

## Commands Reference

| Command | Description |
|---------|-------------|
| `make types` | Generate TypeScript types |
| `make dev-types` | Clean and regenerate types |
| `make clean` | Remove generated files |
| `make install-deps` | Install required dependencies |
| `pnpm run types:generate` | Generate types (from frontend dir) | 