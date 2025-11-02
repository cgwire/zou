from flask import current_app
from flask_jwt_extended import jwt_required

from zou.app.models.task_type import TaskType
from zou.app.models.task_status import TaskStatus
from zou.app.models.project import Project
from zou.app.models.person import Person
from zou.app.models.task import Task

from zou.app.services import deletion_service, tasks_service

from zou.app.blueprints.source.shotgun.base import (
    BaseImportShotgunResource,
    ImportRemoveShotgunBaseResource,
)


class ImportShotgunTasksResource(BaseImportShotgunResource):
    @jwt_required()
    def post(self):
        """
        Import shotgun tasks
        ---
        description: Import Shotgun tasks. Send a list of Shotgun task
          entries in the JSON body. Only tasks with steps and projects are
          imported. Returns created or updated tasks with assignees.
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
                      description: Shotgun ID of the task
                      example: 12345
                    cached_display_name:
                      type: string
                      description: Task display name
                      example: "Modeling for Asset"
                    start_date:
                      type: string
                      format: date
                      description: Start date
                      example: "2024-01-15"
                    due_date:
                      type: string
                      format: date
                      description: Due date
                      example: "2024-02-15"
                    sg_sort_order:
                      type: integer
                      description: Sort order
                      example: 1
                    duration:
                      type: integer
                      description: Duration in days
                      example: 30
                    step:
                      type: object
                      description: Step (task type) information
                      properties:
                        id:
                          type: integer
                          example: 11111
                    project:
                      type: object
                      description: Project information
                      properties:
                        id:
                          type: integer
                          example: 22222
                    entity:
                      type: object
                      description: Entity information
                      properties:
                        id:
                          type: integer
                          example: 33333
                        type:
                          type: string
                          example: "Asset"
                    sg_status_list:
                      type: string
                      description: Status short name
                      example: "IP"
                    created_by:
                      type: object
                      description: Creator information
                      properties:
                        id:
                          type: integer
                          example: 44444
                    task_assignees:
                      type: array
                      description: Task assignees
                      items:
                        type: object
                        properties:
                          id:
                            type: integer
                            example: 55555
              example:
                - id: 12345
                  cached_display_name: "Modeling for Asset"
                  start_date: "2024-01-15"
                  due_date: "2024-02-15"
                  sg_sort_order: 1
                  duration: 30
                  step:
                    id: 11111
                  project:
                    id: 22222
                  entity:
                    id: 33333
                    type: "Asset"
                  sg_status_list: "IP"
                  created_by:
                    id: 44444
                  task_assignees:
                    - id: 55555
        responses:
          200:
            description: Tasks imported successfully
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
                        description: Task unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Task name
                        example: "Modeling for Asset"
                      start_date:
                        type: string
                        format: date
                        description: Start date
                        example: "2024-01-15"
                      due_date:
                        type: string
                        format: date
                        description: Due date
                        example: "2024-02-15"
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

    def prepare_import(self):
        self.project_ids = Project.get_id_map()
        self.person_ids = Person.get_id_map()
        self.task_type_ids = TaskType.get_id_map(field="shotgun_id")
        self.task_status_ids = TaskStatus.get_id_map(field="short_name")

    def filtered_entries(self):
        return [x for x in self.sg_entries if self.is_valid_task(x)]

    def is_valid_task(self, sg_task):
        return sg_task["step"] is not None and sg_task["project"] is not None

    def extract_data(self, sg_task):
        entity_id = self.get_entity_id(sg_task["entity"])
        task_status_id = self.task_status_ids.get(
            sg_task["sg_status_list"], None
        )
        step_shotgun_id = sg_task["step"]["id"]
        assigner_id = self.person_ids.get(sg_task["created_by"]["id"], None)
        project_id = self.project_ids.get(sg_task["project"]["id"], None)
        task_type_id = self.task_type_ids.get(step_shotgun_id, None)
        assignees = self.extract_assignees(sg_task, self.person_ids)

        return {
            "name": sg_task["cached_display_name"],
            "shotgun_id": sg_task["id"],
            "start_date": sg_task["start_date"],
            "due_date": sg_task["due_date"],
            "sort_order": sg_task["sg_sort_order"],
            "duration": sg_task["duration"],
            "task_type_id": task_type_id,
            "task_status_id": task_status_id,
            "project_id": project_id,
            "entity_id": entity_id,
            "assigner_id": assigner_id,
            "assignees": assignees,
        }

    def get_entity_id(self, sg_entity):
        entity_id = None
        if sg_entity is not None:
            entity_sg_id = sg_entity["id"]
            entity_type = sg_entity["type"]
            if entity_type == "Asset":
                entity_id = self.get_asset_id(entity_sg_id)
            elif entity_type == "Shot":
                entity_id = self.get_shot_id(entity_sg_id)
            elif entity_type == "Scene":
                entity_id = self.get_scene_id(entity_sg_id)
            elif entity_type == "Sequence":
                entity_id = self.get_sequence_id(entity_sg_id)
            elif entity_type == "Episode":
                entity_id = self.get_episode_id(entity_sg_id)
            else:
                return None

        return entity_id

    def extract_assignees(self, sg_task, person_ids):
        assignees = []
        if len(sg_task["task_assignees"]) > 0:
            for sg_person in sg_task["task_assignees"]:
                person_id = person_ids[sg_person["id"]]
                person = Person.get(person_id)
                assignees.append(person)
        return assignees

    def import_entry(self, data):
        task = Task.get_by(shotgun_id=data["shotgun_id"])

        if task is None:
            task = Task.get_by(
                name=data["name"],
                project_id=data["project_id"],
                task_type_id=data["task_type_id"],
                entity_id=data["entity_id"],
            )

        if task is None:
            task = Task(**data)
            task.save()
            current_app.logger.info("Task created: %s" % task)
        else:
            existing_task = Task.get_by(
                name=data["name"],
                project_id=data["project_id"],
                task_type_id=data["task_type_id"],
                entity_id=data["entity_id"],
            )

            if existing_task is not None:
                data.pop("name", None)
                data.pop("project_id", None)
                data.pop("task_type_id", None)
                data.pop("entity_id", None)

            task.update(data)
            tasks_service.clear_task_cache(str(task.id))
            current_app.logger.info("Task updated: %s" % task)

        return task


class ImportRemoveShotgunTaskResource(ImportRemoveShotgunBaseResource):
    def __init__(self):
        ImportRemoveShotgunBaseResource.__init__(self, Task, self.delete_func)

    @jwt_required()
    def post(self):
        """
        Remove shotgun task
        ---
        description: Remove a Shotgun task from the database. Provide the
          Shotgun entry ID in the JSON body.
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
                    description: Shotgun ID of the task to remove
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
                      description: ID of the removed task, if found
                      example: a24a6ea4-ce75-4665-a070-57453082c25
          400:
            description: Invalid request body or instance not found
        """
        return super().post()

    def delete_func(self, entity):
        deletion_service.remove_task(entity.id)
        tasks_service.clear_task_cache(str(entity.id))
