from flask import current_app
from flask_jwt_extended import jwt_required
from sqlalchemy.exc import StatementError

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.exceptions import WrongParameterException
from zou.app.models.entity import Entity
from zou.app.models.output_file import QUALITIES, OutputFile
from zou.app.models.project import Project
from zou.app.models.working_file import WorkingFile
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

    def check_read_permissions(self, options=None):
        permissions_service.block_access_to_vendor()
        return True

    def serialize_list(self, entries, relations=False):
        output_files = super().serialize_list(entries, relations=relations)
        source_file_ids = {
            output_file.source_file_id
            for output_file in entries
            if output_file.source_file_id is not None
        }
        working_files = {}
        if source_file_ids:
            working_files = {
                working_file.id: working_file
                for working_file in WorkingFile.query.filter(
                    WorkingFile.id.in_(source_file_ids)
                ).all()
            }
        working_file_access = {}
        for output_file, serialized in zip(entries, output_files):
            working_file = working_files.get(output_file.source_file_id)
            if working_file is None:
                continue
            task_id = str(working_file.task_id)
            if task_id not in working_file_access:
                try:
                    permissions_service.check_working_file_access(task_id)
                    working_file_access[task_id] = True
                except permissions.PermissionDenied:
                    working_file_access[task_id] = False
            if not working_file_access[task_id]:
                serialized["source_file_id"] = None
                if "source_file" in serialized:
                    serialized["source_file"] = None
        return output_files

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

    def serialize_update_response(self, instance):
        output_file = super().serialize_update_response(instance)
        if instance.source_file_id is not None:
            working_file = WorkingFile.get(instance.source_file_id)
            try:
                permissions_service.check_working_file_access(
                    working_file.task_id
                )
            except permissions.PermissionDenied:
                output_file["source_file_id"] = None
        return output_file

    def check_update_permissions(self, output_file, data):
        entity = entities_service.get_entity(output_file["entity_id"])
        if permissions_service.has_manager_project_access(
            entity["project_id"]
        ):
            has_output_access = True
        else:
            has_output_access = permissions_service.check_working_on_entity(
                output_file["temporal_entity_id"] or output_file["entity_id"]
            )

        # Updating an output file must not let a user attach a Working file
        # from a task they cannot read. Existing clients may update this
        # optional relation, so retain the API shape and validate the target.
        working_file_id = data.get("source_file_id")
        if working_file_id is not None:
            working_file = files_service.get_working_file(working_file_id)
            permissions_service.check_working_file_access(
                working_file["task_id"]
            )

        return has_output_access

    @jwt_required()
    @swag_from(SPECS["OutputFileResource_get"])
    def get(self, instance_id):
        """
        Get output file
        """
        try:
            output_file = dict(files_service.get_output_file(instance_id))
            self.check_read_permissions(output_file)
            source_file_id = output_file.get("source_file_id")
            if source_file_id is not None:
                working_file = WorkingFile.get(source_file_id)
                try:
                    permissions_service.check_working_file_access(working_file.task_id)
                except permissions.PermissionDenied:
                    output_file["source_file_id"] = None
            return self.clean_get_result(output_file)

        except StatementError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        except ValueError:
            raise WrongParameterException("Invalid value.")

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
