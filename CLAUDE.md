# Zou - Project Guidelines

Zou is the REST API backend for **Kitsu**, a production management tool for animation/VFX studios. Built on Flask + PostgreSQL.

## Quick Reference

```bash
# Lint / format
pre-commit run --all-files

# Generate a migration
zou migrate-db --message "Add column X to table Y"
```

## Architecture

```
zou/
├── app/
│   ├── __init__.py          # Flask app factory, JWT/auth setup
│   ├── api.py               # Blueprint registration, plugin loading
│   ├── config.py            # All config from env vars
│   ├── blueprints/          # ~25 feature-based API blueprint packages
│   │   ├── auth/            # Login, logout, 2FA, SSO
│   │   ├── crud/            # Generic CRUD for 40+ models
│   │   │   ├── base.py      # BaseModelsResource / BaseModelResource
│   │   │   └── *.py         # Per-model CRUD overrides
│   │   └── <feature>/       # assets, shots, tasks, projects, etc.
│   │       ├── __init__.py  # routes list + blueprint
│   │       ├── resources.py # Resource classes (HTTP handlers)
│   │       └── schemas.py   # Pydantic request validation
│   ├── models/              # ~50 SQLAlchemy models (BaseMixin)
│   ├── services/            # ~40 stateless business logic modules
│   ├── stores/              # File storage, Redis, event publisher
│   └── utils/               # Cache, events, permissions, validation, etc.
├── migrations/              # Alembic migration versions
├── remote/                  # Remote job runners (playlist, normalize)
└── cli.py                   # CLI commands (zou init-db, create-admin, etc.)
tests/
├── base.py                  # ApiDBTestCase with fixture generators
├── conftest.py              # Schema create/drop per session
├── models/                  # CRUD model tests
├── services/                # Service function tests
├── utils/                   # Utility tests
└── <feature>/               # Route-level tests per blueprint
specs/                       # Detailed architecture specs (for reference)
```

### Request lifecycle

```
HTTP → Flask routing → Resource method → @jwt_required()
  → check_*_permissions() → Service function → Model query/mutation
  → Event emission → JSON serialization → HTTP Response
```

## Code Conventions

### Formatting
- **Black** with line length 79 (`pyproject.toml`)
- **Autoflake** removes unused imports/variables
- Pre-commit hooks enforce both — run `pre-commit install` after cloning

### Python style
- Python 3.10+ (no walrus operator abuse, keep it readable)
- Services are **module-level functions**, not classes
- Models inherit `db.Model, BaseMixin, SerializerMixin`
- UUIDs everywhere for primary keys (`UUIDType(binary=False)`)
- **String formatting: f-strings only** for any new or edited code. Do not introduce `"... %s" % x` or `.format(...)`. Pre-existing `%`-formatted lines in a file you're editing can stay — don't scope-creep — but every new line you add uses f-strings. Multi-line: implicit concatenation of f-string literals, not `+`.
- **No parentheses around tuple literals** where they add nothing: write `return a, b`, not `return (a, b)`. Same for unpacking. Don't refactor untouched code for this.
- **Docstrings: opening and closing `"""` each on their own line.** Always put a newline immediately after the opening `"""` and immediately before the closing `"""`, even for one-liners. Do not write `"""Summary on the same line."""` or `"""First line\n    second line."""`.

  ```python
  # Wrong
  """Return the task or None."""
  """Common flow for bulk download: check permissions,
  build the bundle, send it as attachment."""

  # Right
  """
  Return the task or None.
  """
  """
  Common flow for bulk download: check permissions,
  build the bundle, send it as attachment.
  """
  ```

### Naming
- Model class: `PascalCase` (e.g., `TaskStatus`)
- Table: auto `snake_case` (e.g., `task_status`)
- Route: `kebab-case` (e.g., `/data/task-statuses`)
- FK column: `<table>_id` (e.g., `project_id`)
- M2M link table: `<table1>_<table2>_link`
- Service module: `<domain>_service.py` (e.g., `tasks_service.py`)
- Service functions: verb-first (`get_task()`, `create_task()`, `update_task()`)
- Raw vs serialized: `get_task_raw()` returns ORM object, `get_task()` returns dict

### Commit messages
- Prefix commits with the **domain** in brackets, not the change type
- The domain is the affected feature area (e.g., `projects`, `tasks`, `assets`, `shots`, `auth`, `playlists`, `previews`)
- Examples: `[projects] Avoid ObjectDeletedError when removing project tasks`, `[auth] Fix 2FA token expiration`, `[tasks] Allow bulk status update`
- Use `[tests]`, `[qa]`, `[docs]` only for changes that are purely test/lint/documentation with no domain

