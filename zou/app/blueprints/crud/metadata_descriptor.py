from flask_jwt_extended import jwt_required

from zou.app.models.metadata_descriptor import (
    MetadataDescriptor,
    METADATA_DESCRIPTOR_TYPES,
)

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.utils import permissions
from zou.app.models.project import Project
from zou.app.services import user_service

from zou.app.services.exception import (
    WrongParameterException,
)


class MetadataDescriptorsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, MetadataDescriptor)

    def check_read_permissions(self, options=None):
        return not permissions.has_vendor_permissions()

    @jwt_required()
    def get(self):
        """
        Get metadata descriptors
        ---
        tags:
          - Crud
        description: Retrieve all metadata descriptors. Supports filtering
          via query parameters and pagination. Vendor access is blocked.
          Includes project permission filtering for non-admin users.
        parameters:
          - in: query
            name: page
            required: false
            schema:
              type: integer
            example: 1
            description: Page number for pagination
          - in: query
            name: limit
            required: false
            schema:
              type: integer
            example: 50
            description: Number of results per page
          - in: query
            name: relations
            required: false
            schema:
              type: boolean
            default: true
            example: true
            description: Whether to include relations
        responses:
            200:
              description: Metadata descriptors retrieved successfully
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          example: Custom Field
                        field_name:
                          type: string
                          example: custom_field
                        data_type:
                          type: string
                          example: text
                        project_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        created_at:
                          type: string
                          format: date-time
                          example: "2024-01-15T10:30:00Z"
                        updated_at:
                          type: string
                          format: date-time
                          example: "2024-01-15T10:30:00Z"
            400:
              description: Invalid filter format or query error
        """
        return super().get()

    @jwt_required()
    def post(self):
        """
        Create metadata descriptor
        ---
        tags:
          - Crud
        description: Create a new metadata descriptor with data provided in
          the request body. JSON format is expected. Validates data_type.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - name
                  - field_name
                  - data_type
                  - project_id
                properties:
                  name:
                    type: string
                    example: Custom Field
                  field_name:
                    type: string
                    example: custom_field
                  data_type:
                    type: string
                    example: text
                  project_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  entity_type:
                    type: string
                    example: Asset
        responses:
            201:
              description: Metadata descriptor created successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        example: Custom Field
                      field_name:
                        type: string
                        example: custom_field
                      data_type:
                        type: string
                        example: text
                      project_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      entity_type:
                        type: string
                        example: Asset
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
            400:
              description: Invalid data format or invalid data_type
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
    def get(self, instance_id):
        """
        Get metadata descriptor
        ---
        tags:
          - Crud
        description: Retrieve a metadata descriptor by its ID and return
          it as a JSON object. Supports including relations.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: relations
            required: false
            schema:
              type: boolean
            default: true
            example: true
            description: Whether to include relations
        responses:
            200:
              description: Metadata descriptor retrieved successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        example: Custom Field
                      field_name:
                        type: string
                        example: custom_field
                      data_type:
                        type: string
                        example: text
                      project_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      entity_type:
                        type: string
                        example: Asset
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
            400:
              description: Invalid ID format or query error
        """
        return super().get(instance_id)

    @jwt_required()
    def put(self, instance_id):
        """
        Update metadata descriptor
        ---
        tags:
          - Crud
        description: Update a metadata descriptor with data provided in the
          request body. JSON format is expected. Validates data_type.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  name:
                    type: string
                    example: Updated Custom Field
                  data_type:
                    type: string
                    example: number
        responses:
            200:
              description: Metadata descriptor updated successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        example: Updated Custom Field
                      field_name:
                        type: string
                        example: custom_field
                      data_type:
                        type: string
                        example: number
                      project_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T11:00:00Z"
            400:
              description: Invalid data format or invalid data_type
        """
        return super().put(instance_id)

    @jwt_required()
    def delete(self, instance_id):
        """
        Delete metadata descriptor
        ---
        tags:
          - Crud
        description: Delete a metadata descriptor by its ID. Returns empty
          response on success.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
              description: Metadata descriptor deleted successfully
            400:
              description: Integrity error or cannot delete
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
