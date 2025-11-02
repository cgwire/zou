from flask_jwt_extended import jwt_required

from zou.app.models.entity import EntityLink
from zou.app.utils import fields

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.services.exception import (
    EntityLinkNotFoundException,
    WrongParameterException,
)


class EntityLinksResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, EntityLink)

    @jwt_required()
    def get(self):
        """
        Get entity links
        ---
        tags:
          - Crud
        description: Retrieve all entity links. Supports filtering via
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
              description: Entity links retrieved successfully
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
        Create entity link
        ---
        tags:
          - Crud
        description: Create a new entity link with data provided in the
          request body. JSON format is expected. Links entities together
          in casting relationships.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - entity_in_id
                  - entity_out_id
                properties:
                  entity_in_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  entity_out_id:
                    type: string
                    format: uuid
                    example: b24a6ea4-ce75-4665-a070-57453082c25
                  nb_occurences:
                    type: integer
                    default: 1
                    example: 1
                  label:
                    type: string
                    example: fixed
        responses:
            201:
              description: Entity link created successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      entity_in_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      entity_out_id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
                      nb_occurences:
                        type: integer
                        example: 1
                      label:
                        type: string
                        example: fixed
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


class EntityLinkResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, EntityLink)

    @jwt_required()
    def get(self, instance_id):
        """
        Get entity link
        ---
        tags:
          - Crud
        description: Retrieve an entity link by its ID and return it as a
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
              description: Entity link retrieved successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      entity_in_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      entity_out_id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
                      nb_occurences:
                        type: integer
                        example: 1
                      label:
                        type: string
                        example: fixed
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
        Update entity link
        ---
        tags:
          - Crud
        description: Update an entity link with data provided in the
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
                  nb_occurences:
                    type: integer
                    example: 2
                  label:
                    type: string
                    example: updated
        responses:
            200:
              description: Entity link updated successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      entity_in_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      entity_out_id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
                      nb_occurences:
                        type: integer
                        example: 2
                      label:
                        type: string
                        example: updated
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
        Delete entity link
        ---
        tags:
          - Crud
        description: Delete an entity link by its ID. Returns empty
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
              description: Entity link deleted successfully
            400:
              description: Integrity error or cannot delete
        """
        return super().delete(instance_id)

    def get_model_or_404(self, instance_id):
        if not fields.is_valid_id(instance_id):
            raise WrongParameterException("Malformed ID.")
        instance = self.model.get_by(id=instance_id)
        if instance is None:
            raise EntityLinkNotFoundException
        return instance
