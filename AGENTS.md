# AGENTS.md

<!-- AGENTS.md shared standard v1 — canonical copy: https://github.com/MuckRock/gps/blob/main/AGENTS.md -->

## Code comments

Comments say **why**, not what. If the code already says it, delete the comment.

- **One or two short sentences.** If it needs a paragraph, it belongs in a
  doc comment, the PR description, or a doc under `docs/`.
- **Keep the consequence, drop the lead-in.** The clause naming what the
  code does is the half to cut; the clause saying what breaks otherwise is
  the half worth keeping.
- **Never describe code that is not there.** No "this used to...", no
  narrating the change, no explaining why something was removed. `git log`
  and the PR hold that.
- **No reasoning out loud.** Don't walk through scenarios, anticipate
  objections, or record the thought process behind a choice.
- **Do comment the surprising**: a constraint an external system imposes,
  an ordering requirement, a failure that cannot be seen locally. That is
  what a reader cannot get from the code.

```typescript
// Good - a constraint you cannot see from here
// The API rejects a redaction whose page range crosses a document split.

// Bad - narrates the change
// `currentPage` is now derived from the store instead of a prop, so
// this component no longer needs to read it from context.
```

## Docstrings / doc comments

One line on what it does. Add more only for a contract a caller needs:
what it rejects/throws, what it returns in the edge case, ordering it
requires, side effects it has, a cost worth avoiding.

Two tests before you keep a second paragraph:

- Does it restate the first line in more words? Delete it.
- Would a caller behave differently for knowing it? Keep it, in one or two
  sentences.

```typescript
// Good - the whole contract, one line
/** Does the document still have pages pending OCR? */

// Good - a second paragraph a caller acts on
/**
 * The document's current processing status, or "error" if any page failed.
 *
 * Read from the cached store value; the document list renders one row
 * per document and cannot afford an API call each.
 */
```

## Pull request descriptions

Open with one sentence on what changes. Then:

- **Behaviour changes** — name them, or say "none".
- **Migrations** — what they do, whether they reverse.
- **What to check** — the QA steps, as a checklist.

Bullets, not prose. Don't recount how the change came about or what was
tried first.

## Tests

Name the behaviour, not the mechanism: `renders the error state when
OCR fails`, not `test handle error`. A test whose assertion would pass
against the unfixed code is not a test.

<!-- /AGENTS.md shared standard -->

## Project Overview

DocumentCloud is a document management and analysis platform built with Django REST Framework. It allows users to upload, process, annotate, and publish documents with features like OCR, entity extraction, add-ons system, and collaborative projects.

## Architecture

### Core Components

