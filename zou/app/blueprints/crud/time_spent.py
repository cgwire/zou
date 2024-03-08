from flask import abort

from sqlalchemy import func

from zou.app.utils import events

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource
from zou.app.services import user_service, tasks_service

from zou.app.models.time_spent import TimeSpent
from zou.app.models.task import Task


class TimeSpentsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, TimeSpent)

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