### Pull request descriptions
PR bodies follow a strict two-paragraph format. Do **not** use `## Summary` / `## Test plan` headers — match the existing repo convention exactly:

```markdown
**Problem**
- Concise bullet point describing the issue
- Another bullet if there are multiple related issues

**Solution**
- Concise bullet point describing what was changed to fix it
- Another bullet for related changes
```

Rules:
- Bullets are short and factual — no narrative paragraphs, no marketing language
- One PR = one logical change (or a small bundle of tightly related fixes); each problem bullet maps to one or more solution bullets
- Reference issues with `Fix #1234` or `cgwire/gazu#395` on a final line if applicable
- No `🤖 Generated with` footer, no `## Test plan` checklist — tests are listed in commit messages, not PR bodies

## Blueprints & Resources

### Adding a new feature endpoint

1. Create `zou/app/blueprints/<name>/`:
   - `__init__.py` — routes list + blueprint
   - `resources.py` — Resource classes
   - `schemas.py` — Pydantic schemas

2. Register in `zou/app/api.py`:
```python
from zou.app.blueprints.<name> import blueprint as <name>_blueprint
app.register_blueprint(<name>_blueprint)
```

### Resource pattern

```python
from flask.views import MethodView
from flask_jwt_extended import jwt_required
from zou.app.utils import permissions, validation
from zou.app.blueprints.<name>.schemas import MySchema

class MyResource(MethodView):
    @jwt_required()
    def post(self):
        permissions.check_manager_permissions()
        data = validation.validate_request_body(MySchema)
        result = my_service.create_something(data.field1, data.field2)
        return result, 201
```

### CRUD resources

For standard model CRUD, extend `BaseModelsResource` / `BaseModelResource` in `zou/app/blueprints/crud/`. Override permission hooks:
- `check_read_permissions()`, `check_create_permissions(data)`
- `check_update_permissions(instance, data)`, `check_delete_permissions(instance)`
- `add_project_permission_filter(query)` — scope queries to user's projects

## Pydantic Validation (v2)

All request body validation uses Pydantic v2 schemas. **Do not use `ArgsMixin` for body parsing** — `ArgsMixin.get_args` is for query parameters only. `flask_restful` and `reqparse` are gone: resources are plain Flask `MethodView` classes.

### Schema pattern

```python
# zou/app/blueprints/<name>/schemas.py
from typing import Optional
from pydantic import Field
from zou.app.utils.validation import BaseSchema

class CreateThingSchema(BaseSchema):
    name: str = Field(..., min_length=1, description="Thing name")
    project_id: str = Field(..., description="Parent project UUID")
    description: Optional[str] = None
```

- `BaseSchema` extends `BaseModel` with `extra="ignore"` (unknown fields are silently dropped)
- Use `Field(...)` for required fields, `Field(default=...)` or `Optional[X] = None` for optional
- Call `validation.validate_request_body(SchemaClass)` in your resource — returns validated model or raises `WrongParameterException` (400)

### Query parameters

Query parameters (page, limit, filters) are still read via `ArgsMixin` methods: `get_text_parameter()`, `get_bool_parameter()`, etc. Only request **bodies** use Pydantic.

### Style: push validation into the schema you touch

No dedicated refactor pass, but when you edit a schema or add one, use the Pydantic features instead of service-side checks:

- `@model_validator(mode="after")` for cross-field invariants (e.g. "if `is_for_all` then no `episode_id`") instead of a `WrongParameterException` raise in the service
- shared `Annotated` types for recurring fields (UUID strings, hex colors) instead of repeating the same `Field` constraints
- `TypeAdapter` to validate ad-hoc payloads (a list of ids) without declaring a full schema

## Services

Services are stateless modules in `zou/app/services/`. **All database access lives here**: a resource never builds an ORM query or calls a model directly, it checks permissions, validates input and calls service functions. Caller-dependent shaping (role-based serialization, vendor filtering) stays in the resource. Key patterns:

```python
# Caching
from zou.app.utils import cache

@cache.memoize_function(120)  # TTL in seconds
def get_thing(thing_id):
    return Thing.get(thing_id).serialize()

# Invalidation after mutation
def update_thing(thing_id, data):
    thing = Thing.get(thing_id)
    thing.update(data)
    cache.cache.delete_memoized(get_thing, thing_id)
    events.emit("thing:update", {"thing_id": str(thing.id)})
    return thing.serialize()
```

- Raise domain exceptions from `zou/app/services/exception.py` (e.g., `ThingNotFoundException`)
- Emit events after mutations: `events.emit("entity:action", data, project_id=...)`
- `get_*_raw()` returns SQLAlchemy instance (for internal use), `get_*()` returns serialized dict

## Models

All models in `zou/app/models/` inherit `db.Model, BaseMixin, SerializerMixin`.

