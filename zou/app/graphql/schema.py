import graphene
from graphene import relay
from graphene_sqlalchemy import SQLAlchemyObjectType, SQLAlchemyConnectionField
from zou.app.models.person import Person as PersonModel
from zou.app.models.comment import Comment as CommentModel

class Person(SQLAlchemyObjectType):
    class Meta:
        model = PersonModel
        interfaces = (relay.Node, )

class Comment(SQLAlchemyObjectType):
    class Meta:
        model = CommentModel
        interfaces = (relay.Node, )

class Query(graphene.ObjectType):
    node = relay.Node.Field()
    # Allows sorting over multiple columns, by default over the primary key
    all_comments = SQLAlchemyConnectionField(Comment.connection)
    # Allows sorting over multiple columns, by default over the primary key
    all_persons = SQLAlchemyConnectionField(Person.connection)

schema = graphene.Schema(query=Query)
