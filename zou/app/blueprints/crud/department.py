from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource

from zou.app.models.department import Department

from zou.app.services import tasks_service


class DepartmentsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Department)

    def check_read_permissions(self):
        return True

    def post_creation(self, instance):
        tasks_service.clear_department_cache(str(instance.id))
        return instance.serialize()


class DepartmentResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Department)

    def check_read_permissions(self, instance):
        return True

    def post_update(self, instance_dict, data):
        tasks_service.clear_department_cache(instance_dict["id"])
        return instance_dict

    def post_delete(self, instance_dict):
        tasks_service.clear_department_cache(instance_dict["id"])
        return instance_dict
