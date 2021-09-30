from graphene.types.objecttype import ObjectType
from zou.app.models.entity import Entity as EntityModel
from zou.app.services import (
    entities_service,
)

class DefaultResolver():

    def __init__(self, graphql_type: ObjectType):
        self.graphql_type = graphql_type

    def get_query(self, root, info):
        return self.graphql_type.get_query(info)

    def __call__(self, root, info, **kwargs):
        query = self.get_query(root, info)
        # TODO: Implement dynamic filters
        return query.all()

class EntityResolver(DefaultResolver):

    def __init__(self, graphql_type: ObjectType, entity_type: str):
        self.graphql_type = graphql_type
        self.entity_type_name = entity_type

    @property
    def entity_type(self):
        entity_type = entities_service.get_entity_type_by_name(self.entity_type_name)

        if entity_type is None:
            raise KeyError("Invalid entity type name")
        return entity_type

    def get_query(self, root, info):
        query = self.graphql_type.get_query(info)
        query = query.filter(EntityModel.project_id == root.id)
        query = query.filter(EntityModel.entity_type_id == self.entity_type["id"])
        return query

class EntityParentResolver(EntityResolver):

    def get_query(self, root, info):
        query = self.graphql_type.get_query(info)
        query = query.filter(EntityModel.entity_type_id == self.entity_type["id"])
        return query

class EntityChildResolver(EntityResolver):

    def get_query(self, root, info):
        query = self.graphql_type.get_query(info)
        query = query.filter(EntityModel.parent_id == root.id)
        query = query.filter(EntityModel.entity_type_id == self.entity_type["id"])
        return query
