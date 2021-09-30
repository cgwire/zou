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

class DefaultChildResolver(DefaultResolver):

    def __init__(self, graphql_type: ObjectType, model_type, foreign_key: str):
        self.graphql_type = graphql_type
        self.model_type = model_type
        self.foreign_key = foreign_key

    def get_query(self, root, info):
        query = self.graphql_type.get_query(info)
        if root is not None:
            query = query.filter(getattr(self.model_type, self.foreign_key) == root.id)
        return query

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
        if root is not None:
            query = query.filter(EntityModel.project_id == root.id)
        query = query.filter(EntityModel.entity_type_id == self.entity_type["id"])
        return query

class EntityChildResolver(EntityResolver):

    def get_query(self, root, info):
        query = self.graphql_type.get_query(info)
        if root is not None:
            query = query.filter(EntityModel.parent_id == root.id)
        query = query.filter(EntityModel.entity_type_id == self.entity_type["id"])
        return query

class PreviewUrlResolver(DefaultResolver):

    def __init__(self, lod: str):
        self.lod = lod
    
    def __call_(self, root, info, **kwargs):
        if root is None:
            return ""
        lod = self.lod if not kwargs.get("lod") else kwargs["lod"]
        if root.is_movie:
            return f"/pictures/{lod}/preview-files/{root.id}.{root.extension}"
        else:
            lod = self.lod if self.lod != "low" else "thumbnails"
            return f"/movies/{lod}/preview-files/{root.id}.{root.extension}"
