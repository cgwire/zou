# Plugins

The Kitsu API (Zou) plugin system allows you to create extensions of the API.
Each plugin includes a `manifest.toml` file to describe plugin and manage its
versioning. Each plugin can add routes to the API and add tables to the database.

---

## Quickstart

Create your plugin:

```bash
python zou/cli.py create-plugin-skeleton --path ./plugin_name --id plugin-name
```

Install it:

```
python zou/cli.py install-plugin --path ./plugin-name
```

Then restart your Zou server.

All added routes will live under the path `plugins/plugin-name`.


## Plugin structure

Plugins are structured this way:

```
my_plugin/
├── __init__.py
├── manifest.toml
├── models.py
├── resources.py
├── logo.png
├── migrations/
│   ├── env.py
│   ├── versions/
│   ├── /
/
```

---

### `__init__.py`

List the routes you are adding via the plugin.

### `resources.py`

Describe resources tied to routes here.

### `models.py`

Add some new models in this python file. Generate related migration files:

```
zou migrate-plugin-db --path ./plugins/my-plugin
```

### `manifest.toml`

A manifest file is required to describe how to deploy your plugin and inform
other users about how it can be used.
It contains the plugin metadata:

```toml
id = "my_plugin"
name = "My Plugin"
version = "0.1.0"
description = "My plugin description."
maintainer = "Author <author@example.com>"
website = "mywebsite.com"
license = "GPL-3.0-only"
```

---

## Best practices

* Use unique plugin IDs.
* Follow semantic versioning (`x.y.z`).
* Include at least one route or feature inside your plugin module.
* Write migrations if your plugin defines database models.
* For license use SPDX identifier (see [here](https://spdx.org/licenses/)).

---

## Full process

Follow this simple workflow to start with writing your own plugin.


1. Create your plugin:

    ```
    zou create-plugin-skeleton --path ./plugins --id my-plugin
    ```

3. Implement routes in the `resource.py` file.

3. Add routes to the `__init__.py` file.

4. Implement models (if needed) in the `models.py` file.

5. Add some informations about your plugin in the `manifest.toml` file.

6. Generate database migrations (if needed):

    ```
    zou migrate-plugin-db --path ./plugins/my-plugin
    ```

7. Package it:

    ```
    zou create-plugin-package --path ./plugins/my-plugin --output-path ./dist
    ```

8. Install it:

    ```
    zou install-plugin --path ./dist/my-plugin.zip
    ```

9. List installed plugins:

    ```
    zou list-plugins
    ```

10. Uninstall if needed:

    ```
    zou uninstall-plugin --id my-plugin
    ```

---


## CLI Commands

### `install_plugin`

Install a plugin from a local folder or `.zip` package.

```bash
zou install-plugin --path /path/to/plugin
```

**Options:**

* `--path`: Path to the plugin folder or `.zip` archive (required).
* `--force`: Overwrite if already installed (default: `False`).

**Note:** You need to restart the Zou server after installing a plugin.

---

### `uninstall_plugin`

Uninstall a previously installed plugin.

```bash
zou uninstall-plugin --id my_plugin
```

**Options:**

* `--id`: Plugin ID to uninstall (required).

**Note:** This removes plugin files and unregisters its migrations.
It will remove all your data

---

### `create_plugin_skeleton`

Generate the basic structure of a plugin. It will allow to start quickly your
plugin development.

```bash
zou create-plugin-skeleton --path ./plugins --id my_plugin
```

**Options:**

* `--path`: Directory where the plugin will be created (required).
* `--id`: Unique plugin ID (required).
* `--name`: Human-readable plugin name (default: `"MyPlugin"`).
* `--description`: Short description (default: `"My plugin description."`).
* `--version`: Semantic version string (default: `"0.1.0"`).
* `--maintainer`: Contact info (default: `"Author <author@author.com>"`).
* `--website`: Plugin/project website (default: `"mywebsite.com"`).
* `--license`: License (default: `"GPL-3.0-only"`).
* `--force`: Overwrite if directory exists (default: `False`).

This command generates:

* `manifest.toml` with plugin metadata
* Initial folder structure for code, migrations, etc.

---

### `create_plugin_package`

Package a plugin folder into a zip file, ready for installation.

```bash
zou create-plugin-package --path ./plugins/my_plugin --output-path ./dist
```

**Options:**

* `--path`: Plugin source folder (required).
* `--output-path`: Destination folder for the `.zip` (required).
* `--force`: Overwrite existing archive if present (default: `False`).

---

### `list_plugins`

List all currently installed plugins.

```bash
zou list-plugins
```

**Options:**

* `--format`: `table` or `json` (default: `table`).
* `--verbose`: Show more metadata.
* `--filter-field`: Filter by a specific field (`plugin_id`, `name`, `maintainer`, `license`).
* `--filter-value`: Value to search in the selected field.

---

### `migrate_plugin_db`

Run database migrations for a plugin.

```bash
zou migrate-plugin-db --path ./plugins/my_plugin
```

**Options:**

* `--path`: Path to the plugin folder (required).
* `--message`: Optional migration message (default: `""`).

This generates and applies Alembic migration scripts for the plugin’s database schema.
