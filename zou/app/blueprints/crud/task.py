from flask import request, current_app
from flask_restful import reqparse
from flask_jwt_extended import jwt_required

from sqlalchemy.exc import IntegrityError

from zou.app.models.person import Person
from zou.app.models.project import Project
from zou.app.models.task import Task

from zou.app.services import user_service, tasks_service, deletion_service
from zou.app.utils import permissions

from .base import BaseModelsResource, BaseModelResource


class TasksResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Task)

    def check_read_permissions(self):
        return True

    def add_project_permission_filter(self, query):
        if permissions.has_vendor_permissions():
            query = query.filter(user_service.build_assignee_filter())
        elif not permissions.has_admin_permissions():
            query = query.join(Project).filter(
                user_service.build_related_projects_filter()
            )
        return query

    def post(self):
        """
        Create a task with data given in the request body. JSON format is
        expected. The model performs the validation automatically when
        instantiated.
        """
        try:
            data = request.json
            is_assignees = "assignees" in data
            assignees = None

            if is_assignees:
                assignees = data["assignees"]
                persons = Person.query.filter(Person.id.in_(assignees)).all()
                del data["assignees"]

            instance = self.model(**data)
            if assignees is not None:
                instance.assignees = persons
            instance.save()

            return tasks_service.get_task_with_relations(str(instance.id)), 201

        except TypeError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        except IntegrityError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": "Task already exists."}, 400


class TaskResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Task)

    def check_read_permissions(self, task):
        user_service.check_project_access(task["project_id"])
        user_service.check_entity_access(task["entity_id"])

    def check_update_permissions(self, task, data):
        user_service.check_supervisor_task_access(task, data)

    def check_delete_permissions(self, task):
        user_service.check_manager_project_access(task["project_id"])

    def post_update(self, instance_dict):
        tasks_service.clear_task_cache(instance_dict["id"])

    @jwt_required
    def delete(self, instance_id):
        """
        Delete a model corresponding at given ID and return it as a JSON
        object.
        """
        parser = reqparse.RequestParser()
        parser.add_argument("force", default=False, type=bool)
        args = parser.parse_args()

        instance = self.get_model_or_404(instance_id)

        try:
            instance_dict = instance.serialize()
            self.check_delete_permissions(instance_dict)
            deletion_service.remove_task(instance_id, force=args["force"])
            tasks_service.clear_task_cache(instance_id)
            self.post_delete(instance_dict)

        except IntegrityError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        return "", 204
