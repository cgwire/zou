import importlib
import sys

from zou.app import config
from zou.app.utils.plugins import load_plugins
from zou.app.utils import events

# Blueprint packages of zou.app.blueprints to register, in registration
# order. Each package exposes a `blueprint` object.
BLUEPRINT_MODULES = [
    "auth",
    "assets",
    "breakdown",
    "chats",
    "comments",
    "crud",
    "departments",
    "entities",
    "export",
    "events",
    "files",
    "source",
    "index",
    "news",
    "persons",
    "playlists",
    "shared",
    "projects",
    "project_templates",
    "shots",
    "tasks",
    "previews",
    "user",
    "edits",
    "search",
    "concepts",
]


def configure(app):
    """
    Turn Flask app into a REST API. It configures routes, auth and events
    system.
    """
    app.url_map.strict_slashes = False
    configure_api_routes(app)
    register_event_handlers(app)
    load_plugins(app)
    return app


def configure_api_routes(app):
    """
    Register blueprints (modules). Each blueprint describe routes and
    associated resources (controllers).
    """
    for module_name in BLUEPRINT_MODULES:
        module = importlib.import_module(f"zou.app.blueprints.{module_name}")
        app.register_blueprint(module.blueprint)

    if config.ADMIN_TOKEN:
        from zou.app.blueprints.admin import blueprint as admin_blueprint

        app.register_blueprint(admin_blueprint)

    return app


def register_event_handlers(app):
    """
    Load code from event handlers folder. Then it registers in the event manager
    each event handler listed in the __init_.py.
    """
    sys.path.insert(0, app.config["EVENT_HANDLERS_FOLDER"])
    try:
        import event_handlers
    except ModuleNotFoundError as exception:
        # Handlers are optional: having no event handlers folder is fine,
        # but a broken import inside the handlers themselves is not and
        # must not be swallowed.
        if exception.name != "event_handlers":
            raise
        return app
    events.register_all(event_handlers.event_map, app)
    return app
