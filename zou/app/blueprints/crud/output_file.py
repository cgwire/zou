from flask import abort, current_app

from sqlalchemy.exc import StatementError
from flask_jwt_extended import jwt_required

from zou.app.utils import events
from zou.app.models.output_file import OutputFile
from zou.app.models.entity import Entity
from zou.app.models.project import Project
from zou.app.services import user_service, entities_service, files_service
from zou.app.utils import permissions

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource


class OutputFilesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, OutputFile)

    def check_read_permissions(self):
        user_service.block_access_to_vendor()
        return True

    def add_project_permission_filter(self, query):
        if permissions.has_admin_permissions():
            return query
        else:
            query = (
                query.join(Entity, OutputFile.entity_id == Entity.id)
                .join(Project)
                .filter(user_service.build_related_projects_filter())
            )
            return query

    def emit_create_event(self, instance_dict):
        entity = entities_service.get_entity(instance_dict["entity_id"])
        return events.emit(
            "output-file:new",
            {"output_file_id": instance_dict["id"]},
            project_id=entity["project_id"],
        )


class OutputFileResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, OutputFile)

    def check_read_permissions(self, instance):
        entity = entities_service.get_entity(instance["entity_id"])
        user_service.check_project_access(entity["project_id"])
        user_service.check_entity_access(entity["id"])
        return True

    def check_update_permissions(self, output_file, data):
        if permissions.has_manager_permissions():
            return True
        else:
            return user_service.check_working_on_entity(
                output_file["temporal_entity_id"] or output_file["entity_id"]
            )

    @jwt_required()
    def get(self, instance_id):
        """
        Retrieve a model corresponding at given ID and return it as a JSON
        object.
        ---
        tags:
          - Crud
        parameters:
          - in: path
            name: output_file_id
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
            output_file = files_service.get_output_file(instance_id)
            self.check_read_permissions(output_file)
            return self.clean_get_result(output_file)

        except StatementError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        except ValueError:
            abort(404)

    def post_update(self, instance_dict, data):
        files_service.clear_output_file_cache(instance_dict["id"])
        return instance_dict

    def post_delete(self, instance_dict):
        files_service.clear_output_file_cache(instance_dict["id"])
        return instance_dict

    def emit_update_event(self, instance_dict):
        entity = entities_service.get_entity(instance_dict["entity_id"])
        return events.emit(
            "output-file:update",
            {"output_file_id": instance_dict["id"]},
            project_id=entity["project_id"],
        )

    def emit_delete_event(self, instance_dict):
        entity = entities_service.get_entity(instance_dict["entity_id"])
        return events.emit(
            "output-file:delete",
            {"output_file_id": instance_dict["id"]},
            project_id=entity["project_id"],
        )
