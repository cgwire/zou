from zou.app.models.custom_action import CustomAction

from .base import BaseModelsResource, BaseModelResource

from zou.app.services import custom_actions_service, user_service


class CustomActionsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, CustomAction)

    def check_read_permissions(self):
        user_service.block_access_to_vendor()
        return True

    def post_creation(self, custom_action):
        custom_actions_service.clear_custom_action_cache()
        return custom_action.serialize()


class CustomActionResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, CustomAction)

    def post_update(self, custom_action):
        custom_actions_service.clear_custom_action_cache()
        return custom_action

    def post_delete(self, custom_action):
        custom_actions_service.clear_custom_action_cache()
        return custom_action
