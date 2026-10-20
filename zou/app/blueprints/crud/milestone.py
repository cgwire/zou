import re

from flask_jwt_extended import jwt_required

from zou.app.models.milestone import (
    Milestone,
    MILESTONE_STATUSES,
    MILESTONE_TYPES,
)
from zou.app.services import permissions_service
from zou.app.services import user_service
from zou.app.services.exception import WrongParameterException

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource

HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}")
MILESTONE_TYPE_CODES = [code for code, _ in MILESTONE_TYPES]
MILESTONE_STATUS_CODES = [code for code, _ in MILESTONE_STATUSES]


def check_milestone_fields(data):
    """
    Reject a color that is not #RRGGBB and a type or status outside the
    allowed choices. ChoiceType would store an unknown code and fail only
    when the row is read back.
    """
    color = data.get("color")
    if color is not None and (
        not isinstance(color, str) or not HEX_COLOR_RE.fullmatch(color)
    ):
        raise WrongParameterException(
            "Color must be a hex string formatted as #RRGGBB."
        )
    if "milestone_type" in data and (
        data["milestone_type"] not in MILESTONE_TYPE_CODES
    ):
        raise WrongParameterException(
            "Milestone type must be one of: "
            f"{', '.join(MILESTONE_TYPE_CODES)}."
        )
    if "status" in data and data["status"] not in MILESTONE_STATUS_CODES:
        raise WrongParameterException(
            "Milestone status must be one of: "
            f"{', '.join(MILESTONE_STATUS_CODES)}."
        )
    return data


class MilestonesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Milestone)

    def check_create_permissions(self, milestone):
        permissions_service.check_manager_project_access(
            milestone["project_id"]
        )

    def check_creation_integrity(self, data):
        return check_milestone_fields(data)

    @jwt_required()
    def get(self):
        """
        Get milestones
        ---
        tags:
          - Crud
        description: Retrieve all milestones. Supports filtering via query
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
              description: Milestones retrieved successfully
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
        Create milestone
        ---
        tags:
          - Crud
        description: Create a new milestone with data provided in the
          request body. JSON format is expected. Requires manager access
          to the project.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - name
                  - project_id
                  - date
                properties:
                  name:
                    type: string
                    example: Milestone Name
                  project_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  date:
                    type: string
                    format: date
                    example: "2024-03-31"
                  color:
                    type: string
                    pattern: "^#[0-9a-fA-F]{6}$"
                    example: "#ff0000"
                  milestone_type:
                    type: string
                    enum: [kickoff, review, approval, delivery, other]
                    default: other
                  status:
                    type: string
                    enum: [todo, wfa, done]
                    default: todo
        responses:
            201:
              description: Milestone created successfully
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
                        example: Milestone Name
                      project_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      date:
                        type: string
                        format: date
                        example: "2024-03-31"
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


class MilestoneResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Milestone)

    def check_read_permissions(self, milestone):
        permissions_service.check_project_access(milestone["project_id"])
        permissions_service.block_access_to_vendor()

    @jwt_required()
    def get(self, instance_id):
        """
        Get milestone
        ---
        tags:
          - Crud
        description: Retrieve a milestone by its ID and return it as a
          JSON object. Supports including relations. Vendor access is
          blocked. Requires project access.
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
              description: Milestone retrieved successfully
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
                        example: Milestone Name
                      project_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      date:
                        type: string
                        format: date
                        example: "2024-03-31"
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
        Update milestone
        ---
        tags:
          - Crud
        description: Update a milestone with data provided in the request
          body. JSON format is expected. Requires manager access to the
          project.
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
                    example: Updated Milestone Name
                  date:
                    type: string
                    format: date
                    example: "2024-04-30"
                  color:
                    type: string
                    nullable: true
                    pattern: "^#[0-9a-fA-F]{6}$"
                    example: "#00aa11"
                  milestone_type:
                    type: string
                    enum: [kickoff, review, approval, delivery, other]
                  status:
                    type: string
                    enum: [todo, wfa, done]
        responses:
            200:
              description: Milestone updated successfully
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
                        example: Updated Milestone Name
                      project_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      date:
                        type: string
                        format: date
                        example: "2024-04-30"
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
        Delete milestone
        ---
        tags:
          - Crud
        description: Delete a milestone by its ID. Returns empty response
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
              description: Milestone deleted successfully
            400:
              description: Integrity error or cannot delete
        """
        return super().delete(instance_id)

    def update_data(self, data, instance_id):
        data = super().update_data(data, instance_id)
        return check_milestone_fields(data)

    def check_update_permissions(self, milestone, data):
        return permissions_service.check_manager_project_access(
            milestone["project_id"]
        )

    def check_delete_permissions(self, milestone):
        return permissions_service.check_manager_project_access(
            milestone["project_id"]
        )
