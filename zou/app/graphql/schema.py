import graphene
from graphene_sqlalchemy import SQLAlchemyObjectType

from zou.app.models.software import Software as SoftwareModel
from zou.app.models.working_file import WorkingFile as WorkingFileModel
from zou.app.models.output_type import OutputType as OutputTypeModel
from zou.app.models.output_file import OutputFile as OutputFileModel
from zou.app.models.preview_file import PreviewFile as PreviewFileModel
from zou.app.models.task_type import TaskType as TaskTypeModel
from zou.app.models.task_status import TaskStatus as TaskStatusModel
from zou.app.models.task import Task as TaskModel
from zou.app.models.entity_type import EntityType as EntityTypeModel
from zou.app.models.entity import Entity as EntityModel
from zou.app.models.project_status import ProjectStatus as ProjectStatusModel
from zou.app.models.project import Project as ProjectModel
from zou.app.models.attachment_file import (
    AttachmentFile as AttachmentFileModel,
)
from zou.app.models.comment import Comment as CommentModel
from zou.app.models.department import Department as DepartmentModel
from zou.app.models.person import Person as PersonModel
from zou.app.graphql.resolvers import (
    DefaultResolver,
    IDResolver,
    EntityResolver,
    IDEntityResolver,
    EntityChildResolver,
    PreviewUrlResolver,
)
from zou.app.graphql import converters


class Software(SQLAlchemyObjectType):
    class Meta:
        model = SoftwareModel


class WorkingFile(SQLAlchemyObjectType):
    class Meta:
        model = WorkingFileModel


class OutputType(SQLAlchemyObjectType):
    class Meta:
        model = OutputTypeModel


class OutputFile(SQLAlchemyObjectType):
    class Meta:
        model = OutputFileModel


class PreviewFile(SQLAlchemyObjectType):
    class Meta:
        model = PreviewFileModel

    file_url = graphene.Field(
        graphene.String,
        resolver=PreviewUrlResolver(lod="originals"),
        lod=graphene.String(required=False),
    )


class Comment(SQLAlchemyObjectType):
    class Meta:
        model = CommentModel

    person = graphene.Field(
        "zou.app.graphql.schema.Person",
        resolver=DefaultResolver(PersonModel, "id", "person_id"),
    )


class TaskType(SQLAlchemyObjectType):
    class Meta:
        model = TaskTypeModel


class TaskStatus(SQLAlchemyObjectType):
    class Meta:
        model = TaskStatusModel


class Task(SQLAlchemyObjectType):
    class Meta:
        model = TaskModel

    previews = graphene.List(
        PreviewFile,
        resolver=DefaultResolver(PreviewFileModel, "task_id"),
    )
    status = graphene.Field(
        TaskStatus,
        resolver=DefaultResolver(
            TaskStatusModel, "id", "task_status_id", query_all=False
        ),
    )
    type = graphene.Field(
        TaskType,
        resolver=DefaultResolver(
            TaskTypeModel, "id", "task_type_id", query_all=False
        ),
    )


class EntityType(SQLAlchemyObjectType):
    class Meta:
        model = EntityTypeModel


class Shot(SQLAlchemyObjectType):
    class Meta:
        model = EntityModel

    tasks = graphene.List(
        Task,
        resolver=DefaultResolver(TaskModel, "entity_id"),
    )
    type = graphene.Field(
        EntityType,
        resolver=DefaultResolver(
            EntityTypeModel, "id", "entity_type_id", query_all=False
        ),
    )
    preview_file_id = graphene.Field(
        PreviewFile,
        resolver=DefaultResolver(
            PreviewFileModel, "id", "preview_file_id", query_all=False
        ),
    )


class Sequence(SQLAlchemyObjectType):
    class Meta:
        model = EntityModel

    shots = graphene.List(
        Shot,
        resolver=EntityChildResolver("Shot", EntityModel),
    )


class Asset(SQLAlchemyObjectType):
    class Meta:
        model = EntityModel

    tasks = graphene.List(
        Task,
        resolver=DefaultResolver(TaskModel, "entity_id"),
    )
    preview_file_id = graphene.Field(
        PreviewFile,
        resolver=DefaultResolver(
            PreviewFileModel, "id", "preview_file_id", query_all=False
        ),
    )


class ProjectStatus(SQLAlchemyObjectType):
    class Meta:
        model = ProjectStatusModel


class Project(SQLAlchemyObjectType):
    class Meta:
        model = ProjectModel

    sequences = graphene.List(
        Sequence,
        resolver=EntityResolver("Sequence", EntityModel),
    )
    assets = graphene.List(
        Sequence,
        resolver=EntityResolver("Asset", EntityModel),
    )


