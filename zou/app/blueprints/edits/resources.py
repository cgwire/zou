from flasgger import swag_from
from flask import request
from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app.services import (
    persons_service,
    projects_service,
    playlists_service,
    edits_service,
    shots_service,
    tasks_service,
    permissions_service,
    cascade_deletion_service,
)

from zou.app.mixin import ArgsMixin
from zou.app.utils import permissions, query, validation
from zou.app.blueprints.edits.schemas import NewEditSchema


class EditResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/EditResource_get.yml")
    def get(self, edit_id):
        """
        Get edit
        """
        edit = edits_service.get_full_edit(edit_id)
        permissions_service.check_project_access(edit["project_id"])
        permissions_service.check_entity_access(edit["id"])
        return edit

    @jwt_required()
    @swag_from("openapi/EditResource_delete.yml")
    def delete(self, edit_id):
        """
        Delete edit
        """
        force = self.get_force()
        edit = edits_service.get_edit(edit_id)
        if edit["created_by"] == persons_service.get_current_user()["id"]:
            permissions_service.check_belong_to_project(edit["project_id"])
        else:
            permissions_service.check_manager_project_access(
                edit["project_id"]
            )
        cascade_deletion_service.remove_edit(edit_id, force=force)
        return "", 204


class AllEditsResource(MethodView):
    @jwt_required()
    @swag_from("openapi/AllEditsResource_get.yml")
    def get(self):
        """
        Get all edits
        """
        criterions = query.get_query_criterions_from_request(request)
        permissions_service.check_project_access(
            criterions.get("project_id", None)
        )
        permissions_service.scope_criterions_to_vendor(criterions)
        return edits_service.get_edits(criterions)


class EditTaskTypesResource(MethodView):
    @jwt_required()
    @swag_from("openapi/EditTaskTypesResource_get.yml")
    def get(self, edit_id):
        """
        Get edit task types
        """
        edit = edits_service.get_edit(edit_id)
        permissions_service.check_project_access(edit["project_id"])
        permissions_service.check_entity_access(edit["id"])
        return tasks_service.get_task_types_for_edit(edit_id)


class EditTasksResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/EditTasksResource_get.yml")
    def get(self, edit_id):
        """
        Get edit tasks
        """
        edit = edits_service.get_edit(edit_id)
        permissions_service.check_project_access(edit["project_id"])
        permissions_service.check_entity_access(edit["id"])
        relations = self.get_relations()
        return tasks_service.get_tasks_for_edit(edit_id, relations=relations)


class EpisodeEditTasksResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/EpisodeEditTasksResource_get.yml")
    def get(self, episode_id):
        """
        Get episode edit tasks
        """
        episode = shots_service.get_episode(episode_id)
        permissions_service.check_project_access(episode["project_id"])
        permissions_service.check_entity_access(episode["id"])
        if permissions.has_vendor_permissions():
            raise permissions.PermissionDenied
        relations = self.get_relations()
        return tasks_service.get_edit_tasks_for_episode(
            episode_id, relations=relations
        )


class EpisodeEditsResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/EpisodeEditsResource_get.yml")
    def get(self, episode_id):
        """
        Get episode edits
        """
        episode = shots_service.get_episode(episode_id)
        permissions_service.check_project_access(episode["project_id"])
        permissions_service.check_entity_access(episode["id"])
        relations = self.get_relations()
        return permissions_service.mask_metadata_for_vendor(
            "Edit",
            edits_service.get_edits_for_episode(
                episode_id, relations=relations
            ),
        )


class EditPreviewsResource(MethodView):
    @jwt_required()
    @swag_from("openapi/EditPreviewsResource_get.yml")
    def get(self, edit_id):
        """
        Get edit previews
        """
        edit = edits_service.get_edit(edit_id)
        permissions_service.check_project_access(edit["project_id"])
        permissions_service.check_entity_access(edit["id"])
        return playlists_service.get_entity_previews_by_task_type(edit_id)


class EditsAndTasksResource(MethodView):
    @jwt_required()
    @swag_from("openapi/EditsAndTasksResource_get.yml")
    def get(self):
        """
        Get edits and tasks
        """
        criterions = query.get_query_criterions_from_request(request)
        query.check_criterion_id_format(criterions)
        permissions_service.check_project_access(
            criterions.get("project_id", None)
        )
        permissions_service.scope_criterions_to_vendor(criterions)
        return edits_service.get_edits_and_tasks(criterions)


class ProjectEditsResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/ProjectEditsResource_get.yml")
    def get(self, project_id):
        """
        Get project edits
        """
        projects_service.get_project(project_id)
        permissions_service.check_project_access(project_id)
        return permissions_service.mask_metadata_for_vendor(
            "Edit",
            edits_service.get_edits_for_project(
                project_id, only_assigned=permissions.has_vendor_permissions()
            ),
            project_id,
        )

    @jwt_required()
    @swag_from("openapi/ProjectEditsResource_post.yml")
    def post(self, project_id):
        """
        Create edit
        """
        body = validation.validate_request_body(NewEditSchema)
        projects_service.get_project(project_id)
        permissions_service.check_manager_project_access(project_id)

        edit = edits_service.create_edit(
            project_id,
            body.name,
            data=body.data,
            description=body.description,
            parent_id=str(body.episode_id) if body.episode_id else None,
            created_by=persons_service.get_current_user()["id"],
        )
        return edit, 201


class EditVersionsResource(MethodView):
    """
    Retrieve data versions of given edit.
    """

    @jwt_required()
    @swag_from("openapi/EditVersionsResource_get.yml")
    def get(self, edit_id):
        """
        Get edit versions
        """
        edit = edits_service.get_edit(edit_id)
        permissions_service.check_project_access(edit["project_id"])
        permissions_service.check_entity_access(edit["id"])
        return edits_service.get_edit_versions(edit_id)
