from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource

from zou.app.models.department import Department

from zou.app.services import tasks_service
from zou.app.services.exception import (
    ArgumentsException,
)


class DepartmentsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Department)

    def check_read_permissions(self):
        return True

    def post_creation(self, instance):
        tasks_service.clear_department_cache(str(instance.id))
        return instance.serialize()

    def update_data(self, data):
        data = super().update_data(data)
        name = data.get("name", None)
        department = Department.get_by(name=name)
        if department is not None:
            raise ArgumentsException(
                "A department type with similar name already exists"
            )
        return data


class DepartmentResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Department)

    def check_read_permissions(self, instance):
        return True

    def update_data(self, data, instance_id):
        data = super().update_data(data, instance_id)
        name = data.get("name", None)
        if name is not None:
            department = Department.get_by(name=name)
            if department is not None and instance_id != str(department.id):
                raise ArgumentsException(
                    "A department with similar name already exists"
                )
        return data

    def post_update(self, instance_dict, data):
        tasks_service.clear_department_cache(instance_dict["id"])
        return instance_dict

    def post_delete(self, instance_dict):
        tasks_service.clear_department_cache(instance_dict["id"])
        return instance_dict
