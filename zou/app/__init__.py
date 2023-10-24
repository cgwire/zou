import traceback

from flask import Flask, jsonify, current_app
from flasgger import Swagger
from flask_jwt_extended import JWTManager
from flask_principal import Principal, identity_changed, Identity
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_mail import Mail

from jwt import ExpiredSignatureError
from babel.core import UnknownLocaleError
from meilisearch.errors import (
    MeilisearchApiError,
    MeilisearchCommunicationError,
)

from zou.app import config, swagger
from zou.app.stores import auth_tokens_store, file_store
from zou.app.services.exception import (
    ModelWithRelationsDeletionException,
    PersonNotFoundException,
    WrongIdFormatException,
    WrongParameterException,
    WrongTaskTypeForEntityException,
)

from zou.app.utils import cache, fs, logs, monitoring
from zou.app.utils.flask import ParsedUserAgent, ORJSONProvider

app = Flask(__name__)
app.json = ORJSONProvider(app)
app.request_class.user_agent_class = ParsedUserAgent
app.config.from_object(config)

monitoring.init_monitoring(app)

if config.LOGS_MODE == "ovh":
    logs.configure_logs_ovh(app)

db = SQLAlchemy(app)
migrate = Migrate(app, db)  # DB schema migration features
app.extensions["sqlalchemy"].db = db

app.secret_key = app.config["SECRET_KEY"]
jwt = JWTManager(app)  # JWT auth tokens
Principal(app)  # Permissions
cache.cache.init_app(app)  # Function caching
mail = Mail()
mail.init_app(app)  # To send emails
swagger = Swagger(
    app, template=swagger.swagger_template, config=swagger.swagger_config
)


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


@app.errorhandler(MeilisearchCommunicationError)
def indexer_not_reachable(error):
    current_app.logger.error("Indexer not reachable")
    return jsonify(error=True, message="Indexer not reachable"), 500


@app.errorhandler(MeilisearchApiError)
def indexer_key_error(error):
    if error.code == "invalid_api_key":
        current_app.logger.error("The indexer key is rejected")
        return jsonify(error=True, message="The indexer key is rejected"), 500
    else:
        raise error


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


def load_api(app):
    from zou.app import api

    api.configure(app)

    fs.mkdir_p(app.config["TMP_DIR"])
    configure_auth()


file_store.configure_storages(app)
load_api(app)
