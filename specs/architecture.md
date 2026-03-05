# Architecture Overview

Zou is the REST API backend for Kitsu, a production management tool for animation and VFX studios. It is built on Flask with PostgreSQL.

## Tech stack

- **Framework**: Flask + Flask-RESTful
- **Database**: PostgreSQL (psycopg3 driver) via Flask-SQLAlchemy
- **Migrations**: Alembic via Flask-Migrate
- **Auth**: Flask-JWT-Extended (access + refresh tokens)
- **Caching**: Flask-Caching backed by Redis (DB 1)
- **Event bus**: Redis pub/sub (DB 0)
- **Job queue**: Nomad (optional, for preview processing)
- **Search**: Meilisearch (optional, full-text indexing)
- **Storage**: Local filesystem, S3, or OpenStack Swift
- **Email**: Flask-Mail (SMTP)

## Directory layout

```
zou/
├── app/
│   ├── __init__.py          # Flask app factory, extensions init
│   ├── api.py               # Blueprint registration, plugin loading
│   ├── config.py            # All configuration from env vars
│   ├── blueprints/          # 25 feature-based blueprint packages
│   │   ├── auth/            # Login, logout, 2FA, SSO
│   │   ├── crud/            # Generic CRUD for 40+ models
│   │   ├── assets/          # Asset management
│   │   ├── shots/           # Shot/sequence management
│   │   ├── tasks/           # Task lifecycle
│   │   ├── comments/        # Task comments and replies
│   │   ├── persons/         # User management
│   │   ├── projects/        # Project settings
│   │   ├── files/           # File metadata and versioning
│   │   ├── previews/        # Preview file management
│   │   ├── playlists/       # Review playlists
│   │   └── ...              # breakdown, chats, concepts, edits,
│   │                        # entities, events, export, index,
│   │                        # news, search, source, user,
│   │                        # departments
│   ├── models/              # 50 SQLAlchemy model files
│   ├── services/            # 40 business logic modules
│   ├── stores/              # File storage abstraction
│   └── utils/               # 31 utility modules
├── migrations/              # Alembic migration versions
├── remote/                  # Remote job execution
└── cli.py                   # CLI commands
tests/
├── base.py                  # ApiDBTestCase base class
├── models/                  # CRUD blueprint tests
├── services/                # Service tests
├── utils/                   # Utility tests
└── ...                      # Route-level tests
plugins/                     # External plugin packages
```

## Request lifecycle

```
HTTP Request
  → Flask routing
  → Blueprint resource method (get/post/put/delete)
  → @jwt_required() decorator (auth check)
  → check_*_permissions() (role + project/entity access)
  → Service function (business logic)
  → Model query/mutation (SQLAlchemy)
  → Event emission (Redis pub/sub + DB persist)
  → JSON serialization (SerializerMixin)
  → HTTP Response
```

## Multi-tenancy model

Implicit via ownership chains, not schema-level isolation:

```
Studio → Organisation → Project → Entity/Task/...
              ↓
         Department → Person
```

Permissions are enforced at the blueprint/service layer. Every endpoint checks that the requesting user has access to the relevant project or entity.

## Key design patterns

1. **Blueprint + Resource**: Each feature is a Flask blueprint containing Flask-RESTful Resource classes.
2. **Service layer**: Blueprints delegate to stateless service functions. Services handle business logic, caching, and event emission.
3. **Generic CRUD**: `BaseModelsResource` and `BaseModelResource` provide list/create and get/update/delete for any model. Subclasses override permission hooks.
4. **Event-driven**: Mutations emit events via Redis pub/sub. The event stream daemon broadcasts to WebSocket clients for live UI updates.
5. **Memoized caching**: Frequently accessed data (persons, projects, task types) is cached in Redis with explicit invalidation on mutation.
