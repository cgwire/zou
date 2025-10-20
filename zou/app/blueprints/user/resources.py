from flask import abort, request
from flask_restful import Resource, inputs

from zou.app.mixin import ArgsMixin
from zou.app.services import (
    assets_service,
    chats_service,
    entities_service,
    persons_service,
    projects_service,
    shots_service,
    time_spents_service,
    user_service,
)
from zou.app.utils import date_helpers
from zou.app.services.exception import WrongDateFormatException


class AssetTasksResource(Resource):

    def get(self, asset_id):
        """
        Get asset tasks
        ---
        description: Return tasks related to given asset for current user.
        tags:
        - User
        parameters:
          - in: path
            name: asset_id
            required: true
            schema:
              type: string
              format: uuid
            description: Asset unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Tasks related to given asset for current user
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
                          example: "Modeling"
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
                        assigner_id:
                          type: string
                          format: uuid
                          description: Person who assigned the task
                          example: e68e0ie8-gi19-8009-e514-91897426g69
                        assignees:
                          type: array
                          items:
                            type: string
                            format: uuid
                          description: List of assigned person identifiers
                          example: ["f79f1jf9-hj20-9010-f625-a09008537h80"]
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
        assets_service.get_asset(asset_id)
        return user_service.get_tasks_for_entity(asset_id)


class AssetTaskTypesResource(Resource):

    def get(self, asset_id):
        """
        Get asset task types
        ---
        description: Retrieve task types related to a specific asset for the
          current user. Returns all task types available for the given asset.
        tags:
        - User
        parameters:
          - in: path
            name: asset_id
            required: true
            schema:
              type: string
              format: uuid
            description: Asset unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Task types related to given asset for current user
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
                          example: "Modeling"
                        short_name:
                          type: string
                          description: Task type short name
                          example: "MOD"
                        color:
                          type: string
                          description: Task type color
                          example: "#FF0000"
                        priority:
                          type: integer
                          description: Task type priority
                          example: 1
                        for_entity:
                          type: string
                          description: Entity type this task type applies to
                          example: "Asset"
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
        assets_service.get_asset(asset_id)
        return user_service.get_task_types_for_entity(asset_id)


class ShotTaskTypesResource(Resource):

    def get(self, shot_id):
        """
        Get shot task types
        ---
        description: Retrieve task types related to a specific shot for the
          current user. Returns all task types available for the given shot.
        tags:
        - User
        parameters:
          - in: path
            name: shot_id
            required: true
            schema:
              type: string
              format: uuid
            description: Shot unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Task types related to given shot for current user
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
                          example: "Animation"
                        short_name:
                          type: string
                          description: Task type short name
                          example: "ANIM"
                        color:
                          type: string
                          description: Task type color
                          example: "#00FF00"
                        priority:
                          type: integer
                          description: Task type priority
                          example: 2
                        for_entity:
                          type: string
                          description: Entity type this task type applies to
                          example: "Shot"
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
        shots_service.get_shot(shot_id)
        return user_service.get_task_types_for_entity(shot_id)


class SceneTaskTypesResource(Resource):
    """
    Return tasks related to given scene for current user.
    """

    def get(self, scene_id):
        """
        Get scene task types
        ---
        description: Retrieve task types related to a specific scene for the
          current user.
        tags:
        - User
        parameters:
          - in: path
            name: scene_id
            required: true
            schema:
              type: string
              format: uuid
            description: Scene unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Task types related to given scene for current user
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
                          example: "Layout"
                        short_name:
                          type: string
                          description: Task type short name
                          example: "LAY"
                        color:
                          type: string
                          description: Task type color
                          example: "#0000FF"
                        priority:
                          type: integer
                          description: Task type priority
                          example: 3
                        for_entity:
                          type: string
                          description: Entity type this task type applies to
                          example: "Scene"
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
        shots_service.get_scene(scene_id)
        return user_service.get_task_types_for_entity(scene_id)


class SequenceTaskTypesResource(Resource):

    def get(self, sequence_id):
        """
        Get sequence task types
        ---
        description: Retrieve task types related to a specific sequence for the
          current user.
        tags:
        - User
        parameters:
          - in: path
            name: sequence_id
            required: true
            schema:
              type: string
              format: uuid
            description: Sequence unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Task types related to given sequence for current user
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
                          example: "Compositing"
                        short_name:
                          type: string
                          description: Task type short name
                          example: "COMP"
                        color:
                          type: string
                          description: Task type color
                          example: "#FFFF00"
                        priority:
                          type: integer
                          description: Task type priority
                          example: 4
                        for_entity:
                          type: string
                          description: Entity type this task type applies to
                          example: "Sequence"
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
        shots_service.get_sequence(sequence_id)
        return user_service.get_task_types_for_entity(sequence_id)


class AssetTypeAssetsResource(Resource):

    def get(self, project_id, asset_type_id):
        """
        Get project assets
        ---
        description: Retrieve assets of a specific type within a project
          matching the asset type in the given project if the user has access.
        tags:
        - User
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: asset_type_id
            required: true
            schema:
              type: string
              format: uuid
            description: Asset type unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
            200:
              description: Assets of given type in the specified project
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
                          description: Asset unique identifier
                          example: c46c8gc6-eg97-6887-c292-79675204e47
                        name:
                          type: string
                          description: Asset name
                          example: "Main Character"
                        description:
                          type: string
                          description: Asset description
                          example: "Main character model for the project"
                        asset_type_id:
                          type: string
                          format: uuid
                          description: Asset type identifier
                          example: d57d9hd7-fh08-7998-d403-80786315f58
                        project_id:
                          type: string
                          format: uuid
                          description: Project identifier
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
        projects_service.get_project(project_id)
        assets_service.get_asset_type(asset_type_id)
        return user_service.get_assets_for_asset_type(
            project_id, asset_type_id
        )


