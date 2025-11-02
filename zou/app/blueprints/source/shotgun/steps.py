from flask import current_app
from flask_restful import Resource
from flask_jwt_extended import jwt_required

from zou.app.models.department import Department
from zou.app.models.task_type import TaskType
from zou.app.utils import colors
from zou.app.services import tasks_service

from zou.app.blueprints.source.shotgun.base import (
    BaseImportShotgunResource,
    ImportRemoveShotgunBaseResource,
)


class ImportShotgunStepsResource(BaseImportShotgunResource):
    def __init__(self):
        Resource.__init__(self)

    @jwt_required()
    def post(self):
        """
        Import shotgun steps
        ---
        description: Import Shotgun steps (task types). Send a list of
          Shotgun step entries in the JSON body. Returns created or updated
          task types with departments.
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
                      description: Shotgun ID of the step
                      example: 12345
                    code:
                      type: string
                      description: Step code (used to extract department)
                      example: "Animation Modeling"
                    short_name:
                      type: string
                      description: Step short name
                      example: "mod"
                    color:
                      type: string
                      description: Color in RGB format
                      example: "255,128,0"
                    entity_type:
                      type: string
                      description: Entity type this step applies to
                      example: "Asset"
              example:
                - id: 12345
                  code: "Animation Modeling"
                  short_name: "mod"
                  color: "255,128,0"
                  entity_type: "Asset"
        responses:
          200:
            description: Task types imported successfully
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
                        description: Task type unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Task type name
                        example: "Animation Modeling"
                      short_name:
                        type: string
                        description: Task type short name
                        example: "mod"
                      color:
                        type: string
                        description: Task type color in hex format
                        example: "#FF8000"
                      for_entity:
                        type: string
                        description: Entity type
                        example: "Asset"
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

    def extract_data(self, sg_step):
        color = self.extract_color(sg_step)
        department_name = self.extract_department_name(sg_step)
        return {
            "name": sg_step["code"],
            "short_name": sg_step.get("short_name", ""),
            "shotgun_id": sg_step["id"],
            "color": color,
            "department_name": department_name,
            "for_entity": sg_step.get("entity_type", "Asset"),
        }

    def extract_color(self, sg_step):
        color = sg_step.get("color", "0,0,0")
        return colors.rgb_to_hex(color)

    def extract_department_name(self, sg_step):
        splitted_name = sg_step["code"].split(" ")
        department_name = splitted_name[0]
        return department_name

    def import_entry(self, data):
        department = self.save_department(data)
        return self.save_task_type(department, data)

    def save_department(self, data):
        department = Department.get_by(name=data["department_name"])
        if department is None:
            department_data = {
                "name": data["department_name"],
                "color": data["color"],
            }
            department = Department(**department_data)
            department.save()
            current_app.logger.info("Department created: %s" % department)
        del data["department_name"]
        return department

    def save_task_type(self, department, data):
        task_type = TaskType.get_by(shotgun_id=data["shotgun_id"])
        data["department_id"] = department.id
        if task_type is None:
            task_type = TaskType.get_by(
                name=data["name"], for_entity=data["for_entity"]
            )

        if task_type is None:
            task_type = TaskType(**data)
            task_type.save()
            current_app.logger.info("Task Type created: %s" % task_type)
        else:
            existing_task_type = TaskType.get_by(
                name=data["name"],
                for_entity=data["for_entity"],
                department_id=data["department_id"],
            )
            if existing_task_type is not None:
                data.pop("name", None)
                data.pop("for_entity", None)
                data.pop("department_id", None)
            task_type.update(data)
            tasks_service.clear_task_type_cache(str(task_type.id))
            current_app.logger.info("Task Type updated: %s" % task_type)
        return task_type


class ImportRemoveShotgunStepResource(ImportRemoveShotgunBaseResource):
    def __init__(self):
        ImportRemoveShotgunBaseResource.__init__(self, TaskType)

    @jwt_required()
    def post(self):
        """
        Remove shotgun step
        ---
        description: Remove a Shotgun step (task type) from the database.
          Provide the Shotgun entry ID in the JSON body.
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
                    description: Shotgun ID of the step to remove
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
                      description: ID of the removed step, if found
                      example: a24a6ea4-ce75-4665-a070-57453082c25
          400:
            description: Invalid request body or instance not found
        """
        return super().post()
