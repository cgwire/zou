from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.models.studio import Studio

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource

from zou.app.services import (
    task_types_service,
)


class StudiosResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Studio)

    def check_read_permissions(self, options=None):
        return True

    @jwt_required()
    @swag_from("openapi/StudiosResource_get.yml")
    def get(self):
        """
        Get studios
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/StudiosResource_post.yml")
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
    @swag_from("openapi/StudioResource_get.yml")
    def get(self, instance_id):
        """
        Get studio
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/StudioResource_put.yml")
    def put(self, instance_id):
        """
        Update studio
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/StudioResource_delete.yml")
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
