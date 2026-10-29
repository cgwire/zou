from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app.blueprints.entities.schemas import CreateEntityTasksSchema
from zou.app.exceptions import EntityNotFoundException
from zou.app.mixin import ArgsMixin
from zou.app.services import (
    cascade_deletion_service,
    entities_service,
    news_service,
    permissions_service,
    preview_files_service,
    projects_service,
    task_types_service,
    tasks_service,
    time_spents_service,
)
from zou.app.utils import permissions, validation
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi.yml")


class EntityNewsResource(MethodView):
    @jwt_required()
    @swag_from(SPECS["EntityNewsResource_get"])
    def get(self, entity_id):
        """
        Get entity news
        """
        entity = entities_service.get_entity(entity_id)
        permissions_service.check_project_access(entity["project_id"])
        permissions_service.check_entity_access(entity_id)
        permissions_service.block_access_to_client()
        return news_service.get_news_for_entity(entity_id)


class EntityPreviewFilesResource(MethodView):
    @jwt_required()
    @swag_from(SPECS["EntityPreviewFilesResource_get"])
    def get(self, entity_id):
        """
        Get entity preview files
        """
        entity = entities_service.get_entity(entity_id)
        permissions_service.check_project_access(entity["project_id"])
        permissions_service.check_entity_access(entity_id)
        return preview_files_service.get_preview_files_for_entity(entity_id)


class EntityTimeSpentsResource(MethodView):
    @jwt_required()
    @swag_from(SPECS["EntityTimeSpentsResource_get"])
    def get(self, entity_id):
        """
        Get entity time spent
        """
        entity = entities_service.get_entity(entity_id)
        permissions_service.check_project_access(entity["project_id"])
        permissions_service.check_entity_access(entity_id)
        permissions_service.block_access_to_client()
        return time_spents_service.get_time_spents_for_entity(entity_id)


class EntitiesLinkedWithTasksResource(MethodView):
    @jwt_required()
    @swag_from(SPECS["EntitiesLinkedWithTasksResource_get"])
    def get(self, entity_id):
        """
        Get linked entities
        """
        entity = entities_service.get_entity(entity_id)
        permissions_service.check_project_access(entity["project_id"])
        permissions_service.check_entity_access(entity_id)
        permissions_service.block_access_to_client()
        return entities_service.get_linked_entities_with_tasks(entity_id)


class EntityTaskCreationResource(MethodView):
    @jwt_required()
    @swag_from(SPECS["EntityTaskCreationResource_post"])
    def post(self, entity_id):
        """
        Create tasks for an entity
        """
        entity = entities_service.get_entity(entity_id)
        permissions_service.check_project_access(entity["project_id"])
        permissions_service.check_entity_access(entity_id)
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied
        body = validation.validate_request_body(CreateEntityTasksSchema)
        task_types = [
            task_types_service.get_task_type(task_type_id)
            for task_type_id in body.task_type_ids
        ]
        tasks = tasks_service.create_tasks_for_entity(entity, task_types)
        return tasks, 201


class ProjectDeleteEntitiesResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from(SPECS["ProjectDeleteEntitiesResource_post"])
    def post(self, project_id):
        """
        Delete entities batch
        """
        force = self.get_force()
        projects_service.get_project(project_id)
        entity_ids = validation.validate_id_list()

        for entity_id in entity_ids:
            try:
                entity = entities_service.get_entity(entity_id)
            except EntityNotFoundException:
                # Nothing to authorize for an entity that is already gone.
                continue
            permissions_service.check_entity_delete_access(entity, force=force)

        return (
            cascade_deletion_service.remove_entities(
                project_id, entity_ids, force=force
            ),
            200,
        )
