import json
import os
from copy import deepcopy

from flask import jsonify

from zou import __version__
from zou.app.openapi_schemas import (
    AssetSchema,
    AssetInstanceSchema,
    AssetTypeSchema,
    AttachmentFileSchema,
    BuildJobSchema,
    CommentSchema,
    CustomActionSchema,
    DataImportErrorSchema,
    DayOffSchema,
    DepartmentSchema,
    DesktopLoginLogSchema,
    EpisodeSchema,
    EventSchema,
    FileStatusSchema,
    LoginLogSchema,
    MetadataSchema,
    MilestoneSchema,
    NewsSchema,
    NotificationSchema,
    OrganisationSchema,
    OutputFileSchema,
    OutputTypeSchema,
    PersonSchema,
    PlaylistSchema,
    PreviewFileSchema,
    ProjectSchema,
    ProjectStatusSchema,
    ScheduleItemSchema,
    SearchFilterSchema,
    SequenceSchema,
    ShotSchema,
    SoftwareSchema,
    StatusAutomationSchema,
    SubscriptionToNotificationsSchema,
    StudioSchema,
    TaskSchema,
    TaskStatusSchema,
    TaskTypeSchema,
    TimeSpentSchema,
    WorkingFileSchema,
)

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
    "specs": [{"endpoint": "openapi", "route": "/openapi-raw.json"}],
    "static_url_path": "/docs",
    "swagger_ui": True,
    "specs_route": "/apidocs/",
    "openapi": "3.0.2",
}


description = f"""
## Welcome to the Kitsu API specification
```Version: {__version__}```

The Kitsu API allows to store and manage the data of your animation/VFX production. Through it you can link all the tools of your pipeline and make sure they are all synchronized.

An easy to use Python client to access this API is available:
[Python Kitsu Client documentation](https://gazu.cg-wire.com/)

## Authentication<div class="auth">

<p>Before you can use any of the endpoints outlined below,
you will need to obtain a JWT token to authorize your requests.
</p>

<p>
You will find detailed information on how to retrieve authentication tokens in the
[Zou documentation](https://zou.cg-wire.com/api/).
</p>

<p>
All API requests require authentication via JWT tokens passed in the Authorization header.
</p>
"""

