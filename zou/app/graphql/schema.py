import graphene
from graphene_sqlalchemy import SQLAlchemyObjectType

from zou.app.models.software import Software as SoftwareModel
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
from zou.app.models.attachment_file import AttachmentFile as AttachmentFileModel
from zou.app.models.comment import Comment as CommentModel
from zou.app.models.department import Department as DepartmentModel
from zou.app.models.person import Person as PersonModel
from zou.app.graphql.resolvers import DefaultResolver, EntityResolver, EntityChildResolver, PreviewUrlResolver
from zou.app.graphql.filter import FilterSet
from zou.app.graphql import converters

class Software(SQLAlchemyObjectType):
    class Meta:
        model = SoftwareModel

class OutputType(SQLAlchemyObjectType):
    class Meta:
        model = OutputTypeModel

class OutputFile(SQLAlchemyObjectType):
    class Meta:
        model = OutputFileModel

class PreviewFile(SQLAlchemyObjectType):
    class Meta:
        model = PreviewFileModel
        
    file_url = graphene.Field(graphene.String, resolver=PreviewUrlResolver(lod="originals"), args={"lod": graphene.String(required=False)})

class Comment(SQLAlchemyObjectType):
    class Meta:
        model = CommentModel

    person = graphene.Field("zou.app.graphql.schema.Person", resolver=DefaultResolver(PersonModel, "id", "person_id"), filters=FilterSet(required=False))

class TaskType(SQLAlchemyObjectType):
    class Meta:
        model = TaskTypeModel

class TaskStatus(SQLAlchemyObjectType):
    class Meta:
        model = TaskStatusModel

class Task(SQLAlchemyObjectType):
    class Meta:
        model = TaskModel

    previews = graphene.List(PreviewFile, resolver=DefaultResolver(PreviewFileModel, "task_id"))
    status = graphene.Field(TaskStatus, resolver=DefaultResolver(TaskStatusModel, "id", "task_status_id"))
    type = graphene.Field(TaskType, resolver=DefaultResolver(TaskStatusModel, "id", "task_type_id"))

class EntityType(SQLAlchemyObjectType):
    class Meta:
        model = EntityTypeModel

class Shot(SQLAlchemyObjectType):
    class Meta:
        model = EntityModel
    
    tasks = graphene.List(Task, resolver=DefaultResolver(TaskModel, "entity_id"))

class Sequence(SQLAlchemyObjectType):
    class Meta:
        model = EntityModel

    shots = graphene.List(Shot, resolver=EntityChildResolver("Shot", EntityModel))

class Asset(SQLAlchemyObjectType):
    class Meta:
        model = EntityModel
    
    tasks = graphene.List(Task, resolver=DefaultResolver(TaskModel, "entity_id"))

class ProjectStatus(SQLAlchemyObjectType):
    class Meta:
        model = ProjectStatusModel

class Project(SQLAlchemyObjectType):
    class Meta:
        model = ProjectModel

    sequences = graphene.List(Sequence, resolver=EntityResolver("Sequence", EntityModel))
    assets = graphene.List(Sequence, resolver=EntityResolver("Asset", EntityModel))

class AttachmentFile(SQLAlchemyObjectType):
    class Meta:
        model = AttachmentFileModel

class Department(SQLAlchemyObjectType):
    class Meta:
        model = DepartmentModel

class Person(SQLAlchemyObjectType):
    class Meta:
        model = PersonModel

    comments = graphene.List(Task, resolver=DefaultResolver(CommentModel, "person_id"))

class Query(graphene.ObjectType):
    softwares = graphene.List(Software, resolver=DefaultResolver(SoftwareModel))
    output_types = graphene.List(OutputType, resolver=DefaultResolver(OutputTypeModel))
    output_files = graphene.List(OutputFile, resolver=DefaultResolver(OutputFileModel))
    preview_files = graphene.List(PreviewFile, resolver=DefaultResolver(PreviewFileModel))
    task_types = graphene.List(TaskType, resolver=DefaultResolver(TaskTypeModel))
    task_status = graphene.List(TaskStatus, resolver=DefaultResolver(TaskStatusModel))
    tasks = graphene.List(Task, resolver=DefaultResolver(TaskModel))
    entity_types = graphene.List(EntityType, resolver=DefaultResolver(EntityTypeModel))
    shots = graphene.List(Shot, resolver=EntityResolver("Shot", EntityModel))
    sequences = graphene.List(Sequence, resolver=EntityResolver("Sequence", EntityModel))
    assets = graphene.List(Asset, resolver=EntityResolver("Asset", EntityModel))
    project_status = graphene.List(ProjectStatus, resolver=DefaultResolver(ProjectStatusModel))
    projects = graphene.List(Project, resolver=DefaultResolver(ProjectModel))
    attachment_files = graphene.List(AttachmentFile, resolver=DefaultResolver(AttachmentFileModel))
    comments = graphene.List(Comment, resolver=DefaultResolver(CommentModel))
    persons = graphene.List(Person, resolver=DefaultResolver(PersonModel))

schema = graphene.Schema(query=Query)
