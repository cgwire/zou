from flask_jwt_extended import jwt_required

from zou.app.models.asset_instance import AssetInstance

from zou.app.services import assets_service, user_service
from zou.app.utils import permissions

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class AssetInstancesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, AssetInstance)

    @jwt_required()
    def get(self):
        """
        Get asset instances
        ---
        tags:
          - Crud
        description: Retrieve all asset instances. Supports filtering via
          query parameters and pagination.
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
              description: Asset instances retrieved successfully
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
        Create asset instance
        ---
        tags:
          - Crud
        description: Create a new asset instance with data provided in the
          request body. JSON format is expected.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - asset_id
                properties:
                  asset_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  name:
                    type: string
                    example: Instance Name
        responses:
            201:
              description: Asset instance created successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      asset_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        example: Instance Name
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
            400:
              description: Invalid data format or validation error
        """
        return super().post()


class AssetInstanceResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, AssetInstance)
        self.protected_fields.append("number")

    @jwt_required()
    def get(self, instance_id):
        """
        Get asset instance
        ---
        tags:
          - Crud
        description: Retrieve an asset instance by its ID and return it as a
          JSON object. Supports including relations.
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
              description: Asset instance retrieved successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      asset_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        example: Instance Name
                      number:
                        type: integer
                        example: 1
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
        Update asset instance
        ---
        tags:
          - Crud
        description: Update an asset instance with data provided in the
          request body. JSON format is expected.
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
                    example: Updated Instance Name
        responses:
            200:
              description: Asset instance updated successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      asset_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        example: Updated Instance Name
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T11:00:00Z"
            400:
              description: Invalid data format or validation error
        """
        return super().put(instance_id)

    @jwt_required()
    def delete(self, instance_id):
        """
        Delete asset instance
        ---
        tags:
          - Crud
        description: Delete an asset instance by its ID. Returns empty
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
              description: Asset instance deleted successfully
            400:
              description: Integrity error or cannot delete
        """
        return super().delete(instance_id)

    def check_read_permissions(self, instance):
        if permissions.has_admin_permissions():
            return True
        else:
            asset_instance = self.get_model_or_404(instance["id"])
            asset = assets_service.get_asset(asset_instance.asset_id)
            user_service.check_project_access(asset["project_id"])
            user_service.check_entity_access(asset["id"])
            return True

    def check_update_permissions(self, asset_instance, data):
        if permissions.has_admin_permissions():
            return True
        else:
            asset = assets_service.get_asset(asset_instance["asset_id"])
            user_service.check_project_access(asset["project_id"])
            user_service.check_entity_access(asset["id"])
            return True
