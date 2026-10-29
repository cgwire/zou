from flask import current_app
from flask_jwt_extended import jwt_required
from sqlalchemy.exc import StatementError

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.exceptions import WrongParameterException
from zou.app.models.entity import Entity
from zou.app.models.preview_file import VALIDATION_STATUSES
from zou.app.models.project import Project
from zou.app.models.working_file import WorkingFile
from zou.app.services import files_service, permissions_service, user_service
from zou.app.utils import permissions
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/working_file.yml")


def check_validation_status(data):
    if "validation_status" in data and data["validation_status"] not in [
        status for status, _ in VALIDATION_STATUSES
    ]:
        raise WrongParameterException("Invalid validation_status")


class WorkingFilesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, WorkingFile)

    def get_relations_eager_load(self):
        return [WorkingFile.outputs]

    def check_read_permissions(self, options=None):
        """
        Require a task or entity scope for non-admin working-file queries.
        """
        if permissions.has_admin_permissions():
            return True

        options = options or {}
        task_id = options.get("task_id")
        entity_id = options.get("entity_id")
        if task_id:
            return permissions_service.check_working_file_access(task_id)
        if entity_id:
            return permissions_service.check_working_file_entity_access(
                entity_id
            )
        raise permissions.PermissionDenied

    @jwt_required()
    @swag_from(SPECS["WorkingFilesResource_get"])
    def get(self):
        """
        Get working files
        """
        return super().get()

    def check_create_permissions(self, data):
        """
        Require the task-scoped action to create a WorkingFile revision.
        """
        raise permissions.PermissionDenied

    @jwt_required()
    @swag_from(SPECS["WorkingFilesResource_post"])
    def post(self):
        """
        Create working file
        """
        return super().post()

    def update_data(self, data):
        data = super().update_data(data)
        check_validation_status(data)
        return data

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
        # A WorkingFile's task, entity, and person identify its security
        # scope and owner. Generic CRUD updates must not be able to reassign
        # those fields after permission checks have run against stored state.
        self.protected_fields += ["task_id", "entity_id", "person_id"]

    def check_read_permissions(self, instance):
        working_file = files_service.get_working_file(instance["id"])
        return permissions_service.check_working_file_access(
            working_file["task_id"]
        )

    def check_update_permissions(self, instance, data):
        working_file = files_service.get_working_file(instance["id"])
        return permissions_service.check_working_file_access(
            working_file["task_id"], require_assigned_artist=True
        )

    @jwt_required()
    @swag_from(SPECS["WorkingFileResource_put"])
    def put(self, instance_id):
        """
        Update working file
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["WorkingFileResource_delete"])
    def delete(self, instance_id):
        """
        Delete working file
        """
        return super().delete(instance_id)

    @jwt_required()
    @swag_from(SPECS["WorkingFileResource_get"])
    def get(self, instance_id):
        """
        Get working file
        """
        try:
            working_file = files_service.get_working_file(instance_id)
            self.check_read_permissions(working_file)
            return self.clean_get_result(working_file)

        except StatementError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        except ValueError:
            raise WrongParameterException("Invalid value.")

    def update_data(self, data, instance_id):
        data = super().update_data(data, instance_id)
        check_validation_status(data)
        return data

    def post_update(self, instance_dict, data):
        files_service.clear_working_file_cache(instance_dict["id"])
        return instance_dict

    def post_delete(self, instance_dict):
        files_service.clear_working_file_cache(instance_dict["id"])
        return instance_dict
