# Plugin System

## Structure

Plugins are Python packages in the `PLUGIN_FOLDER` directory. Each plugin can provide API routes, database models, migrations, and a Vue.js frontend.

```
my-plugin/
├── manifest.toml       # Required: metadata
├── __init__.py          # Required: routes list
├── models.py            # Optional: SQLAlchemy models
├── migrations/          # Optional: Alembic migrations
│   ├── alembic.ini
│   ├── env.py
│   └── versions/
└── frontend/            # Optional: Vue.js SPA
    └── dist/
```

## Manifest

```toml
[project]
id = "my-plugin"
name = "My Plugin"
version = "1.0.0"
license = "MIT"
description = "Plugin description"
maintainer = "Name <email>"
website = "https://example.com"
frontend_project_enabled = false
frontend_studio_enabled = false
```

## Routes

The plugin module must expose a `routes` list:

```python
from flask_restful import Resource
from flask_jwt_extended import jwt_required

class MyResource(Resource):
    @jwt_required()
    def get(self):
        return {"data": "response"}

routes = [
    ("/endpoint", MyResource),
]
```

Routes are mounted at `/plugins/<plugin-id>/`.

## Database

Plugin tables are prefixed `plugin_<plugin_id>_` to avoid collisions. Migrations use Alembic and are run via `run_plugin_migrations()`.

## Loading

Plugins are loaded at app startup in `zou/app/api.py` → `load_plugins(app)`. The loader:

1. Scans `PLUGIN_FOLDER` for subdirectories
2. Validates `manifest.toml` (semver version, SPDX license)
3. Imports the module and reads `routes`
4. Creates a Flask blueprint with prefix `/plugins/<id>`
5. Serves frontend static files from `frontend/dist/`
6. Logs errors without crashing the app

## Frontend

If the plugin has a `frontend/dist/` directory, files are served as static resources. The `index.html` is the SPA entry point. Frontend flags in the manifest control where the plugin UI appears in Kitsu.
