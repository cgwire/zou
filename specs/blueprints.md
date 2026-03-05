# Blueprints and Routing

## Registration

All blueprints are registered in `zou/app/api.py`. Each blueprint package defines a `routes` list and a `blueprint` object. Registration uses:

```python
configure_api_from_blueprint(blueprint, routes)
```

This wraps Flask-RESTful's `Api` around the blueprint and adds all routes.

## Blueprint list

| Blueprint | Prefix | Purpose |
|-----------|--------|---------|
| auth | `/auth/` | Login, logout, password reset, 2FA, SSO |
| user | `/auth/` | Current user profile, preferences, avatar |
| crud | `/data/` | Generic CRUD for 40+ models |
| assets | `/data/` | Asset types, casting, task relations |
| shots | `/data/`, `/actions/` | Shot/sequence/episode management |
| tasks | `/data/`, `/actions/` | Task lifecycle, assignments, time tracking |
| comments | `/actions/` | Task comments, replies, attachments |
| persons | `/data/`, `/actions/` | User management, day-offs, quotas |
| projects | `/data/`, `/actions/` | Project settings, team, budgets, schedules |
| files | `/data/`, `/actions/` | Working files, output files, file paths |
| previews | `/data/` | Preview uploads, thumbnails |
| playlists | `/data/` | Review playlists, sharing |
| breakdown | `/data/` | Episode/sequence breakdown |
| chats | `/data/` | Entity chat messages |
| concepts | `/data/` | Concept art |
| departments | `/data/` | Department management |
| edits | `/data/` | Video editing content |
| entities | `/data/` | Entity types, entity links |
| events | `/data/` | Event history |
| export | `/actions/` | CSV export, reports |
| index | `/` | Health check |
| news | `/data/` | Studio news |
| search | `/search/` | Meilisearch full-text search |
| source | `/data/` | Data import from external sources |

## CRUD blueprint

The `crud` blueprint (`zou/app/blueprints/crud/`) provides generic REST endpoints for 40+ models. Each model gets two resource classes:

- `<Model>sResource(BaseModelsResource)` → `GET /data/<route>`, `POST /data/<route>`
- `<Model>Resource(BaseModelResource)` → `GET/PUT/DELETE /data/<route>/<id>`

### BaseModelsResource (list + create)

```python
class BaseModelsResource(Resource):
    def get(self):
        # Query params: ?page=&limit=&relations=&<field>=<value>
        # Pagination: page > 0 returns {data, total, nb_pages, limit, offset, page}
        # page == -1 returns unpaginated array
        # Filtering: column names as query params, ILIKE for name field

    def post(self):
        # Creates instance from JSON body
        # Strips protected_fields (id, created_at, updated_at)
        # Emits create event
        # Returns 201
```

### BaseModelResource (single item)

```python
class BaseModelResource(Resource):
    def get(self, instance_id):   # Returns instance or 404
    def put(self, instance_id):   # Updates fields, returns 200 or 404
    def delete(self, instance_id): # Returns 204 or 404
```

### Permission hooks to override

| Hook | Called by | Purpose |
|------|----------|---------|
| `check_read_permissions(options)` | GET list | Filter or deny access |
| `check_read_permissions(instance_dict)` | GET single | Deny access to specific instance |
| `check_create_permissions(data)` | POST | Validate creation rights |
| `check_update_permissions(instance_dict, data)` | PUT | Validate update rights |
| `check_delete_permissions(instance_dict)` | DELETE | Validate deletion rights |
| `check_creation_integrity(data)` | POST | Business rule validation |

### Lifecycle hooks

| Hook | When | Use case |
|------|------|----------|
| `update_data(data)` | Before create/update | Strip or transform fields |
| `post_creation(instance)` | After create, before response | Side effects |
| `pre_update(instance_dict, data)` | Before update | Validate transitions |
| `post_update(instance_dict, data)` | After update | Cache invalidation, events |
| `pre_delete(instance_dict)` | Before delete | Cleanup related data |
| `post_delete(instance_dict)` | After delete | Events, cache invalidation |
| `clean_get_result(result)` | Before response | Transform response data |

## Adding a new blueprint

1. Create `zou/app/blueprints/<name>/__init__.py`:
```python
from flask import Blueprint
from zou.app.utils.api import configure_api_from_blueprint

routes = [
    ("/data/<route>", MyListResource),
    ("/data/<route>/<instance_id>", MySingleResource),
]

blueprint = Blueprint("<name>", "<name>")
api = configure_api_from_blueprint(blueprint, routes)
```

2. Register in `zou/app/api.py`:
```python
from zou.app.blueprints.<name> import blueprint as <name>_blueprint
app.register_blueprint(<name>_blueprint)
```

## Adding a CRUD endpoint for a new model

1. Create `zou/app/blueprints/crud/<model_name>.py`:
```python
from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource
from zou.app.models.<model_name> import MyModel

class MyModelsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, MyModel)

    def check_read_permissions(self, options=None):
        # implement access control

class MyModelResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, MyModel)

    def check_read_permissions(self, instance_dict):
        # implement access control
```

2. Add routes in `zou/app/blueprints/crud/__init__.py`:
```python
("/data/my-models", MyModelsResource),
("/data/my-models/<instance_id>", MyModelResource),
```
