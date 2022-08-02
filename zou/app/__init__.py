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

from . import config
from .stores import auth_tokens_store
from .index_schema import init_indexes
from .services.exception import (
    ModelWithRelationsDeletionException,
    PersonNotFoundException,
    WrongIdFormatException,
    WrongParameterException,
)
from .utils import fs, logs

from zou.app.utils import cache
from zou import __version__


app = Flask(__name__)
app.config.from_object(config)

swagger_template = {
  "swagger": "2.0",
  "info": {
    "title": "Kitsu API",
    "description": f"## Welcome to Zou (Kitsu API) documentation \n```Version: {__version__}``` \n\nZou is an API that allows to store and manage the data of your CG production. Through it you can link all the tools of your pipeline and make sure they are all synchronized.\n\n To integrate it in your tools you can rely on the dedicated Python client named [Gazu](https://gazu.cg-wire.com/).\n\nThe source is available on [Github](https://github.com/cgwire/zou).\n\n## Who is it for?\n\nThe audience for Zou is made of Technical Directors, ITs and Software Engineers from CG studios. With Zou they can enhance the tools they provide to all departments.\n\nOn top of it, you can deploy Kitsu, the production tracker developed by CGWire.\n\n## Features\n\nZou can:\n\n* Store production data: projects, shots, assets, tasks, files metadata and validations.\n* Provide folder and file paths for any task.\n* Data import from Shotgun or CSV files.\n* Export main data to CSV files.\n* Provide helpers to manage task workflow (start, publish, retake).\n* Provide an event system to plug external modules on it.\n\n",
    "contact": {
      "name": "CGWire",
      "email": "support@cg-wire.com",
      "url": "https://www.cg-wire.com"
    },
    "termsOfService": "https://www.cg-wire.com/terms.html",
    "version": __version__,
    "license": {
        "name": "AGPL 3.0",
        "url": "https://www.gnu.org/licenses/agpl-3.0.en.html"
    },
  },
  "host": "localhost:8080",
  "basePath": "/api",
  "schemes": [
    "http",
    "https"
  ],
  "tags": [
    { "name": "Authentification" },
    { "name": "Assets" },
    { "name": "Breakdown" },
    { "name": "Comments" },
    { "name": "Crud" },
    { "name": "Edits" },
    { "name": "Entities" },
    { "name": "Events" },
    { "name": "Export" },
    { "name": "Files" },
    { "name": "Index" },
    { "name": "News" },
    { "name": "Persons" },
    { "name": "Playlists" },
    { "name": "Previews" },
    { "name": "Projects" },
    { "name": "Search" },
    { "name": "Shots" },
    { "name": "Source" },
    { "name": "Tasks" },
    { "name": "User" }
  ],
    "definitions": {
      "Assets": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string",
            "description": "Name of asset"
          },
          "code": {
            "type": "string",
            "description": "Utility field for the pipeline to identify the asset"
          },
          "description": {
            "type": "string",
            "description": "Asset brief"
          },
          "canceled": {
            "type": "boolean",
            "default": "False",
            "description": "True if the asset has been delete one time, False otherwise"
          },
          "project_id": {
            "type": "string",
            "format": "UUID",
            "description": "Project ID"
          },
          "entity_type_id": {
            "type": "string",
            "format": "UUID",
            "description": "Asset type ID"
          },
          "source_id": {
            "type": "string",
            "format": "UUID",
            "description": "Field uset to set the episode_id"
          },
          "preview_file_id": {
            "type": "string",
            "format": "UUID",
            "description": "ID of preview file used as thumbnail"
          },
          "data": {
            "type": "string",
            "format": "json",
            "description": "Free JSON field to add metadata"
          },
          "shotgun_id": {
            "type": "integer",
            "description": "Used for synchronization with a Shotgun instance"
          }
        }
      },
      "Asset instances": {
        "type": "object",
        "properties": {
          "asset_id": {
            "type": "string",
            "format": "UUID",
            "description": "Instantiated asset"
          },
          "name": {
            "type": "string"
          },
          "number": {
            "type": "integer"
          },
          "description": {
            "type": "string"
          },
          "active": {
            "type": "boolean",
            "default": "True"
          },
          "data": {
            "type": "string",
            "format": "json",
            "description": "Free JSON field to add metadata"
          },
          "scene_id": {
            "type": "string",
            "format": "UUID",
            "description": "Target scene"
          },
          "target_asset_id": {
            "type": "string",
            "format": "UUID",
            "description": "Use when instantiating an asset in an asset is required"
          }
        }
      },
      "Asset types": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string"
          }
        }
      },
      "Comments": {
        "type": "object",
        "properties": {
          "shotgun_id": {
            "type": "integer",
            "description": "Used for synchronization with a Shotgun instance"
          },
          "object_id": {
            "type": "string",
            "format": "UUID",
            "description": "Unique ID of the commented model instance"
          },
          "object_type": {
            "type": "string",
            "description": "Model type of the comment model instance"
          },
          "text": {
            "type": "string"
          },
          "data": {
            "type": "string",
            "format": "json",
            "description": "Free JSON field to add metadata"
          },
          "replies": {
            "type": "string",
            "format": "json",
            "default": "[]"
          },
          "checklist": {
            "type": "string",
            "format": "json"
          },
          "pinned": {
            "type": "boolean"
          },
          "task_status_id": {
            "type": "string",
            "format": "UUID",
            "description": "Task status attached to comment"
          },
          "person_id": {
            "type": "string",
            "format": "UUID",
            "description": "The person who publishes the comment"
          },
          "preview_file_id": {
            "type": "string",
            "format": "UUID",
            "description": "ID of preview file used as thumbnail"
          }
        }
      },
      "Episodes": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string",
            "description": "Name of episode"
          },
          "code": {
            "type": "string",
            "description": "Utility field for the pipeline to identify the episode"
          },
          "description": {
            "type": "string",
            "description": "Episode brief"
          },
          "canceled": {
            "type": "boolean",
            "default": "False",
            "description": "True if the episode has been delete one time, False otherwise"
          },
          "project_id": {
            "type": "string",
            "format": "UUID",
            "description": "Project ID"
          },
          "source_id": {
            "type": "string",
            "format": "UUID",
            "description": "Field uset to set the episode_id"
          },
          "preview_file_id": {
            "type": "string",
            "format": "UUID",
            "description": "ID of preview file used as thumbnail"
          },
          "data": {
            "type": "string",
            "format": "json",
            "description": "Free JSON field to add metadata"
          },
          "shotgun_id": {
            "type": "integer",
            "description": "Used for synchronization with a Shotgun instance"
          }
        }
      },
      "Events": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string",
            "description": "Name of event"
          },
          "user_id": {
            "type": "string",
            "format": "UUID",
            "description": "The user who made the action that emitted the event"
          },
          "project_id": {
            "type": "string",
            "format": "UUID",
            "description": "Project ID"
          },
          "data": {
            "type": "string",
            "format": "json",
            "description": "Free JSON field to add metadata"
          }
        }
      },
      "File status": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string"
          },
          "color": {
            "type": "string"
          }
        }
      },
      "Metadata": {
        "type": "object",
        "properties": {
          "project_id": {
            "type": "string",
            "format": "UUID",
            "description": "ID of project for which metadata are added"
          },
          "entity_type": {
            "type": "string",
            "description": "Asset or Shot"
          },
          "name": {
            "type": "string",
            "description": "Field name for GUI"
          },
          "field_name": {
            "type": "string",
            "description": "Technical field name"
          },
          "choices": {
            "type": "string",
            "format": "json",
            "description": "Array of string that represents the available values for this metadate (this metatada is considered as a free field if this array is empty)"
          },
          "for_client": {
            "type": "boolean"
          }
        }
      },
      "Notifications": {
        "type": "object",
        "properties": {
          "read": {
            "type": "boolean",
            "description": "True if user read it, False otherwise"
          },
          "change": {
            "type": "boolean",
            "description": "True if there is status change related to this status, False otherwise"
          },
          "person_id": {
            "type": "string",
            "format": "UUID",
            "description": "The user to who the notification is aimed at"
          },
          "author_id": {
            "type": "string",
            "format": "UUID",
            "description": "Author of the event to notify"
          },
          "comment_id": {
            "type": "string",
            "format": "UUID",
            "description": "Comment related to the notification, if there is any"
          },
          "task_id": {
            "type": "string",
            "format": "UUID",
            "description": "Task related to the notification, if there is any"
          },
          "reply_id": {
            "type": "string",
            "format": "UUID",
            "description": "Reply related to notification"
          },
          "type": {
            "type": "string",
            "description": "Type of notification"
          }
        }
      },
      "Output files": {
        "type": "object",
        "properties": {
          "shotgun_id": {
            "type": "integer",
            "description": "Used for synchronization with a Shotgun instance"
          },
          "name": {
            "type": "string",
            "description": "Name of output file"
          },
          "extension": {
            "type": "string",
            "description": "Extension of output file"
          },
          "description": {
            "type": "string",
            "description": "Output file brief"
          },
          "comment": {
            "type": "string",
            "description": "Comment on output file"
          },
          "revision": {
            "type": "integer",
            "description": "Revision number of output file"
          },
          "size": {
            "type": "integer",
            "description": "Size of output file"
          },
          "checksum": {
            "type": "string",
            "description": "Checksum of output file"
          },
          "source": {
            "type": "string",
            "description": "Created by a script, a webgui or a desktop gui"
          },
          "path": {
            "type": "string",
            "description": "File path on the production hard drive"
          },
          "representation": {
            "type": "string",
            "description": "Precise what kind of output it is (abc, jpgs, pngs, etc.)"
          },
          "nb_elements": {
            "type": "integer",
            "default": "1",
            "description": "For image sequence"
          },
          "canceled": {
            "type": "boolean",
          },
          "file_status_id": {
            "type": "string",
            "format": "UUID",
            "description": "File status ID"
          },
          "entity_id": {
            "type": "string",
            "format": "UUID",
            "description": "Asset or Shot concerned by the output file"
          },
          "asset_instance_id": {
            "type": "string",
            "format": "UUID",
            "description": "Asset instance ID"
          },
          "output_type_id": {
            "type": "string",
            "format": "UUID",
            "description": "Type of output (geometry, cache, etc.)"
          },
          "task_type_id": {
            "type": "string",
            "format": "UUID",
            "description": "Task type related to this output file (modeling, animation, etc.)"
          },
          "person_id": {
            "type": "string",
            "format": "UUID",
            "description": "Author of the file"
          },
          "source_file_id": {
            "type": "string",
            "format": "UUID",
            "description": "Working file that led to create this output file"
          },
          "temporal_entity_id": {
            "type": "string",
            "format": "UUID",
            "description": "Shot, scene or sequence needed for output files related to an asset instance"
          },
          "data": {
            "type": "string",
            "format": "json",
            "description": "Free JSON field to add metadata"
          }
        }
      },
      "Output types": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string"
          },
          "short_name": {
            "type": "string"
          }
        }
      },
      "Persons": {
        "type": "object",
        "properties": {
          "first_name": {
            "type": "string"
          },
          "last_name": {
            "type": "string"
          },
          "email": {
            "type": "string",
            "description": "Serve as login"
          },
          "phone": {
            "type": "string"
          },
          "active": {
            "type": "boolean",
            "description": "True if the person is still in the studio, False otherwise"
          },
          "last_presence": {
            "type": "string",
            "format": "date",
            "description": "Last time the person worked for the studio"
          },
          "password": {
            "type": "string",
            "format": "byte"
          },
          "desktop_login": {
            "type": "string",
            "description": "Login used on desktop"
          },
          "shotgun_id": {
            "type": "integer",
            "description": "Used for synchronization with a Shotgun instance"
          },
          "timezone": {
            "type": "string"
          },
          "locale": {
            "type": "string"
          },
          "data": {
            "type": "string",
            "format": "json",
            "description": "Free JSON field to add metadata"
          },
          "role": {
            "type": "string",
            "default": "user"
          },
          "has_avatar": {
            "type": "boolean",
            "default": "False",
            "description": "True if user has an avatar, Flase otherwise"
          },
          "notifications_enabled": {
            "type": "boolean",
          },
          "notifications_slack_enabled": {
            "type": "boolean",
          },
          "notifications_slack_userid": {
            "type": "string",
          },
          "notifications_mattermost_enabled": {
            "type": "boolean",
          },
          "notifications_mattermost_userid": {
            "type": "string",
          },
          "notifications_discord_enabled": {
            "type": "boolean",
          },
          "notifications_discord_userid": {
            "type": "string",
          }
        }
      },
      "Playlists": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string",
            "description": "Name of playlist"
          },
          "shots": {
            "type": "string",
            "format": "json",
            "description": "JSON field describing shot and preview listed in"
          },
          "project_id": {
            "type": "string",
            "format": "UUID",
            "description": "Project ID"
          },
          "episode_id": {
            "type": "string",
            "format": "UUID",
            "description": "Episode ID"
          },
          "for_client": {
            "type": "boolean",
            "default": "False"
          },
          "for_entity": {
            "type": "string",
            "default": "shot"
          },
          "is_for_all": {
            "type": "boolean",
            "default": "False"
          },
          "task_type_id": {
            "type": "string",
            "format": "UUID",
            "description": "Task type ID"
          }
        }
      },
      "Preview files": {
        "type": "object",
        "properties": {
          "shotgun_id": {
            "type": "integer",
            "description": "Used for synchronization with a Shotgun instance"
          },
          "name": {
            "type": "string",
            "description": "Name of preview file"
          },
          "original_name": {
            "type": "string",
            "description": "Original name of preview file"
          },
          "revision": {
            "type": "integer",
            "default": "1",
            "description": "Revision number of preview file"
          },
          "position": {
            "type": "integer",
            "default": "1",
            "description": "Position of preview file"
          },
          "extension": {
            "type": "string",
            "description": "Extension of preview file"
          },
          "description": {
            "type": "string",
            "description": "Preview file brief"
          },
          "path": {
            "type": "string",
            "description": "File path on the production hard drive"
          },
          "source": {
            "type": "string",
            "description": "Created by a script, a webgui or a desktop gui"
          },
          "file_size": {
            "type": "integer",
            "default": "0",
            "description": "Size of output file"
          },
          "comment": {
            "type": "string",
            "description": "Comment on output file"
          },
          "checksum": {
            "type": "string",
            "description": "Checksum of output file"
          },
          "representation": {
            "type": "string",
            "description": "Precise what kind of output it is (abc, jpgs, pngs, etc.)"
          },
          "nb_elements": {
            "type": "integer",
            "default": "1",
            "description": "For image sequence"
          },
          "canceled": {
            "type": "boolean",
          },
          "file_status_id": {
            "type": "string",
            "format": "UUID",
            "description": "File status ID"
          },
          "entity_id": {
            "type": "string",
            "format": "UUID",
            "description": "Asset or Shot concerned by the output file"
          },
          "asset_instance_id": {
            "type": "string",
            "format": "UUID",
            "description": "Asset instance ID"
          },
          "output_type_id": {
            "type": "string",
            "format": "UUID",
            "description": "Type of output (geometry, cache, etc.)"
          },
          "task_type_id": {
            "type": "string",
            "format": "UUID",
            "description": "Task type related to this output file (modeling, animation, etc.)"
          },
          "person_id": {
            "type": "string",
            "format": "UUID",
            "description": "Author of the file"
          },
          "source_file_id": {
            "type": "string",
            "format": "UUID",
            "description": "Working file that led to create this output file"
          },
          "temporal_entity_id": {
            "type": "string",
            "format": "UUID",
            "description": "Shot, scene or sequence needed for output files related to an asset instance"
          },
          "data": {
            "type": "string",
            "format": "json",
            "description": "Free JSON field to add metadata"
          }
        }
      },
      "Projects": {
        "type": "object",
        "properties": {
          "id": {
            "type": "integer",
            "format": "int64"
          },
          "name": {
            "type": "string"
          }
        }
      },
      "Search filters": {
        "type": "object",
        "properties": {
          "id": {
            "type": "integer",
            "format": "int64"
          },
          "name": {
            "type": "string"
          }
        }
      },
      "Sequences": {
        "type": "object",
        "properties": {
          "id": {
            "type": "integer",
            "format": "int64"
          },
          "seq": {
            "type": "string"
          }
        }
      },
      "Shots": {
        "type": "object",
        "properties": {
          "id": {
            "type": "integer",
            "format": "int64"
          },
          "name": {
            "type": "string"
          }
        }
      },
      "Software": {
        "type": "object",
        "properties": {
          "id": {
            "type": "integer",
            "format": "int64"
          },
          "name": {
            "type": "string"
          }
        }
      },
      "Subscriptions to notifications": {
        "type": "object",
        "properties": {
          "id": {
            "type": "integer",
            "format": "int64"
          },
          "name": {
            "type": "string"
          }
        }
      },
      "Tasks": {
        "type": "object",
        "properties": {
          "id": {
            "type": "integer",
            "format": "int64"
          },
          "name": {
            "type": "string"
          }
        }
      },
      "Task status": {
        "type": "object",
        "properties": {
          "id": {
            "type": "integer",
            "format": "int64"
          },
          "name": {
            "type": "string"
          }
        }
      },
      "Task types": {
        "type": "object",
        "properties": {
          "id": {
            "type": "integer",
            "format": "int64"
          },
          "name": {
            "type": "string"
          }
        }
      },
      "Time spents": {
        "type": "object",
        "properties": {
          "id": {
            "type": "integer",
            "format": "int64"
          },
          "name": {
            "type": "string"
          }
        }
      },
      "Working files": {
        "type": "object",
        "properties": {
          "id": {
            "type": "integer",
            "format": "int64"
          },
          "name": {
            "type": "string"
          }
        }
      }
    }
}

