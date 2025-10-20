from flask import request
from flask_restful import Resource
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
    @jwt_required()
    def get(self, edit_id):
        """
        Get edit
        ---
        description: Retrieve detailed information about a specific edit.
        tags:
          - Edits
        parameters:
          - in: path
            name: edit_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the edit
        responses:
          200:
            description: Edit information successfully retrieved
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Edit unique identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    name:
                      type: string
                      description: Edit name
                      example: "Opening Sequence"
                    description:
                      type: string
                      description: Edit description
                      example: "Main opening sequence edit"
                    project_id:
                      type: string
                      format: uuid
                      description: Project identifier
                      example: b35b7fb5-df86-5776-b181-68564193d36
                    episode_id:
                      type: string
                      format: uuid
                      description: Episode identifier
                      example: c46c8gc6-eg97-6887-c292-79675204e47
                    created_at:
                      type: string
                      format: date-time
                      description: Creation timestamp
                      example: "2023-01-01T12:00:00Z"
                    updated_at:
                      type: string
                      format: date-time
                      description: Last update timestamp
                      example: "2023-01-01T12:30:00Z"
        """
        edit = edits_service.get_full_edit(edit_id)
        if edit is None:
            edits_service.clear_edit_cache(edit_id)
            edit = edits_service.get_full_edit(edit_id)
        user_service.check_project_access(edit["project_id"])
        user_service.check_entity_access(edit["id"])
        return edit

    @jwt_required()
    def delete(self, edit_id):
        """
        Delete edit
        ---
        description: Permanently remove an edit from the system. Only edit creators or project managers can delete edits.
        tags:
          - Edits
        parameters:
          - in: path
            name: edit_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the edit to delete
          - in: query
            name: force
            type: boolean
            required: false
            description: Force deletion bypassing validation checks
            example: false
        responses:
          204:
            description: Edit successfully deleted
        """
        force = self.get_force()
        edit = edits_service.get_edit(edit_id)
        if edit["created_by"] == persons_service.get_current_user()["id"]:
            user_service.check_belong_to_project(edit["project_id"])
        else:
            user_service.check_manager_project_access(edit["project_id"])
        edits_service.remove_edit(edit_id, force=force)
        return "", 204


class EditsResource(Resource):
    @jwt_required()
    def get(self):
        """
        Get edits
        ---
        description: Retrieve all edit entries with filtering support. Filters can be specified in the query string.
        tags:
          - Edits
        parameters:
          - in: query
            name: project_id
            required: false
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Filter edits by specific project
          - in: query
            name: name
            required: false
            type: string
            example: "Opening Sequence"
            description: Filter edits by name
          - in: query
            name: force
            required: false
            type: boolean
            default: false
            description: Force parameter for additional filtering
            example: false
        responses:
          200:
            description: List of edits successfully retrieved
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Edit unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Edit name
                        example: "Opening Sequence"
                      description:
                        type: string
                        description: Edit description
                        example: "Main opening sequence edit"
                      project_id:
                        type: string
                        format: uuid
                        description: Project identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      episode_id:
                        type: string
                        format: uuid
                        description: Episode identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2023-01-01T12:00:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:30:00Z"
        """
        criterions = query.get_query_criterions_from_request(request)
        user_service.check_project_access(criterions.get("project_id", None))
        if permissions.has_vendor_permissions():
            criterions["assigned_to"] = persons_service.get_current_user()[
                "id"
            ]
        return edits_service.get_edits(criterions)


