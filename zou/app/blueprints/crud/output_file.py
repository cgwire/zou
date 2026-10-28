from flask import current_app
from flask_jwt_extended import jwt_required
from sqlalchemy.exc import StatementError

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.exceptions import WrongParameterException
from zou.app.models.entity import Entity
from zou.app.models.output_file import QUALITIES, OutputFile
from zou.app.models.project import Project
from zou.app.services import (
    entities_service,
    files_service,
    permissions_service,
    user_service,
)
from zou.app.utils import events, permissions
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/output_file.yml")


def check_quality(data):
    if data.get("quality") is not None and data["quality"] not in [
        quality for quality, _ in QUALITIES
    ]:
        raise WrongParameterException("Invalid quality")


class OutputFilesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, OutputFile)

    @jwt_required()
    @swag_from(SPECS["OutputFilesResource_get"])
    def get(self):
        """
        Get output files
        """
        return super().get()

    def check_read_permissions(self, options=None):
        return True

    def update_data(self, data):
        data = super().update_data(data)
        check_quality(data)
        return data

    def add_project_permission_filter(self, query):
        if permissions.has_admin_permissions():
            return query
        else:
            query = (
                query.join(Entity, OutputFile.entity_id == Entity.id)
                .join(Project)
                .filter(user_service.build_related_projects_filter())
            )
            # A vendor reads no output file, on the projects they are one.
            vendor_project_ids = user_service.get_project_ids_with_roles(
                "vendor"
            )
            if vendor_project_ids:
                query = query.filter(
                    Entity.project_id.not_in(vendor_project_ids)
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
        permissions_service.check_project_access(entity["project_id"])
        permissions_service.check_entity_access(entity["id"])
        return True

    def check_update_permissions(self, output_file, data):
        entity = entities_service.get_entity(output_file["entity_id"])
        if permissions_service.has_manager_project_access(
            entity["project_id"]
        ):
            return True
        else:
            return permissions_service.check_working_on_entity(
                output_file["temporal_entity_id"] or output_file["entity_id"]
            )

    @jwt_required()
    @swag_from(SPECS["OutputFileResource_get"])
    def get(self, instance_id):
        """
        Get output file
        """
        try:
            output_file = files_service.get_output_file(instance_id)
            self.check_read_permissions(output_file)
            return self.clean_get_result(output_file)

        except StatementError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        except ValueError:
            raise WrongParameterException("Invalid value.")

    @jwt_required()
    @swag_from(SPECS["OutputFileResource_put"])
    def put(self, instance_id):
        """
        Update output file
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["OutputFileResource_delete"])
    def delete(self, instance_id):
        """
        Delete output file
        """
        return super().delete(instance_id)

    def update_data(self, data, instance_id):
        data = super().update_data(data, instance_id)
        check_quality(data)
        return data

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
