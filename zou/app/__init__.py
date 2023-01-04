import os
import flask_fs
import traceback

from flask import Flask, jsonify
from flasgger import Swagger
from flask_restful import current_app
from flask_jwt_extended import JWTManager
from flask_principal import Principal, identity_changed, Identity
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_mail import Mail
from jwt import ExpiredSignatureError
from babel.core import UnknownLocaleError

from . import config, swagger
from .stores import auth_tokens_store
from .services.exception import (
    ModelWithRelationsDeletionException,
    PersonNotFoundException,
    WrongIdFormatException,
    WrongParameterException,
    WrongTaskTypeForEntityException,
)
from .utils import fs, logs

from zou.app.utils import cache
from zou.app.utils.sentry import init_sentry

init_sentry()
app = Flask(__name__)
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


@app.errorhandler(404)
def page_not_found(error):
    return jsonify(error=True, message=str(error)), 404


@app.errorhandler(WrongIdFormatException)
def id_parameter_format_error(error):
    return (
        jsonify(
            error=True,
            message="One of the ID sent in parameter is not properly formatted.",
        ),
        400,
    )


@app.errorhandler(WrongParameterException)
def wrong_parameter(error):
    return jsonify(error=True, message=str(error)), 400


@app.errorhandler(ExpiredSignatureError)
def wrong_token_signature(error):
    return jsonify(error=True, message=str(error)), 401


@app.errorhandler(ModelWithRelationsDeletionException)
def try_delete_model_with_relations(error):
    return jsonify(error=True, message=str(error)), 400


@app.errorhandler(WrongTaskTypeForEntityException)
def wrong_task_type_for_entity(error):
    return jsonify(error=True, message=str(error)), 400


@app.errorhandler(UnknownLocaleError)
def wrong_locale_label(error):
    return jsonify(error=True, message=str(error)), 400


if not config.DEBUG:

    @app.errorhandler(Exception)
    def server_error(error):
        stacktrace = traceback.format_exc()
        current_app.logger.error(stacktrace)
        return (
            jsonify(error=True, message=str(error), stacktrace=stacktrace),
            500,
        )


def configure_auth():
    from zou.app.services import persons_service

    @jwt.token_in_blocklist_loader
    def check_if_token_is_revoked(decrypted_token):
        return auth_tokens_store.is_revoked(decrypted_token)

    @jwt.user_lookup_loader
    def add_permissions(callback):
        try:
            user = persons_service.get_current_user()
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
