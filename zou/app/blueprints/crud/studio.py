from flask_jwt_extended import jwt_required

from zou.app.models.studio import Studio

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource

from zou.app.services import tasks_service


class StudiosResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Studio)

    def check_read_permissions(self, options=None):
        return True

    @jwt_required()
    def get(self):
        """
        Get studios
        ---
        tags:
          - Crud
        description: Retrieve all studios. Supports filtering via query
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
              description: Studios retrieved successfully
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
        Create studio
        ---
        tags:
          - Crud
        description: Create a new studio with data provided in the
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
                    example: Studio Name
                  hours_by_day:
                    type: number
                    example: 8.0
        responses:
            201:
              description: Studio created successfully
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
                        example: Studio Name
                      hours_by_day:
                        type: number
                        example: 8.0
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

    def post_creation(self, instance):
        tasks_service.clear_studio_cache(str(instance.id))
        return instance.serialize()


class StudioResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Studio)

    def check_read_permissions(self, instance):
        return True

    @jwt_required()
    def get(self, instance_id):
        """
        Get studio
        ---
        tags:
          - Crud
        description: Retrieve a studio by its ID and return it as a
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
              description: Studio retrieved successfully
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
                        example: Studio Name
                      hours_by_day:
                        type: number
                        example: 8.0
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
        Update studio
        ---
        tags:
          - Crud
        description: Update a studio with data provided in the request
          body. JSON format is expected.
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
                    example: Updated Studio Name
                  hours_by_day:
                    type: number
                    example: 7.5
        responses:
            200:
              description: Studio updated successfully
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
                        example: Updated Studio Name
                      hours_by_day:
                        type: number
                        example: 7.5
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
        Delete studio
        ---
        tags:
          - Crud
        description: Delete a studio by its ID. Returns empty response
          on success.
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
              description: Studio deleted successfully
            400:
              description: Integrity error or cannot delete
        """
        return super().delete(instance_id)

    def post_update(self, instance_dict, data):
        tasks_service.clear_studio_cache(instance_dict["id"])
        return instance_dict

    def post_delete(self, instance_dict):
        tasks_service.clear_studio_cache(instance_dict["id"])
        return instance_dict