class AttachmentFile(SQLAlchemyObjectType):
    class Meta:
        model = AttachmentFileModel


class Department(SQLAlchemyObjectType):
    class Meta:
        model = DepartmentModel


class Person(SQLAlchemyObjectType):
    class Meta:
        model = PersonModel

    comments = graphene.List(
        Comment,
        resolver=DefaultResolver(CommentModel, "person_id"),
    )


class Query(graphene.ObjectType):
    software = graphene.Field(
        Software,
        resolver=IDResolver(SoftwareModel),
        id=graphene.String(),
    )
    softwares = graphene.List(
        Software,
        resolver=DefaultResolver(SoftwareModel),
    )
    output_type = graphene.Field(
        OutputType,
        resolver=DefaultResolver(OutputTypeModel),
        id=graphene.String(),
    )
    output_types = graphene.List(
        OutputType,
        resolver=DefaultResolver(OutputTypeModel),
    )
    output_file = graphene.Field(
        OutputFile,
        resolver=DefaultResolver(OutputFileModel),
        id=graphene.String(),
    )
    output_files = graphene.List(
        OutputFile,
        resolver=DefaultResolver(OutputFileModel),
    )
    preview_file = graphene.Field(
        PreviewFile,
        resolver=DefaultResolver(PreviewFileModel),
        id=graphene.String(),
    )
    preview_files = graphene.List(
        PreviewFile,
        resolver=DefaultResolver(PreviewFileModel),
    )
    task_type = graphene.Field(
        TaskType,
        resolver=DefaultResolver(TaskTypeModel),
        id=graphene.String(),
    )
    task_types = graphene.List(
        TaskType,
        resolver=DefaultResolver(TaskTypeModel),
    )
    task_status = graphene.Field(
        TaskStatus,
        resolver=DefaultResolver(TaskStatusModel),
        id=graphene.String(),
    )
    task_statuses = graphene.List(
        TaskStatus,
        resolver=DefaultResolver(TaskStatusModel),
    )
    task = graphene.Field(
        Task,
        resolver=DefaultResolver(TaskModel),
        id=graphene.String(),
    )
    tasks = graphene.List(
        Task,
        resolver=DefaultResolver(TaskModel),
    )
    entity_type = graphene.Field(
        EntityType,
        resolver=DefaultResolver(EntityTypeModel),
        id=graphene.String(),
    )
    entity_types = graphene.List(
        EntityType,
        resolver=DefaultResolver(EntityTypeModel),
    )
    shot = graphene.Field(
        Shot,
        resolver=IDEntityResolver("Shot", EntityModel),
        id=graphene.String(),
    )
    shots = graphene.List(
        Shot,
        resolver=EntityResolver("Shot", EntityModel),
    )
    sequence = graphene.Field(
        Sequence,
        resolver=IDEntityResolver("Sequence", EntityModel),
        id=graphene.String(),
    )
    sequences = graphene.List(
        Sequence,
        resolver=EntityResolver("Sequence", EntityModel),
    )
    asset = graphene.Field(
        Asset,
        resolver=IDEntityResolver("Asset", EntityModel),
        id=graphene.String(),
    )
    assets = graphene.List(
        Asset,
        resolver=EntityResolver("Asset", EntityModel),
    )
    project_status = graphene.Field(
        ProjectStatus,
        resolver=IDResolver(ProjectStatusModel),
        id=graphene.String(),
    )
    project_statuses = graphene.List(
        ProjectStatus,
        resolver=DefaultResolver(ProjectStatusModel),
    )
    project = graphene.Field(
        Project,
        resolver=IDResolver(ProjectModel),
        id=graphene.String(),
    )
    projects = graphene.List(
        Project,
        resolver=DefaultResolver(ProjectModel),
    )
    attachment_file = graphene.Field(
        Comment,
        resolver=IDResolver(AttachmentFileModel),
        id=graphene.String(),
    )
    attachment_files = graphene.List(
        AttachmentFile,
        resolver=DefaultResolver(AttachmentFileModel),
    )
    comment = graphene.Field(
        Comment,
        resolver=IDResolver(CommentModel),
        id=graphene.String(),
    )
    comments = graphene.List(
        Comment,
        resolver=DefaultResolver(CommentModel),
    )
    person = graphene.Field(
        Person,
        resolver=IDResolver(PersonModel),
        id=graphene.String(),
    )
    persons = graphene.List(
        Person,
        resolver=DefaultResolver(PersonModel),
    )


schema = graphene.Schema(query=Query, auto_camelcase=False)