swagger_config = {
    "headers": [
      ('Access-Control-Allow-Origin', '*'),
      ('Access-Control-Allow-Methods', "GET, POST, PUT, DELETE, OPTIONS"),
      ('Access-Control-Allow-Credentials', "true")
    ],
    "specs": [
        {
            "endpoint": 'openapi',
            "route": '/openapi.json'
        }
    ],
    "static_url_path": "/docs",
    "swagger_ui": True,
    "specs_route": "/apidocs/"
}

logs.configure_logs(app)

if not app.config["FILE_TREE_FOLDER"]:
    # Default file_trees are included in Python package: use root_path
    app.config["FILE_TREE_FOLDER"] = os.path.join(app.root_path, "file_trees")

if not app.config["PREVIEW_FOLDER"]:
    app.config["PREVIEW_FOLDER"] = os.path.join(app.instance_path, "previews")

if not app.config["INDEXES_FOLDER"]:
    app.config["INDEXES_FOLDER"] = os.path.join(app.instance_path, "indexes")

init_indexes(app.config["INDEXES_FOLDER"])

db = SQLAlchemy(app)
migrate = Migrate(app, db)  # DB schema migration features

app.secret_key = app.config["SECRET_KEY"]
jwt = JWTManager(app)  # JWT auth tokens
Principal(app)  # Permissions
cache.cache.init_app(app)  # Function caching
flask_fs.init_app(app)  # To save files in object storage
mail = Mail()
mail.init_app(app)  # To send emails
swagger = Swagger(app, template=swagger_template, config=swagger_config)


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
