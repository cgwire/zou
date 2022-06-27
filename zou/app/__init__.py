import os
import flask_fs
import traceback

from flask import Flask, jsonify
from flask_restful import current_app
from flask_jwt_extended import JWTManager
from flask_principal import Principal, identity_changed, Identity
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_mail import Mail
from jwt import ExpiredSignatureError
from whoosh import index

from . import config
from .index_schema import asset_schema
from .stores import auth_tokens_store
from .services.exception import (
    ModelWithRelationsDeletionException,
    PersonNotFoundException,
    WrongIdFormatException,
    WrongParameterException,
)
from .utils import fs, logs

from zou.app.utils import cache


app = Flask(__name__)
app.config.from_object(config)

from flask_restplus import Api

flask_app = Api(app = app,
                version="1.0",
                title="Zou API",
                description="This is a test.")

#blueprint auth
name_space_auth = flask_app.namespace('auth', description='Authentification')

#blueprint assets
name_space_assets = flask_app.namespace('data/assets', description='Assets')
name_space_asset_types = flask_app.namespace('data/asset-types', description='Asset Types')

#blueprint breakdown
name_space_projects = flask_app.namespace('data/projects', description='Projects')
name_space_scenes = flask_app.namespace('data/scenes', description='Scenes')
name_space_shots = flask_app.namespace('data/shots', description='Shots')

#blueprint comments
name_space_tasks = flask_app.namespace('data/tasks', description='Tasks')
name_space_attachment_files = flask_app.namespace('data/attachment-files', description='Attachment Files')
name_space_actions_tasks = flask_app.namespace('actions/tasks', description='Actions Tasks')
name_space_actions_projects = flask_app.namespace('actions/projects', description='Actions Projects')

#blueprint crud
name_space_project_status = flask_app.namespace('data/project-status', description='Project Status')
name_space_entity_types = flask_app.namespace('data/entity-types', description='Entity Types')
name_space_entity_links = flask_app.namespace('data/entity-links', description='Entity Links')

name_space_task_types = flask_app.namespace('data/task-types', description='Task Types')
name_space_task_type_links = flask_app.namespace('data/task-type-links', description='Task Type Links')
name_space_task_status = flask_app.namespace('data/task-status', description='Task Status')
name_space_departments = flask_app.namespace('data/departments', description='Departments')
name_space_organisations = flask_app.namespace('data/organisations', description='Organisations')
name_space_softwares = flask_app.namespace('data/softwares', description='Softwares')
name_space_file_status = flask_app.namespace('data/file-status', description='File Status')
name_space_output_files = flask_app.namespace('data/output-files', description='Output Files')
name_space_output_types = flask_app.namespace('data/output-types', description='Output Types')
name_space_preview_files = flask_app.namespace('data/preview-files', description='Preview Files')
name_space_working_files = flask_app.namespace('data/working-files', description='Working Files')
name_space_comments = flask_app.namespace('data/comments', description='Comments')
name_space_time_spents = flask_app.namespace('data/time-spents', description='Time Spents')
name_space_day_offs = flask_app.namespace('data/day-offs', description='Day Offs')
name_space_custom_actions = flask_app.namespace('data/custom-actions', description='Custom actions')
name_space_status_automations = flask_app.namespace('data/status-automations', description='Status Automations')
name_space_playlists = flask_app.namespace('data/playlists', description='Playlists')
name_space_notifications = flask_app.namespace('data/notifications', description='Notifications')
name_space_news = flask_app.namespace('data/news', description='News')
name_space_milestones = flask_app.namespace('data/milestones', description='milestones')
name_space_search_filters = flask_app.namespace('data/search-filters', description='Search Filters')
name_space_schedule_items = flask_app.namespace('data/schedule-items', description='Schedule Items')
name_space_metadata_descriptors = flask_app.namespace('data/metadata-descriptors', description='Metadata Descriptors')
name_space_subscriptions = flask_app.namespace('data/subscriptions', description='Subscriptions')