```python
class MyModel(db.Model, BaseMixin, SerializerMixin):
    name = db.Column(db.String(80), nullable=False, unique=True)
    project_id = db.Column(UUIDType(binary=False), db.ForeignKey("project.id"))
    data = db.Column(JSONB)
```

`BaseMixin` provides: `create()`, `get(id)`, `get_by()`, `get_all_by()`, `update(data)`, `delete()`, `serialize()`.

The `Entity` model is **polymorphic** — assets, shots, sequences, episodes are all rows distinguished by `entity_type_id`. Write operations on entities go through the `data/entities/` routes; several entity-noun sub-routes are GET-only.

## Permissions & Roles

Roles (highest to lowest): **admin > manager > supervisor > user > client > vendor**

```python
from zou.app.utils import permissions

permissions.check_admin_permissions()                # admin only
permissions.check_manager_permissions()              # admin or manager
permissions.check_at_least_supervisor_permissions()  # supervisor+
user_service.check_project_access(project_id)        # user is team member
```

### Order matters: resolve the project first

A role can be set **per project** (`project_person_link.role`), and
`permissions._effective_role()` returns that role when one is resolved,
falling back to the global role otherwise. The resolution is a **side effect**
of the project access check:

```python
check_belong_to_project(project_id)   # sets g.project_role, clears it on failure
check_project_access(project_id)      # same, and raises
resolve_project_role(project_id)      # named variant, when you only want the side effect
```

So any `has_*_permissions()` / `check_*_permissions()` called **before** one of
those reads the *global* role, silently:

```python
# Wrong — reads the global role, per-project role never applies
if permissions.has_client_permissions():
    raise permissions.PermissionDenied
user_service.check_project_access(task["project_id"])

# Right
user_service.check_project_access(task["project_id"])
if permissions.has_client_permissions():
    raise permissions.PermissionDenied
```

Nothing in the signatures says this — it is the single most common source of
authorization bugs in this codebase.

Two more traps in the same family:

- `check_entity_access(entity_id)` is **only a vendor filter**. It returns
  `True` immediately for every other role and never looks at the project. It
  complements `check_project_access`, it never replaces it.
- `check_person_access(person_id)` is **admin or self**, nothing else.
- Prefer the `check_*` variants that raise over the `has_*` booleans. When you
  do use a boolean, make sure every branch ends in a denial.

## Security review rules

Findings live in `.audit/` (generated, gitignored — not part of the codebase).
The rules below are what repeated audits actually caught; follow them when
adding or reviewing a route.

**One data path, one policy.** The dominant defect class here is two routes
serving the same data with different guards — list vs. single, bulk vs. unit,
export vs. import. When you add a route next to an existing one, copy its
guard or change both. `tests/misc/test_crud_permission_symmetry.py` enforces
this for CRUD list/single pairs.

**Never trust a client-supplied id to belong to its parent.** A route that
takes `<task_id>/<comment_id>/<attachment_file_id>` must check each link, not
just the first. Load the child and compare its foreign key.

**Filters run before serialization.** `BaseModelsResource.build_filters`
accepts any ORM descriptor, so a column hidden from the response is still
queryable (`?daily_salary=320`). Masking output is not masking data.

**Protect `project_id` on write.** `BaseModelResource.protected_fields`
defaults to `["id", "created_at", "updated_at"]`. Permission hooks validate the
*current* project read from the instance; without protection, a `PUT` body can
move the row to another project.

**Never put a caller-dependent filter inside a memoized service.**
`@cache.memoize_function` keys on the arguments only. A filter that depends on
`g.project_role` or `get_current_user()` inside a memoized function serves the
first caller's scoped result to everyone for the TTL. Pass the scoping in as an
argument, or apply it in the resource.

**File paths derive from server-side identifiers.** Never join a client string
onto a path: `os.path.join` does not normalize `..` and silently discards the
prefix when the second argument is absolute. Use a generated UUID for the
stem, and validate any extension against an allowlist.

**Sanitize DB errors before returning them.** Use
`crud.base.build_db_error_message`; raw SQLAlchemy text carries constraint
names, column names and bound values.

**Escape values interpolated into email templates.**
`utils/email_i18n.get_email_translation` uses `str.format()` on HTML
templates. Anything reaching it from a request — a header, a comment body — is
injected raw into a mail the studio genuinely sends.

## Events

```python
from zou.app.utils import events

events.emit("task:update", {"task_id": str(task.id)}, project_id=str(task.project_id))
```

Format: `<table_name>:<action>` — e.g., `task:new`, `comment:delete`, `person:update`. Events are persisted to `ApiEvent` and broadcast via Redis pub/sub to WebSocket clients.

## Testing

