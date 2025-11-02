from flask_jwt_extended import jwt_required

from zou.app.models.custom_action import CustomAction

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource

from zou.app.services import custom_actions_service, user_service


class CustomActionsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, CustomAction)

    def check_read_permissions(self, options=None):
        user_service.block_access_to_vendor()
        return True

    @jwt_required()
    def get(self):
        """
        Get custom actions
        ---
        tags:
          - Crud
        description: Retrieve all custom actions. Supports filtering via
          query parameters and pagination. Vendor access is blocked.
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
              description: Custom actions retrieved successfully
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
        Create custom action
        ---
        tags:
          - Crud
        description: Create a new custom action with data provided in the
          request body. JSON format is expected.
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
                    example: Custom Action Name
                  url_pattern:
                    type: string
                    example: "/api/actions/{id}"
        responses:
            201:
              description: Custom action created successfully
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
                        example: Custom Action Name
                      url_pattern:
                        type: string
                        example: "/api/actions/{id}"
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

    def post_creation(self, custom_action):
        custom_actions_service.clear_custom_action_cache()
        return custom_action.serialize()


class CustomActionResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, CustomAction)

    @jwt_required()
    def get(self, instance_id):
        """
        Get custom action
        ---
        tags:
          - Crud
        description: Retrieve a custom action by its ID and return it as a
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
              description: Custom action retrieved successfully
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
                        example: Custom Action Name
                      url_pattern:
                        type: string
                        example: "/api/actions/{id}"
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
        Update custom action
        ---
        tags:
          - Crud
        description: Update a custom action with data provided in the
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
                    example: Updated Custom Action Name
                  url_pattern:
                    type: string
                    example: "/api/actions/{id}"
        responses:
            200:
              description: Custom action updated successfully
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
                        example: Updated Custom Action Name
                      url_pattern:
                        type: string
                        example: "/api/actions/{id}"
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
        Delete custom action
        ---
        tags:
          - Crud
        description: Delete a custom action by its ID. Returns empty
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
              description: Custom action deleted successfully
            400:
              description: Integrity error or cannot delete
        """
        return super().delete(instance_id)

    def post_update(self, custom_action, data):
        custom_actions_service.clear_custom_action_cache()
        return custom_action

    def post_delete(self, custom_action):
        custom_actions_service.clear_custom_action_cache()
        return custom_action
