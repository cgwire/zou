from zou.app import db
from zou.app.models.entity import Entity as EntityModel
from zou.app.services import (
    entities_service,
)


class DefaultResolver:
    def __init__(
        self,
        model_type: db.Model = None,
        foreign_key: str = "",
        parent_key: str = "id",
        query_all: bool = True,
    ):
        self.model_type = model_type
        self.foreign_key = foreign_key
        self.parent_key = parent_key
        self.query_all = query_all

    @staticmethod
    def add_filter(a, b, operator):
        if operator == "eq":
            return a == b
        elif operator == "ne":
            return a != b
        elif operator == "lt":
            return a < b
        elif operator == "gt":
            return a > b

    def get_query(self, root):
        query = self.model_type.query
        if all([root, self.model_type, self.foreign_key]):
            query = query.filter(
                getattr(self.model_type, self.foreign_key)
                == getattr(root, self.parent_key)
            )
        return query

    def __call__(self, root, info, **kwargs):
        query = self.get_query(root)

        for filter_set in kwargs.get("filters", []):
            for filter in filter_set.get("filters", []):
                query = query.filter(
                    self.add_filter(
                        getattr(self.model_type, filter_set["field"]),
                        filter["filter_value"],
                        filter["filter_type"],
                    )
                )

        if self.query_all:
            return query.all()
        else:
            return query.first()


class EntityResolver(DefaultResolver):
    def __init__(self, entity_type: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.entity_type_name = entity_type
        self.model_type = EntityModel
        self.foreign_key = "project_id"

    @property
    def entity_type(self):
        entity_type = entities_service.get_entity_type_by_name(
            self.entity_type_name
        )

        if entity_type is None:
            raise KeyError("Invalid entity type name")
        return entity_type

    def get_query(self, root):
        query = super().get_query(root)
        query = query.filter(
            self.model_type.entity_type_id == self.entity_type["id"]
        )
        return query


class EntityChildResolver(EntityResolver):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.foreign_key = "parent_id"


class PreviewUrlResolver(DefaultResolver):
    def __init__(self, lod: str):
        self.lod = lod

    def __call__(self, root, info, **kwargs):
        if root is None:
            return ""
        lod = self.lod if not kwargs.get("lod") else kwargs["lod"]
        if root.is_movie:
            return f"/movies/{lod}/preview-files/{root.id}.{root.extension}"
        else:
            return f"/pictures/{lod}/preview-files/{root.id}.{root.extension}"
