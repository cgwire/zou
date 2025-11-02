from flask import abort
from flask_jwt_extended import jwt_required

from sqlalchemy import func

from zou.app.utils import events

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource
from zou.app.services import user_service, tasks_service

from zou.app.models.time_spent import TimeSpent
from zou.app.models.task import Task


class TimeSpentsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, TimeSpent)

    @jwt_required()
    def get(self):
        """
        Get time spents
        ---
        tags:
          - Crud
        description: Retrieve all time spent records. Supports filtering
          via query parameters and pagination. Supports date range
          filtering with start_date and end_date.
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
            name: start_date
            required: false
            schema:
              type: string
              format: date
            example: "2024-01-01"
            description: Start date for date range filter
          - in: query
            name: end_date
            required: false
            schema:
              type: string
              format: date
            example: "2024-01-31"
            description: End date for date range filter
        responses:
            200:
              description: Time spent records retrieved successfully
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
        Create time spent
        ---
        tags:
          - Crud
        description: Create a new time spent record with data provided
          in the request body. JSON format is expected. Updates task
          duration automatically.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - task_id
                  - person_id
                  - date
                  - duration
                properties:
                  task_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  person_id:
                    type: string
                    format: uuid
                    example: b24a6ea4-ce75-4665-a070-57453082c25
                  date:
                    type: string
                    format: date
                    example: "2024-01-15"
                  duration:
                    type: number
                    example: 8.5
        responses:
            201:
              description: Time spent record created successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      task_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      person_id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
                      date:
                        type: string
                        format: date
                        example: "2024-01-15"
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
                        example: "2024-01-15T10:30:00Z"
            400:
              description: Invalid data format or validation error
        """
        return super().post()

    def apply_filters(self, query, options):
        query = super(TimeSpentsResource, self).apply_filters(query, options)
        start_date = options.get("start_date", None)
        end_date = options.get("end_date", None)
        if not start_date and not end_date:
            return query

        if None in [start_date, end_date]:
            abort(
                400,
                "If querying for a range of dates, both a `start_date` and an "
                "`end_date` must be given.",
            )

        return query.filter(
            self.model.date.between(
                func.cast(start_date, TimeSpent.date.type)
            ),
            func.cast(end_date, TimeSpent.date.type),
        )

    def post_creation(self, instance):
        task_id = str(instance.task_id)
        task = Task.get(task_id)
        task.duration = sum(
            time_spent.duration
            for time_spent in TimeSpent.get_all_by(task_id=task_id)
        )
        task.save()
        tasks_service.clear_task_cache(task_id)
        events.emit(
            "task:update",
            {"task_id": task_id},
            project_id=str(task.project_id),
        )
        return instance.serialize()


class TimeSpentResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, TimeSpent)

    def check_delete_permissions(self, instance_dict):
        return user_service.check_time_spent_access(
            instance_dict["task_id"], instance_dict["person_id"]
        )

    @jwt_required()
    def get(self, instance_id):
        """
        Get time spent
        ---
        tags:
          - Crud
        description: Retrieve a time spent record by its ID and return
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
              description: Time spent record retrieved successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      task_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      person_id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
                      date:
                        type: string
                        format: date
                        example: "2024-01-15"
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
                        example: "2024-01-15T10:30:00Z"
            400:
              description: Invalid ID format or query error
        """
        return super().get(instance_id)

    @jwt_required()
    def put(self, instance_id):
        """
        Update time spent
        ---
        tags:
          - Crud
        description: Update a time spent record with data provided in
          the request body. JSON format is expected. Updates task
          duration automatically.
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
                  date:
                    type: string
                    format: date
                    example: "2024-01-16"
                  duration:
                    type: number
                    example: 7.5
        responses:
            200:
              description: Time spent record updated successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      task_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      person_id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
                      date:
                        type: string
                        format: date
                        example: "2024-01-16"
                      duration:
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
        Delete time spent
        ---
        tags:
          - Crud
        description: Delete a time spent record by its ID. Returns
          empty response on success. Updates task duration
          automatically.
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
              description: Time spent record deleted successfully
            400:
              description: Integrity error or cannot delete
        """
        return super().delete(instance_id)

    def post_update(self, instance_dict, data):
        task = Task.get(instance_dict["task_id"])
        task.duration = sum(
            time_spent.duration
            for time_spent in TimeSpent.get_all_by(
                task_id=instance_dict["task_id"]
            )
        )
        task.save()
        tasks_service.clear_task_cache(instance_dict["task_id"])
        events.emit(
            "task:update",
            {"task_id": instance_dict["task_id"]},
            project_id=str(task.project_id),
        )
        return instance_dict

    def post_delete(self, instance_dict):
        task = Task.get(instance_dict["task_id"])
        task.duration = sum(
            time_spent.duration
            for time_spent in TimeSpent.get_all_by(
                task_id=instance_dict["task_id"]
            )
        )
        task.save()
        tasks_service.clear_task_cache(instance_dict["task_id"])
        events.emit(
            "task:update",
            {"task_id": instance_dict["task_id"]},
            project_id=str(task.project_id),
        )
        return instance_dict
