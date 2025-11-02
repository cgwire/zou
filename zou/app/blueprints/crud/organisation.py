from flask_jwt_extended import jwt_required

from zou.app.models.organisation import Organisation
from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource

from zou.app.services import persons_service
from zou.app.utils.permissions import has_admin_permissions


class OrganisationsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Organisation)

    def check_read_permissions(self, options=None):
        return True

    @jwt_required()
    def get(self):
        """
        Get organisations
        ---
        tags:
          - Crud
        description: Retrieve all organisations. Supports filtering via
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
              description: Organisations retrieved successfully
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
        Create organisation
        ---
        tags:
          - Crud
        description: Create a new organisation with data provided in the
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
              description: Organisation created successfully
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


class OrganisationResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Organisation)

    def check_read_permissions(self, instance):
        return True

    @jwt_required()
    def get(self, instance_id):
        """
        Get organisation
        ---
        tags:
          - Crud
        description: Retrieve an organisation by its ID and return it as
          a JSON object. Supports including relations. Non-admin users
          cannot see chat tokens.
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
              description: Organisation retrieved successfully
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
        Update organisation
        ---
        tags:
          - Crud
        description: Update an organisation with data provided in the
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
                    example: Updated Studio Name
                  hours_by_day:
                    type: number
                    example: 7.5
        responses:
            200:
              description: Organisation updated successfully
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
        Delete organisation
        ---
        tags:
          - Crud
        description: Delete an organisation by its ID. Returns empty
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
              description: Organisation deleted successfully
            400:
              description: Integrity error or cannot delete
        """
        return super().delete(instance_id)

    def pre_update(self, instance_dict, data):
        if "hours_by_day" in data:
            data["hours_by_day"] = float(data["hours_by_day"])
        return data

    def serialize_instance(self, data, relations=True):
        return data.serialize(
            relations=relations,
            ignored_attrs=(
                []
                if has_admin_permissions()
                else [
                    "chat_token_slack",
                    "chat_webhook_mattermost",
                    "chat_token_discord",
                ]
            ),
        )

    def post_update(self, instance_dict, data):
        persons_service.clear_organisation_cache()
        return instance_dict