**documentcloud/** - Main Django apps organized by domain:

- `documents/` - Document models, processing pipeline, and views. Core entity with nested models for Notes, Sections, Entities, and Redactions
- `projects/` - Project management with document memberships and user collaborations
- `organizations/` - Organization management (integrated with Squarelet authentication)
- `users/` - User models and authentication
- `addons/` - Extensible add-on system allowing third-party document processing
- `entities/` - Named entity recognition and extraction
- `oembed/` - oEmbed protocol for document embedding
- `statistics/` - Usage tracking and analytics
- `core/` - Shared utilities and base classes
- `drf_bulk/` - Bulk create/update/delete support for DRF viewsets and routers

### Document Processing Pipeline

Documents go through a multi-stage processing pipeline, typically run via AWS Lambda functions or locally via Celery:

1. **Document Conversion** (`documents/processing/document_conversion/`) - Converts various formats (Word, Excel, etc.) to PDF using LibreOffice
2. **Info & Image** (`documents/processing/info_and_image/`) - Extracts metadata and generates page images using PDFium
3. **OCR** (`documents/processing/ocr/`) - Performs optical character recognition on images (supports Tesseract and Textract engines)
4. **Text Position Extract** (`documents/processing/ocr/main.py`, `documents/processing/utils/main.py`) - Extracts precise text positioning data for highlighting

Processing can run in two modes:

- **Local development**: Celery tasks execute processing synchronously
- **Production**: AWS Lambda functions process documents asynchronously via pub/sub

### Storage Architecture

- **S3/Minio**: Document files, page images, and processing artifacts
- **PostgreSQL**: Relational data (documents, users, projects, etc.)
- **Solr**: Full-text search for documents and notes
- **Redis (Valkey)**: Celery broker, task results, and caching

### Authentication

Integrates with Squarelet (separate microservice) for SSO authentication. DocumentCloud joins Squarelet's docker network in development. Required environment variables:

- `SQUARELET_KEY` and `SQUARELET_SECRET` for OAuth
- `JWT_VERIFYING_KEY` for token verification

## Development Commands

All commands use `invoke` (tasks defined in `tasks.py`):

### Essential Commands

```bash
# Start development environment
export COMPOSE_FILE=local.yml
docker compose up

# Run tests
inv test                           # Run all tests
inv test --path documentcloud/documents  # Run tests in specific directory
inv test --path documentcloud/documents/tests/test_views.py  # Run single file

# Test options
inv test --ipdb                    # Drop into debugger on failure
inv test --slow                    # Include slow tests (skipped by default)
inv test --keywords "keyword"      # Filter tests by keyword
inv testwatch                      # Watch mode for continuous testing

# Code quality
inv format                         # Format code with black and isort
inv pylint                         # Run linter
inv coverage                       # Generate coverage report

# Database and shell access
inv shell                          # Django shell_plus
inv dbshell                        # PostgreSQL shell
inv sh                             # Bash shell in container
inv manage "command"               # Run Django management command
inv run "command"                  # Run arbitrary command in container

# Celery workers
inv celeryworker                   # Start celery worker
inv celerybeat                     # Start celery scheduler

# Dependencies
inv pip-compile                    # Compile requirements files
inv pip-compile --upgrade          # Upgrade all packages
inv pip-compile --package "name"   # Upgrade specific package

# Build
inv build                          # Build docker images
inv build --service documentcloud_django  # Build specific service
```

### Processing Setup (Local Development)

To enable OCR locally:

```bash
inv download_tesseract_data
```

### Solr Configuration

Update Solr schema or config:

```bash
inv update_solr_config
# Then restart: docker compose down && docker compose up
```

## API Architecture

REST API built with Django REST Framework using nested routers:

**Top-level resources:**

- `/api/documents/` - DocumentViewSet (supports bulk operations)
- `/api/projects/` - ProjectViewSet
- `/api/organizations/` - OrganizationViewSet
- `/api/users/` - UserViewSet
- `/api/addons/` - AddOnViewSet
- `/api/addon_runs/` - AddOnRunViewSet
- `/api/addon_events/` - AddOnEventViewSet
- `/api/entities/` - EntityViewSet
- `/api/statistics/` - StatisticsViewSet

**Nested resources:**

- `/api/documents/{id}/notes/` - Document annotations
- `/api/documents/{id}/sections/` - Document sections
- `/api/documents/{id}/entities/` - Document entity occurrences
- `/api/documents/{id}/data/` - Document key-value data
- `/api/documents/{id}/redactions/` - Document redactions
- `/api/projects/{id}/documents/` - Project memberships
- `/api/projects/{id}/users/` - Project collaborations

Custom routers support bulk operations via the in-repo `documentcloud/drf_bulk/` app.

## Key Django Apps

### Documents App

Central to the platform. Models are split across `documents/models/`:

- `document.py` - Main Document model with processing status, access control
- `note.py` - Annotations on documents
- `entity.py` - Legacy entity extraction (deprecated, see entities app)
- `saved_search.py` - Saved search queries

Document processing tasks in `documents/tasks.py` coordinate the pipeline and handle Solr indexing.

### Add-ons System

Extensible system allowing external code to process documents:

- Add-ons can be installed from GitHub repositories
- Runs in isolated environments with configurable parameters
- Events system for real-time updates
- File uploads/downloads per run
- Visual add-ons can render custom UIs

### Entities App

Named entity recognition using Google Cloud Natural Language API:

- Extracts persons, organizations, locations, events, etc.
- Links entity occurrences across documents
- Relevance scoring and filtering

## Testing

Tests organized alongside source code in `tests/` directories.

**Markers:**

- `@pytest.mark.slow` - Expensive tests (skipped by default with `inv test`)
- `@pytest.mark.solr` - Tests requiring Solr test instance

Test configuration in `pytest.ini` uses `config.settings.test` for isolated test database.

## Environment Configuration

Environment variables in `.envs/.local/`:

- `.django` - Django and application settings
- `.postgres` - Database credentials

Critical settings:

- `DJANGO_SETTINGS_MODULE` - config.settings.{local,test,production}
- `DATABASE_URL` - PostgreSQL connection
- `REDIS_URL` - Redis connection for Celery
- `MINIO_*` - S3-compatible storage (MinIO in local development)
- `SOLR_URL` - Solr search endpoint

## Docker Services

Defined in `local.yml`:

- `documentcloud_django` - Main Django app (port 8000)
- `documentcloud_postgres` - PostgreSQL 15
- `documentcloud_redis` - Valkey 9.1 (Celery broker)
- `documentcloud_processing_redis` - Valkey 9.1 (processing tasks)
- `documentcloud_minio` - S3-compatible storage (port 9000)
- `documentcloud_solr` - Solr 8.3 (port 8983)
- `documentcloud_test_solr` - Separate Solr for tests (port 8984)
- `documentcloud_celeryworker` - Background task worker
- `documentcloud_celerybeat` - Scheduled task runner

All services join the `squarelet_default` network for authentication.

## Common Patterns

### Permissions

Uses `django-rules` for object-level permissions. Rules defined in `{app}/rules.py` files, except `documents/rules/`, which is a package with one module per model. Check permissions with `user.has_perm('documents.view_document', document)`.

### Access Control

Documents and add-ons use an integer `Access` enum (`documents/choices.py`); projects use a `private` boolean plus `CollaboratorAccess` for collaborators:

- `public` (0) - Anyone
- `organization` (1) - Organization members
- `private` (2) - Owner only
- `invisible` (3) - Taken down; not exposed in the API

### Search

Solr-backed search in `documents/search.py` and `documents/solr.py`. Complex query parsing using `luqum` library. Separate cores for documents and notes.

### Celery Tasks

Shared tasks defined with `@shared_task` decorator. Time limits configured per task. Processing tasks use pub/sub in production, direct execution in local development.

## URLs and Routing

Main URL configuration in `config/urls.py`. Uses `drf-nested-routers` for nested REST resources. Special routes:

- `/admin/` - Django admin (set by `ADMIN_URL`; production reads it from `DJANGO_ADMIN_URL`)
- `/api/` - REST API root
- `/api/schema/` - OpenAPI schema (drf-spectacular)
- `/files/documents/{id}/{path}` - File serving
- `/visual/{slug}/` - Visual add-on proxy

## Key Dependencies

- Django 5.2 with django-environ for configuration
- Django REST Framework with drf-spectacular for OpenAPI
- Celery for async tasks
- Solr (pysolr) for search
- PDF processing: pdfplumber, pikepdf, pymupdf
- ML/AI: numpy, google-cloud-language
- Cloud: boto3, gcsfs, smart-open
- Authentication: squarelet-auth, social-auth-core

## Deployment

Production deployment on Heroku with AWS Lambda for document processing. Lambda functions deployed via:

```bash
inv deploy_lambdas            # Production
inv deploy_lambdas --staging  # Staging
```

## Local Development URLs

- Django API: https://api.dev.documentcloud.org/
- Django Admin: https://api.dev.documentcloud.org/admin/
- MinIO Console: http://minio.documentcloud.org:9000
- Solr Admin: http://localhost:8983
- Frontend: https://dev.documentcloud.org (separate repo)
- Accounts: https://dev.squarelet.com/ (separate repo)
