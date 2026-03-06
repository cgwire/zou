# Services

## Pattern

Services are stateless Python modules in `zou/app/services/`. They contain plain functions (no classes). Blueprints call service functions for business logic; services call models for persistence.

```
Blueprint resource → Service function → Model query/mutation → Event emission
```

## Conventions

- One module per domain: `tasks_service.py`, `persons_service.py`, etc.
- Functions named with verbs: `get_task()`, `create_task()`, `update_task()`, `delete_task()`
- `get_*_raw()` returns the SQLAlchemy model instance
- `get_*()` returns a serialized dict
- Raise specific exceptions from `zou/app/services/exception.py` (e.g., `TaskNotFoundException`)
- Emit events after mutations via `events_service.emit()`
- Use `@cache.memoize_function(timeout)` for expensive reads

## Service list

| Service | Purpose |
|---------|---------|
| `assets_service` | Asset types, assets, casting |
| `auth_service` | Login, token generation, LDAP/SAML |
| `backup_service` | Database backup |
| `base_service` | Shared helpers (model retrieval) |
| `breakdown_service` | Episode/sequence breakdowns |
| `chats_service` | Entity chat threads and messages |
| `comments_service` | Comment CRUD, replies, attachments, acknowledgments |
| `concepts_service` | Concept art management |
| `deletion_service` | Safe deletion with relationship cleanup |
| `edits_service` | Edit/video content |
| `emails_service` | Email template rendering and sending |
| `entities_service` | Generic entity operations |
| `events_service` | Event emission and persistence |
| `files_service` | Working files, output files, file paths, versioning |
| `index_service` | Meilisearch indexing |
| `names_service` | Naming convention utilities |
| `news_service` | Studio news/announcements |
| `notifications_service` | Notification creation and subscriptions |
| `persons_service` | Person CRUD, departments, presence |
| `playlists_service` | Playlists, sharing, build jobs |
| `preview_files_service` | Preview uploads, thumbnails, annotations |
| `projects_service` | Project CRUD, team, settings, metadata |
| `schedule_service` | Schedule items, milestones, production schedules |
| `shots_service` | Shots, sequences, episodes, scenes |
| `status_automations_service` | Automatic status transitions |
| `sync_service` | Data import/export synchronization |
| `tasks_service` | Task lifecycle, assignments, status, time tracking |
| `templates_service` | File tree templates |
| `user_service` | Current user context, access checks |

## Caching pattern

```python
from zou.app.utils import cache

@cache.memoize_function(120)  # cached 120 seconds
def get_person(person_id):
    return Person.get(person_id).serialize()

def update_person(person_id, data):
    person = Person.get(person_id)
    person.update(data)
    cache.cache.delete_memoized(get_person, person_id)  # invalidate
    return person.serialize()
```

## Event emission pattern

```python
from zou.app.services import events_service

def create_task(data):
    task = Task.create(**data)
    events_service.emit(
        "task:new",
        {"task_id": str(task.id)},
        project_id=str(task.project_id),
    )
    return task.serialize()
```

## Exception pattern

All service exceptions live in `zou/app/services/exception.py`. Each model has a corresponding `<Model>NotFoundException`. Blueprints catch these and return appropriate HTTP status codes.

```python
from zou.app.services.exception import TaskNotFoundException

def get_task(task_id):
    task = Task.get(task_id)
    if task is None:
        raise TaskNotFoundException
    return task.serialize()
```
