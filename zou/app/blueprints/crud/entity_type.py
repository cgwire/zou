from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource

from zou.app.models.entity_type import EntityType
from zou.app.utils import events
from zou.app.services import entities_service, assets_service


class EntityTypesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, EntityType)

    def all_entries(self, query=None, relations=False):
        if query is None:
            query = self.model.query

        return [
            asset_type.serialize(relations=relations)
            for asset_type in query.all()
        ]

    def check_read_permissions(self):
        return True

    def emit_create_event(self, instance_dict):
        events.emit("asset-type:new", {"asset_type_id": instance_dict["id"]})

    def update_data(self, data):
        # Handle asset types the task type is dedicated to
        data["task_types"] = assets_service.get_task_types_from_asset_type(
            data
        )

        return data

    def post_creation(self, instance):
        assets_service.clear_asset_type_cache()
        return instance.serialize(relations=True)


class EntityTypeResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, EntityType)

    def check_read_permissions(self, instance):
        return True

    def emit_update_event(self, instance_dict):
        events.emit(
            "asset-type:update", {"asset_type_id": instance_dict["id"]}
        )

    def emit_delete_event(self, instance_dict):
        events.emit(
            "asset-type:delete", {"asset_type_id": instance_dict["id"]}
        )

    def update_data(self, data, instance_id):
        # Handle task types dedicated task type is dedicated to
        data["task_types"] = assets_service.get_task_types_from_asset_type(
            data
        )

        return data

    def post_update(self, instance_dict):
        entities_service.clear_entity_type_cache(instance_dict["id"])
        assets_service.clear_asset_type_cache()
        instance_dict["task_types"] = [
            str(task_types.id) for task_types in self.instance.task_types
        ]
        return instance_dict

    def post_delete(self, instance_dict):
        entities_service.clear_entity_type_cache(instance_dict["id"])
        assets_service.clear_asset_type_cache()
        return instance_dict
