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
    "title": "Zou",
    "description": "# Welcome to the Zou (Kitsu API) documentation \n\nZou is an API that allows to store and manage the data of your CG production. Through it you can link all the tools of your pipeline and make sure they are all synchronized.\n\n To integrate it in your tools you can rely on the dedicated Python client named [Gazu](https://gazu.cg-wire.com/).\n\nThe source is available on [Github](https://github.com/cgwire/zou).\n\n# Who is it for?\n\nThe audience for Zou is made of Technical Directors, ITs and Software Engineers from CG studios. With Zou they can enhance the tools they provide to all departments.\n\nOn top of it, you can deploy Kitsu, the production tracker developed by CGWire.\n\n# Features\n\nZou can:\n\n* Store production data: projects, shots, assets, tasks, files metadata and validations.\n* Provide folder and file paths for any task.\n* Data import from Shotgun or CSV files.\n* Export main data to CSV files.\n* Provide helpers to manage task workflow (start, publish, retake).\n* Provide an event system to plug external modules on it.\n\n",
    "contact": {
      "email": "support@cg-wire.com",
      "url": "https://www.cg-wire.com",
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
            "type": "string"
          },
          "code": {
            "type": "string"
          },
          "description": {
            "type": "string"
          },
          "canceled": {
            "type": "boolean",
            "default": "False"
          },
          "project_id": {
            "type": "string",
            "format": "UUID"
          },
          "entity_type_id": {
            "type": "string",
            "format": "UUID"
          },
          "source_id": {
            "type": "string",
            "format": "UUID"
          },
          "preview_file_id": {
            "type": "string",
            "format": "UUID"
          },
          "data": {
            "type": "string",
            "format": "json"
          },
          "shotgun_id": {
            "type": "string",
            "format": "UUID"
          }
        }
      },
      "Asset instances": {
        "type": "object",
        "properties": {
          "asset_id": {
            "type": "string",
            "format": "UUID"
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
            "format": "json"
          },
          "scene_id": {
            "type": "string",
            "format": "UUID"
          },
          "target_asset_id": {
            "type": "string",
            "format": "UUID"
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
            "type": "string",
            "format": "UUID"
          },
          "object_id": {
            "type": "string",
            "format": "UUID"
          },
          "object_type": {
            "type": "string"
          },
          "text": {
            "type": "string"
          },
          "data": {
            "type": "string",
            "format": "json"
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
            "format": "UUID"
          },
          "person_id": {
            "type": "string",
            "format": "UUID"
          },
          "preview_file_id": {
            "type": "string",
            "format": "UUID"
          }
        }
      },
      "Episodes": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string"
          },
          "code": {
            "type": "string"
          },
          "description": {
            "type": "string"
          },
          "canceled": {
            "type": "boolean",
            "default": "False"
          },
          "project_id": {
            "type": "string",
            "format": "UUID"
          },
          "source_id": {
            "type": "string",
            "format": "UUID"
          },
          "preview_file_id": {
            "type": "string",
            "format": "UUID"
          },
          "data": {
            "type": "string",
            "format": "json"
          },
          "shotgun_id": {
            "type": "string",
            "format": "UUID"
          }
        }
      },
      "Events": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string"
          },
          "user_id": {
            "type": "string",
            "format": "UUID"
          },
          "data": {
            "type": "string",
            "format": "json"
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
          "id": {
            "type": "integer",
            "format": "int64"
          },
          "name": {
            "type": "string"
          }
        }
      },
      "Notifications": {
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
      "Output files": {
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
      "Output types": {
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
            "type": "string"
          },
          "phone": {
            "type": "string"
          },
          "active": {
            "type": "boolean",
            "default": "true"
          },
          "last_presence": {
            "type": "string",
            "format": "date"
          },
          "password": {
            "type": "string",
            "format": "byte"
          },
          "desktop_login": {
            "type": "string"
          },
          "shotgun_id": {
            "type": "string",
            "format": "UUID"
          },
          "timezone": {
            "type": "string"
          },
          "locale": {
            "type": "string"
          },
          "data": {
            "type": "string",
            "format": "json"
          },
          "role": {
            "type": "string",
            "default": "user"
          },
          "has_avatar": {
            "type": "boolean",
            "default": "False"
          }
        }
      },
      "Playlists": {
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
      "Preview files": {
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
          "name": {
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
swagger = Swagger(app, template=swagger_template)


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
