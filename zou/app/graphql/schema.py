import graphene
from graphene import relay
from graphene_sqlalchemy import SQLAlchemyObjectType, SQLAlchemyConnectionField
from sqlalchemy.orm import aliased
from sqlalchemy_utils import UUIDType, EmailType, LocaleType, TimezoneType
from graphene_sqlalchemy.converter import convert_sqlalchemy_type

from zou.app.models.person import Person as PersonModel
from zou.app.models.comment import Comment as CommentModel
from zou.app.models.project import Project as ProjectModel
from zou.app.models.entity import Entity as EntityModel

from zou.app import db

@convert_sqlalchemy_type.register(UUIDType)
def convert_uuid(type, column, registry=None):
    return graphene.ID

@convert_sqlalchemy_type.register(EmailType)
def convert_email(type, column, registry=None):
    return graphene.String

@convert_sqlalchemy_type.register(LocaleType)
def convert_locale(type, column, registry=None):
    return graphene.String

@convert_sqlalchemy_type.register(TimezoneType)
def convert_timezone(type, column, registry=None):
    return graphene.String

@convert_sqlalchemy_type.register(db.LargeBinary)
def convert_largebinary(type, column, registry=None):
    return graphene.String

class Person(SQLAlchemyObjectType):
    class Meta:
        model = PersonModel
        interfaces = (relay.Node, )

class Comment(SQLAlchemyObjectType):
    class Meta:
        model = CommentModel
        interfaces = (relay.Node, )

class Project(SQLAlchemyObjectType):
    class Meta:
        model = ProjectModel
        interfaces = (relay.Node, )

class Shot(SQLAlchemyObjectType):
    class Meta:
        model = EntityModel
        interfaces = (relay.Node, )

class Sequence(SQLAlchemyObjectType):
    class Meta:
        model = EntityModel

    shots = Shot()

    @staticmethod
    def resolve_shots(root, info, **kwargs):
        query = EntityModel.query
        query = (
            query.join(ProjectModel)
            .add_columns(Project.name)
        )
        return {"root": root, "info": info, "kwargs": kwargs, "data": query.all()}

class Query(graphene.ObjectType):
    node = relay.Node.Field()
    # Allows sorting over multiple columns, by default over the primary key
    comments = SQLAlchemyConnectionField(Comment.connection)
    persons = SQLAlchemyConnectionField(Person.connection)
    projects = SQLAlchemyConnectionField(Project.connection)
    sequences = SQLAlchemyConnectionField(Sequence.connection)
    shots = SQLAlchemyConnectionField(Shot.connection)
    shot = relay.Node.Field(Shot)

schema = graphene.Schema(query=Query)