swagger_template = {
    "openapi": "3.0.2",
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
    "components": {
        "securitySchemes": {
            "JWT Authorization": {
                "name": "Authorization",
                "in": "header",
                "type": "apiKey",
                "description": "Format in header: **Authorization: Bearer {token}**. \n\n Value example: Bearer xxxxx.yyyyy.zzzzz",
            }
        },
        "schemas": {
            "Asset": AssetSchema,
            "AssetInstance": AssetInstanceSchema,
            "AssetType": AssetTypeSchema,
            "AttachmentFile": AttachmentFileSchema,
            "BuildJob": BuildJobSchema,
            "Comment": CommentSchema,
            "CustomAction": CustomActionSchema,
            "DataImportError": DataImportErrorSchema,
            "DayOff": DayOffSchema,
            "Department": DepartmentSchema,
            "DesktopLoginLog": DesktopLoginLogSchema,
            "Episode": EpisodeSchema,
            "Event": EventSchema,
            "FileStatus": FileStatusSchema,
            "LoginLog": LoginLogSchema,
            "Metadata": MetadataSchema,
            "Milestone": MilestoneSchema,
            "News": NewsSchema,
            "Notification": NotificationSchema,
            "Organisation": OrganisationSchema,
            "OutputFile": OutputFileSchema,
            "OutputType": OutputTypeSchema,
            "Person": PersonSchema,
            "Playlist": PlaylistSchema,
            "PreviewFile": PreviewFileSchema,
            "Project": ProjectSchema,
            "ProjectStatus": ProjectStatusSchema,
            "ScheduleItem": ScheduleItemSchema,
            "SearchFilter": SearchFilterSchema,
            "Sequence": SequenceSchema,
            "Shot": ShotSchema,
            "Software": SoftwareSchema,
            "StatusAutomation": StatusAutomationSchema,
            "SubscriptionToNotifications": SubscriptionToNotificationsSchema,
            "Studio": StudioSchema,
            "Task": TaskSchema,
            "TaskStatus": TaskStatusSchema,
            "TaskType": TaskTypeSchema,
            "TimeSpent": TimeSpentSchema,
            "WorkingFile": WorkingFileSchema,
        },
    },
    "security": [{"JWT Authorization": []}],
    "tags": [
        {
            "name": "Authentication",
            "description": "User authentication, login, logout, and session management",
        },
        {
            "name": "Assets",
            "description": f"""Production asset management including 3D models, textures, and media files.\n\n```json\nAsset {json.dumps(AssetSchema, indent=2)}\n```""",
        },
        {
            "name": "Breakdown",
            "description": "Shot breakdown management and asset-to-shot relationships",
        },
        {
            "name": "Chat",
            "description": "Real-time messaging and communication features",
        },
        {
            "name": "Comments",
            "description": f"""Task comments, feedback, and collaboration tools.\n\n```json\nComment {json.dumps(CommentSchema, indent=2)}\n```""",
        },
        {
            "name": "Concepts",
            "description": "Concept art and design asset management",
        },
        {
            "name": "Crud",
            "description": "Generic CRUD operations for various data models",
        },
        {
            "name": "Departments",
            "description": f"""Department management and organizational structure.\n\n```json\nDepartment {json.dumps(DepartmentSchema, indent=2)}\n```""",
        },
        {
            "name": "Edits",
            "description": "Edit management for post-production workflows",
        },
        {
            "name": "Entities",
            "description": "Generic entity management and relationships",
        },
        {
            "name": "Events",
            "description": f"""Event streaming and real-time notifications.\n\n```json\nEvent {json.dumps(EventSchema, indent=2)}\n```""",
        },
        {
            "name": "Export",
            "description": "Data export functionality for reports and integrations",
        },
        {
            "name": "Files",
            "description": "File management, uploads, and storage operations",
        },
        {
            "name": "Import",
            "description": "Data import from external sources and file formats",
        },
        {
            "name": "Index",
            "description": "System status, health checks, and configuration",
        },
        {
            "name": "News",
            "description": "Production news feed and activity tracking",
        },
        {
            "name": "Persons",
            "description": f"""User and team member management.\n\n```json\nPerson {json.dumps(PersonSchema, indent=2)}\n```""",
        },
        {
            "name": "Playlists",
            "description": f"""Media playlists and review sessions. \n\n```json\nPlaylist {json.dumps(PlaylistSchema, indent=2)}\n```""",
        },
        {
            "name": "Previews",
            "description": f"""Preview generation and thumbnail management. \n\n```json\nPreviewFile {json.dumps(PreviewFileSchema, indent=2)}\n```""",
        },
        {
            "name": "Projects",
            "description": f"""Project management and production organization.\n\n```json\nProject {json.dumps(ProjectSchema, indent=2)}\n```""",
        },
        {
            "name": "Search",
            "description": f"""Search functionality across all production data.\n\n```json\nSearchFilter {json.dumps(SearchFilterSchema, indent=2)}\n```""",
        },
        {
            "name": "Shots",
            "description": f"""Shot management, sequences, and episodes.\n\n```json\nShot {json.dumps(ShotSchema, indent=2)}\n```""",
        },
        {
            "name": "Tasks",
            "description": f"""Task management, assignments, and progress tracking.\n\n```json\nTask {json.dumps(TaskSchema, indent=2)}\n```""",
        },
        {
            "name": "User",
            "description": "User-specific data and personal workspace management",
        },
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
        "Asset": AssetSchema,
        "AssetInstance": AssetInstanceSchema,
        "AssetType": AssetTypeSchema,
        "AttachmentFile": AttachmentFileSchema,
        "BuildJob": BuildJobSchema,
        "Comment": CommentSchema,
        "CustomAction": CustomActionSchema,
        "DataImportError": DataImportErrorSchema,
        "DayOff": DayOffSchema,
        "Department": DepartmentSchema,
        "DesktopLoginLog": DesktopLoginLogSchema,
        "Episode": EpisodeSchema,
        "Event": EventSchema,
        "FileStatus": FileStatusSchema,
        "LoginLog": LoginLogSchema,
        "Metadata": MetadataSchema,
        "Milestone": MilestoneSchema,
        "News": NewsSchema,
        "Notification": NotificationSchema,
        "Organisation": OrganisationSchema,
        "OutputFile": OutputFileSchema,
        "OutputType": OutputTypeSchema,
        "Person": PersonSchema,
        "Playlist": PlaylistSchema,
        "PreviewFile": PreviewFileSchema,
        "Project": ProjectSchema,
        "ProjectStatus": ProjectStatusSchema,
        "ScheduleItem": ScheduleItemSchema,
        "SearchFilter": SearchFilterSchema,
        "Sequence": SequenceSchema,
        "Shot": ShotSchema,
        "Software": SoftwareSchema,
        "StatusAutomation": StatusAutomationSchema,
        "SubscriptionToNotifications": SubscriptionToNotificationsSchema,
        "Studio": StudioSchema,
        "Task": TaskSchema,
        "TaskStatus": TaskStatusSchema,
        "TaskType": TaskTypeSchema,
        "TimeSpent": TimeSpentSchema,
        "WorkingFile": WorkingFileSchema,
    },
}


def configure_openapi_route(app, swagger_instance):
    @app.route("/openapi.json")
    def openapi_spec():
        api_spec = swagger_instance.get_apispecs("openapi")

        json_path = os.path.join(app.root_path, "openapi-code-samples.json")
        with open(json_path, "r") as f:
            code_samples_spec = json.load(f)

        merged_api_spec = deepcopy(api_spec)

        api_paths = merged_api_spec.setdefault("paths", {})
        code_paths = code_samples_spec.get("paths", {})

        for path, methods in code_paths.items():
            api_path_item = api_paths.setdefault(path, {})

            for method, method_spec in methods.items():
                api_method_spec = api_path_item.setdefault(method, {})
                api_method_spec.update(method_spec)

        return jsonify(merged_api_spec)
