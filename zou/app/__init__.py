import traceback
import uuid

from flask import Flask, jsonify, current_app
from flasgger import Swagger
from flask_jwt_extended import JWTManager
from flask_principal import (
    Principal,
    Identity,
    identity_changed,
    RoleNeed,
    UserNeed,
    identity_loaded,
)
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
    UnactiveUserException,
)

from zou.app.utils import cache, fs, logs, monitoring
from zou.app.utils.flask import (
    ParsedUserAgent,
    ORJSONProvider,
    wrong_auth_handler,
)

from zou.app.utils.saml import saml_client_for
from zou.app.utils.fido import get_fido_server

app = Flask(__name__)
app.json = ORJSONProvider(app)
app.request_class.user_agent_class = ParsedUserAgent
app.config.from_object(config)

monitoring.init_monitoring(app)

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

if config.SAML_ENABLED:
    app.extensions["saml_client"] = saml_client_for(config.SAML_METADATA_URL)

app.extensions["fido_server"] = get_fido_server()


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
    return jsonify(error=True, message=str(error), data=error.dict), 400


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
    from zou.app.services.auth_service import logout

    def check_active_identity(identity, identity_type, jti):
        if not identity.active:
            if identity_type == "person":
                logout(jti=jti)
            current_app.logger.error(
                f"Identity {identity.id} is not active anymore"
            )
            raise UnactiveUserException

    @jwt.token_in_blocklist_loader
    def check_if_token_is_revoked(_, payload):
        identity_type = payload.get("identity_type")
        if identity_type == "person":
            return auth_tokens_store.is_revoked(payload["jti"])
        elif identity_type in ["bot", "person_api"]:
            return persons_service.is_jti_revoked(payload["jti"])
        else:
            return True

    @jwt.user_lookup_loader
    def user_lookup_callback(_, payload):
        identity_type = payload.get("identity_type")
        try:
            identity = persons_service.get_person_raw(payload["sub"])
        except PersonNotFoundException:
            return wrong_auth_handler()
        check_active_identity(identity, identity_type, jti=payload["jti"])
        identity_changed.send(
            current_app._get_current_object(),
            identity=Identity(identity.id, identity_type),
        )
        return identity

    @identity_loaded.connect_via(app)
    def on_identity_loaded(_, identity):
        try:
            if isinstance(identity.id, (str, uuid.UUID)):
                identity.user = persons_service.get_person_raw(identity.id)

                if hasattr(identity.user, "id"):
                    identity.provides.add(UserNeed(identity.user.id))

                if identity.user.role == "admin":
                    identity.provides.add(RoleNeed("admin"))
                    identity.provides.add(RoleNeed("manager"))

                if identity.user.role == "manager":
                    identity.provides.add(RoleNeed("manager"))

                if identity.user.role == "supervisor":
                    identity.provides.add(RoleNeed("supervisor"))

                if identity.user.role == "client":
                    identity.provides.add(RoleNeed("client"))

                if identity.user.role == "vendor":
                    identity.provides.add(RoleNeed("vendor"))

                identity.provides.add(RoleNeed(identity.auth_type))

            return identity

        except Exception as e:
            if isinstance(e, TimeoutError):
                current_app.logger.error("Identity loading timed out")
            if isinstance(e, (PersonNotFoundException, UnactiveUserException)):
                pass
            else:
                current_app.logger.error(e, exc_info=1)
                if hasattr(e, "message"):
                    current_app.logger.error(e.message)
            return wrong_auth_handler()


def load_api(app):
    from zou.app import api

    api.configure(app)

    fs.mkdir_p(app.config["TMP_DIR"])
    configure_auth()


file_store.configure_storages(app)
load_api(app)
