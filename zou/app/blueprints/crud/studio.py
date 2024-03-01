from zou.app.models.studio import Studio

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource

from zou.app.services import tasks_service


class StudiosResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Studio)

    def check_read_permissions(self):
        return True

    def post_creation(self, instance):
        tasks_service.clear_studio_cache(str(instance.id))
        return instance.serialize()


class StudioResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Studio)

    def check_read_permissions(self, instance):
        return True

    def post_update(self, instance_dict, data):
        tasks_service.clear_studio_cache(instance_dict["id"])
        return instance_dict

    def post_delete(self, instance_dict):
        tasks_service.clear_studio_cache(instance_dict["id"])
        return instance_dict