class OpenProjectsResource(Resource, ArgsMixin):

    def get(self):
        """
        Get open projects
        ---
        description: Retrieve open projects for which the current user has at
          least one task assigned. Optionally filter by project name.
        tags:
        - User
        parameters:
          - in: query
            name: name
            required: false
            schema:
              type: string
            description: Filter projects by name
            example: "My Project"
        responses:
            200:
              description: Open projects with assigned tasks for current user
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
                          description: Project unique identifier
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          description: Project name
                          example: "My Project"
                        description:
                          type: string
                          description: Project description
                          example: "A sample project"
                        status:
                          type: string
                          description: Project status
                          example: "Active"
                        fps:
                          type: number
                          description: Frames per second
                          example: 24.0
                        ratio:
                          type: string
                          description: Aspect ratio
                          example: "16:9"
                        resolution:
                          type: string
                          description: Project resolution
                          example: "1920x1080"
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
        name = self.get_text_parameter("name")
        return user_service.get_open_projects(name=name)


class ProjectSequencesResource(Resource):

    def get(self, project_id):
        """
        Get project sequences
        ---
        description: Retrieve sequences related to a specific project for the
          current user. Returns all sequences in the project if the user has
          access.
        tags:
        - User
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Sequences related to given project
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
                          description: Sequence unique identifier
                          example: b35b7fb5-df86-5776-b181-68564193d36
                        name:
                          type: string
                          description: Sequence name
                          example: "SEQ001"
                        description:
                          type: string
                          description: Sequence description
                          example: "Main sequence"
                        project_id:
                          type: string
                          format: uuid
                          description: Project identifier
                          example: c46c8gc6-eg97-6887-c292-79675204e47
                        fps:
                          type: number
                          description: Frames per second
                          example: 24.0
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
        return user_service.get_sequences_for_project(project_id)


class ProjectEpisodesResource(Resource):

    def get(self, project_id):
        """
        Get project episodes
        ---
        description: Retrieve episodes related to a specific project for the
          current user. Returns all episodes in the project if the user has
          access.
        tags:
        - User
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Episodes related to given project
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
                          description: Episode unique identifier
                          example: b35b7fb5-df86-5776-b181-68564193d36
                        name:
                          type: string
                          description: Episode name
                          example: "Episode 01"
                        description:
                          type: string
                          description: Episode description
                          example: "First episode"
                        project_id:
                          type: string
                          format: uuid
                          description: Project identifier
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
        return user_service.get_project_episodes(project_id)


class ProjectAssetTypesResource(Resource):

    def get(self, project_id):
        """
        Get project asset types
        ---
        description: Retrieve asset types related to a specific project for the
          current user.
        tags:
        - User
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Asset types related to given project
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
                          description: Asset type unique identifier
                          example: b35b7fb5-df86-5776-b181-68564193d36
                        name:
                          type: string
                          description: Asset type name
                          example: "Character"
                        short_name:
                          type: string
                          description: Asset type short name
                          example: "CHAR"
                        color:
                          type: string
                          description: Asset type color
                          example: "#FF0000"
                        project_id:
                          type: string
                          format: uuid
                          description: Project identifier
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
        return user_service.get_asset_types_for_project(project_id)


class SequenceShotsResource(Resource):

    def get(self, sequence_id):
        """
        Get sequence shots
        ---
        description: Retrieve shots related to a specific sequence for the
          current user.
        tags:
        - User
        parameters:
          - in: path
            name: sequence_id
            required: true
            schema:
              type: string
              format: uuid
            description: Sequence unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Shots related to given sequence
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
                          description: Shot unique identifier
                          example: b35b7fb5-df86-5776-b181-68564193d36
                        name:
                          type: string
                          description: Shot name
                          example: "SH001"
                        description:
                          type: string
                          description: Shot description
                          example: "Main shot"
                        sequence_id:
                          type: string
                          format: uuid
                          description: Sequence identifier
                          example: c46c8gc6-eg97-6887-c292-79675204e47
                        project_id:
                          type: string
                          format: uuid
                          description: Project identifier
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
                          example: "2023-01-01T12:30:00Z"
        """
        shots_service.get_sequence(sequence_id)
        return user_service.get_shots_for_sequence(sequence_id)


class SequenceScenesResource(Resource):

    def get(self, sequence_id):
        """
        Get sequence scenes
        ---
        description: Retrieve scenes related to a specific sequence for the
          current user.
        tags:
        - User
        parameters:
          - in: path
            name: sequence_id
            required: true
            schema:
              type: string
              format: uuid
            description: Sequence unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Scenes related to given sequence
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
                          description: Scene unique identifier
                          example: b35b7fb5-df86-5776-b181-68564193d36
                        name:
                          type: string
                          description: Scene name
                          example: "SC001"
                        description:
                          type: string
                          description: Scene description
                          example: "Main scene"
                        sequence_id:
                          type: string
                          format: uuid
                          description: Sequence identifier
                          example: c46c8gc6-eg97-6887-c292-79675204e47
                        project_id:
                          type: string
                          format: uuid
                          description: Project identifier
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
                          example: "2023-01-01T12:30:00Z"
        """
        shots_service.get_sequence(sequence_id)
        return user_service.get_scenes_for_sequence(sequence_id)


class ShotTasksResource(Resource):

    def get(self, shot_id):
        """
        Get shot tasks
        ---
        description: Retrieve tasks related to a specific shot for the current
          user. Returns all tasks assigned to the user for the given shot.
        tags:
        - User
        parameters:
          - in: path
            name: shot_id
            required: true
            schema:
              type: string
              format: uuid
            description: Shot unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Tasks related to given shot
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
                          example: "Animation"
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
                        assigner_id:
                          type: string
                          format: uuid
                          description: Person who assigned the task
                          example: e68e0ie8-gi19-8009-e514-91897426g69
                        assignees:
                          type: array
                          items:
                            type: string
                            format: uuid
                          description: List of assigned person identifiers
                          example: ["f79f1jf9-hj20-9010-f625-a09008537h80"]
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
        shots_service.get_shot(shot_id)
        return user_service.get_tasks_for_entity(shot_id)


class SceneTasksResource(Resource):

    def get(self, scene_id):
        """
        Get scene tasks
        ---
        description: Retrieve tasks related to a specific scene for the current
          user.
        tags:
        - User
        parameters:
          - in: path
            name: scene_id
            required: true
            schema:
              type: string
              format: uuid
            description: Scene unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Tasks related to given scene
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
                          example: "Layout"
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
                        assigner_id:
                          type: string
                          format: uuid
                          description: Person who assigned the task
                          example: e68e0ie8-gi19-8009-e514-91897426g69
                        assignees:
                          type: array
                          items:
                            type: string
                            format: uuid
                          description: List of assigned person identifiers
                          example: ["f79f1jf9-hj20-9010-f625-a09008537h80"]
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
        shots_service.get_scene(scene_id)
        return user_service.get_tasks_for_entity(scene_id)


