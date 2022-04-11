from zou.app.models.metadata_descriptor import MetadataDescriptor

from zou.app.models.department import Department

from .base import BaseModelResource, BaseModelsResource

from sqlalchemy.exc import StatementError

from zou.app.services.exception import DepartmentNotFoundException


class MetadataDescriptorsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, MetadataDescriptor)

    def all_entries(self, query=None, relations=False):
        if query is None:
            query = self.model.query

        return [
            metadata_descriptor.serialize(relations=True)
            for metadata_descriptor in query.all()
        ]


class MetadataDescriptorResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, MetadataDescriptor)

    def post_update(self, instance_dict):
        instance_dict["departments"] = [
            str(department.id) for department in self.instance.departments
        ]
        return instance_dict

    def update_data(self, data, instance_id):
        if "departments" in data:
            try:
                departments = []
                for department_id in data["departments"]:
                    department = Department.get(department_id)
                    if department is not None:
                        departments.append(department)
            except StatementError:
                raise DepartmentNotFoundException()
            data["departments"] = departments
        return data
