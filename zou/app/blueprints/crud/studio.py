from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.models.studio import Studio
from zou.app.services import (
    task_types_service,
)
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/studio.yml")


class StudiosResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Studio)

    def check_read_permissions(self, options=None):
        return True

    @jwt_required()
    @swag_from(SPECS["StudiosResource_get"])
    def get(self):
        """
        Get studios
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["StudiosResource_post"])
    def post(self):
        """
        Create studio
        """
        return super().post()

    def post_creation(self, instance):
        task_types_service.clear_studio_cache(str(instance.id))
        return instance.serialize(relations=True)


class StudioResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Studio)

    def check_read_permissions(self, instance):
        return True

    @jwt_required()
    @swag_from(SPECS["StudioResource_get"])
    def get(self, instance_id):
        """
        Get studio
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["StudioResource_put"])
    def put(self, instance_id):
        """
        Update studio
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["StudioResource_delete"])
    def delete(self, instance_id):
        """
        Delete studio
        """
        return super().delete(instance_id)

    def post_update(self, instance_dict, data):
        task_types_service.clear_studio_cache(instance_dict["id"])
        return instance_dict

    def post_delete(self, instance_dict):
        task_types_service.clear_studio_cache(instance_dict["id"])
        return instance_dict
