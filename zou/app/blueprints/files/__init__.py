from zou.app.utils.api import create_blueprint_for_api

from .resources import (
    WorkingFilePathResource,
    LastWorkingFilesResource,
    ModifiedFileResource,
    CommentWorkingFileResource,
    NewWorkingFileResource,
    TaskWorkingFilesResource,
    EntityWorkingFilesResource,
    EntityOutputFilePathResource,
    GetNextEntityOutputFileRevisionResource,
    NewEntityOutputFileResource,
    LastEntityOutputFilesResource,
    EntityOutputTypesResource,
    EntityOutputTypeOutputFilesResource,
    InstanceOutputFilePathResource,
    NewInstanceOutputFileResource,
    GetNextInstanceOutputFileRevisionResource,
    LastInstanceOutputFilesResource,
    InstanceOutputTypesResource,
    InstanceOutputTypeOutputFilesResource,
    EntityOutputFilesResource,
    InstanceOutputFilesResource,
    SetTreeResource,
    FileResource,
    WorkingFileFileResource,
    GuessFromPathResource,
)

routes = [
    ("/data/files/<uuid:file_id>", FileResource),
    ("/data/tasks/<uuid:task_id>/working-files", TaskWorkingFilesResource),
    ("/data/tasks/<uuid:task_id>/working-files/new", NewWorkingFileResource),
    (
        "/data/tasks/<uuid:task_id>/working-files/last-revisions",
        LastWorkingFilesResource,
    ),
    ("/data/tasks/<uuid:task_id>/working-file-path", WorkingFilePathResource),
    (
        "/data/asset-instances/<uuid:asset_instance_id>"
        "/entities/<uuid:temporal_entity_id>/output-files/new",
        NewInstanceOutputFileResource,
    ),
    (
        "/data/asset-instances/<uuid:asset_instance_id>"
        "/entities/<uuid:temporal_entity_id>/output-files/next-revision",
        GetNextInstanceOutputFileRevisionResource,
    ),
    (
        "/data/asset-instances/<uuid:asset_instance_id>"
        "/entities/<uuid:temporal_entity_id>/output-files/last-revisions",
        LastInstanceOutputFilesResource,
    ),
    (
        "/data/asset-instances/<uuid:asset_instance_id>"
        "/entities/<uuid:temporal_entity_id>/output-types",
        InstanceOutputTypesResource,
    ),
    (
        "/data/asset-instances/<uuid:asset_instance_id>"
        "/entities/<uuid:temporal_entity_id>/output-types"
        "/<uuid:output_type_id>/output-files",
        InstanceOutputTypeOutputFilesResource,
    ),
    (
        "/data/asset-instances/<uuid:asset_instance_id>"
        "/entities/<uuid:temporal_entity_id>/output-file-path",
        InstanceOutputFilePathResource,
    ),
    (
        "/data/entities/<uuid:entity_id>/working-files",
        EntityWorkingFilesResource,
    ),
    (
        "/data/entities/<uuid:entity_id>/output-files/new",
        NewEntityOutputFileResource,
    ),
    (
        "/data/entities/<uuid:entity_id>/output-files/next-revision",
        GetNextEntityOutputFileRevisionResource,
    ),
    (
        "/data/entities/<uuid:entity_id>/output-files/last-revisions",
        LastEntityOutputFilesResource,
    ),
    (
        "/data/entities/<uuid:entity_id>/output-types",
        EntityOutputTypesResource,
    ),
    (
        "/data/entities/<uuid:entity_id>/output-types/<uuid:output_type_id>/output-files",
        EntityOutputTypeOutputFilesResource,
    ),
    (
        "/data/entities/<uuid:entity_id>/output-files",
        EntityOutputFilesResource,
    ),
    (
        "/data/asset-instances/<uuid:asset_instance_id>/output-files",
        InstanceOutputFilesResource,
    ),
    (
        "/data/entities/<uuid:entity_id>/output-file-path",
        EntityOutputFilePathResource,
    ),
    ("/data/entities/guess_from_path", GuessFromPathResource),
    (
        "/data/working-files/<uuid:working_file_id>/file",
        WorkingFileFileResource,
    ),
    ("/actions/projects/<uuid:project_id>/set-file-tree", SetTreeResource),
    (
        "/actions/working-files/<uuid:working_file_id>/comment",
        CommentWorkingFileResource,
    ),
    (
        "/actions/working-files/<uuid:working_file_id>/modified",
        ModifiedFileResource,
    ),
]

blueprint = create_blueprint_for_api("files", routes)