class SequenceTasksResource(Resource):

    def get(self, sequence_id):
        """
        Get sequence tasks
        ---
        description: Retrieve tasks related to a specific sequence for the
          current user.
          sequence.
        tags:
        - User
        parameters:
          - in: path
            name: sequence_id
            required: true
            schema:
              type: string
              format: uuid
            description: Sequence unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Tasks related to given sequence
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
                          example: "Compositing"
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
                        assigner_id:
                          type: string
                          format: uuid
                          description: Person who assigned the task
                          example: e68e0ie8-gi19-8009-e514-91897426g69
                        assignees:
                          type: array
                          items:
                            type: string
                            format: uuid
                          description: List of assigned person identifiers
                          example: ["f79f1jf9-hj20-9010-f625-a09008537h80"]
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
        shots_service.get_sequence(sequence_id)
        return user_service.get_tasks_for_entity(sequence_id)


class TodosResource(Resource):

    def get(self):
        """
        Get my tasks
        ---
        description: Retrieve ttasks currently assigned to current user and of which status
          has is_done attribute set to false.
        tags:
        - User
        responses:
            200:
              description: Unfinished tasks currently assigned to current user
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
                          example: "Modeling"
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
                        assigner_id:
                          type: string
                          format: uuid
                          description: Person who assigned the task
                          example: e68e0ie8-gi19-8009-e514-91897426g69
                        assignees:
                          type: array
                          items:
                            type: string
                            format: uuid
                          description: List of assigned person identifiers
                          example: ["f79f1jf9-hj20-9010-f625-a09008537h80"]
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
        return user_service.get_todos()


class ToChecksResource(Resource):

    def get(self):
        """
        Get tasks requiring feedback
        ---
        description: Retrieve tasks requiring feedback for departments where the
          current user is a supervisor. Returns empty list if user is not a
          supervisor.
        tags:
        - User
        responses:
            200:
              description: Tasks requiring feedback in current user departments
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
                          example: "Review"
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
                        assigner_id:
                          type: string
                          format: uuid
                          description: Person who assigned the task
                          example: e68e0ie8-gi19-8009-e514-91897426g69
                        assignees:
                          type: array
                          items:
                            type: string
                            format: uuid
                          description: List of assigned person identifiers
                          example: ["f79f1jf9-hj20-9010-f625-a09008537h80"]
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
        return user_service.get_tasks_to_check()


class DoneResource(Resource):

    def get(self):
        """
        Get done tasks
        ---
        description: Retrieve tasks currently assigned to the current user with
          status marked as done. Returns only tasks from open projects.
        tags:
        - User
        responses:
            200:
              description: Finished tasks currently assigned to current user
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
                          example: "Completed Task"
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
                        assigner_id:
                          type: string
                          format: uuid
                          description: Person who assigned the task
                          example: e68e0ie8-gi19-8009-e514-91897426g69
                        assignees:
                          type: array
                          items:
                            type: string
                            format: uuid
                          description: List of assigned person identifiers
                          example: ["f79f1jf9-hj20-9010-f625-a09008537h80"]
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
        return user_service.get_done_tasks()


