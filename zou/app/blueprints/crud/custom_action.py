from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.models.custom_action import CustomAction

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource
from zou.app.exceptions import WrongParameterException

from zou.app.services import (
    custom_actions_service,
    permissions_service,
    user_service,
)


class CustomActionsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, CustomAction)

    def check_read_permissions(self, options=None):
        permissions_service.block_access_to_vendor()
        return True

    def check_creation_integrity(self, data):
        """
        Validate that the required 'name' field is present and not None.
        """
        if "name" not in data or data.get("name") is None:
            raise WrongParameterException(
                "The 'name' field is required and cannot be None."
            )
        return data

    @jwt_required()
    @swag_from("openapi/CustomActionsResource_get.yml")
    def get(self):
        """
        Get custom actions
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/CustomActionsResource_post.yml")
    def post(self):
        """
        Create custom action
        """
        return super().post()

    def post_creation(self, custom_action):
        custom_actions_service.clear_custom_action_cache()
        return custom_action.serialize(relations=True)


class CustomActionResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, CustomAction)

    @jwt_required()
    @swag_from("openapi/CustomActionResource_get.yml")
    def get(self, instance_id):
        """
        Get custom action
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/CustomActionResource_put.yml")
    def put(self, instance_id):
        """
        Update custom action
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/CustomActionResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete custom action
        """
        return super().delete(instance_id)

    def pre_update(self, instance_dict, data):
        """
        Validate that if 'name' is being updated, it is not None.
        """
        if "name" in data and data.get("name") is None:
            raise WrongParameterException(
                "The 'name' field cannot be set to None."
            )
        return data

    def post_update(self, custom_action, data):
        custom_actions_service.clear_custom_action_cache()
        return custom_action

    def post_delete(self, custom_action):
        custom_actions_service.clear_custom_action_cache()
        return custom_action
