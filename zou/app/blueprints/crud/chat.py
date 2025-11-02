from flask_jwt_extended import jwt_required

from zou.app.models.chat import Chat

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class ChatsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Chat)

    @jwt_required()
    def get(self):
        """
        Get chats
        ---
        tags:
          - Crud
        description: Retrieve all chats. Supports filtering via query
          parameters and pagination.
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
              description: Chats retrieved successfully
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
        Create chat
        ---
        tags:
          - Crud
        description: Create a new chat with data provided in the request
          body. JSON format is expected.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - object_id
                  - object_type
                properties:
                  object_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  object_type:
                    type: string
                    example: Asset
                  name:
                    type: string
                    example: Chat Name
        responses:
            201:
              description: Chat created successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      object_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      object_type:
                        type: string
                        example: Asset
                      name:
                        type: string
                        example: Chat Name
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


class ChatResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Chat)

    @jwt_required()
    def get(self, instance_id):
        """
        Get chat
        ---
        tags:
          - Crud
        description: Retrieve a chat by its ID and return it as a JSON
          object. Supports including relations.
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
              description: Chat retrieved successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      object_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      object_type:
                        type: string
                        example: Asset
                      name:
                        type: string
                        example: Chat Name
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
        Update chat
        ---
        tags:
          - Crud
        description: Update a chat with data provided in the request body.
          JSON format is expected.
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
                    example: Updated Chat Name
        responses:
            200:
              description: Chat updated successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      object_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      object_type:
                        type: string
                        example: Asset
                      name:
                        type: string
                        example: Updated Chat Name
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
        Delete chat
        ---
        tags:
          - Crud
        description: Delete a chat by its ID. Returns empty response on
          success.
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
              description: Chat deleted successfully
            400:
              description: Integrity error or cannot delete
        """
        return super().delete(instance_id)