class FiltersResource(Resource, ArgsMixin):

    def get(self):
        """
        Get filters
        ---
        description: Retrieve filters for the current user limited to open
          projects only.
        tags:
        - User
        responses:
            200:
              description: Filters for current user and only for open projects
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
                          description: Filter unique identifier
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          description: Filter name
                          example: "My Filter"
                        query:
                          type: string
                          description: Filter query JSON
                          example: '{"project_id": "uuid"}'
                        list_type:
                          type: string
                          description: List type
                          example: "todo"
                        entity_type:
                          type: string
                          description: Entity type
                          example: "Asset"
                        project_id:
                          type: string
                          format: uuid
                          description: Project identifier
                          example: b35b7fb5-df86-5776-b181-68564193d36
                        is_shared:
                          type: boolean
                          description: Whether filter is shared
                          example: false
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
        return user_service.get_filters()

    def post(self):
        """
        Create filter
        ---
        description: Create a new filter for the current user limited to open
          projects only.
        tags:
        - User
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - name
                  - query
                  - list_type
                  - project_id
                properties:
                  name:
                    type: string
                    description: Filter name
                    example: "My Custom Filter"
                  query:
                    type: string
                    description: Filter query as JSON string
                    example: '{"project_id": "uuid"}'
                  list_type:
                    type: string
                    description: Type of list this filter applies to
                    example: "todo"
                  entity_type:
                    type: string
                    description: Entity type this filter applies to
                    example: "Asset"
                  project_id:
                    type: string
                    format: uuid
                    description: Project identifier
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  is_shared:
                    type: boolean
                    description: Whether to share this filter with others
                    default: false
                    example: false
                  search_filter_group_id:
                    type: string
                    format: uuid
                    description: Filter group identifier
                    example: b35b7fb5-df86-5776-b181-68564193d36
                  department_id:
                    type: string
                    format: uuid
                    description: Department identifier
                    example: c46c8gc6-eg97-6887-c292-79675204e47
        responses:
            201:
              description: Filter created successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Filter unique identifier
                        example: d57d9hd7-fh08-7998-d403-80786315f58
                      name:
                        type: string
                        description: Filter name
                        example: "My Custom Filter"
                      query:
                        type: string
                        description: Filter query JSON
                        example: '{"project_id": "uuid"}'
                      list_type:
                        type: string
                        description: List type
                        example: "todo"
                      entity_type:
                        type: string
                        description: Entity type
                        example: "Asset"
                      project_id:
                        type: string
                        format: uuid
                        description: Project identifier
                        example: e68e0ie8-gi19-8009-e514-91897426g69
                      is_shared:
                        type: boolean
                        description: Whether filter is shared
                        example: false
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
            400:
              description: Bad request
        """
        arguments = self.get_arguments()

        return (
            user_service.create_filter(
                arguments["list_type"],
                arguments["name"],
                arguments["query"],
                arguments["project_id"],
                arguments["entity_type"],
                arguments["is_shared"],
                arguments["search_filter_group_id"],
                department_id=arguments["department_id"],
            ),
            201,
        )

    def get_arguments(self):
        return self.get_args(
            [
                ("name", "", True),
                ("query", "", True),
                ("list_type", "todo", True),
                ("project_id", None, False),
                ("entity_type", None, False),
                ("is_shared", False, False, inputs.boolean),
                ("search_filter_group_id", None, False),
                ("department_id", None, False),
            ]
        )


class FilterResource(Resource, ArgsMixin):

    def put(self, filter_id):
        """
        Update filter
        ---
        description: Update an existing filter if it is owned by the current
          user.
        tags:
        - User
        parameters:
          - in: path
            name: filter_id
            required: true
            schema:
              type: string
              format: uuid
            description: Filter unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  name:
                    type: string
                    description: Filter name
                    example: "Updated Filter Name"
                  search_query:
                    type: string
                    description: Updated filter query
                    example: '{"status": "active"}'
                  search_filter_group_id:
                    type: string
                    format: uuid
                    description: Filter group identifier
                    example: b35b7fb5-df86-5776-b181-68564193d36
                  is_shared:
                    type: boolean
                    description: Whether to share this filter
                    example: true
                  project_id:
                    type: string
                    format: uuid
                    description: Project identifier
                    example: c46c8gc6-eg97-6887-c292-79675204e47
                  department_id:
                    type: string
                    format: uuid
                    description: Department identifier
                    example: d57d9hd7-fh08-7998-d403-80786315f58
        responses:
            200:
              description: Filter updated successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Filter unique identifier
                        example: e68e0ie8-gi19-8009-e514-91897426g69
                      name:
                        type: string
                        description: Filter name
                        example: "Updated Filter Name"
                      query:
                        type: string
                        description: Filter query JSON
                        example: '{"status": "active"}'
                      list_type:
                        type: string
                        description: List type
                        example: "todo"
                      entity_type:
                        type: string
                        description: Entity type
                        example: "Asset"
                      project_id:
                        type: string
                        format: uuid
                        description: Project identifier
                        example: f79f1jf9-hj20-9010-f625-a09008537h80
                      is_shared:
                        type: boolean
                        description: Whether filter is shared
                        example: true
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
        data = self.get_args(
            [
                ("name", None, False),
                ("search_query", None, False),
                ("search_filter_group_id", None, False),
                ("is_shared", None, False, inputs.boolean),
                ("project_id", None, None),
                ("department_id", None, None),
            ]
        )
        data = self.clear_empty_fields(
            data, ignored_fields=["search_filter_group_id"]
        )
        user_filter = user_service.update_filter(filter_id, data)
        return user_filter, 200

    def delete(self, filter_id):
        """
        Delete filter
        ---
        description: Delete a specific filter if it is owned by the current
          user.
        tags:
        - User
        parameters:
          - in: path
            name: filter_id
            required: true
            schema:
              type: string
              format: uuid
            description: Filter unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
              description: Filter deleted successfully
        """
        user_service.remove_filter(filter_id)
        return "", 204


