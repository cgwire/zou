# Plugin System

## Structure

Plugins are Python packages in the `PLUGIN_FOLDER` directory. Each plugin can provide API routes, database models, migrations, and a Vue.js frontend.

```
my-plugin/
├── manifest.toml        # Required: metadata
├── __init__.py          # Required: routes list
├── models.py            # Optional: SQLAlchemy models
├── migrations/          # Optional: Alembic revisions only
│   └── versions/        # Plugin's revision files (.py)
└── frontend/            # Optional: Vue.js UI
    └── dist/
        ├── index.html   # Iframe SPA entry (optional)
        └── plugin.js    # Host-integration bundle (optional)
```

> **Note** — plugins do **not** ship `env.py`, `alembic.ini` or `script.py.mako`. Zou owns those files under `zou/app/utils/plugin_alembic_template/` and points alembic at them via `script_location` while overriding `version_locations` to the plugin's own `migrations/versions/` directory. This avoids the "Table is already defined for this MetaData instance" class of bugs that comes from re-executing `models.py` from a plugin-owned `env.py` after the install hook has already imported the plugin module. See `zou/app/utils/plugins.py:_build_plugin_alembic_config` for the wiring.

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
from flask.views import MethodView
from flask_jwt_extended import jwt_required

class MyResource(MethodView):
    @jwt_required()
    def get(self):
        return {"data": "response"}

routes = [
    ("/endpoint", MyResource),
]
```

Routes are mounted at `/plugins/<plugin-id>/`.

## Database

Plugin tables are prefixed `plugin_<plugin_id>_` to avoid collisions. Each plugin has its own alembic version table named `alembic_version_<plugin_id>` so different plugins can advance independently.

Migrations use Alembic and are run via `run_plugin_migrations()`. The shared `env.py` (in `zou/app/utils/plugin_alembic_template/`) loads the plugin's `models.py` lazily — it skips re-execution if the plugin's tables are already in `db.metadata`, which is the normal case after `install_plugin` has already imported the plugin package to call its lifecycle hooks. The plugin path is passed in via `alembic_cfg.attributes["plugin_path"]` so the shared env.py knows which manifest to load.

To create a new revision after changing `models.py`:

```bash
zou migrate-plugin --path /path/to/my-plugin --message "Add foo column"
```

This calls `migrate_plugin_db()`, which uses the same shared template via `_build_plugin_alembic_config()` and writes the new revision file into `migrations/versions/`.

## Loading

Plugins are loaded at app startup in `zou/app/api.py` → `load_plugins(app)`. The loader:

1. Scans `PLUGIN_FOLDER` for subdirectories
2. Validates `manifest.toml` (semver version, SPDX license)
3. Imports the module and reads `routes`
4. Creates a Flask blueprint with prefix `/plugins/<id>`
5. Serves frontend static files from `frontend/dist/` when the plugin exposes a UI (see Frontend)
6. Logs errors without crashing the app

## Frontend

Static `/frontend` routes depend on how the plugin exposes UI:

- Iframe SPA (`frontend_project_enabled` or `frontend_studio_enabled`): `/plugins/<id>/frontend` (`index.html`) and `/plugins/<id>/frontend/<path>`
- Host-integration bundle only (`frontend/dist/plugin.js`, no iframe flags): `/plugins/<id>/frontend/<path>` alone, so Kitsu can load `plugin.js`

Previously only the iframe flags registered these routes.

`Plugin.present()` exposes **`injected`: true** when the host-integration
bundle (`frontend/dist/plugin.js`) is detected. Kitsu uses that field to load
the bundle into the host instead of falling back to the iframe. It is derived
from the filesystem (not stored in the database or the manifest), cached for
the process, and invalidated on `install-plugin` / uninstall (otherwise
restart after a manual copy of `plugin.js`).
