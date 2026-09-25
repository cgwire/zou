from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.models.metadata_descriptor import (
    MetadataDescriptor,
    METADATA_DESCRIPTOR_TYPES,
)

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.utils import permissions
from zou.app.models.project import Project
from zou.app.services import user_service

from zou.app.exceptions import (
    WrongParameterException,
)


class MetadataDescriptorsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, MetadataDescriptor)

    def get_relations_eager_load(self):
        return [MetadataDescriptor.departments]

    def check_read_permissions(self, options=None):
        return not permissions.has_vendor_permissions()

    @jwt_required()
    @swag_from("openapi/MetadataDescriptorsResource_get.yml")
    def get(self):
        """
        Get metadata descriptors
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/MetadataDescriptorsResource_post.yml")
    def post(self):
        """
        Create metadata descriptor
        """
        return super().post()

    def add_project_permission_filter(self, query):
        if not permissions.has_admin_permissions():
            query = query.join(Project).filter(
                user_service.build_related_projects_filter()
            )
        return query

    def check_creation_integrity(self, data):
        """
        Check if the data descriptor has a valid data_type.
        """
        if "data_type" in data:
            types = [type_name for type_name, _ in METADATA_DESCRIPTOR_TYPES]
            if data["data_type"] not in types:
                raise WrongParameterException("Invalid data_type")
        return True

    def all_entries(self, query=None, relations=True):
        if query is None:
            query = self.model.query

        return [
            metadata_descriptor.serialize(relations=relations)
            for metadata_descriptor in query.all()
        ]


class MetadataDescriptorResource(BaseModelResource):

    def __init__(self):
        BaseModelResource.__init__(self, MetadataDescriptor)

    @jwt_required()
    @swag_from("openapi/MetadataDescriptorResource_get.yml")
    def get(self, instance_id):
        """
        Get metadata descriptor
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/MetadataDescriptorResource_put.yml")
    def put(self, instance_id):
        """
        Update metadata descriptor
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/MetadataDescriptorResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete metadata descriptor
        """
        return super().delete(instance_id)

    def update_data(self, data, instance_id):
        """
        Check if the data descriptor has a valid data_type and valid
        departments.
        """
        data = super().update_data(data, instance_id)
        if "data_type" in data:
            types = [type_name for type_name, _ in METADATA_DESCRIPTOR_TYPES]
            if data["data_type"] not in types:
                raise WrongParameterException("Invalid data_type")
        return data
