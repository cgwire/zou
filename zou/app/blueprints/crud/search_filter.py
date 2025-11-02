from flask_jwt_extended import jwt_required

from zou.app.models.search_filter import SearchFilter

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class SearchFiltersResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, SearchFilter)

    @jwt_required()
    def get(self):
        """
        Get search filters
        ---
        tags:
          - Crud
        description: Retrieve all search filters. Supports filtering via
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
              description: Search filters retrieved successfully
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
        Create search filter
        ---
        tags:
          - Crud
        description: Create a new search filter with data provided in
          the request body. JSON format is expected.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - name
                  - person_id
                  - search_filter_group_id
                properties:
                  name:
                    type: string
                    example: My Filter
                  person_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  search_filter_group_id:
                    type: string
                    format: uuid
                    example: b24a6ea4-ce75-4665-a070-57453082c25
                  list_type:
                    type: string
                    example: assets
        responses:
            201:
              description: Search filter created successfully
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
                        example: My Filter
                      person_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      search_filter_group_id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
                      list_type:
                        type: string
                        example: assets
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


class SearchFilterResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, SearchFilter)

    @jwt_required()
    def get(self, instance_id):
        """
        Get search filter
        ---
        tags:
          - Crud
        description: Retrieve a search filter by its ID and return it
          as a JSON object. Supports including relations.
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
              description: Search filter retrieved successfully
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
                        example: My Filter
                      person_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      search_filter_group_id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
                      list_type:
                        type: string
                        example: assets
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
        Update search filter
        ---
        tags:
          - Crud
        description: Update a search filter with data provided in the
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
                    example: Updated Filter Name
                  list_type:
                    type: string
                    example: shots
        responses:
            200:
              description: Search filter updated successfully
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
                        example: Updated Filter Name
                      person_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      search_filter_group_id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
                      list_type:
                        type: string
                        example: shots
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
        Delete search filter
        ---
        tags:
          - Crud
        description: Delete a search filter by its ID. Returns empty
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
              description: Search filter deleted successfully
            400:
              description: Integrity error or cannot delete
        """
        return super().delete(instance_id)
