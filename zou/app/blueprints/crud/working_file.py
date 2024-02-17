from flask import abort, current_app

from sqlalchemy.exc import StatementError
from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource

from zou.app.models.entity import Entity
from zou.app.models.project import Project
from zou.app.models.working_file import WorkingFile
from zou.app.services import user_service, tasks_service, files_service
from zou.app.utils import permissions


class WorkingFilesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, WorkingFile)

    def check_read_permissions(self):
        """
        Overriding so that people without admin credentials can still access
        this resource.
        """
        user_service.block_access_to_vendor()
        return True

    def add_project_permission_filter(self, query):
        """
        Filtering to keep only the files from projects available to the user's
        team. Allows projects that are no longer open.
        """
        if permissions.has_admin_permissions():
            return query
        else:
            query = (
                query.join(Entity, WorkingFile.entity_id == Entity.id)
                .join(Project)
                .filter(user_service.build_team_filter())
            )
            return query


class WorkingFileResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, WorkingFile)

    def check_read_permissions(self, instance):
        working_file = files_service.get_working_file(instance["id"])
        task = tasks_service.get_task(working_file["task_id"])
        user_service.check_project_access(task["project_id"])
        user_service.check_entity_access(task["entity_id"])
        return True

    def check_update_permissions(self, instance, data):
        working_file = files_service.get_working_file(instance["id"])
        task = tasks_service.get_task(working_file["task_id"])
        user_service.check_project_access(task["project_id"])
        user_service.check_entity_access(task["entity_id"])
        return True

    @jwt_required()
    def get(self, instance_id):
        """
        Retrieve a working file corresponding at given ID and return it as a
        JSON object.
        ---
        tags:
          - Crud
        parameters:
          - in: path
            name: working_file_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Model as a JSON object
            400:
                description: Statement error
            404:
                description: Value error
        """
        try:
            working_file = files_service.get_working_file(instance_id)
            self.check_read_permissions(working_file)
            return self.clean_get_result(working_file)

        except StatementError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        except ValueError:
            abort(404)

    def post_update(self, instance_dict, data):
        files_service.clear_working_file_cache(instance_dict["id"])
        return instance_dict

    def post_delete(self, instance_dict):
        files_service.clear_working_file_cache(instance_dict["id"])
        return instance_dict