class FilterGroupsResource(Resource, ArgsMixin):

    def get(self):
        """
        Get filter groups
        ---
        description: Retrieve filter groups for the current user limited to open
          projects only.
        tags:
        - User
        responses:
            200:
              description: Filter groups for current user and only for open projects
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
                          description: Filter group unique identifier
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          description: Filter group name
                          example: "My Filter Group"
                        color:
                          type: string
                          description: Filter group color
                          example: "#FF0000"
                        list_type:
                          type: string
                          description: List type
                          example: "todo"
                        entity_type:
                          type: string
                          description: Entity type
                          example: "Asset"
                        project_id:
                          type: string
                          format: uuid
                          description: Project identifier
                          example: b35b7fb5-df86-5776-b181-68564193d36
                        is_shared:
                          type: boolean
                          description: Whether filter group is shared
                          example: false
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
        return user_service.get_filter_groups()

    def post(self):
        """
        Create filter group
        ---
        description: Create a new filter group for the current user limited to
          open projects only. The filter group can be shared with other users.
        tags:
        - User
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - name
                  - color
                  - list_type
                  - project_id
                properties:
                  name:
                    type: string
                    description: Filter group name
                    example: "My Filter Group"
                  color:
                    type: string
                    description: Filter group color in hex format
                    example: "#FF0000"
                  list_type:
                    type: string
                    description: Type of list this filter group applies to
                    example: "todo"
                  entity_type:
                    type: string
                    description: Entity type this filter group applies to
                    example: "Asset"
                  is_shared:
                    type: boolean
                    description: Whether to share this filter group with others
                    default: false
                    example: false
                  project_id:
                    type: string
                    format: uuid
                    description: Project identifier
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  department_id:
                    type: string
                    format: uuid
                    description: Department identifier
                    example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
            201:
              description: Filter group created successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Filter group unique identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      name:
                        type: string
                        description: Filter group name
                        example: "My Filter Group"
                      color:
                        type: string
                        description: Filter group color
                        example: "#FF0000"
                      list_type:
                        type: string
                        description: List type
                        example: "todo"
                      entity_type:
                        type: string
                        description: Entity type
                        example: "Asset"
                      project_id:
                        type: string
                        format: uuid
                        description: Project identifier
                        example: d57d9hd7-fh08-7998-d403-80786315f58
                      is_shared:
                        type: boolean
                        description: Whether filter group is shared
                        example: false
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
            400:
              description: Bad request
        """
        arguments = self.get_arguments()
        return (
            user_service.create_filter_group(
                arguments["list_type"],
                arguments["name"],
                arguments["color"],
                arguments["project_id"],
                arguments["entity_type"],
                arguments["is_shared"],
                arguments["department_id"],
            ),
            201,
        )

    def get_arguments(self):
        return self.get_args(
            [
                ("name", "", True),
                ("color", "", True),
                ("list_type", "todo", True),
                ("project_id", None, False),
                ("is_shared", False, False, inputs.boolean),
                ("entity_type", None, False),
                ("department_id", None, False),
            ]
        )


class FilterGroupResource(Resource, ArgsMixin):

    def get(self, search_filter_group_id):
        """
        Get filter group
        ---
        description: Retrieve a specific filter group for the current user.
          Returns detailed information about the filter group.
        tags:
        - User
        parameters:
          - in: path
            name: search_filter_group_id
            required: true
            schema:
              type: string
              format: uuid
            description: Filter group unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Filter group details
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Filter group unique identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      name:
                        type: string
                        description: Filter group name
                        example: "My Filter Group"
                      color:
                        type: string
                        description: Filter group color
                        example: "#FF0000"
                      list_type:
                        type: string
                        description: List type
                        example: "todo"
                      entity_type:
                        type: string
                        description: Entity type
                        example: "Asset"
                      project_id:
                        type: string
                        format: uuid
                        description: Project identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      is_shared:
                        type: boolean
                        description: Whether filter group is shared
                        example: false
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
        return user_service.get_filter_group(search_filter_group_id)

    def put(self, filter_group_id):
        """
        Update filter group
        ---
        description: Update an existing filter group if it is owned by the
          current user. Allows modification of filter group properties.
        tags:
        - User
        parameters:
          - in: path
            name: filter_group_id
            required: true
            schema:
              type: string
              format: uuid
            description: Filter group unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  name:
                    type: string
                    description: Filter group name
                    example: "Updated Filter Group"
                  color:
                    type: string
                    description: Filter group color
                    example: "#00FF00"
                  is_shared:
                    type: boolean
                    description: Whether to share this filter group
                    example: true
                  project_id:
                    type: string
                    format: uuid
                    description: Project identifier
                    example: b35b7fb5-df86-5776-b181-68564193d36
                  department_id:
                    type: string
                    format: uuid
                    description: Department identifier
                    example: c46c8gc6-eg97-6887-c292-79675204e47
        responses:
            200:
              description: Filter group updated successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Filter group unique identifier
                        example: d57d9hd7-fh08-7998-d403-80786315f58
                      name:
                        type: string
                        description: Filter group name
                        example: "Updated Filter Group"
                      color:
                        type: string
                        description: Filter group color
                        example: "#00FF00"
                      list_type:
                        type: string
                        description: List type
                        example: "todo"
                      entity_type:
                        type: string
                        description: Entity type
                        example: "Asset"
                      project_id:
                        type: string
                        format: uuid
                        description: Project identifier
                        example: e68e0ie8-gi19-8009-e514-91897426g69
                      is_shared:
                        type: boolean
                        description: Whether filter group is shared
                        example: true
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
        data = self.get_args(
            [
                ("name", None, False),
                ("color", None, False),
                ("is_shared", None, False, inputs.boolean),
                ("project_id", None, None),
                ("department_id", None, None),
            ]
        )

        data = self.clear_empty_fields(data)
        user_filter = user_service.update_filter_group(filter_group_id, data)
        return user_filter, 200

    def delete(self, filter_group_id):
        """
        Delete filter group
        ---
        description: Delete a specific filter group if it is owned by the
          current user.
        tags:
        - User
        parameters:
          - in: path
            name: filter_group_id
            required: true
            schema:
              type: string
              format: uuid
            description: Filter group unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
              description: Filter group deleted successfully
        """
        user_service.remove_filter_group(filter_group_id)
        return "", 204


class DesktopLoginLogsResource(Resource, ArgsMixin):

    def get(self):
        """
        Get desktop login logs
        ---
        description: Retrieve desktop login logs for the current user.
        tags:
        - User
        responses:
            200:
              description: Desktop login logs for current user
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
                          description: Login log unique identifier
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        person_id:
                          type: string
                          format: uuid
                          description: Person identifier
                          example: b35b7fb5-df86-5776-b181-68564193d36
                        date:
                          type: string
                          format: date
                          description: Login date
                          example: "2023-01-01"
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
        current_user = persons_service.get_current_user()
        return persons_service.get_desktop_login_logs(current_user["id"])

    def post(self):
        """
        Create desktop login log
        ---
        description: Create a desktop login log entry for the current user.
        tags:
        - User
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  date:
                    type: string
                    format: date
                    description: Login date
                    example: "2023-01-01"
        responses:
            201:
              description: Desktop login log created successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Login log unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      person_id:
                        type: string
                        format: uuid
                        description: Person identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      date:
                        type: string
                        format: date
                        description: Login date
                        example: "2023-01-01"
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
            400:
              description: Bad request
        """
        arguments = self.get_args(
            ["date", date_helpers.get_utc_now_datetime()]
        )
        current_user = persons_service.get_current_user()
        desktop_login_log = persons_service.create_desktop_login_logs(
            current_user["id"], arguments["date"]
        )
        return desktop_login_log, 201


