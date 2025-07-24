import sys

from zou.app.blueprints.assets import blueprint as assets_blueprint
from zou.app.blueprints.auth import blueprint as auth_blueprint
from zou.app.blueprints.breakdown import blueprint as breakdown_blueprint
from zou.app.blueprints.chats import blueprint as chats_blueprint
from zou.app.blueprints.comments import blueprint as comments_blueprint
from zou.app.blueprints.crud import blueprint as crud_blueprint
from zou.app.blueprints.departments import blueprint as departments_blueprint
from zou.app.blueprints.entities import blueprint as entities_blueprint
from zou.app.blueprints.events import blueprint as events_blueprint
from zou.app.blueprints.export import blueprint as export_blueprint
from zou.app.blueprints.files import blueprint as files_blueprint
from zou.app.blueprints.index import blueprint as index_blueprint
from zou.app.blueprints.search import blueprint as search_blueprint
from zou.app.blueprints.news import blueprint as news_blueprint
from zou.app.blueprints.persons import blueprint as persons_blueprint
from zou.app.blueprints.playlists import blueprint as playlists_blueprint
from zou.app.blueprints.projects import blueprint as projects_blueprint
from zou.app.blueprints.previews import blueprint as previews_blueprint
from zou.app.blueprints.source import blueprint as import_blueprint
from zou.app.blueprints.shots import blueprint as shots_blueprint
from zou.app.blueprints.tasks import blueprint as tasks_blueprint
from zou.app.blueprints.user import blueprint as user_blueprint
from zou.app.blueprints.edits import blueprint as edits_blueprint
from zou.app.blueprints.concepts import blueprint as concepts_blueprint

from zou.app.utils.plugins import load_plugins
from zou.app.utils import events


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
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(assets_blueprint)
    app.register_blueprint(breakdown_blueprint)
    app.register_blueprint(chats_blueprint)
    app.register_blueprint(comments_blueprint)
    app.register_blueprint(crud_blueprint)
    app.register_blueprint(departments_blueprint)
    app.register_blueprint(entities_blueprint)
    app.register_blueprint(export_blueprint)
    app.register_blueprint(events_blueprint)
    app.register_blueprint(files_blueprint)
    app.register_blueprint(import_blueprint)
    app.register_blueprint(index_blueprint)
    app.register_blueprint(news_blueprint)
    app.register_blueprint(persons_blueprint)
    app.register_blueprint(playlists_blueprint)
    app.register_blueprint(projects_blueprint)
    app.register_blueprint(shots_blueprint)
    app.register_blueprint(tasks_blueprint)
    app.register_blueprint(previews_blueprint)
    app.register_blueprint(user_blueprint)
    app.register_blueprint(edits_blueprint)
    app.register_blueprint(search_blueprint)
    app.register_blueprint(concepts_blueprint)
    return app


def register_event_handlers(app):
    """
    Load code from event handlers folder. Then it registers in the event manager
    each event handler listed in the __init_.py.
    """
    sys.path.insert(0, app.config["EVENT_HANDLERS_FOLDER"])
    try:
        import event_handlers

        events.register_all(event_handlers.event_map, app)
    except ImportError:
        # Event handlers folder is not properly configured.
        # Handlers are optional, that's why this error is ignored.
        # app.logger.info("No event handlers folder is configured.")
        pass
    return app
