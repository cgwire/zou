import graphene
from graphene_sqlalchemy import SQLAlchemyObjectType

from zou.app.models.project import Project as ProjectModel
from zou.app.models.entity import Entity as EntityModel
from zou.app.models.task import Task as TaskModel
from zou.app.models.person import Person as PersonModel
from zou.app.graphql.resolvers import DefaultResolver, EntityResolver, EntityChildResolver, EntityParentResolver
from zou.app.graphql import converters

class Task(SQLAlchemyObjectType):
    class Meta:
        model = TaskModel

class Shot(SQLAlchemyObjectType):
    class Meta:
        model = EntityModel

class Sequence(SQLAlchemyObjectType):
    class Meta:
        model = EntityModel

    shots = graphene.List(Shot, resolver=EntityChildResolver(Shot, "Shot"))

class Project(SQLAlchemyObjectType):
    class Meta:
        model = ProjectModel

    sequences = graphene.List(Sequence, resolver=EntityResolver(Sequence, "Sequence"))
    assets = graphene.List(Sequence, resolver=EntityResolver(Sequence, "Asset"))

class Person(SQLAlchemyObjectType):
    class Meta:
        model = PersonModel

class Query(graphene.ObjectType):
    tasks = graphene.List(Task, resolver=DefaultResolver)
    shots = graphene.List(Shot, resolver=EntityParentResolver(Shot, "Shot"))
    sequences = graphene.List(Sequence, resolver=EntityParentResolver(Sequence, "Sequence"))
    assets = graphene.List(Sequence, resolver=EntityParentResolver(Sequence, "Asset"))
    projects = graphene.List(Project, resolver=DefaultResolver)
    persons = graphene.List(Person, resolver=DefaultResolver)

schema = graphene.Schema(query=Query)
