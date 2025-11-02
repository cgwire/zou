from flask import request, current_app
from flask_jwt_extended import jwt_required

from sqlalchemy.orm import aliased
from sqlalchemy.exc import IntegrityError

from zou.app.mixin import ArgsMixin
from zou.app.models.entity import Entity
from zou.app.models.person import Person
from zou.app.models.project import Project
from zou.app.models.task import Task

from zou.app.services import (
    user_service,
    tasks_service,
    deletion_service,
    entities_service,
    assets_service,
)
from zou.app.utils import permissions

from zou.app.services.exception import WrongTaskTypeForEntityException

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource


class TasksResource(BaseModelsResource, ArgsMixin):
    def __init__(self):
        BaseModelsResource.__init__(self, Task)

    def check_read_permissions(self, options=None):
        return True

    @jwt_required()
    def get(self):
        """
        Get tasks
        ---
        tags:
          - Crud
        description: Retrieve all tasks. Supports filtering via query
          parameters and pagination. Includes project permission filtering
          for non-admin users. Vendor users only see assigned tasks.
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
          - in: query
            name: episode_id
            required: false
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Filter tasks by episode ID
        responses:
            200:
              description: Tasks retrieved successfully
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

    def add_project_permission_filter(self, query):
        if permissions.has_vendor_permissions():
            query = query.filter(user_service.build_assignee_filter())
        elif not permissions.has_admin_permissions():
            query = query.join(Project).filter(
                user_service.build_related_projects_filter()
            )
        return query

    def build_filters(self, options):
        (
            many_join_filter,
            in_filter,
            name_filter,
            criterions,
        ) = super().build_filters(options)
        if "episode_id" in criterions:
            del criterions["episode_id"]
        return (
            many_join_filter,
            in_filter,
            name_filter,
            criterions,
        )

    def apply_filters(self, query, options):
        query = super().apply_filters(query, options)

        episode_id = options.get("episode_id", None)
        if episode_id is not None:
            Sequence = aliased(Entity)
            query = (
                query.join(Entity, Task.entity_id == Entity.id)
                .join(Sequence, Entity.parent_id == Sequence.id)
                .filter(Sequence.parent_id == episode_id)
            )

        return query

    @jwt_required()
    def post(self):
        """
        Create task
        ---
        tags:
          - Crud
        description: Create a task with data provided in the request
          body. JSON format is expected. The task type must match the
          entity type.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - task_type_id
                  - entity_id
                properties:
                  task_type_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  entity_id:
                    type: string
                    format: uuid
                    example: b24a6ea4-ce75-4665-a070-57453082c25
                  assignees:
                    type: array
                    items:
                      type: string
                      format: uuid
                    example: ["c24a6ea4-ce75-4665-a070-57453082c25"]
        responses:
            201:
              description: Task created successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: d24a6ea4-ce75-4665-a070-57453082c25
                      task_type_id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      entity_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      assignees:
                        type: array
                        items:
                          type: string
                          format: uuid
                        example: ["c24a6ea4-ce75-4665-a070-57453082c25"]
            400:
              description: Task type does not match entity type or task already exists
        """
        try:
            data = request.json
            is_assignees = "assignees" in data
            assignees = None

            task_type = tasks_service.get_task_type(data["task_type_id"])
            entity = entities_service.get_entity(data["entity_id"])
            if task_type["for_entity"] == "Asset":
                if not assets_service.is_asset_dict(entity):
                    raise WrongTaskTypeForEntityException(
                        "Task type of the task does not match entity type."
                    )
            elif (
                entities_service.get_temporal_entity_type_by_name(
                    task_type["for_entity"]
                )["id"]
                != entity["entity_type_id"]
            ):
                raise WrongTaskTypeForEntityException(
                    "Task type of the task does not match entity type."
                )

            if is_assignees:
                assignees = data["assignees"]
                persons = Person.query.filter(Person.id.in_(assignees)).all()
                del data["assignees"]

            instance = self.model(**data)
            if assignees is not None:
                instance.assignees = persons
            instance.save()
            self.emit_create_event(instance.serialize())

            return (
                tasks_service.get_task(str(instance.id), relations=True),
                201,
            )

        except TypeError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        except IntegrityError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": "Task already exists."}, 400


class TaskResource(BaseModelResource, ArgsMixin):
    def __init__(self):
        BaseModelResource.__init__(self, Task)

    def check_read_permissions(self, task):
        user_service.check_project_access(task["project_id"])
        user_service.check_entity_access(task["entity_id"])

    @jwt_required()
    def get(self, instance_id):
        """
        Get task
        ---
        tags:
          - Crud
        description: Retrieve a task by its ID and return it as a JSON
          object. Supports including relations. Requires project and
          entity access.
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
              description: Task retrieved successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      task_type_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      entity_id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
                      project_id:
                        type: string
                        format: uuid
                        example: d24a6ea4-ce75-4665-a070-57453082c25
                      task_status_id:
                        type: string
                        format: uuid
                        example: e24a6ea4-ce75-4665-a070-57453082c25
                      assignees:
                        type: array
                        items:
                          type: string
                          format: uuid
                        example: ["f24a6ea4-ce75-4665-a070-57453082c25"]
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
        Update task
        ---
        tags:
          - Crud
        description: Update a task with data provided in the request
          body. JSON format is expected. Requires supervisor access.
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
                  task_status_id:
                    type: string
                    format: uuid
                    example: b24a6ea4-ce75-4665-a070-57453082c25
                  assignees:
                    type: array
                    items:
                      type: string
                      format: uuid
                    example: ["c24a6ea4-ce75-4665-a070-57453082c25"]
                  duration:
                    type: number
                    example: 8.5
        responses:
            200:
              description: Task updated successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      task_type_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      entity_id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
                      project_id:
                        type: string
                        format: uuid
                        example: d24a6ea4-ce75-4665-a070-57453082c25
                      task_status_id:
                        type: string
                        format: uuid
                        example: e24a6ea4-ce75-4665-a070-57453082c25
                      assignees:
                        type: array
                        items:
                          type: string
                          format: uuid
                        example: ["f24a6ea4-ce75-4665-a070-57453082c25"]
                      duration:
                        type: number
                        example: 8.5
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

    def check_update_permissions(self, task, data):
        user_service.check_supervisor_task_access(task, data)

    def check_delete_permissions(self, task):
        user_service.check_manager_project_access(task["project_id"])

    def post_update(self, instance_dict, data):
        tasks_service.clear_task_cache(instance_dict["id"])
        return instance_dict

    @jwt_required()
    def delete(self, instance_id):
        """
        Delete task
        ---
        tags:
          - Crud
        description: Delete a task by its ID. Returns empty response on
          success. May require force flag if task has associated data.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: force
            required: false
            schema:
              type: boolean
            default: false
            example: false
            description: Force deletion even if task has associated data
        responses:
            204:
              description: Task deleted successfully
            400:
              description: Integrity error or cannot delete
        """
        force = self.get_force()

        instance = self.get_model_or_404(instance_id)

        try:
            instance_dict = instance.serialize()
            self.check_delete_permissions(instance_dict)
            deletion_service.remove_task(instance_id, force=force)
            tasks_service.clear_task_cache(instance_id)
            self.post_delete(instance_dict)

        except IntegrityError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        return "", 204