class NotificationsResource(Resource, ArgsMixin):

    def get(self):
        """
        Get notifications
        ---
        description: Retrieve the last 100 user notifications filtered by
          given parameters. Supports filtering by date range, task type, status,
          and other criteria.
        tags:
        - User
        parameters:
          - in: query
            name: after
            required: false
            schema:
              type: string
              format: date
            description: Filter notifications after this date
            example: "2023-01-01"
          - in: query
            name: before
            required: false
            schema:
              type: string
              format: date
            description: Filter notifications before this date
            example: "2023-12-31"
          - in: query
            name: task_type_id
            required: false
            schema:
              type: string
              format: uuid
            description: Filter by task type ID
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: task_status_id
            required: false
            schema:
              type: string
              format: uuid
            description: Filter by task status ID
            example: b35b7fb5-df86-5776-b181-68564193d36
          - in: query
            name: type
            required: false
            schema:
              type: string
            description: Filter by notification type
            example: "comment"
          - in: query
            name: read
            required: false
            schema:
              type: boolean
            description: Filter by read status
            example: false
          - in: query
            name: watching
            required: false
            schema:
              type: boolean
            description: Filter by watching status
            example: true
        responses:
            200:
              description: Last 100 user notifications matching filters
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
                          description: Notification unique identifier
                          example: c46c8gc6-eg97-6887-c292-79675204e47
                        type:
                          type: string
                          description: Notification type
                          example: "comment"
                        read:
                          type: boolean
                          description: Whether notification is read
                          example: false
                        author_id:
                          type: string
                          format: uuid
                          description: Author person identifier
                          example: d57d9hd7-fh08-7998-d403-80786315f58
                        comment_id:
                          type: string
                          format: uuid
                          description: Comment identifier
                          example: e68e0ie8-gi19-8009-e514-91897426g69
                        task_id:
                          type: string
                          format: uuid
                          description: Task identifier
                          example: f79f1jf9-hj20-9010-f625-a09008537h80
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
        (
            after,
            before,
            task_type_id,
            task_status_id,
            notification_type,
        ) = self.get_arguments()

        read = None
        if request.args.get("read", None) is not None:
            read = self.get_bool_parameter("read")
        watching = None
        if request.args.get("watching", None) is not None:
            watching = self.get_bool_parameter("watching")
        notifications = user_service.get_last_notifications(
            before=before,
            task_type_id=task_type_id,
            task_status_id=task_status_id,
            notification_type=notification_type,
            read=read,
            watching=watching,
        )
        return notifications

    def get_arguments(self):
        return (
            self.get_text_parameter("after"),
            self.get_text_parameter("before"),
            self.get_text_parameter("task_type_id"),
            self.get_text_parameter("task_status_id"),
            self.get_text_parameter("type"),
        )


class NotificationResource(Resource, ArgsMixin):

    def get(self, notification_id):
        """
        Get notification
        ---
        description: Retrieve a specific notification by ID, only if it
          belongs to the current user.
        tags:
        - User
        parameters:
          - in: path
            name: notification_id
            required: true
            schema:
              type: string
              format: uuid
            description: Notification unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Notification details
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Notification unique identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      type:
                        type: string
                        description: Notification type
                        example: "comment"
                      read:
                        type: boolean
                        description: Whether notification is read
                        example: false
                      author_id:
                        type: string
                        format: uuid
                        description: Author person identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      comment_id:
                        type: string
                        format: uuid
                        description: Comment identifier
                        example: d57d9hd7-fh08-7998-d403-80786315f58
                      task_id:
                        type: string
                        format: uuid
                        description: Task identifier
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
        return user_service.get_notification(notification_id)

    def put(self, notification_id):
        """
        Update notification
        ---
        description: Change the read status of a specific notification. Only
          the notification owner can update their notifications.
        tags:
        - User
        parameters:
          - in: path
            name: notification_id
            required: true
            schema:
              type: string
              format: uuid
            description: Notification unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  read:
                    type: boolean
                    description: Mark notification as read or unread
                    example: true
        responses:
            200:
              description: Notification updated successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Notification unique identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      type:
                        type: string
                        description: Notification type
                        example: "comment"
                      read:
                        type: boolean
                        description: Whether notification is read
                        example: true
                      author_id:
                        type: string
                        format: uuid
                        description: Author person identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      comment_id:
                        type: string
                        format: uuid
                        description: Comment identifier
                        example: d57d9hd7-fh08-7998-d403-80786315f58
                      task_id:
                        type: string
                        format: uuid
                        description: Task identifier
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
        data = self.get_args([("read", None, False, inputs.boolean)])
        return user_service.update_notification(notification_id, data["read"])


class MarkAllNotificationsAsReadResource(Resource):

    def post(self):
        """
        Mark all notifications as read
        ---
        description: Mark all notifications as read for the current user.
        tags:
        - User
        responses:
            200:
              description: Success object
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      success:
                        type: boolean
                        description: Operation success status
                        example: true
        """
        user_service.mark_notifications_as_read()
        return {"success": True}


class HasTaskSubscribedResource(Resource):

    def get(self, task_id):
        """
        Check task subscription
        ---
        description: Check if the current user has subscribed to a specific
          task.
        tags:
        - User
        parameters:
          - in: path
            name: task_id
            required: true
            schema:
              type: string
              format: uuid
            description: Task unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Subscription status for the task
              content:
                application/json:
                  schema:
                    type: boolean
                    example: true
        """
        return user_service.has_task_subscription(task_id)


class TaskSubscribeResource(Resource):

    def post(self, task_id):
        """
        Subscribe to task
        ---
        description: Create a subscription entry for the current user and
          given task. When subscribed, the user receives notifications for all
          comments posted on the task.
        tags:
        - User
        parameters:
          - in: path
            name: task_id
            required: true
            schema:
              type: string
              format: uuid
            description: Task unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
              description: Subscription created successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Subscription unique identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      person_id:
                        type: string
                        format: uuid
                        description: Person identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      task_id:
                        type: string
                        format: uuid
                        description: Task identifier
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
                        example: "2023-01-01T12:30:00Z"
        """
        return user_service.subscribe_to_task(task_id), 201


class TaskUnsubscribeResource(Resource):

    def delete(self, task_id):
        """
        Unsubscribe from task
        ---
        description: Remove the subscription entry for the current user and
          given task. The user will no longer receive notifications for this
          task.
        tags:
        - User
        parameters:
          - in: path
            name: task_id
            required: true
            schema:
              type: string
              format: uuid
            description: Task unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
              description: Subscription removed successfully
        """
        user_service.unsubscribe_from_task(task_id)
        return "", 204


class HasSequenceSubscribedResource(Resource):

    def get(self, sequence_id, task_type_id):
        """
        Check sequence subscription
        ---
        description: Check if the current user has subscribed to a specific
          sequence and task type combination. Returns true if subscribed.
        tags:
        - User
        parameters:
          - in: path
            name: sequence_id
            required: true
            schema:
              type: string
              format: uuid
            description: Sequence unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
            required: true
            schema:
              type: string
              format: uuid
            description: Task type unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
            200:
              description: Subscription status for the sequence and task type
              content:
                application/json:
                  schema:
                    type: boolean
                    example: true
        """
        return user_service.has_sequence_subscription(
            sequence_id, task_type_id
        )


class SequenceSubscribeResource(Resource):

    def post(self, sequence_id, task_type_id):
        """
        Subscribe to sequence
        ---
        description: Create a subscription entry for the current user, given
          sequence, and task type. When subscribed, the user receives
          notifications for all comments posted on tasks related to the
          sequence.
        tags:
        - User
        parameters:
          - in: path
            name: sequence_id
            required: true
            schema:
              type: string
              format: uuid
            description: Sequence unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
            required: true
            schema:
              type: string
              format: uuid
            description: Task type unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
            201:
              description: Subscription created successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Subscription unique identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      person_id:
                        type: string
                        format: uuid
                        description: Person identifier
                        example: d57d9hd7-fh08-7998-d403-80786315f58
                      sequence_id:
                        type: string
                        format: uuid
                        description: Sequence identifier
                        example: e68e0ie8-gi19-8009-e514-91897426g69
                      task_type_id:
                        type: string
                        format: uuid
                        description: Task type identifier
                        example: f79f1jf9-hj20-9010-f625-a09008537h80
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
        subscription = user_service.subscribe_to_sequence(
            sequence_id, task_type_id
        )
        return subscription, 201


