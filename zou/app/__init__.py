import traceback
import uuid

from flask import Flask, jsonify, current_app, request
from flasgger import Swagger
from flask_cors import CORS
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

from werkzeug.exceptions import HTTPException
from jwt import ExpiredSignatureError
from babel.core import UnknownLocaleError
from meilisearch.errors import (
    MeilisearchApiError,
    MeilisearchCommunicationError,
)

from zou.app import config
from zou.app import swagger as swagger_module
from zou.app.swagger import configure_openapi_route
from zou.app.stores import auth_tokens_store, config_store, file_store
from zou.app.indexer import indexing
from zou.app.services.exception import (
    ModelWithRelationsDeletionException,
    PersonNotFoundException,
    PreviewProcessingFailedException,
    TwoFactorAuthenticationRequiredException,
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
from zou.app.utils.oidc import oidc_client_for
from zou.app.utils.fido import get_fido_server

# Extensions are created unbound and attached to an app in create_app().
# Models are declared against `db.Model`, which is available without an
# app, so importing this module no longer needs a fully wired app.
db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
mail = Mail()
swagger = None
# The module-level `app` is NOT created at import time: it is built
# lazily by __getattr__ (bottom of this module) on first access, so
# importing zou.app or any submodule stays side-effect free. Entry
# points (wsgi, debug, event_stream, tests) either access `zou.app.app`
# or call create_app() explicitly.


def shutdown_session(exception=None):
    """
    Clean up database session when application context is torn down.
    This ensures connections are properly returned to the pool.

    Flask-SQLAlchemy automatically commits on successful requests and rolls back
    on exceptions, but we ensure proper cleanup here to prevent connection
    leaks.
    """
    try:
        if exception is not None and db.session.is_active:
            db.session.rollback()
    except Exception:
        pass
    finally:
        db.session.remove()


def set_security_headers(response):
    """
    Add baseline security headers to every response. nosniff stops the
    browser from MIME-sniffing a response into an executable type, e.g.
    rendering an uploaded file served as octet-stream as HTML. The
    frame headers block cross-origin embedding (clickjacking) while
    keeping same-origin embedding allowed, since Kitsu and Zou share
    the same origin in the standard deployment.
    """
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault(
        "Content-Security-Policy", "frame-ancestors 'self'"
    )
    response.headers.setdefault(
        "Referrer-Policy", "strict-origin-when-cross-origin"
    )
    return response


def page_not_found(error):
    return jsonify(error=True, message=str(error)), 404


def http_error(error):
    """
    Return HTTP errors raised by resources (abort calls) as JSON instead
    of the default werkzeug HTML page, as flask_restful used to do.
    """
    if error.response is not None:
        return error.response
    return jsonify(error=True, message=error.description), error.code


def id_parameter_format_error(error):
    return (
        jsonify(
            error=True,
            message="One of the ID sent in parameter is not properly formatted.",
        ),
        400,
    )


def wrong_parameter(error):
    return jsonify(error=True, message=str(error), data=error.dict), 400


def preview_processing_failed(error):
    return jsonify(error=True, message=str(error), data=error.dict), 500


def wrong_token_signature(error):
    return jsonify(error=True, message=str(error)), 401


def try_delete_model_with_relations(error):
    return jsonify(error=True, message=str(error)), 400


def wrong_task_type_for_entity(error):
    return jsonify(error=True, message=str(error)), 400


def wrong_locale_label(error):
    return jsonify(error=True, message=str(error)), 400


def indexer_not_reachable(error):
    current_app.logger.error("Indexer not reachable")
    return jsonify(error=True, message="Indexer not reachable"), 500


def indexer_key_error(error):
    if error.code == "invalid_api_key":
        current_app.logger.error("The indexer key is rejected")
        return jsonify(error=True, message="The indexer key is rejected"), 500
    else:
        raise error


def two_factor_auth_required(error):
    return (
        jsonify(
            error=True,
            two_factor_authentication_required=True,
            message="Two-factor authentication setup is required. "
            "Please configure 2FA before accessing the API.",
        ),
        403,
    )


def server_error(error):
    # HTTPExceptions (404, 405, ...) carry their own status code; let
    # Flask render them normally instead of masking every one as a 500.
    if isinstance(error, HTTPException):
        return error
    stacktrace = traceback.format_exc()
    current_app.logger.error(
        f"Unhandled error on {request.method} {request.path}\n{stacktrace}"
    )
    if config.DEBUG:
        return (
            jsonify(error=True, message=str(error), stacktrace=stacktrace),
            500,
        )
    # No exception details for the client in production: the message can
    # embed internals (SQL, paths); everything is in the logs above.
    return jsonify(error=True, message="Internal server error."), 500


def register_error_handlers(app):
    """
    Register the request lifecycle hooks and the JSON error handlers on
    the given app.
    """
    app.teardown_appcontext(shutdown_session)
    app.after_request(set_security_headers)
    app.register_error_handler(404, page_not_found)
    app.register_error_handler(HTTPException, http_error)
    app.register_error_handler(
        WrongIdFormatException, id_parameter_format_error
    )
    app.register_error_handler(WrongParameterException, wrong_parameter)
    app.register_error_handler(
        PreviewProcessingFailedException, preview_processing_failed
    )
    app.register_error_handler(ExpiredSignatureError, wrong_token_signature)
    app.register_error_handler(
        ModelWithRelationsDeletionException, try_delete_model_with_relations
    )
    app.register_error_handler(
        WrongTaskTypeForEntityException, wrong_task_type_for_entity
    )
    app.register_error_handler(UnknownLocaleError, wrong_locale_label)
    app.register_error_handler(
        MeilisearchCommunicationError, indexer_not_reachable
    )
    app.register_error_handler(MeilisearchApiError, indexer_key_error)
    app.register_error_handler(
        TwoFactorAuthenticationRequiredException, two_factor_auth_required
    )
    app.register_error_handler(Exception, server_error)


def configure_auth(app):
    from zou.app.services import persons_service
    from zou.app.services.auth_service import logout

    def check_active_identity(identity, identity_type, jti, refresh_jti=None):
        if not identity.active:
            if identity_type == "person":
                logout(jti=jti, refresh_jti=refresh_jti)
            current_app.logger.error(
                f"Identity {identity.id} is not active anymore"
            )
            raise UnactiveUserException

    @jwt.token_in_blocklist_loader
    def check_if_token_is_revoked(_, payload):
        jti = payload.get("jti")
        if jti is None:
            return True
        identity_type = payload.get("identity_type")
        if identity_type == "person":
            return auth_tokens_store.is_revoked(jti)
        elif identity_type in ["bot", "person_api"]:
            return persons_service.is_jti_revoked(jti)
        else:
            return True

    @jwt.user_lookup_loader
    def user_lookup_callback(_, payload):
        identity_type = payload.get("identity_type")
        try:
            identity = persons_service.get_person_raw_cached(payload["sub"])
        except PersonNotFoundException:
            return wrong_auth_handler()
        check_active_identity(
            identity,
            identity_type,
            jti=payload["jti"],
            refresh_jti=payload.get("refresh_jti"),
        )

        if payload.get("requires_2fa_setup"):
            allowed_paths = {
                "/auth/totp",
                "/auth/email-otp",
                "/auth/fido",
                "/auth/recovery-codes",
                "/auth/login",
                "/auth/logout",
                "/auth/authenticated",
                "/auth/refresh-token",
            }
            if request.path not in allowed_paths:
                raise TwoFactorAuthenticationRequiredException()

        identity_changed.send(
            current_app._get_current_object(),
            identity=Identity(identity.id, identity_type),
        )
        return identity

    @identity_loaded.connect_via(app)
    def on_identity_loaded(_, identity):
        try:
            if isinstance(identity.id, (str, uuid.UUID)):
                identity.user = persons_service.get_person_raw_cached(
                    identity.id
                )

                if hasattr(identity.user, "id"):
                    identity.provides.add(UserNeed(identity.user.id))

                if identity.user.role == "admin":
                    identity.provides.add(RoleNeed("admin"))
                    identity.provides.add(RoleNeed("manager"))

                elif identity.user.role == "manager":
                    identity.provides.add(RoleNeed("manager"))

                elif identity.user.role == "supervisor":
                    identity.provides.add(RoleNeed("supervisor"))

                elif identity.user.role == "client":
                    identity.provides.add(RoleNeed("client"))

                elif identity.user.role == "vendor":
                    identity.provides.add(RoleNeed("vendor"))

                identity.provides.add(RoleNeed(identity.auth_type))

            return identity

        except (PersonNotFoundException, UnactiveUserException):
            return wrong_auth_handler()
        except TimeoutError:
            current_app.logger.error("Identity loading timed out")
            return wrong_auth_handler()
        except Exception as e:
            current_app.logger.error(e, exc_info=1)
            return wrong_auth_handler()


def load_api(app):
    from zou.app import api

    api.configure(app)

    fs.mkdir_p(app.config["TMP_DIR"])
    configure_auth(app)


def create_app(config_object=config):
    """
    Build and wire a Zou Flask application: extensions, JSON provider,
    error handlers, auth, storages and API routes. Nothing is built at
    import time: entry points call this explicitly, and legacy
    `from zou.app import app` imports get the same instance lazily via
    the module __getattr__ below.

    Assigns the module-level `app` early (before the API is loaded)
    because blueprints and services imported during load_api still do
    `from zou.app import app` at import time.
    """
    global app, swagger

    app = Flask(__name__)
    app.json = ORJSONProvider(app)
    app.request_class.user_agent_class = ParsedUserAgent
    app.config.from_object(config_object)

    monitoring.init_monitoring(app)
    logs.configure_logs_ovh(app)

    db.init_app(app)
    migrate.init_app(app, db)
    app.extensions["sqlalchemy"].db = db

    app.secret_key = app.config["SECRET_KEY"]
    jwt.init_app(app)
    Principal(app)
    cache.cache.init_app(app)
    mail.init_app(app)
    swagger = Swagger(
        app,
        template=swagger_module.swagger_template,
        config=swagger_module.swagger_config,
    )
    configure_openapi_route(app, swagger)

    if config_object.CORS_ALLOWED_ORIGINS:
        CORS(
            app,
            resources={r"/*": {"origins": config_object.CORS_ALLOWED_ORIGINS}},
            supports_credentials=True,
        )

    if config_object.SAML_ENABLED:
        app.extensions["saml_client"] = saml_client_for(
            config_object.SAML_METADATA_URL
        )

    if config_object.OIDC_ENABLED:
        app.extensions["oidc_client"] = oidc_client_for(app)

    app.extensions["fido_server"] = get_fido_server()

    if config_object.INDEXER["key"] is not None:
        app.extensions["indexer_client"] = indexing.init_client()

    register_error_handlers(app)

    file_store.configure_storages(app)
    config_store.sync_config()
    load_api(app)

    return app


def __getattr__(name):
    """
    Build the default application on first access to `zou.app.app`
    (PEP 562). Keeps `from zou.app import app` and the gunicorn
    `zou.app:app` entry point working while making the boot lazy:
    importing zou.app or its submodules no longer wires the whole API.
    Once built, create_app() assigns the module global, so this hook
    only ever fires once per process.
    """
    if name == "app":
        return create_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
