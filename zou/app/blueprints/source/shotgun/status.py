from flask import current_app
from flask_jwt_extended import jwt_required

from zou.app.models.task_status import TaskStatus
from zou.app.utils import colors
from zou.app.services import tasks_service
from zou.app.blueprints.source.shotgun.base import (
    BaseImportShotgunResource,
    ImportRemoveShotgunBaseResource,
)


class ImportShotgunStatusResource(BaseImportShotgunResource):
    @jwt_required()
    def post(self):
        """
        Import shotgun task statuses
        ---
        description: Import Shotgun task statuses. Send a list of Shotgun
          status entries in the JSON body. Returns created or updated task
          statuses with colors.
        tags:
          - Import
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    id:
                      type: integer
                      description: Shotgun ID of the status
                      example: 12345
                    name:
                      type: string
                      description: Status name
                      example: "In Progress"
                    code:
                      type: string
                      description: Status short code
                      example: "IP"
                    bg_color:
                      type: string
                      description: Background color in RGB format
                      example: "255,128,0"
              example:
                - id: 12345
                  name: "In Progress"
                  code: "IP"
                  bg_color: "255,128,0"
        responses:
          200:
            description: Task statuses imported successfully
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
                        description: Task status unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Status name
                        example: "In Progress"
                      short_name:
                        type: string
                        description: Status short code
                        example: "IP"
                      color:
                        type: string
                        description: Status color in hex format
                        example: "#FF8000"
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        description: Update timestamp
                        example: "2024-01-15T11:00:00Z"
          400:
            description: Invalid request body or data format error
        """
        return super().post()

    def import_entry(self, data):
        task_status = self.get_existing_status(data)
        if task_status is None:
            task_status = TaskStatus(**data)
            task_status.save()
            current_app.logger.info("TaskStatus created: %s" % task_status)
        else:
            task_status.update(data)
            tasks_service.clear_task_status_cache(str(task_status.id))
            current_app.logger.info("TaskStatus updated: %s" % task_status)
        return task_status

    def extract_data(self, sg_status):
        color = sg_status.get("bg_color", "0,0,0")
        if color is None:
            color = "0,0,0"

        return {
            "name": sg_status["name"],
            "short_name": sg_status["code"],
            "shotgun_id": sg_status["id"],
            "color": colors.rgb_to_hex(color),
        }

    def get_existing_status(self, data):
        task_status = TaskStatus.get_by(shotgun_id=data["shotgun_id"])
        if task_status is None:
            task_status = TaskStatus.get_by(short_name=data["short_name"])
        return task_status


class ImportRemoveShotgunStatusResource(ImportRemoveShotgunBaseResource):
    def __init__(self):
        ImportRemoveShotgunBaseResource.__init__(self, TaskStatus)

    @jwt_required()
    def post(self):
        """
        Remove shotgun task status
        ---
        description: Remove a Shotgun task status from the database. Provide
          the Shotgun entry ID in the JSON body.
        tags:
          - Import
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - id
                properties:
                  id:
                    type: integer
                    description: Shotgun ID of the task status to remove
                    example: 12345
              example:
                id: 12345
        responses:
          200:
            description: Removal result returned
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    success:
                      type: boolean
                      description: Whether the removal was successful
                      example: true
                    removed_instance_id:
                      type: string
                      format: uuid
                      description: ID of the removed task status, if found
                      example: a24a6ea4-ce75-4665-a070-57453082c25
          400:
            description: Invalid request body or instance not found
        """
        return super().post()
