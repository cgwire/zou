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
    EntityResolver,
    EntityChildResolver,
    PreviewUrlResolver,
)
from zou.app.graphql.filter import FilterSet, test_dynamic
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
        filters=graphene.List(FilterSet, required=False),
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
        filters=graphene.List(FilterSet, required=False),
    )
    status = graphene.Field(
        TaskStatus,
        resolver=DefaultResolver(TaskStatusModel, "id", "task_status_id"),
        filters=graphene.List(FilterSet, required=False),
    )
    type = graphene.Field(
        TaskType,
        resolver=DefaultResolver(TaskStatusModel, "id", "task_type_id"),
        filters=graphene.List(FilterSet, required=False),
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
        filters=graphene.List(FilterSet, required=False),
    )


class Sequence(SQLAlchemyObjectType):
    class Meta:
        model = EntityModel

    shots = graphene.List(
        Shot,
        resolver=EntityChildResolver("Shot", EntityModel),
        filters=test_dynamic(EntityModel),
    )


class Asset(SQLAlchemyObjectType):
    class Meta:
        model = EntityModel

    tasks = graphene.List(
        Task,
        resolver=DefaultResolver(TaskModel, "entity_id"),
        filters=graphene.List(FilterSet, required=False),
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
        filters=graphene.List(FilterSet, required=False),
    )
    assets = graphene.List(
        Sequence,
        resolver=EntityResolver("Asset", EntityModel),
        filters=graphene.List(FilterSet, required=False),
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
        filters=graphene.List(FilterSet, required=False),
    )


class Query(graphene.ObjectType):
    softwares = graphene.List(
        Software,
        resolver=DefaultResolver(SoftwareModel),
        filters=graphene.List(FilterSet, required=False),
    )
    output_types = graphene.List(
        OutputType,
        resolver=DefaultResolver(OutputTypeModel),
        filters=graphene.List(FilterSet, required=False),
    )
    output_files = graphene.List(
        OutputFile,
        resolver=DefaultResolver(OutputFileModel),
        filters=graphene.List(FilterSet, required=False),
    )
    preview_files = graphene.List(
        PreviewFile,
        resolver=DefaultResolver(PreviewFileModel),
        filters=graphene.List(FilterSet, required=False),
    )
    task_types = graphene.List(
        TaskType,
        resolver=DefaultResolver(TaskTypeModel),
        filters=graphene.List(FilterSet, required=False),
    )
    task_status = graphene.List(
        TaskStatus,
        resolver=DefaultResolver(TaskStatusModel),
        filters=graphene.List(FilterSet, required=False),
    )
    tasks = graphene.List(
        Task,
        resolver=DefaultResolver(TaskModel),
        filters=graphene.List(FilterSet, required=False),
    )
    entity_types = graphene.List(
        EntityType,
        resolver=DefaultResolver(EntityTypeModel),
        filters=graphene.List(FilterSet, required=False),
    )
    shots = graphene.List(
        Shot,
        resolver=EntityResolver("Shot", EntityModel),
        filters=graphene.List(FilterSet, required=False),
    )
    sequences = graphene.List(
        Sequence,
        resolver=EntityResolver("Sequence", EntityModel),
        filters=graphene.List(FilterSet, required=False),
    )
    assets = graphene.List(
        Asset,
        resolver=EntityResolver("Asset", EntityModel),
        filters=graphene.List(FilterSet, required=False),
    )
    project_status = graphene.List(
        ProjectStatus,
        resolver=DefaultResolver(ProjectStatusModel),
        filters=graphene.List(FilterSet, required=False),
    )
    projects = graphene.List(
        Project,
        resolver=DefaultResolver(ProjectModel),
        filters=graphene.List(FilterSet, required=False),
    )
    attachment_files = graphene.List(
        AttachmentFile,
        resolver=DefaultResolver(AttachmentFileModel),
        filters=graphene.List(FilterSet, required=False),
    )
    comments = graphene.List(
        Comment,
        resolver=DefaultResolver(CommentModel),
        filters=graphene.List(FilterSet, required=False),
    )
    persons = graphene.List(
        Person,
        resolver=DefaultResolver(PersonModel),
        filters=graphene.List(FilterSet, required=False),
    )


schema = graphene.Schema(query=Query)
