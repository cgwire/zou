import os
import flask_fs
import traceback
import json

from flask import Flask, current_app
from flasgger import Swagger
from flask_jwt_extended import JWTManager
from flask_principal import Principal, identity_changed, Identity
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_mail import Mail
from babel.core import UnknownLocaleError
from werkzeug.exceptions import HTTPException

from . import config, swagger
from .stores import auth_tokens_store
from .services.exception import (
    PersonNotFoundException,
)
from .utils import fs, logs

from zou.app.utils import cache
from zou.app.utils.sentry import init_sentry
from zou.app.utils.user_agent import ParsedUserAgent

init_sentry()
app = Flask(__name__)
app.request_class.user_agent_class = ParsedUserAgent
app.config.from_object(config)

logs.configure_logs(app)

if not app.config["FILE_TREE_FOLDER"]:
    # Default file_trees are included in Python package: use root_path
    app.config["FILE_TREE_FOLDER"] = os.path.join(app.root_path, "file_trees")

db = SQLAlchemy(app)
migrate = Migrate(app, db)  # DB schema migration features

app.secret_key = app.config["SECRET_KEY"]
jwt = JWTManager(app)  # JWT auth tokens
Principal(app)  # Permissions
cache.cache.init_app(app)  # Function caching
flask_fs.init_app(app)  # To save files in object storage
mail = Mail()
mail.init_app(app)  # To send emails
swagger = Swagger(
    app, template=swagger.swagger_template, config=swagger.swagger_config
)


if config.SENTRY_DEBUG_URL:

    @app.route(config.SENTRY_DEBUG_URL)
    def trigger_error():
        division_by_zero = 1 / 0


@app.teardown_appcontext
def shutdown_session(exception=None):
    db.session.remove()


@app.errorhandler(Exception)
def handle_http_exception(e):
    """Return JSON instead of HTML for exceptions."""
    if isinstance(e, HTTPException):
        response = e.get_response()
        # replace the body with JSON
        response.data = json.dumps(
            {
                "error": True,
                "code": e.code,
                "name": e.name,
                "description": e.description,
            }
        )
        response.content_type = "application/json"
    else:
        status_code = 500
        if isinstance(e, UnknownLocaleError):
            status_code = 400
        response_data = {
            "error": True,
            "code": status_code,
            "name": e.__class__.__name__,
            "description": str(e),
        }
        response = response_data, status_code
    stacktrace = traceback.format_exc()
    if not config.DEBUG:
        current_app.logger.error(stacktrace)
    else:
        current_app.logger.info(stacktrace)
    return response


def configure_auth():
    from zou.app.services import persons_service

    @jwt.token_in_blocklist_loader
    def check_if_token_is_revoked(_, payload):
        return auth_tokens_store.is_revoked(payload)

    @jwt.user_lookup_loader
    def add_permissions(_, payload):
        try:
            user = persons_service.get_person(payload["user_id"])
            if user is not None:
                identity_changed.send(
                    current_app._get_current_object(),
                    identity=Identity(user["id"]),
                )
            return user
        except PersonNotFoundException:
            return None


def load_api():
    from . import api

    api.configure(app)

    fs.mkdir_p(app.config["TMP_DIR"])
    configure_auth()


load_api()
