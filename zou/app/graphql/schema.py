import graphene
from graphene_sqlalchemy import SQLAlchemyObjectType

from zou.app.models.software import Software as SoftwareModel
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
from zou.app.graphql.resolvers import DefaultResolver, EntityResolver, EntityChildResolver, EntityParentResolver
from zou.app.graphql import converters

class Software(SQLAlchemyObjectType):
    class Meta:
        model = SoftwareModel

class PreviewFile(SQLAlchemyObjectType):
    class Meta:
        model = PreviewFileModel

class TaskType(SQLAlchemyObjectType):
    class Meta:
        model = TaskTypeModel

class TaskStatus(SQLAlchemyObjectType):
    class Meta:
        model = TaskStatusModel

class Task(SQLAlchemyObjectType):
    class Meta:
        model = TaskModel

class EntityType(SQLAlchemyObjectType):
    class Meta:
        model = EntityTypeModel

class Shot(SQLAlchemyObjectType):
    class Meta:
        model = EntityModel

class Sequence(SQLAlchemyObjectType):
    class Meta:
        model = EntityModel

    shots = graphene.List(Shot, resolver=EntityChildResolver(Shot, "Shot"))

class ProjectStatus(SQLAlchemyObjectType):
    class Meta:
        model = ProjectStatusModel

class Project(SQLAlchemyObjectType):
    class Meta:
        model = ProjectModel

    sequences = graphene.List(Sequence, resolver=EntityResolver(Sequence, "Sequence"))
    assets = graphene.List(Sequence, resolver=EntityResolver(Sequence, "Asset"))

class AttachmentFile(SQLAlchemyObjectType):
    class Meta:
        model = AttachmentFileModel

class Comment(SQLAlchemyObjectType):
    class Meta:
        model = CommentModel

class Department(SQLAlchemyObjectType):
    class Meta:
        model = DepartmentModel

class Person(SQLAlchemyObjectType):
    class Meta:
        model = PersonModel

class Query(graphene.ObjectType):
    softwares = graphene.List(Software, resolver=DefaultResolver(Software))
    preview_files = graphene.List(PreviewFile, resolver=DefaultResolver(PreviewFile))
    task_types = graphene.List(TaskType, resolver=DefaultResolver(TaskType))
    task_status = graphene.List(TaskStatus, resolver=DefaultResolver(TaskStatus))
    tasks = graphene.List(Task, resolver=DefaultResolver(Task))
    entity_types = graphene.List(EntityType, resolver=DefaultResolver(EntityType))
    shots = graphene.List(Shot, resolver=EntityParentResolver(Shot, "Shot"))
    sequences = graphene.List(Sequence, resolver=EntityParentResolver(Sequence, "Sequence"))
    assets = graphene.List(Sequence, resolver=EntityParentResolver(Sequence, "Asset"))
    project_status = graphene.List(ProjectStatus, resolver=DefaultResolver(ProjectStatus))
    projects = graphene.List(Project, resolver=DefaultResolver(Project))
    attachment_files = graphene.List(AttachmentFile, resolver=DefaultResolver(AttachmentFile))
    comments = graphene.List(Comment, resolver=DefaultResolver(Comment))
    persons = graphene.List(Person, resolver=DefaultResolver(Person))

schema = graphene.Schema(query=Query)
