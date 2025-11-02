from flask_jwt_extended import jwt_required

from zou.app.models.event import ApiEvent

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class EventsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, ApiEvent)

    @jwt_required()
    def get(self):
        """
        Get events
        ---
        tags:
          - Crud
        description: Retrieve all events. Supports filtering via query
          parameters and pagination. Limited to 1000 results.
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
              description: Events retrieved successfully
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
                          example: Event Name
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

    def all_entries(self, query=None, relations=False):
        if query is None:
            query = self.model.query

        return self.serialize_list(
            query.limit(1000).all(), relations=relations
        )


class EventResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, ApiEvent)

    @jwt_required()
    def get(self, instance_id):
        """
        Get event
        ---
        tags:
          - Crud
        description: Retrieve an event by its ID and return it as a JSON
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
              description: Event retrieved successfully
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
                        example: Event Name
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
        Update event
        ---
        tags:
          - Crud
        description: Update an event with data provided in the request
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
                    example: Updated Event Name
        responses:
            200:
              description: Event updated successfully
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
                        example: Updated Event Name
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
        Delete event
        ---
        tags:
          - Crud
        description: Delete an event by its ID. Returns empty response
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
              description: Event deleted successfully
            400:
              description: Integrity error or cannot delete
        """
        return super().delete(instance_id)
