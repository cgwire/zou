# Event System

## Overview

Mutations emit events that are persisted to the database and broadcast via Redis pub/sub. An event stream daemon relays events to WebSocket clients for live UI updates.

## Emission

```python
from zou.app.utils import events

events.emit(
    "task:new",                          # event name
    {"task_id": str(task.id)},           # event data
    project_id=str(task.project_id),     # optional scope
    persist=True,                        # save to ApiEvent table (default True)
)
```

## Event naming

Format: `<table_name>:<action>` (underscores in table name replaced by hyphens).

Examples: `task:new`, `task:update`, `task:delete`, `comment:new`, `person:update`.

The data dict always includes `<table_name>_id`.

## Flow

1. **Handler execution** — registered handlers run synchronously in-process
2. **Redis publish** — event published to Redis channel for subscribers
3. **DB persistence** — `ApiEvent` record created with timestamp and data
4. **Event stream** — daemon on port 5001 subscribes to Redis, broadcasts via WebSocket

## Handler registration

Handlers are loaded from `EVENT_HANDLERS_FOLDER` at startup:

```python
# event_handlers/task_new.py
def handle_event(app, data):
    task_id = data["task_id"]
    # send notification, update index, trigger webhook, etc.
```

Handlers are mapped by event name in `event_handlers/event_map`.

## Querying events

Events are queryable via `GET /data/events/` with filters on name, project, date range. The `ApiEvent` model stores:

- `name` — event name (indexed)
- `user_id` — person who triggered it
- `project_id` — project scope (indexed)
- `data` — JSONB payload
- `created_at` — timestamp