class SequenceUnsubscribeResource(Resource):

    def delete(self, sequence_id, task_type_id):
        """
        Unsubscribe from sequence
        ---
        description: Remove the subscription entry for the current user, given
          sequence, and task type. The user will no longer receive
          notifications for tasks related to this sequence.
        tags:
        - User
        parameters:
          - in: path
            name: sequence_id
            required: true
            schema:
              type: string
              format: uuid
            description: Sequence unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
            required: true
            schema:
              type: string
              format: uuid
            description: Task type unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
            204:
              description: Subscription removed successfully
        """
        user_service.unsubscribe_from_sequence(sequence_id, task_type_id)
        return "", 204


class SequenceSubscriptionsResource(Resource):

    def get(self, project_id, task_type_id):
        """
        Get sequence subscriptions
        ---
        description: Retrieve list of sequence IDs to which the current user
          has subscribed for a given task type within a specific project.
        tags:
        - User
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
            required: true
            schema:
              type: string
              format: uuid
            description: Task type unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
            200:
              description: List of subscribed sequence IDs for the task type
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: string
                      format: uuid
                      example: c46c8gc6-eg97-6887-c292-79675204e47
        """
        return user_service.get_sequence_subscriptions(
            project_id, task_type_id
        )


class TimeSpentsResource(Resource):
    """
    Get all time spents for the current user.
    Optionnaly can accept date range parameters.
    """

    def get(self):
        """
        Get time spents
        ---
        description: Retrieve all time spent entries for the current user.
          Optionally accepts date range parameters to filter results.
        tags:
        - User
        parameters:
          - in: query
            name: start_date
            required: false
            schema:
              type: string
              format: date
            description: Start date for filtering time spents
            example: "2023-01-01"
          - in: query
            name: end_date
            required: false
            schema:
              type: string
              format: date
            description: End date for filtering time spents
            example: "2023-12-31"
        responses:
            200:
              description: Time spent entries for the current user
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
                          description: Time spent unique identifier
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        person_id:
                          type: string
                          format: uuid
                          description: Person identifier
                          example: b35b7fb5-df86-5776-b181-68564193d36
                        task_id:
                          type: string
                          format: uuid
                          description: Task identifier
                          example: c46c8gc6-eg97-6887-c292-79675204e47
                        date:
                          type: string
                          format: date
                          description: Date of time spent
                          example: "2023-01-01"
                        duration:
                          type: number
                          description: Duration in seconds
                          example: 3600
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
            400:
              description: Wrong date format
        """
        arguments = self.get_args(["start_date", "end_date"])
        start_date, end_date = arguments["start_date"], arguments["end_date"]
        current_user = persons_service.get_current_user()
        if not start_date and not end_date:
            return time_spents_service.get_time_spents(current_user["id"])

        if None in [start_date, end_date]:
            abort(
                400,
                "If querying for a range of dates, both a `start_date` and"
                " an `end_date` must be given.",
            )

        try:
            return time_spents_service.get_time_spents_range(
                current_user["id"], start_date, end_date
            )
        except WrongDateFormatException:
            abort(
                400,
                f"Wrong date format for {start_date} and/or {end_date}",
            )


class DateTimeSpentsResource(Resource):

    def get(self, date):
        """
        Get time spents by date
        ---
        description: Retrieve time spent entries for the current user on a
          specific date. Returns all time entries for the given date.
        tags:
        - User
        parameters:
          - in: path
            name: date
            required: true
            schema:
              type: string
              format: date
            description: Date to get time spents for
            example: "2023-01-01"
        responses:
            200:
              description: Time spent entries for the current user on given date
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      date:
                        type: string
                        format: date
                        description: Date of time spent
                        example: "2023-01-01"
                      total_duration:
                        type: number
                        description: Total duration in seconds
                        example: 28800
                      entries:
                        type: array
                        items:
                          type: object
                          properties:
                            id:
                              type: string
                              format: uuid
                              description: Time spent unique identifier
                              example: a24a6ea4-ce75-4665-a070-57453082c25
                            task_id:
                              type: string
                              format: uuid
                              description: Task identifier
                              example: b35b7fb5-df86-5776-b181-68564193d36
                            duration:
                              type: number
                              description: Duration in seconds
                              example: 3600
                            created_at:
                              type: string
                              format: date-time
                              description: Creation timestamp
                              example: "2023-01-01T12:00:00Z"
            400:
              description: Wrong date format
        """
        try:
            current_user = persons_service.get_current_user()
            return time_spents_service.get_time_spents(
                current_user["id"], date
            )
        except WrongDateFormatException:
            abort(400)


