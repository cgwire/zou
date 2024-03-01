from zou.app.models.metadata_descriptor import (
    MetadataDescriptor,
    METADATA_DESCRIPTOR_TYPES,
)

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource

from zou.app.services.exception import (
    ArgumentsException,
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

    def update_data(self, data, instance_id):
        """
        Check if the data descriptor has a valid data_type and valid
        departments.
        """
        data = super().update_data(data, instance_id)
        if "data_type" in data:
            types = [type_name for type_name, _ in METADATA_DESCRIPTOR_TYPES]
            if data["data_type"] not in types:
                raise ArgumentsException("Invalid data_type")
        return data
