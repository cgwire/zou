from flask_jwt_extended import jwt_required

from zou.app.models.preview_background_file import PreviewBackgroundFile
from zou.app.services.exception import WrongParameterException
from zou.app.services import files_service, deletion_service

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class PreviewBackgroundFilesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, PreviewBackgroundFile)

    def check_read_permissions(self, options=None):
        return True

    @jwt_required()
    def get(self):
        """
        Get preview background files
        ---
        tags:
          - Crud
        description: Retrieve all preview background files. Supports
          filtering via query parameters and pagination.
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
            default: false
            example: false
            description: Whether to include relations
        responses:
            200:
              description: Preview background files retrieved successfully
              content:
                application/json:
                  schema:
                    oneOf:
                      - type: array
                        items:
                          type: object
                      - type: object
                        properties:
                          data:
                            type: array
                            items:
                              type: object
                            example: []
                          total:
                            type: integer
                            example: 100
                          nb_pages:
                            type: integer
                            example: 2
                          limit:
                            type: integer
                            example: 50
                          offset:
                            type: integer
                            example: 0
                          page:
                            type: integer
                            example: 1
            400:
              description: Invalid filter format or query error
        """
        return super().get()

    @jwt_required()
    def post(self):
        """
        Create preview background file
        ---
        tags:
          - Crud
        description: Create a new preview background file with data
          provided in the request body. JSON format is expected.
          Names must be unique. If is_default is true, resets other
          defaults.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - name
                properties:
                  name:
                    type: string
                    example: background_file_name
                  is_default:
                    type: boolean
                    default: false
                    example: false
        responses:
            201:
              description: Preview background file created successfully
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
                        example: background_file_name
                      is_default:
                        type: boolean
                        example: false
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
            400:
              description: Invalid data format or name already exists
        """
        return super().post()

    def update_data(self, data):
        data = super().update_data(data)
        name = data.get("name", None)
        preview_background_file = PreviewBackgroundFile.get_by(name=name)
        if preview_background_file is not None:
            raise WrongParameterException(
                "A preview background file with similar name already exists"
            )
        return data

    def post_creation(self, instance):
        if instance.is_default:
            files_service.reset_default_preview_background_files(instance.id)
        files_service.clear_preview_background_file_cache(str(instance.id))
        return instance.serialize()


class PreviewBackgroundFileResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, PreviewBackgroundFile)

    def check_read_permissions(self, instance):
        return True

    @jwt_required()
    def get(self, instance_id):
        """
        Get preview background file
        ---
        tags:
          - Crud
        description: Retrieve a preview background file by its ID and
          return it as a JSON object. Supports including relations.
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
              description: Preview background file retrieved successfully
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
                        example: background_file_name
                      is_default:
                        type: boolean
                        example: false
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
        Update preview background file
        ---
        tags:
          - Crud
        description: Update a preview background file with data provided
          in the request body. JSON format is expected. Names must be
          unique. If is_default is set to true, resets other defaults.
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
                    example: updated_background_file_name
                  is_default:
                    type: boolean
                    example: true
        responses:
            200:
              description: Preview background file updated successfully
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
                        example: updated_background_file_name
                      is_default:
                        type: boolean
                        example: true
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T11:00:00Z"
            400:
              description: Invalid data format or name already exists
        """
        return super().put(instance_id)

    @jwt_required()
    def delete(self, instance_id):
        """
        Delete preview background file
        ---
        tags:
          - Crud
        description: Delete a preview background file by its ID. Returns
          empty response on success.
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
              description: Preview background file deleted successfully
            400:
              description: Integrity error or cannot delete
        """
        return super().delete(instance_id)

    def update_data(self, data, instance_id):
        data = super().update_data(data, instance_id)
        name = data.get("name", None)
        if name is not None:
            preview_background_file = PreviewBackgroundFile.get_by(name=name)
            if preview_background_file is not None and instance_id != str(
                preview_background_file.id
            ):
                raise WrongParameterException(
                    "A preview background file with similar name already exists"
                )
        return data

    def post_update(self, instance_dict, data):
        if instance_dict["is_default"]:
            files_service.reset_default_preview_background_files(
                instance_dict["id"]
            )
        files_service.clear_preview_background_file_cache(instance_dict["id"])
        return instance_dict

    def post_delete(self, instance_dict):
        deletion_service.clear_preview_background_files(instance_dict["id"])
        files_service.clear_preview_background_file_cache(instance_dict["id"])
        return instance_dict