class TaskTimeSpentResource(Resource):

    def get(self, task_id, date):
        """
        Get task time spent
        ---
        description: Retrieve time spent entries for the current user on a
          specific task and date. Returns detailed time tracking information.
        tags:
        - User
        parameters:
          - in: path
            name: task_id
            required: true
            schema:
              type: string
              format: uuid
            description: Task unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: date
            required: true
            schema:
              type: string
              format: date
            description: Date to get time spent for
            example: "2023-01-01"
        responses:
            200:
              description: Time spent entry for the current user on given task and date
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Time spent unique identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      person_id:
                        type: string
                        format: uuid
                        description: Person identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      task_id:
                        type: string
                        format: uuid
                        description: Task identifier
                        example: d57d9hd7-fh08-7998-d403-80786315f58
                      date:
                        type: string
                        format: date
                        description: Date of time spent
                        example: "2023-01-01"
                      duration:
                        type: number
                        description: Duration in seconds
                        example: 3600
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
        try:
            current_user = persons_service.get_current_user()
            return time_spents_service.get_time_spent(
                current_user["id"], task_id, date
            )
        except WrongDateFormatException:
            abort(404)


class DayOffResource(Resource):

    def get(self, date):
        """
        Get day off
        ---
        description: Retrieve day off information for the current user on a
          specific date.
        tags:
        - User
        parameters:
          - in: path
            name: date
            required: true
            schema:
              type: string
              format: date
            description: Date to check for day off
            example: "2023-01-01"
        responses:
            200:
              description: Day off object for the current user on given date
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Day off unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      person_id:
                        type: string
                        format: uuid
                        description: Person identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      date:
                        type: string
                        format: date
                        description: Day off date
                        example: "2023-01-01"
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
        try:
            current_user = persons_service.get_current_user()
            return time_spents_service.get_day_off(current_user["id"], date)
        except WrongDateFormatException:
            abort(404)


class ContextResource(Resource):

    def get(self):
        """
        Get context
        ---
        description: Retrieve context information required to properly run a
          full application connected to the API. Returns user, project, and
          system configuration data.
        tags:
        - User
        responses:
            200:
              description: Context information for running a full app connected to the API
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      user:
                        type: object
                        description: Current user information
                        example: {"id": "uuid", "name": "John Doe"}
                      projects:
                        type: array
                        items:
                          type: object
                        description: Available projects
                        example: [{"id": "uuid", "name": "Project 1"}]
                      departments:
                        type: array
                        items:
                          type: object
                        description: Available departments
                        example: [{"id": "uuid", "name": "Animation"}]
                      asset_types:
                        type: array
                        items:
                          type: object
                        description: Available asset types
                        example: [{"id": "uuid", "name": "Character"}]
                      task_types:
                        type: array
                        items:
                          type: object
                        description: Available task types
                        example: [{"id": "uuid", "name": "Modeling"}]
                      task_status:
                        type: array
                        items:
                          type: object
                        description: Available task statuses
                        example: [{"id": "uuid", "name": "In Progress"}]
                      custom_actions:
                        type: array
                        items:
                          type: object
                        description: Available custom actions
                        example: [{"id": "uuid", "name": "Custom Action"}]
                      status_automations:
                        type: array
                        items:
                          type: object
                        description: Available status automations
                        example: [{"id": "uuid", "name": "Auto Status"}]
                      studios:
                        type: array
                        items:
                          type: object
                        description: Available studios
                        example: [{"id": "uuid", "name": "Studio Name"}]
                      notification_count:
                        type: integer
                        description: Number of unread notifications
                        example: 5
                      persons:
                        type: array
                        items:
                          type: object
                        description: Available persons
                        example: [{"id": "uuid", "name": "John Doe"}]
                      project_status:
                        type: array
                        items:
                          type: object
                        description: Available project statuses
                        example: [{"id": "uuid", "name": "Active"}]
                      search_filters:
                        type: array
                        items:
                          type: object
                        description: Available search filters
                        example: [{"id": "uuid", "name": "My Filter"}]
                      search_filter_groups:
                        type: array
                        items:
                          type: object
                        description: Available search filter groups
                        example: [{"id": "uuid", "name": "Filter Group"}]
                      preview_background_files:
                        type: array
                        items:
                          type: object
                        description: Available preview background files
                        example: [{"id": "uuid", "name": "background.jpg"}]
        """
        return user_service.get_context()


class ClearAvatarResource(Resource):

    def delete(self):
        """
        Clear avatar
        ---
        description: Set the has_avatar flag to false for the current user and
          remove the avatar file from storage. This action cannot be undone.
        tags:
        - User
        responses:
            204:
              description: Avatar file deleted successfully
        """
        user = persons_service.get_current_user()
        persons_service.clear_avatar(user["id"])
        return "", 204


class ChatsResource(Resource):

    def get(self):
        """
        Get chats
        ---
        description: Retrieve all chats where the current user is a
          participant. Returns list of chat conversations the user can access.
        tags:
        - User
        responses:
            200:
              description: Chats where user is participant
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
                          description: Chat unique identifier
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        entity_id:
                          type: string
                          format: uuid
                          description: Entity identifier
                          example: b35b7fb5-df86-5776-b181-68564193d36
                        entity_type:
                          type: string
                          description: Entity type
                          example: "Asset"
                        participants:
                          type: array
                          items:
                            type: string
                            format: uuid
                          description: List of participant person identifiers
                          example: ["c46c8gc6-eg97-6887-c292-79675204e47"]
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
        user = persons_service.get_current_user()
        return chats_service.get_chats_for_person(user["id"])


class JoinChatResource(Resource):

    def post(self, entity_id):
        """
        Join chat
        ---
        description: Join a chat for a specific entity by adding the current
          user as a participant. The user will be listed as a participant in
          the chat.
        tags:
        - User
        parameters:
          - in: path
            name: entity_id
            required: true
            schema:
              type: string
              format: uuid
            description: Entity unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
              description: Chat joined successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Chat unique identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      entity_id:
                        type: string
                        format: uuid
                        description: Entity identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      entity_type:
                        type: string
                        description: Entity type
                        example: "Asset"
                      participants:
                        type: array
                        items:
                          type: string
                          format: uuid
                        description: List of participant person identifiers
                        example: ["d57d9hd7-fh08-7998-d403-80786315f58"]
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
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        user_service.check_entity_access(entity["id"])
        person = persons_service.get_current_user()
        return chats_service.join_chat(entity_id, person["id"])

    def delete(self, entity_id):
        """
        Leave chat
        ---
        description: Leave a chat for a specific entity by removing the
          current user from participants. The user will no longer receive
          chat messages for this entity.
        tags:
        - User
        parameters:
          - in: path
            name: entity_id
            required: true
            schema:
              type: string
              format: uuid
            description: Entity unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
              description: Chat left successfully
        """
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        user_service.check_entity_access(entity["id"])
        person = persons_service.get_current_user()
        chats_service.leave_chat(entity_id, person["id"])
        return "", 204
