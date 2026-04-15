from flask import Blueprint
from zou.app.utils.api import configure_api_from_blueprint

from zou.app.blueprints.project_templates.resources import (
    ApplyProjectTemplateResource,
    ProjectTemplateAssetTypeResource,
    ProjectTemplateAssetTypesResource,
    ProjectTemplateBackgroundResource,
    ProjectTemplateBackgroundsResource,
    ProjectTemplateDefaultBackgroundResource,
    ProjectTemplateFromProjectResource,
    ProjectTemplateMetadataDescriptorsResource,
    ProjectTemplateStatusAutomationResource,
    ProjectTemplateStatusAutomationsResource,
    ProjectTemplateTaskStatusResource,
    ProjectTemplateTaskStatusesResource,
    ProjectTemplateTaskTypeResource,
    ProjectTemplateTaskTypesResource,
)

routes = [
    (
        "/data/project-templates/<template_id>/task-types",
        ProjectTemplateTaskTypesResource,
    ),
    (
        "/data/project-templates/<template_id>/task-types/<task_type_id>",
        ProjectTemplateTaskTypeResource,
    ),
    (
        "/data/project-templates/<template_id>/task-statuses",
        ProjectTemplateTaskStatusesResource,
    ),
    (
        "/data/project-templates/<template_id>/task-statuses/<task_status_id>",
        ProjectTemplateTaskStatusResource,
    ),
    (
        "/data/project-templates/<template_id>/asset-types",
        ProjectTemplateAssetTypesResource,
    ),
    (
        "/data/project-templates/<template_id>/asset-types/<asset_type_id>",
        ProjectTemplateAssetTypeResource,
    ),
    (
        "/data/project-templates/<template_id>/status-automations",
        ProjectTemplateStatusAutomationsResource,
    ),
    (
        "/data/project-templates/<template_id>/status-automations/<status_automation_id>",
        ProjectTemplateStatusAutomationResource,
    ),
    (
        "/data/project-templates/<template_id>/metadata-descriptors",
        ProjectTemplateMetadataDescriptorsResource,
    ),
    (
        "/data/project-templates/<template_id>/preview-background-files",
        ProjectTemplateBackgroundsResource,
    ),
    (
        "/data/project-templates/<template_id>/preview-background-files/<preview_background_file_id>",
        ProjectTemplateBackgroundResource,
    ),
    (
        "/data/project-templates/<template_id>/default-preview-background-file",
        ProjectTemplateDefaultBackgroundResource,
    ),
    (
        "/data/project-templates/from-project/<project_id>",
        ProjectTemplateFromProjectResource,
    ),
    (
        "/data/projects/<project_id>/apply-template/<template_id>",
        ApplyProjectTemplateResource,
    ),
]

blueprint = Blueprint("project_templates", "project_templates")
api = configure_api_from_blueprint(blueprint, routes)
