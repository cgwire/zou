from zou import __version__

swagger_config = {
    "headers": [
        ("Access-Control-Allow-Origin", "*"),
        ("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS"),
        ("Access-Control-Allow-Credentials", "true"),
        (
            "Access-Control-Allow-Headers",
            "Authorization, Origin, X-Requested-With, Content-Type, Accept",
        ),
    ],
    "specs": [{"endpoint": "openapi", "route": "/openapi.json"}],
    "static_url_path": "/docs",
    "swagger_ui": True,
    "specs_route": "/apidocs/",
}


description = f"""
## Welcome to the Kitsu API specification
```Version: {__version__}```

The Kitsu API allows to store and manage the data of your animation/VFX production. Through it you can link all the tools of your pipeline and make sure they are all synchronized.

An easy to use Python client to access this API is available:
[Python Kitsu Client documentation](https://gazu.cg-wire.com/)

## Authentication<div class="auth">

<p>Before you can use any of the endpoints outline below,
you will have to get a JWT token to authorize your requests.

You can get a authorization token using a (form-encoded) POST request to ```/auth/login```.
With curl this would look something like ```curl -X POST <server_address>/auth/login -d "email=<youremail>&password=<yourpassword>```.

The response is a JSON object, specifically you'll need to provide the ```access_token``` for your future requests.

Here is a complete authentication process as an example (again using curl):
```
$ curl -X POST <server_address>/api/auth/login -d "email=<youremail>&password=<yourpassword>"'
{{"login": true", "access_token": "eyJ0e...", ...}}
$ jwt=eyJ0e...  # Store the access token for easier use
$ curl -H "Authorization: Bearer $jwt" <server_address>/api/data/projects
[{{...}},
{{...}}]
```
[OpenAPI definition](/openapi.json)
"""

