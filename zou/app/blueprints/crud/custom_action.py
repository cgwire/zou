from zou.app.models.custom_action import CustomAction

from .base import BaseModelsResource, BaseModelResource

from zou.app.services import projects_service


class CustomActionsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, CustomAction)

    def check_read_permissions(self):
        return True

    def post_creation(self, custom_action):
        projects_service.clear_custom_action_cache()
        return custom_action.serialize()


class CustomActionResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, CustomAction)

    def post_update(self, custom_action):
        projects_service.clear_custom_action_cache()
        return custom_action

    def post_delete(self, custom_action):
        projects_service.clear_custom_action_cache()
        return custom_action
