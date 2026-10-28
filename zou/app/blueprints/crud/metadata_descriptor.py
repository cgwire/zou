from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.exceptions import (
    WrongParameterException,
)
from zou.app.models.metadata_descriptor import (
    METADATA_DESCRIPTOR_TYPES,
    MetadataDescriptor,
)
from zou.app.services import (
    metadata_descriptors_service,
    user_service,
)
from zou.app.utils import permissions
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/metadata_descriptor.yml")


class MetadataDescriptorsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, MetadataDescriptor)

    def get_relations_eager_load(self):
        return [MetadataDescriptor.departments]

    def check_read_permissions(self, options=None):
        # Every member of a production reads its descriptors, narrowed on
        # the role held there by add_project_permission_filter.
        return True

    @jwt_required()
    @swag_from(SPECS["MetadataDescriptorsResource_get"])
    def get(self):
        """
        Get metadata descriptors
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["MetadataDescriptorsResource_post"])
    def post(self):
        """
        Create metadata descriptor
        """
        return super().post()

    def add_project_permission_filter(self, query):
        if permissions.has_admin_permissions():
            return query
        # The descriptors of each project are narrowed on the role held on
        # it, as the descriptors route of a production narrows them: the
        # filters of the query string cannot reach the ones left out.
        project_ids = [
            project["id"] for project in user_service.related_projects()
        ]
        return query.filter(
            metadata_descriptors_service.build_metadata_descriptors_filter(
                user_service.get_descriptor_visibilities(project_ids)
            )
        )

    def check_creation_integrity(self, data):
        """
        Check if the data descriptor has a valid data_type, and a field name
        that no built-in field uses.
        """
        if "data_type" in data:
            types = [type_name for type_name, _ in METADATA_DESCRIPTOR_TYPES]
            if data["data_type"] not in types:
                raise WrongParameterException("Invalid data_type")
        metadata_descriptors_service.check_metadata_descriptor_field_name(
            data.get("entity_type"), data.get("field_name")
        )
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
    @swag_from(SPECS["MetadataDescriptorResource_get"])
    def get(self, instance_id):
        """
        Get metadata descriptor
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["MetadataDescriptorResource_put"])
    def put(self, instance_id):
        """
        Update metadata descriptor
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["MetadataDescriptorResource_delete"])
    def delete(self, instance_id):
        """
        Delete metadata descriptor
        """
        return super().delete(instance_id)

    def update_data(self, data, instance_id):
        """
        Check if the data descriptor has a valid data_type and valid
        departments, and that a new field name is not one a built-in field
        uses. A descriptor created on one before that check keeps it.
        """
        data = super().update_data(data, instance_id)
        if "data_type" in data:
            types = [type_name for type_name, _ in METADATA_DESCRIPTOR_TYPES]
            if data["data_type"] not in types:
                raise WrongParameterException("Invalid data_type")
        entity_type = data.get("entity_type", self.instance.entity_type)
        field_name = data.get("field_name", self.instance.field_name)
        if (entity_type, field_name) != (
            self.instance.entity_type,
            self.instance.field_name,
        ):
            metadata_descriptors_service.check_metadata_descriptor_field_name(
                entity_type, field_name
            )
        return data

    def serialize_update_response(self, instance):
        """
        List the departments, as the reads do.
        """
        return instance.serialize(relations=True)