swagger_template = {
    "openapi": "3.1",
    "info": {
        "title": "Kitsu API",
        "description": description,
        "contact": {
            "name": "CGWire",
            "url": "https://www.cg-wire.com",
        },
        "version": __version__,
        "license": {
            "name": "AGPL 3.0",
            "url": "https://www.gnu.org/licenses/agpl-3.0.en.html",
        },
    },
    "externalDocs": {
        "description": "Read the installation documentation",
        "url": "https://zou.cg-wire.com",
    },
    "host": "localhost:8080",
    "basePath": "/api",
    "schemes": ["http", "https"],
    "securityDefinitions": {
        "JWT Authorization": {
            "name": "Authorization",
            "in": "header",
            "type": "apiKey",
            "description": "Format in header: **Authorization: Bearer {token}**. \n\n Value example: Bearer xxxxx.yyyyy.zzzzz",
        }
    },
    "security": [{"JWT Authorization": []}],
    "tags": [
        {"name": "Authentication"},
        {"name": "Assets"},
        {"name": "Breakdown"},
        {"name": "Comments"},
        {"name": "Crud"},
        {"name": "Edits"},
        {"name": "Entities"},
        {"name": "Events"},
        {"name": "Export"},
        {"name": "Files"},
        {"name": "Import"},
        {"name": "Index"},
        {"name": "News"},
        {"name": "Persons"},
        {"name": "Playlists"},
        {"name": "Previews"},
        {"name": "Projects"},
        {"name": "Search"},
        {"name": "Shots"},
        {"name": "Tasks"},
        {"name": "User"},
    ],
    "definitions": {
        " Common fields for all model instances": {
            "type": "object",
            "properties": {
                " id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "A unique ID made of letters, hyphens and numbers",
                    "example": "a24a6ea4-ce75-4665-a070-57453082c25",
                },
                "created_at": {
                    "type": "string",
                    "format": "date-time",
                    "description": "The creation date",
                },
                "updated_at": {
                    "type": "string",
                    "format": "date-time",
                    "description": "The update date",
                },
            },
        },
        "Asset": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of asset"},
                "code": {
                    "type": "string",
                    "description": "Utility field for the pipeline to identify the asset",
                },
                "description": {
                    "type": "string",
                    "description": "Asset brief",
                },
                "canceled": {
                    "type": "boolean",
                    "default": "False",
                    "description": "True if the asset has been delete one time, False otherwise",
                },
                "project_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Project ID",
                },
                "entity_type_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Asset type ID",
                },
                "source_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Field uset to set the episode_id",
                },
                "preview_file_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "ID of preview file used as thumbnail",
                },
                "data": {
                    "type": "string",
                    "format": "json",
                    "description": "Free JSON field to add metadata",
                },
                "shotgun_id": {
                    "type": "integer",
                    "description": "Used for synchronization with a Shotgun instance",
                },
            },
        },
        "AssetInstance": {
            "type": "object",
            "properties": {
                "asset_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Instantiated asset",
                },
                "name": {"type": "string"},
                "number": {"type": "integer"},
                "description": {"type": "string"},
                "active": {"type": "boolean", "default": "True"},
                "data": {
                    "type": "string",
                    "format": "json",
                    "description": "Free JSON field to add metadata",
                },
                "scene_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Target scene",
                },
                "target_asset_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Use when instantiating an asset in an asset is required",
                },
            },
        },
        "AssetType": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        },
        "AttachmentFile": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of attachment file",
                },
                "size": {
                    "type": "integer",
                    "description": "Size of attachment file",
                },
                "extension": {
                    "type": "string",
                    "description": "Extension of attachment file",
                },
                "mimetype": {"type": "string"},
                "comment_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Comment to which the file is attached",
                },
            },
        },
        "BuildJob": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Status of build job (running, failed, succeeded)",
                },
                "job_type": {
                    "type": "string",
                    "description": "Type of build job (archive, movie)",
                },
                "ended_at": {"type": "string", "format": "date-time"},
                "playlist_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Playlist ID",
                },
            },
        },
        "Comment": {
            "type": "object",
            "properties": {
                "shotgun_id": {
                    "type": "integer",
                    "description": "Used for synchronization with a Shotgun instance",
                },
                "object_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Unique ID of the commented model instance",
                },
                "object_type": {
                    "type": "string",
                    "description": "Model type of the comment model instance",
                },
                "text": {"type": "string"},
                "data": {
                    "type": "string",
                    "format": "json",
                    "description": "Free JSON field to add metadata",
                },
                "replies": {
                    "type": "string",
                    "format": "json",
                    "default": "[]",
                },
                "checklist": {"type": "string", "format": "json"},
                "pinned": {"type": "boolean"},
                "task_status_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Task status attached to comment",
                },
                "person_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "The person who publishes the comment",
                },
                "preview_file_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "ID of preview file used as thumbnail",
                },
            },
        },
        "CustomAction": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of custom action",
                },
                "url": {"type": "string"},
                "entity_type": {"type": "string", "default": "all"},
                "is_ajax": {
                    "type": "boolean",
                    "default": "False",
                    "description": "True if the custom action is ajax, False otherwise",
                },
            },
        },
        "DataImportError": {
            "type": "object",
            "properties": {
                "event_data": {
                    "type": "string",
                    "format": "json",
                    "description": "JSON field to add event data",
                },
                "source": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["csv", "shotgun"]},
                },
            },
        },
        "DayOff": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "format": "date"},
                "person_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "The person who will take the day off",
                },
            },
        },
        "Department": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of department",
                },
                "color": {
                    "type": "string",
                    "description": "Color of department",
                },
            },
        },
        "DesktopLoginLog": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "format": "date"},
                "person_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Person ID",
                },
            },
        },
        "Episode": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of episode"},
                "code": {
                    "type": "string",
                    "description": "Utility field for the pipeline to identify the episode",
                },
                "description": {
                    "type": "string",
                    "description": "Episode brief",
                },
                "canceled": {
                    "type": "boolean",
                    "default": "False",
                    "description": "True if the episode has been delete one time, False otherwise",
                },
                "project_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Project ID",
                },
                "source_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Field uset to set the episode_id",
                },
                "preview_file_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "ID of preview file used as thumbnail",
                },
                "data": {
                    "type": "string",
                    "format": "json",
                    "description": "Free JSON field to add metadata",
                },
                "shotgun_id": {
                    "type": "integer",
                    "description": "Used for synchronization with a Shotgun instance",
                },
            },
        },
        "Event": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of event"},
                "user_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "The user who made the action that emitted the event",
                },
                "project_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Project ID",
                },
                "data": {
                    "type": "string",
                    "format": "json",
                    "description": "Free JSON field to add metadata",
                },
            },
        },
        "FileStatus": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "color": {"type": "string"},
            },
        },
        "LoginLog": {
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "web, script"},
                "ip_address": {
                    "type": "string",
                    "description": "IP address of device used to login",
                },
                "person_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Person ID",
                },
            },
        },
        "Metadata": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "ID of project for which metadata are added",
                },
                "entity_type": {
                    "type": "string",
                    "description": "Asset or Shot",
                },
                "name": {
                    "type": "string",
                    "description": "Field name for GUI",
                },
                "field_name": {
                    "type": "string",
                    "description": "Technical field name",
                },
                "choices": {
                    "type": "string",
                    "format": "json",
                    "description": "Array of string that represents the available values for this metadate (this metatada is considered as a free field if this array is empty)",
                },
                "for_client": {"type": "boolean"},
            },
        },
        "Milestone": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "string",
                    "format": "date",
                    "description": "Milestone date of production schedule",
                },
                "name": {"type": "string", "description": "Name of milestone"},
                "task_type_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Task type ID",
                },
                "project_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Project ID",
                },
            },
        },
        "News": {
            "type": "object",
            "properties": {
                "change": {"type": "boolean", "default": "False"},
                "author_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Person who wrote the comment",
                },
                "comment_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Posted comment ID",
                },
                "task_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Task ID",
                },
                "preview_file_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Preview file ID",
                },
            },
        },
        "Notification": {
            "type": "object",
            "properties": {
                "read": {
                    "type": "boolean",
                    "description": "True if user read it, False otherwise",
                },
                "change": {
                    "type": "boolean",
                    "description": "True if there is status change related to this status, False otherwise",
                },
                "person_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "The user to who the notification is aimed at",
                },
                "author_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Author of the event to notify",
                },
                "comment_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Comment related to the notification, if there is any",
                },
                "task_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Task related to the notification, if there is any",
                },
                "reply_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Reply related to notification",
                },
                "type": {
                    "type": "string",
                    "description": "Type of notification",
                },
            },
        },
        "Organisation": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of organisaition",
                },
                "hours_by_day": {"type": "float"},
                "has_avatar": {
                    "type": "boolean",
                    "default": "False",
                    "description": "True if the organisation has an avatar, Flase otherwise",
                },
                "use_original_file_name": {
                    "type": "boolean",
                    "default": "False",
                    "description": "True if the organisation uses original file names, Flase otherwise",
                },
                "timesheets_locked": {
                    "type": "boolean",
                    "default": "False",
                    "description": "True if the organisation's timesheets are locked, False otherwise",
                },
                "hd_by_default": {"type": "boolean", "default": "False"},
                "chat_token_slack": {"type": "string"},
                "chat_webhook_mattermost": {"type": "string"},
                "chat_token_discord": {"type": "string"},
            },
        },
        "OutputFile": {
            "type": "object",
            "properties": {
                "shotgun_id": {
                    "type": "integer",
                    "description": "Used for synchronization with a Shotgun instance",
                },
                "name": {
                    "type": "string",
                    "description": "Name of output file",
                },
                "extension": {
                    "type": "string",
                    "description": "Extension of output file",
                },
                "description": {
                    "type": "string",
                    "description": "Output file brief",
                },
                "comment": {
                    "type": "string",
                    "description": "Comment on output file",
                },
                "revision": {
                    "type": "integer",
                    "description": "Revision number of output file",
                },
                "size": {
                    "type": "integer",
                    "description": "Size of output file",
                },
                "checksum": {
                    "type": "string",
                    "description": "Checksum of output file",
                },
                "source": {
                    "type": "string",
                    "description": "Created by a script, a webgui or a desktop gui",
                },
                "path": {
                    "type": "string",
                    "description": "File path on the production hard drive",
                },
                "representation": {
                    "type": "string",
                    "description": "Precise what kind of output it is (abc, jpgs, pngs, etc.)",
                },
                "nb_elements": {
                    "type": "integer",
                    "default": "1",
                    "description": "For image sequence",
                },
                "canceled": {
                    "type": "boolean",
                },
                "file_status_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "File status ID",
                },
                "entity_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Asset or Shot concerned by the output file",
                },
                "asset_instance_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Asset instance ID",
                },
                "output_type_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Type of output (geometry, cache, etc.)",
                },
                "task_type_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Task type related to this output file (modeling, animation, etc.)",
                },
                "person_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Author of the file",
                },
                "source_file_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Working file that led to create this output file",
                },
                "temporal_entity_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Shot, scene or sequence needed for output files related to an asset instance",
                },
                "data": {
                    "type": "string",
                    "format": "json",
                    "description": "Free JSON field to add metadata",
                },
            },
        },
        "OutputType": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "short_name": {"type": "string"},
            },
        },
        "Person": {
            "type": "object",
            "properties": {
                "first_name": {"type": "string"},
                "last_name": {"type": "string"},
                "email": {"type": "string", "description": "Serve as login"},
                "phone": {"type": "string"},
                "active": {
                    "type": "boolean",
                    "description": "True if the person is still in the studio, False otherwise",
                },
                "last_presence": {
                    "type": "string",
                    "format": "date",
                    "description": "Last time the person worked for the studio",
                },
                "password": {"type": "string", "format": "byte"},
                "desktop_login": {
                    "type": "string",
                    "description": "Login used on desktop",
                },
                "shotgun_id": {
                    "type": "integer",
                    "description": "Used for synchronization with a Shotgun instance",
                },
                "timezone": {"type": "string"},
                "locale": {"type": "string"},
                "data": {
                    "type": "string",
                    "format": "json",
                    "description": "Free JSON field to add metadata",
                },
                "role": {"type": "string", "default": "user"},
                "has_avatar": {
                    "type": "boolean",
                    "default": "False",
                    "description": "True if user has an avatar, Flase otherwise",
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
                },
            },
        },
        "Playlist": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of playlist"},
                "shots": {
                    "type": "string",
                    "format": "json",
                    "description": "JSON field describing shot and preview listed in",
                },
                "project_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Project ID",
                },
                "episode_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Episode ID",
                },
                "for_client": {"type": "boolean", "default": "False"},
                "for_entity": {"type": "string", "default": "shot"},
                "is_for_all": {"type": "boolean", "default": "False"},
                "task_type_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Task type ID",
                },
            },
        },
        "PreviewFile": {
            "type": "object",
            "properties": {
                "shotgun_id": {
                    "type": "integer",
                    "description": "Used for synchronization with a Shotgun instance",
                },
                "name": {
                    "type": "string",
                    "description": "Name of preview file",
                },
                "original_name": {
                    "type": "string",
                    "description": "Original name of preview file",
                },
                "revision": {
                    "type": "integer",
                    "default": "1",
                    "description": "Revision number of preview file",
                },
                "position": {
                    "type": "integer",
                    "default": "1",
                    "description": "Position of preview file",
                },
                "extension": {
                    "type": "string",
                    "description": "Extension of preview file",
                },
                "description": {
                    "type": "string",
                    "description": "Preview file brief",
                },
                "path": {
                    "type": "string",
                    "description": "File path on the production hard drive",
                },
                "source": {
                    "type": "string",
                    "description": "Created by a script, a webgui or a desktop gui",
                },
                "file_size": {
                    "type": "integer",
                    "default": "0",
                    "description": "Size of output file",
                },
                "comment": {
                    "type": "string",
                    "description": "Comment on output file",
                },
                "checksum": {
                    "type": "string",
                    "description": "Checksum of output file",
                },
                "representation": {
                    "type": "string",
                    "description": "Precise what kind of output it is (abc, jpgs, pngs, etc.)",
                },
                "nb_elements": {
                    "type": "integer",
                    "default": "1",
                    "description": "For image sequence",
                },
                "canceled": {
                    "type": "boolean",
                },
                "file_status_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "File status ID",
                },
                "entity_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Asset or Shot concerned by the output file",
                },
                "asset_instance_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Asset instance ID",
                },
                "output_type_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Type of output (geometry, cache, etc.)",
                },
                "task_type_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Task type related to this output file (modeling, animation, etc.)",
                },
                "person_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Author of the file",
                },
                "source_file_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Working file that led to create this output file",
                },
                "temporal_entity_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Shot, scene or sequence needed for output files related to an asset instance",
                },
                "data": {
                    "type": "string",
                    "format": "json",
                    "description": "Free JSON field to add metadata",
                },
            },
        },
        "Project": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of project"},
                "code": {
                    "type": "string",
                    "description": "Utility field for the pipeline to identify the project",
                },
                "description": {
                    "type": "string",
                    "description": "Project brief",
                },
                "shotgun_id": {
                    "type": "integer",
                    "description": "Used for synchronization with a Shotgun instance",
                },
                "file_tree": {
                    "type": "string",
                    "format": "json",
                    "description": "Templates to use to build file paths",
                },
                "data": {
                    "type": "string",
                    "format": "json",
                    "description": "Free JSON field to add metadata",
                },
                "project_status_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Project status ID",
                },
                "has_avatar": {
                    "type": "boolean",
                    "default": "False",
                    "description": "True if the project has an avatar, False otherwise",
                },
                "fps": {"type": "string", "description": "Frames per second"},
                "ratio": {"type": "string"},
                "resolution": {"type": "string"},
                "production_type": {
                    "type": "string",
                    "description": "short, featurefilm or tvshow",
                    "default": "short",
                },
                "end_date": {"type": "string", "format": "date"},
                "start_date": {"type": "string", "format": "date"},
                "man_days": {
                    "type": "integer",
                    "description": "Estimated number of working days to complete the project",
                },
                "nb_episodes": {"type": "integer", "default": "0"},
                "episode_span": {"type": "integer", "default": "0"},
                "max_retakes": {"type": "integer", "default": "0"},
                "is_clients_isolated": {
                    "type": "boolean",
                    "default": "False",
                    "description": "True if the clients are isolated from the project, False otherwise",
                },
            },
        },
        "ProjectStatus": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "color": {"type": "string"},
            },
        },
        "ScheduleItem": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "format": "date"},
                "end_date": {"type": "string", "format": "date"},
                "man_days": {"type": "string", "format": "date"},
                "project_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Project ID",
                },
                "task_type_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Task type ID",
                },
                "object_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Object ID",
                },
            },
        },
        "SearchFilter": {
            "type": "object",
            "properties": {
                "list_type": {"type": "string", "description": "Type of list"},
                "entity_type": {
                    "type": "string",
                    "description": "Type of entity",
                },
                "name": {
                    "type": "string",
                    "description": "Name of search filter",
                },
                "search_query": {"type": "string"},
                "person_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Person ID",
                },
                "project_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Project ID",
                },
            },
        },
        "Sequence": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of sequence"},
                "code": {
                    "type": "string",
                    "description": "Utility field for the pipeline to identify the sequence",
                },
                "description": {
                    "type": "string",
                    "description": "Sequence brief",
                },
                "canceled": {
                    "type": "boolean",
                    "default": "False",
                    "description": "True if the sequence has been delete one time, False otherwise",
                },
                "project_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Project ID",
                },
                "parent_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Episode ID",
                },
                "source_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Field uset to set the episode_id",
                },
                "preview_file_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "ID of preview file used as thumbnail",
                },
                "data": {
                    "type": "string",
                    "format": "json",
                    "description": "Free JSON field to add metadata",
                },
                "shotgun_id": {
                    "type": "integer",
                    "description": "Used for synchronization with a Shotgun instance",
                },
            },
        },
        "Shot": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of shot"},
                "code": {
                    "type": "string",
                    "description": "Utility field for the pipeline to identify the shot",
                },
                "description": {"type": "string", "description": "Shot brief"},
                "canceled": {
                    "type": "boolean",
                    "default": "False",
                    "description": "True if the shot has been delete one time, False otherwise",
                },
                "project_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Project ID",
                },
                "parent_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Episode ID",
                },
                "entity_type_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Shot type ID",
                },
                "source_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Field uset to set the episode_id",
                },
                "preview_file_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "ID of preview file used as thumbnail",
                },
                "data": {
                    "type": "string",
                    "format": "json",
                    "description": "Free JSON field to add metadata",
                },
                "shotgun_id": {
                    "type": "integer",
                    "description": "Used for synchronization with a Shotgun instance",
                },
            },
        },
        "Software": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of software"},
                "short_name": {
                    "type": "string",
                    "description": "Short name of software",
                },
                "file_extension": {
                    "type": "string",
                    "description": "Main extension used for this software's files",
                },
                "secondary_extensions": {
                    "type": "string",
                    "format": "json",
                    "description": "Other extensions used for this software's files",
                },
            },
        },
        "StatusAutomation": {
            "type": "object",
            "properties": {
                "entity_type": {"type": "string", "default": "asset"},
                "in_task_type_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Task type ID",
                },
                "in_task_status_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Task status ID",
                },
                "out_field_type": {
                    "type": "string",
                    "description": "Field type (status, ready_for)",
                },
                "out_task_type_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Task type ID",
                },
                "out_task_status_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Task status ID",
                },
            },
        },
        "SubscriptionToNotifications": {
            "type": "object",
            "properties": {
                "person_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Person ID",
                },
                "task_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Task ID",
                },
                "entity_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Entity ID",
                },
                "task_type_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Task type ID",
                },
            },
        },
        "Task": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of task"},
                "description": {"type": "string", "description": "Task brief"},
                "priority": {
                    "type": "integer",
                    "default": "0",
                    "description": "Priority of task",
                },
                "duration": {
                    "type": "float",
                    "default": "0",
                    "description": "Duration of task",
                },
                "estimation": {
                    "type": "float",
                    "default": "0",
                    "description": "Estimation of duration of task",
                },
                "completion_rate": {
                    "type": "integer",
                    "default": "0",
                    "description": "Completion rate of task",
                },
                "retake_count": {
                    "type": "integer",
                    "default": "0",
                    "description": "Retake count of task",
                },
                "sort_order": {
                    "type": "integer",
                    "default": "0",
                    "description": "Sort order of task",
                },
                "start_date": {"type": "string", "format": "date-time"},
                "due_date": {"type": "string", "format": "date-time"},
                "real_start_date": {"type": "string", "format": "date-time"},
                "end_date": {"type": "string", "format": "date-time"},
                "last_comment_date": {"type": "string", "format": "date-time"},
                "nb_assets_ready": {
                    "type": "integer",
                    "default": "0",
                    "description": "Number of assets ready",
                },
                "data": {
                    "type": "string",
                    "format": "json",
                    "description": "Free JSON field to add metadata",
                },
                "shotgun_id": {
                    "type": "integer",
                    "description": "Used for synchronization with a Shotgun instance",
                },
                "project_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Project ID",
                },
                "task_type_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Task type ID",
                },
                "task_status_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Task status ID",
                },
                "entity_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Entity ID",
                },
                "assigner_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Person ID",
                },
            },
        },
        "TaskStatus": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of task status",
                },
                "short_name": {
                    "type": "string",
                    "description": "Short name of task status",
                },
                "color": {"type": "string"},
                "is_done": {
                    "type": "boolean",
                    "default": "False",
                    "description": "True if the task is done, False otherwise",
                },
                "is_artist_allowed": {
                    "type": "boolean",
                    "default": "True",
                    "description": "True if the artist is allowed, False otherwise",
                },
                "is_client_allowed": {
                    "type": "boolean",
                    "default": "True",
                    "description": "True if the client is allowed, False otherwise",
                },
                "is_retake": {
                    "type": "boolean",
                    "default": "False",
                    "description": "True if the task was retaken, False otherwise",
                },
                "is_feedback_request": {
                    "type": "boolean",
                    "default": "False",
                    "description": "True if feedback was requested, False otherwise",
                },
                "is_default": {
                    "type": "boolean",
                    "default": "False",
                    "description": "True if the task is default, False otherwise",
                },
                "shotgun_id": {
                    "type": "integer",
                    "description": "Used for synchronization with a Shotgun instance",
                },
            },
        },
        "TaskType": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of task type"},
                "short_name": {
                    "type": "string",
                    "description": "Short name of task type",
                },
                "color": {"type": "string", "default": "#FFFFFF"},
                "priority": {
                    "type": "integer",
                    "default": "1",
                    "description": "Priority of task type",
                },
                "for_entity": {"type": "string", "default": "Asset"},
                "allow_timelog": {
                    "type": "boolean",
                    "default": "True",
                    "description": "True if timelog is allowed, False otherwise",
                },
                "shotgun_id": {
                    "type": "integer",
                    "description": "Used for synchronization with a Shotgun instance",
                },
                "department_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Department ID",
                },
            },
        },
        "TimeSpent": {
            "type": "object",
            "properties": {
                "duration": {"type": "float"},
                "date": {"type": "string", "format": "date"},
                "task_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Related task ID",
                },
                "person_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "The person who performed the working time",
                },
            },
        },
        "WorkingFile": {
            "type": "object",
            "properties": {
                "shotgun_id": {
                    "type": "integer",
                    "description": "Used for synchronization with a Shotgun instance",
                },
                "name": {
                    "type": "string",
                    "description": "Name of working file",
                },
                "description": {
                    "type": "string",
                    "description": "working file brief",
                },
                "comment": {
                    "type": "string",
                    "description": "Comment on working file",
                },
                "revision": {
                    "type": "integer",
                    "description": "Revision number of working file",
                },
                "size": {
                    "type": "integer",
                    "description": "Size of working file",
                },
                "checksum": {
                    "type": "string",
                    "description": "Checksum of working file",
                },
                "path": {
                    "type": "string",
                    "description": "File path on the production hard drive",
                },
                "data": {
                    "type": "string",
                    "format": "json",
                    "description": "Free JSON field to add metadata",
                },
                "task_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Task for which the working file is made",
                },
                "entity_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Entity for which the working is made",
                },
                "person_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Author of the file",
                },
                "software_id": {
                    "type": "string",
                    "format": "UUID",
                    "description": "Software used to build this working file",
                },
            },
        },
    },
}
