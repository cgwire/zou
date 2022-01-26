from flask import request
from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required

from zou.app.services import (
    persons_service,
    projects_service,
    playlists_service,
    edits_service,
    tasks_service,
    user_service,
)

from zou.app.mixin import ArgsMixin
from zou.app.utils import permissions, query


class EditResource(Resource, ArgsMixin):
    @jwt_required
    def get(self, edit_id):
        """
        Retrieve given edit.
        """
        edit = edits_service.get_full_edit(edit_id)
        if edit is None:
            edits_service.clear_edit_cache(edit_id)
            edit = edits_service.get_full_edit(edit_id)
        user_service.check_project_access(edit["project_id"])
        user_service.check_entity_access(edit["id"])
        return edit

    @jwt_required
    def delete(self, edit_id):
        """
        Delete given edit.
        """
        force = self.get_force()
        edit = edits_service.get_edit(edit_id)
        user_service.check_manager_project_access(edit["project_id"])
        edits_service.remove_edit(edit_id, force=force)
        return "", 204


class EditsResource(Resource):
    @jwt_required
    def get(self):
        """
        Retrieve all edit entries. Filters can be specified in the query string.
        """
        criterions = query.get_query_criterions_from_request(request)
        user_service.check_project_access(criterions.get("project_id", None))
        if permissions.has_vendor_permissions():
            criterions["assigned_to"] = persons_service.get_current_user()[
                "id"
            ]
        return edits_service.get_edits(criterions)


class AllEditsResource(Resource):
    @jwt_required
    def get(self):
        """
        Retrieve all edit entries. Filters can be specified in the query string.
        """
        criterions = query.get_query_criterions_from_request(request)
        if permissions.has_vendor_permissions():
            criterions["assigned_to"] = persons_service.get_current_user()[
                "id"
            ]
        user_service.check_project_access(criterions.get("project_id", None))
        return edits_service.get_edits(criterions)


class EditTaskTypesResource(Resource):
    @jwt_required
    def get(self, edit_id):
        """
        Retrieve all task types related to a given edit.
        """
        edit = edits_service.get_edit(edit_id)
        user_service.check_project_access(edit["project_id"])
        user_service.check_entity_access(edit["id"])
        return tasks_service.get_task_types_for_edit(edit_id)


class EditTasksResource(Resource, ArgsMixin):
    @jwt_required
    def get(self, edit_id):
        """
        Retrieve all tasks related to a given edit.
        """
        edit = edits_service.get_edit(edit_id)
        user_service.check_project_access(edit["project_id"])
        user_service.check_entity_access(edit["id"])
        relations = self.get_relations()
        return tasks_service.get_tasks_for_edit(edit_id, relations=relations)


class EpisodeEditTasksResource(Resource, ArgsMixin):
    @jwt_required
    def get(self, episode_id):
        """
        Retrieve all tasks related to a given episode.
        """
        episode = edits_service.get_episode(episode_id)
        user_service.check_project_access(episode["project_id"])
        user_service.check_entity_access(episode["id"])
        if permissions.has_vendor_permissions():
            raise permissions.PermissionDenied
        relations = self.get_relations()
        return tasks_service.get_edit_tasks_for_episode(
            episode_id, relations=relations
        )


class EpisodeEditsResource(Resource, ArgsMixin):
    @jwt_required
    def get(self, episode_id):
        """
        Retrieve all edits related to a given episode.
        """
        episode = edits_service.get_episode(episode_id)
        user_service.check_project_access(episode["project_id"])
        user_service.check_entity_access(episode["id"])
        relations = self.get_relations()
        return edits_service.get_edits_for_episode(
            episode_id, relations=relations
        )


class EditPreviewsResource(Resource):
    @jwt_required
    def get(self, edit_id):
        """
        Retrieve all previews related to a given edit. It sends them
        as a dict. Keys are related task type ids and values are arrays
        of preview for this task type.
        """
        edit = edits_service.get_edit(edit_id)
        user_service.check_project_access(edit["project_id"])
        user_service.check_entity_access(edit["id"])
        return playlists_service.get_preview_files_for_entity(edit_id)


class EditsAndTasksResource(Resource):
    @jwt_required
    def get(self):
        """
        Retrieve all edits, adds project name and all related tasks.
        """
        criterions = query.get_query_criterions_from_request(request)
        user_service.check_project_access(criterions.get("project_id", None))
        if permissions.has_vendor_permissions():
            criterions["assigned_to"] = persons_service.get_current_user()[
                "id"
            ]
        return edits_service.get_edits_and_tasks(criterions)


class ProjectEditsResource(Resource):
    @jwt_required
    def get(self, project_id):
        """
        Retrieve all edits related to a given project.
        """
        projects_service.get_project(project_id)
        user_service.check_project_access(project_id)
        return edits_service.get_edits_for_project(
            project_id, only_assigned=permissions.has_vendor_permissions()
        )

    @jwt_required
    def post(self, project_id):
        """
        Create a edit for given project.
        """
        (name, description, data, parent_id) = self.get_arguments()
        projects_service.get_project(project_id)
        user_service.check_manager_project_access(project_id)

        edit = edits_service.create_edit(
            project_id,
            name,
            data=data,
            description=description,
            parent_id=parent_id,
        )
        return edit, 201

    def get_arguments(self):
        parser = reqparse.RequestParser()
        parser.add_argument(
            "name", help="The edit name is required.", required=True
        )
        parser.add_argument("description")
        parser.add_argument("data", type=dict)
        parser.add_argument("episode_id", default=None)
        args = parser.parse_args()
        return (
            args["name"],
            args.get("description", ""),
            args["data"],
            args["episode_id"],
        )


class EditVersionsResource(Resource):
    """
    Retrieve data versions of given edit.
    """

    @jwt_required
    def get(self, edit_id):
        edit = edits_service.get_edit(edit_id)
        user_service.check_project_access(edit["project_id"])
        user_service.check_entity_access(edit["id"])
        return edits_service.get_edit_versions(edit_id)
