from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource

from zou.app.models.entity_type import EntityType
from zou.app.utils import events
from zou.app.services import (
    entity_types_service,
)

from zou.app.exceptions import WrongParameterException


class EntityTypesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, EntityType)

    @jwt_required()
    @swag_from("openapi/EntityTypesResource_get.yml")
    def get(self):
        """
        Get entity types
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/EntityTypesResource_post.yml")
    def post(self):
        """
        Create entity type
        """
        return super().post()

    def all_entries(self, query=None, relations=False):
        if query is None:
            query = self.model.query

        return [
            asset_type.serialize(relations=relations)
            for asset_type in query.all()
        ]

    def check_read_permissions(self, options=None):
        return True

    def emit_create_event(self, instance_dict):
        events.emit("asset-type:new", {"asset_type_id": instance_dict["id"]})

    def post_creation(self, instance):
        entity_types_service.clear_asset_type_cache()
        return instance.serialize(relations=True)

    def check_creation_integrity(self, data):
        entity_type = EntityType.query.filter(
            EntityType.name.ilike(data.get("name", ""))
        ).first()
        if entity_type is not None:
            raise WrongParameterException(
                "Entity type with this name already exists"
            )
        return data


class EntityTypeResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, EntityType)

    def check_read_permissions(self, instance):
        return True

    @jwt_required()
    @swag_from("openapi/EntityTypeResource_get.yml")
    def get(self, instance_id):
        """
        Get entity type
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/EntityTypeResource_put.yml")
    def put(self, instance_id):
        """
        Update entity type
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/EntityTypeResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete entity type
        """
        return super().delete(instance_id)

    def emit_update_event(self, instance_dict):
        events.emit(
            "asset-type:update", {"asset_type_id": instance_dict["id"]}
        )

    def emit_delete_event(self, instance_dict):
        events.emit(
            "asset-type:delete", {"asset_type_id": instance_dict["id"]}
        )

    def post_update(self, instance_dict, data):
        entity_types_service.clear_entity_type_cache(instance_dict["id"])
        entity_types_service.clear_asset_type_cache(instance_dict["id"])
        instance_dict["task_types"] = [
            str(task_types.id) for task_types in self.instance.task_types
        ]
        return instance_dict

    def post_delete(self, instance_dict):
        entity_types_service.clear_entity_type_cache(instance_dict["id"])
        entity_types_service.clear_asset_type_cache(instance_dict["id"])
        return instance_dict
