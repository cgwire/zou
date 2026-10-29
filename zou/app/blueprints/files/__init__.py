from flask import Blueprint

from zou.app.blueprints.files.resources import (
    CommentWorkingFileResource,
    EntityOutputFilePathResource,
    EntityOutputFilesResource,
    EntityOutputTypeOutputFilesResource,
    EntityOutputTypesResource,
    EntityWorkingFilesResource,
    FileResource,
    GetNextEntityOutputFileRevisionResource,
    GetNextInstanceOutputFileRevisionResource,
    GuessFromPathResource,
    InstanceOutputFilePathResource,
    InstanceOutputFilesResource,
    InstanceOutputTypeOutputFilesResource,
    InstanceOutputTypesResource,
    LastEntityOutputFilesResource,
    LastInstanceOutputFilesResource,
    LastWorkingFilesResource,
    ModifiedFileResource,
    NewEntityOutputFileResource,
    NewInstanceOutputFileResource,
    NewWorkingFileResource,
    ProjectOutputFilesResource,
    TaskWorkingFilesResource,
    OutputFileFileResource,
    WorkingFileFileResource,
    WorkingFilePathResource,
)
from zou.app.utils.api import configure_api_from_blueprint

routes = [
    ("/data/files/<file_id>", FileResource),
    ("/data/tasks/<task_id>/working-files", TaskWorkingFilesResource),
    ("/data/tasks/<task_id>/working-files/new", NewWorkingFileResource),
    (
        "/data/tasks/<task_id>/working-files/last-revisions",
        LastWorkingFilesResource,
    ),
    ("/data/tasks/<task_id>/working-file-path", WorkingFilePathResource),
    (
        "/data/asset-instances/<asset_instance_id>"
        "/entities/<temporal_entity_id>/output-files/new",
        NewInstanceOutputFileResource,
    ),
    (
        "/data/asset-instances/<asset_instance_id>"
        "/entities/<temporal_entity_id>/output-files/next-revision",
        GetNextInstanceOutputFileRevisionResource,
    ),
    (
        "/data/asset-instances/<asset_instance_id>"
        "/entities/<temporal_entity_id>/output-files/last-revisions",
        LastInstanceOutputFilesResource,
    ),
    (
        "/data/asset-instances/<asset_instance_id>"
        "/entities/<temporal_entity_id>/output-types",
        InstanceOutputTypesResource,
    ),
    (
        "/data/asset-instances/<asset_instance_id>"
        "/entities/<temporal_entity_id>/output-types"
        "/<output_type_id>/output-files",
        InstanceOutputTypeOutputFilesResource,
    ),
    (
        "/data/asset-instances/<asset_instance_id>"
        "/entities/<temporal_entity_id>/output-file-path",
        InstanceOutputFilePathResource,
    ),
    ("/data/entities/<entity_id>/working-files", EntityWorkingFilesResource),
    (
        "/data/entities/<entity_id>/output-files/new",
        NewEntityOutputFileResource,
    ),
    (
        "/data/entities/<entity_id>/output-files/next-revision",
        GetNextEntityOutputFileRevisionResource,
    ),
    (
        "/data/entities/<entity_id>/output-files/last-revisions",
        LastEntityOutputFilesResource,
    ),
    ("/data/entities/<entity_id>/output-types", EntityOutputTypesResource),
    (
        "/data/entities/<entity_id>/output-types/<output_type_id>/output-files",
        EntityOutputTypeOutputFilesResource,
    ),
    ("/data/entities/<entity_id>/output-files", EntityOutputFilesResource),
    ("/data/projects/<project_id>/output-files", ProjectOutputFilesResource),
    (
        "/data/asset-instances/<asset_instance_id>/output-files",
        InstanceOutputFilesResource,
    ),
    (
        "/data/entities/<entity_id>/output-file-path",
        EntityOutputFilePathResource,
    ),
    ("/data/entities/guess-from-path", GuessFromPathResource),
    # Deprecated snake_case alias, kept because gazu still posts it.
    ("/data/entities/guess_from_path", GuessFromPathResource),
    (
        "/data/working-files/<working_file_id>/file",
        WorkingFileFileResource,
    ),
    (
        "/data/output-files/<output_file_id>/file",
        OutputFileFileResource,
    ),
    (
        "/actions/working-files/<working_file_id>/comment",
        CommentWorkingFileResource,
    ),
    (
        "/actions/working-files/<working_file_id>/modified",
        ModifiedFileResource,
    ),
]

blueprint = Blueprint("files", "files")
api = configure_api_from_blueprint(blueprint, routes)