#blueprint edits
name_space_edits = flask_app.namespace('data/edits', description='Edits')
name_space_episodes = flask_app.namespace('data/episodes', description='Episodes')

#blueprint entities
name_space_entities = flask_app.namespace('data/entities', description='Entities')

#blueprint events
name_space_events = flask_app.namespace('data/events', description='Events')

#blueprint export
name_space_export_csv = flask_app.namespace('export/csv', description='CSV')

#blueprint files
name_space_files = flask_app.namespace('data/files', description='Files')
name_space_entities_not_data = flask_app.namespace('entities', description='Entities')
name_space_asset_instances = flask_app.namespace('data/asset-instances', description='Asset Instances')
name_space_actions_working_files = flask_app.namespace('actions/working-files', description='Actions Working Files')
name_space_output_type = flask_app.namespace('<output_type_id>/output-files', description='Output Types')

#blueprint index
name_space_index = flask_app.namespace('', description='Index')
name_space_status = flask_app.namespace('status', description='Status')
name_space_stats = flask_app.namespace('stats', description='Stats')
name_space_status_txt = flask_app.namespace('status.txt', description='Status')
name_space_config = flask_app.namespace('config', description='Config')

#blueprint persons
name_space_persons = flask_app.namespace('data/persons', description='Persons')
name_space_actions_persons = flask_app.namespace('actions/persons', description='Actions Persons')

#blueprint playlists 
name_space_playlists = flask_app.namespace('data/playlists', description='Playlists')

#blueprint previews
name_space_pictures = flask_app.namespace('pictures', description='Pictures')
name_space_movies = flask_app.namespace('movies', description='Movies')
name_space_actions_entities = flask_app.namespace('actions/entities', description='Actions Entities')
name_space_actions_preview_files = flask_app.namespace('actions/preview-files', description='Preview Files')


#blueprint search
name_space_search = flask_app.namespace('data/search', description='Search')

#blueprint shots
name_space_sequences = flask_app.namespace('data/sequences', description='Sequences')

#blueprint source
name_space_shotgun = flask_app.namespace('import/shotgun', description='Import Shotgun')
name_space_import_csv = flask_app.namespace('import/csv', description='Import CSV')
name_space_kitsu = flask_app.namespace('import/kitsu', description='Import Kitsu')

#blueprint user
name_space_user = flask_app.namespace('data/user', description='User')
name_space_actions_user = flask_app.namespace('actions/user', description='Actions User')
name_space_preview_file_id = flask_app.namespace('', description="Preview File ID")


logs.configure_logs(app)

if not app.config["FILE_TREE_FOLDER"]:
    # Default file_trees are included in Python package: use root_path
    app.config["FILE_TREE_FOLDER"] = os.path.join(app.root_path, "file_trees")

if not app.config["PREVIEW_FOLDER"]:
    app.config["PREVIEW_FOLDER"] = os.path.join(app.instance_path, "previews")

if not app.config["INDEXES_FOLDER"]:
    app.config["INDEXES_FOLDER"] = os.path.join(app.instance_path, "indexes")

index_path = os.path.join(app.config["INDEXES_FOLDER"], "assets")
if not os.path.exists(index_path):
    fs.mkdir_p(index_path)
    index.create_in(index_path, asset_schema)

db = SQLAlchemy(app)
migrate = Migrate(app, db)  # DB schema migration features

app.secret_key = app.config["SECRET_KEY"]
jwt = JWTManager(app)  # JWT auth tokens
Principal(app)  # Permissions
cache.cache.init_app(app)  # Function caching
flask_fs.init_app(app)  # To save files in object storage
mail = Mail()
mail.init_app(app)  # To send emails


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

    @jwt.token_in_blacklist_loader
    def check_if_token_is_revoked(decrypted_token):
        return auth_tokens_store.is_revoked(decrypted_token)

    @jwt.user_loader_callback_loader
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