See `CLAUDE.local.md` (gitignored) for how to run tests on this machine. The test DB schema is created/dropped automatically by `conftest.py`, which also forces `PREVIEW_FOLDER` to a tempdir.

### Test base class

All tests inherit `ApiDBTestCase` (from `tests/base.py`):
- Auto-creates admin user and logs in
- HTTP helpers: `self.get()`, `self.post()`, `self.put()`, `self.delete()`
- 404 helpers: `self.get_404()`, `self.put_404()`, `self.delete_404()`
- `self.get_first(path)` — GET list and return first element
- Fixture generators: `generate_fixture_project()`, `generate_fixture_asset()`, `generate_fixture_task()`, etc.
- `generate_base_context()` — creates project status, project, asset type, department, task type, task status
- `generate_data(Model, N, **kwargs)` — creates N random instances with mixer

### CRUD model test pattern

```python
from tests.base import ApiDBTestCase
from zou.app.models.department import Department

class DepartmentTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_data(Department, 3)

    def test_get_departments(self):
        departments = self.get("data/departments")
        self.assertEqual(len(departments), 3)

    def test_get_department(self):
        department = self.get_first("data/departments")
        department_again = self.get("data/departments/%s" % department["id"])
        self.assertEqual(department, department_again)
        self.get_404("data/departments/%s" % fields.gen_uuid())

    def test_create_department(self):
        data = {"name": "open", "color": "#000000"}
        self.department = self.post("data/departments", data)
        self.assertIsNotNone(self.department["id"])

    def test_update_department(self):
        department = self.get_first("data/departments")
        self.put("data/departments/%s" % department["id"], {"color": "#FFF"})

    def test_delete_department(self):
        department = self.get_first("data/departments")
        self.delete("data/departments/%s" % department["id"])
```

### Service test pattern

```python
from tests.base import ApiDBTestCase
from zou.app.services import my_service
from zou.app.services.exception import MyNotFoundException

class MyServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()

    def test_get_something(self):
        result = my_service.get_something(self.project.id)
        self.assertEqual(len(result), expected)

    def test_not_found(self):
        self.assertRaises(
            MyNotFoundException,
            my_service.get_something,
            "nonexistent-id",
        )
```

## Migrations

```bash
zou migrate-db --message "Add column X to table Y"   # generate
zou upgrade-db                                        # apply
zou downgrade-db --revision "-1"                      # rollback one step
```

Migrations live in `zou/migrations/versions/`. Each file has `upgrade()` and `downgrade()` functions. Use `UUIDType(binary=False)` for UUID columns. New columns must be nullable or defaulted (one-way migrations in production).

## Key Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DB_DATABASE` | zoudb | PostgreSQL database name |
| `DB_HOST` | localhost | PostgreSQL host |
| `SECRET_KEY` | mysecretkey | Flask secret (change in prod!) |
| `KV_HOST` | localhost | Redis host |
| `CACHE_TYPE` | (None) | Set to `simple` for in-memory cache |
| `FS_BACKEND` | local | File storage: local, s3, swift |
| `ENABLE_JOB_QUEUE` | false | Enable RQ/Nomad job queue |
| `INDEXER_KEY` | (None) | Meilisearch API key |
| `MAIL_SERVER` | localhost | SMTP server |

## Detailed Specs

For deeper architectural documentation, see `specs/`:
- `specs/architecture.md` — Full architecture overview
- `specs/blueprints.md` — Blueprint patterns, CRUD hooks
- `specs/models.md` — Model hierarchy, entity type system
- `specs/services.md` — Service patterns, caching, events
- `specs/testing.md` — Test patterns, fixtures
- `specs/auth.md` — Authentication, 2FA, roles
- `specs/configuration.md` — All environment variables
- `specs/events.md` — Event system
- `specs/storage.md` — File storage backends
- `specs/plugins.md` — Plugin system

## Common Tasks Cheatsheet

| Task | How |
|------|-----|
| Add a new model | Create in `zou/app/models/`, add CRUD in `zou/app/blueprints/crud/`, add routes in `crud/__init__.py` |
| Add a feature endpoint | Create blueprint package in `zou/app/blueprints/<name>/`, register in `api.py` |
| Add request validation | Create `schemas.py` with `BaseSchema` subclass, call `validate_request_body()` in resource |
| Add a service | Create `zou/app/services/<name>_service.py` with module-level functions |
| Add caching | Decorate with `@cache.memoize_function(ttl)`, invalidate with `cache.cache.delete_memoized()` |
| Emit an event | `events.emit("entity:action", {"entity_id": str(id)}, project_id=...)` |
| Add a test | Create in `tests/` inheriting `ApiDBTestCase`, use fixture generators |
| Install plugins | `zou install-plugin --path /path/to/plugin` |
| Create admin user | `zou create-admin --email admin@example.com --password secret` |
