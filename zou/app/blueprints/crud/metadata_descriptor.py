from zou.app.models.metadata_descriptor import (
    MetadataDescriptor,
    METADATA_DESCRIPTOR_TYPES,
)

from zou.app.models.department import Department

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource

from sqlalchemy.exc import StatementError

from zou.app.services.exception import (
    ArgumentsException,
    DepartmentNotFoundException,
)


class MetadataDescriptorsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, MetadataDescriptor)

    def all_entries(self, query=None, relations=True):
        if query is None:
            query = self.model.query

        return [
            metadata_descriptor.serialize(relations=relations)
            for metadata_descriptor in query.all()
        ]

    def check_creation_integrity(self, data):
        """
        Check if the data descriptor has a valid data_type.
        """
        if "data_type" in data:
            types = [type_name for type_name, _ in METADATA_DESCRIPTOR_TYPES]
            if data["data_type"] not in types:
                raise ArgumentsException("Invalid data_type")
        return True


class MetadataDescriptorResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, MetadataDescriptor)

    def post_update(self, instance_dict):
        instance_dict["departments"] = [
            str(department.id) for department in self.instance.departments
        ]
        return instance_dict

    def update_data(self, data, instance_id):
        """
        Check if the data descriptor has a valid data_type and valid
        departments.
        """
        if "data_type" in data:
            types = [type_name for type_name, _ in METADATA_DESCRIPTOR_TYPES]
            if data["data_type"] not in types:
                raise ArgumentsException("Invalid data_type")

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
