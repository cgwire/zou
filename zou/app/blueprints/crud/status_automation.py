from flask import current_app
from flask_jwt_extended import jwt_required
from sqlalchemy.exc import IntegrityError, StatementError

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource

from zou.app.models.status_automation import StatusAutomation
from zou.app.models.project import ProjectStatusAutomationLink
from zou.app.services import status_automations_service, user_service


class StatusAutomationsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, StatusAutomation)

    def check_read_permissions(self, options=None):
        user_service.block_access_to_vendor()
        return True

    @jwt_required()
    def get(self):
        """
        Get status automations
        ---
        tags:
          - Crud
        description: Retrieve all status automations. Supports filtering
          via query parameters and pagination. Vendor access is blocked.
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
              description: Status automations retrieved successfully
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
        Create status automation
        ---
        tags:
          - Crud
        description: Create a new status automation with data provided
          in the request body. JSON format is expected.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - source_task_status_id
                  - target_task_status_id
                  - field_name
                  - field_value
                properties:
                  source_task_status_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  target_task_status_id:
                    type: string
                    format: uuid
                    example: b24a6ea4-ce75-4665-a070-57453082c25
                  field_name:
                    type: string
                    example: ready_for
                  field_value:
                    type: string
                    example: production
        responses:
            201:
              description: Status automation created successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      source_task_status_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      target_task_status_id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
                      field_name:
                        type: string
                        example: ready_for
                      field_value:
                        type: string
                        example: production
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

    def post_creation(self, status_automation):
        status_automations_service.clear_status_automation_cache()
        return status_automation.serialize()


class StatusAutomationResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, StatusAutomation)

    @jwt_required()
    def get(self, instance_id):
        """
        Get status automation
        ---
        tags:
          - Crud
        description: Retrieve a status automation by its ID and return
          it as a JSON object. Supports including relations.
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
              description: Status automation retrieved successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      source_task_status_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      target_task_status_id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
                      field_name:
                        type: string
                        example: ready_for
                      field_value:
                        type: string
                        example: production
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
        Update status automation
        ---
        tags:
          - Crud
        description: Update a status automation with data provided in
          the request body. JSON format is expected.
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
                  field_name:
                    type: string
                    example: ready_for
                  field_value:
                    type: string
                    example: approved
        responses:
            200:
              description: Status automation updated successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      source_task_status_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      target_task_status_id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
                      field_name:
                        type: string
                        example: ready_for
                      field_value:
                        type: string
                        example: approved
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

    def post_update(self, status_automation, data):
        status_automations_service.clear_status_automation_cache()
        return status_automation

    @jwt_required()
    def delete(self, instance_id):
        """
        Delete status automation
        ---
        tags:
          - Crud
        description: Delete a status automation by its ID. Returns empty
          response on success. Cannot delete if automation is used in a
          project.
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
              description: Status automation deleted successfully
            400:
              description: Automation is used in a project or integrity error
        """
        instance = self.get_model_or_404(instance_id)
        instance_dict = instance.serialize()
        links = ProjectStatusAutomationLink.query.filter_by(
            status_automation_id=instance_dict["id"]
        ).all()
        if len(links) > 0:
            return {"message": "This automation is used in a project."}, 400

        try:
            self.check_delete_permissions(instance_dict)
            self.pre_delete(instance_dict)
            instance.delete()
            self.emit_delete_event(instance_dict)
            self.post_delete(instance_dict)

        except IntegrityError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        except StatementError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        return "", 204

    def post_delete(self, status_automation):
        status_automations_service.clear_status_automation_cache()
        return status_automation