class AllEditsResource(Resource):
    @jwt_required()
    def get(self):
        """
        Get all edits
        ---
        description: Retrieve all edit entries with filtering support. Filters can be specified in the query string.
        tags:
          - Edits
        parameters:
          - in: query
            name: project_id
            required: false
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Filter edits by specific project
          - in: query
            name: name
            required: false
            type: string
            example: "Opening Sequence"
            description: Filter edits by name
          - in: query
            name: force
            required: false
            type: boolean
            default: false
            description: Force parameter for additional filtering
            example: false
        responses:
          200:
            description: List of all edits successfully retrieved
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Edit unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Edit name
                        example: "Opening Sequence"
                      description:
                        type: string
                        description: Edit description
                        example: "Main opening sequence edit"
                      project_id:
                        type: string
                        format: uuid
                        description: Project identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      episode_id:
                        type: string
                        format: uuid
                        description: Episode identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2023-01-01T12:00:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:30:00Z"
        """
        criterions = query.get_query_criterions_from_request(request)
        if permissions.has_vendor_permissions():
            criterions["assigned_to"] = persons_service.get_current_user()[
                "id"
            ]
        user_service.check_project_access(criterions.get("project_id", None))
        return edits_service.get_edits(criterions)


class EditTaskTypesResource(Resource):
    @jwt_required()
    def get(self, edit_id):
        """
        Get edit task types
        ---
        description: Retrieve all task types that are related to a specific edit.
        tags:
          - Edits
        parameters:
          - in: path
            name: edit_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the edit
        responses:
          200:
            description: List of edit task types successfully retrieved
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Task type unique identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      name:
                        type: string
                        description: Task type name
                        example: "Edit"
                      short_name:
                        type: string
                        description: Task type short name
                        example: "EDT"
                      color:
                        type: string
                        description: Task type color code
                        example: "#FF5733"
                      for_entity:
                        type: string
                        description: Entity type this task type is for
                        example: "Edit"
        """
        edit = edits_service.get_edit(edit_id)
        user_service.check_project_access(edit["project_id"])
        user_service.check_entity_access(edit["id"])
        return tasks_service.get_task_types_for_edit(edit_id)


class EditTasksResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, edit_id):
        """
        Get edit tasks
        ---
        description: Retrieve all tasks that are related to a specific edit.
        tags:
          - Edits
        parameters:
          - in: path
            name: edit_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the edit
          - in: query
            name: relations
            type: boolean
            required: false
            description: Include related entity information
            example: true
        responses:
          200:
            description: List of edit tasks successfully retrieved
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Task unique identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      name:
                        type: string
                        description: Task name
                        example: "Edit Task"
                      task_type_id:
                        type: string
                        format: uuid
                        description: Task type identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      task_status_id:
                        type: string
                        format: uuid
                        description: Task status identifier
                        example: d57d9hd7-fh08-7998-d403-80786315f58
                      entity_id:
                        type: string
                        format: uuid
                        description: Entity identifier
                        example: e68e0ie8-gi19-8009-e514-91897426g69
                      assigned_to:
                        type: string
                        format: uuid
                        description: Assigned person identifier
                        example: f79f1jf9-hj20-9010-f625-02998537h80
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2023-01-01T12:00:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:30:00Z"
        """
        edit = edits_service.get_edit(edit_id)
        user_service.check_project_access(edit["project_id"])
        user_service.check_entity_access(edit["id"])
        relations = self.get_relations()
        return tasks_service.get_tasks_for_edit(edit_id, relations=relations)


class EpisodeEditTasksResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, episode_id):
        """
        Get episode edit tasks
        ---
        description: Retrieve all tasks that are related to a specific episode.
        tags:
          - Edits
        parameters:
          - in: path
            name: episode_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the episode
          - in: query
            name: relations
            type: boolean
            required: false
            description: Include related entity information
            example: true
        responses:
          200:
            description: List of episode edit tasks successfully retrieved
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Task unique identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      name:
                        type: string
                        description: Task name
                        example: "Episode Edit Task"
                      task_type_id:
                        type: string
                        format: uuid
                        description: Task type identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      task_status_id:
                        type: string
                        format: uuid
                        description: Task status identifier
                        example: d57d9hd7-fh08-7998-d403-80786315f58
                      entity_id:
                        type: string
                        format: uuid
                        description: Entity identifier
                        example: e68e0ie8-gi19-8009-e514-91897426g69
                      assigned_to:
                        type: string
                        format: uuid
                        description: Assigned person identifier
                        example: f79f1jf9-hj20-9010-f625-02998537h80
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2023-01-01T12:00:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:30:00Z"
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
    @jwt_required()
    def get(self, episode_id):
        """
        Get episode edits
        ---
        description: Retrieve all edits that are related to a specific episode.
        tags:
          - Edits
        parameters:
          - in: path
            name: episode_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the episode
          - in: query
            name: relations
            type: boolean
            required: false
            description: Include related entity information
            example: true
        responses:
          200:
            description: List of episode edits successfully retrieved
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Edit unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Edit name
                        example: "Episode Edit"
                      description:
                        type: string
                        description: Edit description
                        example: "Main episode edit"
                      project_id:
                        type: string
                        format: uuid
                        description: Project identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      episode_id:
                        type: string
                        format: uuid
                        description: Episode identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2023-01-01T12:00:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:30:00Z"
        """
        episode = edits_service.get_episode(episode_id)
        user_service.check_project_access(episode["project_id"])
        user_service.check_entity_access(episode["id"])
        relations = self.get_relations()
        return edits_service.get_edits_for_episode(
            episode_id, relations=relations
        )


class EditPreviewsResource(Resource):
    @jwt_required()
    def get(self, edit_id):
        """
        Get edit previews
        ---
        description: Retrieve all preview files related to a specific edit.
          Returns them as a dictionary where keys are related task type IDs and
          values are arrays of previews for that task type.
        tags:
          - Edits
        parameters:
          - in: path
            name: edit_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the edit
        responses:
          200:
            description: Edit previews successfully retrieved
            content:
              application/json:
                schema:
                  type: object
                  additionalProperties:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          description: Preview unique identifier
                          example: b35b7fb5-df86-5776-b181-68564193d36
                        name:
                          type: string
                          description: Preview name
                          example: "edit_preview_01"
                        original_name:
                          type: string
                          description: Original file name
                          example: "edit_sequence.mov"
                        file_path:
                          type: string
                          description: File path
                          example: "/previews/edit/edit_preview_01.mov"
                        task_type_id:
                          type: string
                          format: uuid
                          description: Task type identifier
                          example: c46c8gc6-eg97-6887-c292-79675204e47
                        created_at:
                          type: string
                          format: date-time
                          description: Creation timestamp
                          example: "2023-01-01T12:00:00Z"
        """
        edit = edits_service.get_edit(edit_id)
        user_service.check_project_access(edit["project_id"])
        user_service.check_entity_access(edit["id"])
        return playlists_service.get_preview_files_for_entity(edit_id)


class EditsAndTasksResource(Resource):
    @jwt_required()
    def get(self):
        """
        Get edits and tasks
        ---
        description: Retrieve all edits with project name and all related tasks.
        tags:
          - Edits
        parameters:
          - in: query
            name: project_id
            required: false
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Filter edits by specific project
          - in: query
            name: name
            required: false
            type: string
            example: "Opening Sequence"
            description: Filter edits by name
          - in: query
            name: force
            required: false
            type: boolean
            default: false
            description: Force parameter for additional filtering
            example: false
        responses:
          200:
            description: Edits with tasks successfully retrieved
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Edit unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Edit name
                        example: "Opening Sequence"
                      description:
                        type: string
                        description: Edit description
                        example: "Main opening sequence edit"
                      project_id:
                        type: string
                        format: uuid
                        description: Project identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      project_name:
                        type: string
                        description: Project name
                        example: "My Animation Project"
                      episode_id:
                        type: string
                        format: uuid
                        description: Episode identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      tasks:
                        type: array
                        items:
                          type: object
                          properties:
                            id:
                              type: string
                              format: uuid
                              description: Task unique identifier
                              example: d57d9hd7-fh08-7998-d403-80786315f58
                            name:
                              type: string
                              description: Task name
                              example: "Edit Task"
                            task_type_id:
                              type: string
                              format: uuid
                              description: Task type identifier
                              example: e68e0ie8-gi19-8009-e514-91897426g69
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2023-01-01T12:00:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:30:00Z"
        """
        criterions = query.get_query_criterions_from_request(request)
        user_service.check_project_access(criterions.get("project_id", None))
        if permissions.has_vendor_permissions():
            criterions["assigned_to"] = persons_service.get_current_user()[
                "id"
            ]
            criterions["vendor_departments"] = [
                str(department.id)
                for department in persons_service.get_current_user_raw().departments
            ]
        return edits_service.get_edits_and_tasks(criterions)


class ProjectEditsResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, project_id):
        """
        Get project edits
        ---
        description: Retrieve all edits that are related to a specific project.
        tags:
          - Edits
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the project
        responses:
          200:
            description: List of project edits successfully retrieved
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Edit unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Edit name
                        example: "Opening Sequence"
                      description:
                        type: string
                        description: Edit description
                        example: "Main opening sequence edit"
                      project_id:
                        type: string
                        format: uuid
                        description: Project identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      episode_id:
                        type: string
                        format: uuid
                        description: Episode identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2023-01-01T12:00:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:30:00Z"
        """
        projects_service.get_project(project_id)
        user_service.check_project_access(project_id)
        return edits_service.get_edits_for_project(
            project_id, only_assigned=permissions.has_vendor_permissions()
        )

    @jwt_required()
    def post(self, project_id):
        """
        Create edit
        ---
        description: Create a new edit for a specific project with name, description, and optional episode association.
        tags:
          - Edits
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the project
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - name
                properties:
                  name:
                    type: string
                    description: Edit name
                    example: "Opening Sequence"
                  description:
                    type: string
                    description: Edit description
                    example: "Main opening sequence edit"
                  data:
                    type: object
                    description: Additional edit data
                    example: {"duration": 120, "fps": 24}
                  episode_id:
                    type: string
                    format: uuid
                    description: Episode identifier (optional)
                    example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
          201:
            description: Edit successfully created
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Edit unique identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    name:
                      type: string
                      description: Edit name
                      example: "Opening Sequence"
                    description:
                      type: string
                      description: Edit description
                      example: "Main opening sequence edit"
                    project_id:
                      type: string
                      format: uuid
                      description: Project identifier
                      example: b35b7fb5-df86-5776-b181-68564193d36
                    episode_id:
                      type: string
                      format: uuid
                      description: Episode identifier
                      example: c46c8gc6-eg97-6887-c292-79675204e47
                    data:
                      type: object
                      description: Additional edit data
                      example: {"duration": 120, "fps": 24}
                    created_by:
                      type: string
                      format: uuid
                      description: Creator person identifier
                      example: d57d9hd7-fh08-7998-d403-80786315f58
                    created_at:
                      type: string
                      format: date-time
                      description: Creation timestamp
                      example: "2023-01-01T12:00:00Z"
                    updated_at:
                      type: string
                      format: date-time
                      description: Last update timestamp
                      example: "2023-01-01T12:00:00Z"
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
            created_by=persons_service.get_current_user()["id"],
        )
        return edit, 201

    def get_arguments(self):
        args = self.get_args(
            [
                {
                    "name": "name",
                    "help": "The edit name is required.",
                    "required": True,
                },
                "description",
                {"name": "data", "type": dict},
                "episode_id",
            ]
        )

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

    @jwt_required()
    def get(self, edit_id):
        """
        Get edit versions
        ---
        description: Retrieve all data versions of a specific edit. This
          includes historical versions and metadata about changes over time.
        tags:
          - Edits
        parameters:
          - in: path
            name: edit_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the edit
        responses:
          200:
            description: Edit versions successfully retrieved
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Version unique identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      edit_id:
                        type: string
                        format: uuid
                        description: Edit identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      version_number:
                        type: integer
                        description: Version number
                        example: 1
                      data:
                        type: object
                        description: Version data content
                        example: {"duration": 120, "fps": 24, "changes": "Added transitions"}
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2023-01-01T12:00:00Z"
                      created_by:
                        type: string
                        format: uuid
                        description: Creator person identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
        """
        edit = edits_service.get_edit(edit_id)
        user_service.check_project_access(edit["project_id"])
        user_service.check_entity_access(edit["id"])
        return edits_service.get_edit_versions(edit_id)
