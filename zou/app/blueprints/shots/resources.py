from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required

from zou.app.services import (
    breakdown_service,
    deletion_service,
    entities_service,
    persons_service,
    projects_service,
    playlists_service,
    scenes_service,
    shots_service,
    stats_service,
    tasks_service,
    user_service,
)

from zou.app.mixin import ArgsMixin
from zou.app.utils import fields, query, permissions
from zou.app.services.exception import (
    WrongParameterException,
)


class ShotResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, shot_id):
        """
        Get shot
        ---
        tags:
        - Shots
        description: Get a shot by id. Returns full shot data. Use this to fetch
          a single shot with all fields needed by the UI.
        parameters:
          - in: path
            name: shot_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Shot found and returned
                content:
                  application/json:
                    schema:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          example: SH010
                        project_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        parent_id:
                          type: string
                          format: uuid
                          example: c24a6ea4-ce75-4665-a070-57453082c25
                        nb_frames:
                          type: integer
                          example: 120
                        data:
                          type: object
                          example: {"camera": "camA", "cut_in": 1001}
        """
        shot = shots_service.get_full_shot(shot_id)
        if shot is None:
            shots_service.clear_shot_cache(shot_id)
            shot = shots_service.get_full_shot(shot_id)
        user_service.check_project_access(shot["project_id"])
        user_service.check_entity_access(shot["id"])
        return shot

    @jwt_required()
    def put(self, shot_id):
        """
        Update shot
        ---
        tags:
        - Shots
        description: Update a shot by id. Only mutable fields are allowed. Send a
          JSON body with the fields to change.
        parameters:
          - in: path
            name: shot_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                description: Data to update on the shot
                properties:
                  name:
                    type: string
                    example: SH010 new name
                  description:
                    type: string
                    example: Update description for the shot
                  nb_frames:
                    type: integer
                    example: 24
                  data:
                    type: object
                    example: {"camera": "camA", "cut_in": 1001}
        responses:
            200:
                description: Shot updated
                content:
                  application/json:
                    schema:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          example: SH010
                        project_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        parent_id:
                          type: string
                          format: uuid
                          example: c24a6ea4-ce75-4665-a070-57453082c25
                        nb_frames:
                          type: integer
                          example: 120
                        data:
                          type: object
                          example: {"camera": "camA", "cut_in": 1001}
            400:
                description: Invalid body or unsupported fields
        """
        shot = shots_service.get_shot(shot_id)
        user_service.check_manager_project_access(shot["project_id"])
        data = request.json
        if data is None:
            raise WrongParameterException(
                "Data are empty. Please verify that you sent JSON data and"
                " that you set the right headers."
            )
        for field in [
            "id",
            "created_at",
            "updated_at",
            "instance_casting",
            "project_id",
            "entities_in",
            "entities_out",
            "type",
            "shotgun_id",
            "created_by",
        ]:
            data.pop(field, None)

        return shots_service.update_shot(shot_id, data)

    @jwt_required()
    def delete(self, shot_id):
        """
        Delete shot
        ---
        tags:
        - Shots
        description: Delete a shot by id. Requires manager access or ownership of
          the shot.
        parameters:
          - in: path
            name: shot_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
                description: Shot deleted
        """
        force = self.get_force()
        shot = shots_service.get_shot(shot_id)
        if shot["created_by"] == persons_service.get_current_user()["id"]:
            user_service.check_belong_to_project(shot["project_id"])
        else:
            user_service.check_manager_project_access(shot["project_id"])
        shots_service.remove_shot(shot_id, force=force)
        return "", 204


class SceneResource(Resource):
    @jwt_required()
    def get(self, scene_id):
        """
        Get scene
        ---
        tags:
        - Shots
        description: Get a scene by id. Returns full scene data needed by clients.
        parameters:
          - in: path
            name: scene_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Scene found and returned
                content:
                  application/json:
                    schema:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          example: SC001
                        project_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
        """
        scene = shots_service.get_full_scene(scene_id)
        user_service.check_project_access(scene["project_id"])
        user_service.check_entity_access(scene["id"])
        return scene

    @jwt_required()
    def delete(self, scene_id):
        """
        Delete scene
        ---
        tags:
        - Shots
        description: Delete a scene by id. Requires manager access or ownership.
        parameters:
          - in: path
            name: scene_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
                description: Scene deleted
        """
        scene = shots_service.get_scene(scene_id)
        if scene["created_by"] == persons_service.get_current_user()["id"]:
            user_service.check_belong_to_project(scene["project_id"])
        else:
            user_service.check_manager_project_access(scene["project_id"])
        shots_service.remove_scene(scene_id)
        return "", 204


class ShotsResource(Resource):
    @jwt_required()
    def get(self):
        """
        Get shots
        ---
        tags:
        - Shots
        description: Get shots with optional filters. Use query params like
          project_id, sequence_id or parent_id to filter results.
        parameters:
          - in: query
            name: sequence_id
            required: False
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: project_id
            required: False
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: parent_id
            required: False
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All shot entries
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: SH010
                          project_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          parent_id:
                            type: string
                            format: uuid
                            example: c24a6ea4-ce75-4665-a070-57453082c25
        """
        criterions = query.get_query_criterions_from_request(request)
        if "sequence_id" in criterions:
            sequence = shots_service.get_sequence(criterions["sequence_id"])
            criterions["project_id"] = sequence["project_id"]
            criterions["parent_id"] = sequence["id"]
            del criterions["sequence_id"]
        user_service.check_project_access(criterions.get("project_id", None))
        if permissions.has_vendor_permissions():
            criterions["assigned_to"] = persons_service.get_current_user()[
                "id"
            ]
        return shots_service.get_shots(criterions)


class AllShotsResource(Resource):
    @jwt_required()
    def get(self):
        """
        Get all shots
        ---
        tags:
        - Shots
        description: Get all shots across projects with optional filters. Use
          sequence_id, project_id, or parent_id to filter.
        parameters:
          - in: query
            name: sequence_id
            required: False
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: project_id
            required: False
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: parent_id
            required: False
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All shot entries
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: SH020
                          project_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          parent_id:
                            type: string
                            format: uuid
                            example: c24a6ea4-ce75-4665-a070-57453082c25
        """
        criterions = query.get_query_criterions_from_request(request)
        if "sequence_id" in criterions:
            sequence = shots_service.get_sequence(criterions["sequence_id"])
            criterions["project_id"] = sequence["project_id"]
            criterions["parent_id"] = sequence["id"]
            del criterions["sequence_id"]
        if permissions.has_vendor_permissions():
            criterions["assigned_to"] = persons_service.get_current_user()[
                "id"
            ]
        user_service.check_project_access(criterions.get("project_id", None))
        return shots_service.get_shots(criterions)


class ScenesResource(Resource):
    @jwt_required()
    def get(self):
        """
        Get scenes
        ---
        tags:
        - Shots
        description: Get scenes with optional filters. Use project_id to filter
          by project.
        parameters:
          - in: query
            name: project_id
            required: False
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All scene entries
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: SC001
                          project_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
        """
        criterions = query.get_query_criterions_from_request(request)
        user_service.check_project_access(criterions.get("project_id", None))
        return shots_service.get_scenes(criterions)


class ShotAssetsResource(Resource):
    @jwt_required()
    def get(self, shot_id):
        """
        Get shot assets
        ---
        tags:
        - Shots
        description: Get assets linked to a shot. Returns the breakdown casting
          for the shot.
        parameters:
          - in: path
            name: shot_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All assets for given shot
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: Character A
                          entity_type_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
        """
        shot = shots_service.get_shot(shot_id)
        user_service.check_project_access(shot["project_id"])
        user_service.check_entity_access(shot["id"])
        return breakdown_service.get_entity_casting(shot_id)


class ShotTaskTypesResource(Resource):
    @jwt_required()
    def get(self, shot_id):
        """
        Get shot task types
        ---
        tags:
        - Shots
        description: Get task types for a shot.
        parameters:
          - in: path
            name: shot_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All task types related to given shot
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: Animation
        """
        shot = shots_service.get_shot(shot_id)
        user_service.check_project_access(shot["project_id"])
        user_service.check_entity_access(shot["id"])
        return tasks_service.get_task_types_for_shot(shot_id)


class ShotTasksResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, shot_id):
        """
        Get shot tasks
        ---
        tags:
        - Shots
        description: Get tasks for a shot. Optionally include relations using
          query params.
        parameters:
          - in: path
            name: shot_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All tasks related to given shot
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: SH010 Animation
                          task_type_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          task_status_id:
                            type: string
                            format: uuid
                            example: c24a6ea4-ce75-4665-a070-57453082c25
                          entity_id:
                            type: string
                            format: uuid
                            example: d24a6ea4-ce75-4665-a070-57453082c25
                          project_id:
                            type: string
                            format: uuid
                            example: e24a6ea4-ce75-4665-a070-57453082c25
                          assignees:
                            type: array
                            items:
                              type: string
                              format: uuid
                            example: ["f24a6ea4-ce75-4665-a070-57453082c25"]
        """
        shot = shots_service.get_shot(shot_id)
        user_service.check_project_access(shot["project_id"])
        user_service.check_entity_access(shot["id"])
        relations = self.get_relations()
        return tasks_service.get_tasks_for_shot(shot_id, relations=relations)


class SequenceShotTasksResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, sequence_id):
        """
        Get sequence shot tasks
        ---
        tags:
        - Shots
        description: Get shot tasks for a sequence. Restricted for vendor
          permissions.
        parameters:
          - in: path
            name: sequence_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All shot tasks related to given sequence
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: SH010 Animation
                          task_type_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          entity_id:
                            type: string
                            format: uuid
                            example: c24a6ea4-ce75-4665-a070-57453082c25
                          task_status_id:
                            type: string
                            format: uuid
                            example: d24a6ea4-ce75-4665-a070-57453082c25
        """
        sequence = shots_service.get_sequence(sequence_id)
        user_service.check_project_access(sequence["project_id"])
        user_service.check_entity_access(sequence["id"])
        if permissions.has_vendor_permissions():
            raise permissions.PermissionDenied
        relations = self.get_relations()
        return tasks_service.get_shot_tasks_for_sequence(
            sequence_id, relations=relations
        )


class EpisodeShotTasksResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, episode_id):
        """
        Get episode shot tasks
        ---
        tags:
        - Shots
        description: Get shot tasks for an episode. Restricted for vendor
          permissions.
        parameters:
          - in: path
            name: episode_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All shot tasks related to given episode
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: EP01 Layout
                          task_type_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          entity_id:
                            type: string
                            format: uuid
                            example: c24a6ea4-ce75-4665-a070-57453082c25
                          task_status_id:
                            type: string
                            format: uuid
                            example: d24a6ea4-ce75-4665-a070-57453082c25
        """
        episode = shots_service.get_episode(episode_id)
        user_service.check_project_access(episode["project_id"])
        user_service.check_entity_access(episode["id"])
        if permissions.has_vendor_permissions():
            raise permissions.PermissionDenied
        relations = self.get_relations()
        return tasks_service.get_shot_tasks_for_episode(
            episode_id, relations=relations
        )


class EpisodeAssetTasksResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, episode_id):
        """
        Get episode asset tasks
        ---
        tags:
        - Shots
        description: Get asset tasks for an episode. Restricted for vendor
          permissions.
        parameters:
          - in: path
            name: episode_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All assets tasks related to given episode
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: Character Modeling
                          task_type_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          entity_id:
                            type: string
                            format: uuid
                            example: c24a6ea4-ce75-4665-a070-57453082c25
                          task_status_id:
                            type: string
                            format: uuid
                            example: d24a6ea4-ce75-4665-a070-57453082c25
        """
        episode = shots_service.get_episode(episode_id)
        user_service.check_project_access(episode["project_id"])
        user_service.check_entity_access(episode["id"])
        if permissions.has_vendor_permissions():
            raise permissions.PermissionDenied
        relations = self.get_relations()
        return tasks_service.get_asset_tasks_for_episode(
            episode_id, relations=relations
        )


class EpisodeShotsResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, episode_id):
        """
        Get episode shots
        ---
        tags:
        - Shots
        description: Get shots for an episode. Supports including relations via
          query params.
        parameters:
          - in: path
            name: episode_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All shots related to given episode
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: SH010
                          project_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          parent_id:
                            type: string
                            format: uuid
                            example: c24a6ea4-ce75-4665-a070-57453082c25
        """
        episode = shots_service.get_episode(episode_id)
        user_service.check_project_access(episode["project_id"])
        user_service.check_entity_access(episode["id"])
        relations = self.get_relations()
        return shots_service.get_shots_for_episode(
            episode_id, relations=relations
        )


class ShotPreviewsResource(Resource):
    @jwt_required()
    def get(self, shot_id):
        """
        Get shot previews
        ---
        tags:
        - Shots
        description: Return previews for a shot as a dict keyed by task type id.
          Each value is an array of previews for that task type.
        parameters:
          - in: path
            name: shot_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All previews related to given shot
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
                              example: b24a6ea4-ce75-4665-a070-57453082c25
                            revision:
                              type: integer
                              example: 3
                            file_id:
                              type: string
                              format: uuid
                              example: c24a6ea4-ce75-4665-a070-57453082c25
                    example:
                      "a24a6ea4-ce75-4665-a070-57453082c25": [
                        {
                          "id": "b24a6ea4-ce75-4665-a070-57453082c25",
                          "revision": 3,
                          "file_id": "c24a6ea4-ce75-4665-a070-57453082c25"
                        }
                      ]
        """
        shot = shots_service.get_shot(shot_id)
        user_service.check_project_access(shot["project_id"])
        user_service.check_entity_access(shot["id"])
        return playlists_service.get_preview_files_for_entity(shot_id)


class SequenceTasksResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, sequence_id):
        """
        Get sequence tasks
        ---
        tags:
        - Shots
        description: Get tasks for a sequence. Optionally include relations using
          query params.
        parameters:
          - in: path
            name: sequence_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All tasks related to given shot
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: SH010 Animation
                          task_type_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          task_status_id:
                            type: string
                            format: uuid
                            example: c24a6ea4-ce75-4665-a070-57453082c25
                          entity_id:
                            type: string
                            format: uuid
                            example: d24a6ea4-ce75-4665-a070-57453082c25
                          project_id:
                            type: string
                            format: uuid
                            example: e24a6ea4-ce75-4665-a070-57453082c25
        """
        sequence = shots_service.get_sequence(sequence_id)
        user_service.check_project_access(sequence["project_id"])
        relations = self.get_relations()
        return tasks_service.get_tasks_for_sequence(
            sequence_id, relations=relations
        )


class SequenceTaskTypesResource(Resource):
    @jwt_required()
    def get(self, sequence_id):
        """
        Get sequence task types
        ---
        tags:
        - Shots
        description: Get task types for a sequence.
        parameters:
          - in: path
            name: sequence_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All task types related to given shot
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: Animation
        """
        sequence = shots_service.get_sequence(sequence_id)
        user_service.check_project_access(sequence["project_id"])
        return tasks_service.get_task_types_for_sequence(sequence_id)


class ShotsAndTasksResource(Resource):

    @jwt_required()
    def get(self):
        """
        Get shots and tasks
        ---
        tags:
        - Shots
        description: Get shots and their related tasks. Optionally filter by project.
        parameters:
          - in: query
            name: project_id
            required: False
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All shots
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: SH010
                          project_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          tasks:
                            type: array
                            items:
                              type: object
                              properties:
                                id:
                                  type: string
                                  format: uuid
                                  example: c24a6ea4-ce75-4665-a070-57453082c25
                                name:
                                  type: string
                                  example: SH010 Animation
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
        return shots_service.get_shots_and_tasks(criterions)


class SceneAndTasksResource(Resource):
    @jwt_required()
    def get(self):
        """
        Get scenes and tasks
        ---
        tags:
        - Shots
        description: Get scenes and their related tasks. Optionally filter by project.
        parameters:
          - in: query
            name: project_id
            required: False
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All scenes
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: SC001
                          project_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          tasks:
                            type: array
                            items:
                              type: object
                              properties:
                                id:
                                  type: string
                                  format: uuid
                                  example: c24a6ea4-ce75-4665-a070-57453082c25
                                name:
                                  type: string
                                  example: Layout
        """
        criterions = query.get_query_criterions_from_request(request)
        user_service.check_project_access(criterions.get("project_id", None))
        criterions["entity_type_id"] = shots_service.get_scene_type()["id"]
        return entities_service.get_entities_and_tasks(criterions)


class SequenceAndTasksResource(Resource):
    @jwt_required()
    def get(self):
        """
        Get sequences and tasks
        ---
        tags:
        - Shots
        description: Get sequences and their related tasks.
          Optionally filter by project.
        parameters:
          - in: query
            name: project_id
            required: False
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All sequences
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: SQ010
                          project_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          tasks:
                            type: array
                            items:
                              type: object
                              properties:
                                id:
                                  type: string
                                  format: uuid
                                  example: c24a6ea4-ce75-4665-a070-57453082c25
                                name:
                                  type: string
                                  example: SQ010 Editing
        """
        criterions = query.get_query_criterions_from_request(request)
        user_service.check_project_access(criterions.get("project_id", None))
        criterions["entity_type_id"] = shots_service.get_sequence_type()["id"]
        return entities_service.get_entities_and_tasks(criterions)


class EpisodeAndTasksResource(Resource):
    @jwt_required()
    def get(self):
        """
        Get episodes and tasks
        ---
        tags:
        - Shots
        description: Get episodes and their related tasks.
          Optionally filter by project.
        parameters:
          - in: query
            name: project_id
            required: False
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All episodes
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: EP01
                          project_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          tasks:
                            type: array
                            items:
                              type: object
                              properties:
                                id:
                                  type: string
                                  format: uuid
                                  example: c24a6ea4-ce75-4665-a070-57453082c25
                                name:
                                  type: string
                                  example: EP01 Layout
        """
        criterions = query.get_query_criterions_from_request(request)
        user_service.check_project_access(criterions.get("project_id", None))
        criterions["entity_type_id"] = shots_service.get_episode_type()["id"]
        return entities_service.get_entities_and_tasks(criterions)


class ProjectShotsResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, project_id):
        """
        Get project shots
        ---
        tags:
        - Shots
        description: Get shots for a project. May limit to assigned shots for
          vendor users.
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All shots related to given project
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: SH010
                          project_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          parent_id:
                            type: string
                            format: uuid
                            example: c24a6ea4-ce75-4665-a070-57453082c25
        """
        projects_service.get_project(project_id)
        user_service.check_project_access(project_id)
        return shots_service.get_shots_for_project(
            project_id, only_assigned=permissions.has_vendor_permissions()
        )

    @jwt_required()
    def post(self, project_id):
        """
        Create project shot
        ---
        tags:
        - Shots
        description: Create a shot in a project. Provide name and optional
          fields like description, sequence_id and nb_frames.
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
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
                    required: true
                    example: SH010
                  description:
                    type: string
                    required: false
                    example: A short description of the shot
                  sequence_id:
                    type: string
                    format: uuid
                    required: false
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  nb_frames:
                    type: integer
                    required: false
                    example: 24
        responses:
            201:
                description: Shot created
                content:
                  application/json:
                    schema:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          example: SH010
                        project_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        sequence_id:
                          type: string
                          format: uuid
                          example: c24a6ea4-ce75-4665-a070-57453082c25
                        nb_frames:
                          type: integer
                          example: 24
                        description:
                          type: string
                          example: A short description of the shot
        """
        (
            sequence_id,
            name,
            data,
            nb_frames,
            description,
        ) = self.get_arguments()
        projects_service.get_project(project_id)
        user_service.check_manager_project_access(project_id)

        shot = shots_service.create_shot(
            project_id,
            sequence_id,
            name,
            data=data,
            nb_frames=nb_frames,
            description=description,
            created_by=persons_service.get_current_user()["id"],
        )
        return shot, 201

    def get_arguments(self):
        args = self.get_args(
            [
                {"name": "name", "required": True},
                "sequence_id",
                {"name": "data", "type": dict},
                {"name": "nb_frames", "type": int},
                "description",
            ]
        )

        return (
            args["sequence_id"],
            args["name"],
            args["data"],
            args["nb_frames"],
            args["description"],
        )


class ProjectSequencesResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, project_id):
        """
        Get project sequences
        ---
        tags:
        - Shots
        description: Get sequences for a project. May limit to assigned items for
          vendor users.
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All sequences related to given project
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: SQ01
                          project_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          episode_id:
                            type: string
                            format: uuid
                            example: c24a6ea4-ce75-4665-a070-57453082c25
        """
        projects_service.get_project(project_id)
        user_service.check_project_access(project_id)
        return shots_service.get_sequences_for_project(
            project_id, only_assigned=permissions.has_vendor_permissions()
        )

    @jwt_required()
    def post(self, project_id):
        """
        Create project sequence
        ---
        tags:
        - Shots
        description: Create a sequence in a project. Provide name and optional
          episode_id.
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
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
                    required: true
                    example: SQ01
                  episode_id:
                    type: string
                    format: uuid
                    required: false
                    example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
                description: Sequence created
                content:
                  application/json:
                    schema:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          example: SQ01
                        project_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        episode_id:
                          type: string
                          format: uuid
                          example: c24a6ea4-ce75-4665-a070-57453082c25
                        description:
                          type: string
                          example: A sequence description
        """
        (episode_id, name, description, data) = self.get_arguments()
        projects_service.get_project(project_id)
        user_service.check_manager_project_access(project_id)
        sequence = shots_service.create_sequence(
            project_id,
            episode_id,
            name,
            description=description,
            data=data,
            created_by=persons_service.get_current_user()["id"],
        )
        return sequence, 201

    def get_arguments(self):
        args = self.get_args(
            [
                {"name": "name", "required": True},
                "episode_id",
                {"name": "description", "default": ""},
                {"name": "data", "type": dict, "default": {}},
            ]
        )

        return (
            args["episode_id"],
            args["name"],
            args["description"],
            args["data"],
        )


class ProjectEpisodesResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, project_id):
        """
        Get project episodes
        ---
        tags:
        - Shots
        description: Get episodes for a project. May limit to assigned items for
          vendor users.
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All episodes related to given project
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: EP01
                          project_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          description:
                            type: string
                            example: A short description of the episode
                          status:
                            type: string
                            example: running
        """
        projects_service.get_project(project_id)
        user_service.check_project_access(project_id)
        return shots_service.get_episodes_for_project(
            project_id, only_assigned=permissions.has_vendor_permissions()
        )

    @jwt_required()
    def post(self, project_id):
        """
        Create project episode
        ---
        tags:
        - Shots
        description: Create an episode in a project. Provide name and
          description. Status is optional.
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - name
                  - description
                properties:
                  name:
                    type: string
                    required: true
                    example: EP01
                  description:
                    type: string
                    required: true
                    example: A short description of the episode
                  status:
                    type: string
                    required: false
                    example: running
        responses:
            201:
                description: Episode created
                content:
                  application/json:
                    schema:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          example: EP01
                        project_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        description:
                          type: string
                          example: A short description of the episode
                        status:
                          type: string
                          example: running
        """
        name, status, description, data = self.get_arguments()
        projects_service.get_project(project_id)
        user_service.check_manager_project_access(project_id)
        return (
            shots_service.create_episode(
                project_id,
                name,
                status,
                description,
                data,
                created_by=persons_service.get_current_user()["id"],
            ),
            201,
        )

    def get_arguments(self):
        args = self.get_args(
            [
                {"name": "name", "required": True},
                {"name": "status", "default": "running"},
                {"name": "description", "default": ""},
                {"name": "data", "type": dict, "default": {}},
            ]
        )

        return args["name"], args["status"], args["description"], args["data"]


class ProjectEpisodeStatsResource(Resource):
    @jwt_required()
    def get(self, project_id):
        """
        Get episode stats
        ---
        tags:
        - Shots
        description: Return number of tasks by status, task type and episode
          for the project.
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Number of tasks by status, task types and episodes for given project
                content:
                  application/json:
                    schema:
                      type: object
                      additionalProperties:
                        type: object
                        additionalProperties:
                          type: object
                          additionalProperties:
                            type: object
                            properties:
                              count:
                                type: integer
                                example: 120
                              frames:
                                type: integer
                                example: 1440
                              drawings:
                                type: integer
                                example: 360
                      example:
                        episodeId1:
                          taskTypeId1:
                            taskStatusId1:
                              count: 50
                              frames: 600
                              drawings: 150
                            taskStatusId2:
                              count: 70
                              frames: 840
                              drawings: 210
                        all:
                          all:
                            taskStatusId1:
                              count: 200
                              frames: 2400
                              drawings: 600
        """
        projects_service.get_project(project_id)
        user_service.check_project_access(project_id)
        return stats_service.get_episode_stats_for_project(
            project_id, only_assigned=permissions.has_vendor_permissions()
        )


class ProjectEpisodeRetakeStatsResource(Resource):
    @jwt_required()
    def get(self, project_id):
        """
        Get episode retake stats
        ---
        tags:
        - Shots
        description: Return retake and done counts by task type and episode.
          Includes evolution data and max retake count.
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Number of tasks by status, task types and episodes for given project
                content:
                  application/json:
                    schema:
                      type: object
                      additionalProperties:
                        type: object
                        properties:
                          max_retake_count:
                            type: integer
                            example: 4
                          evolution:
                            type: object
                            additionalProperties:
                              type: object
                              properties:
                                retake:
                                  type: object
                                  properties:
                                    count:
                                      type: integer
                                      example: 80
                                    frames:
                                      type: integer
                                      example: 7900
                                    drawings:
                                      type: integer
                                      example: 8000
                                done:
                                  type: object
                                  properties:
                                    count:
                                      type: integer
                                      example: 117
                                    frames:
                                      type: integer
                                      example: 3900
                                    drawings:
                                      type: integer
                                      example: 8000
                          done:
                            type: object
                            properties:
                              count:
                                type: integer
                                example: 197
                              frames:
                                type: integer
                                example: 16090
                              drawings:
                                type: integer
                                example: 16090
                          retake:
                            type: object
                            properties:
                              count:
                                type: integer
                                example: 0
                              frames:
                                type: integer
                                example: 0
                              drawings:
                                type: integer
                                example: 0
                          other:
                            type: object
                            properties:
                              count:
                                type: integer
                                example: 5
                              frames:
                                type: integer
                                example: 185
                              drawings:
                                type: integer
                                example: 185
                      example:
                        episodeId1:
                          max_retake_count: 4
                          evolution:
                            "1":
                              retake:
                                count: 80
                                frames: 7900
                                drawings: 8000
                              done:
                                count: 117
                                frames: 3900
                                drawings: 8000
                          done:
                            count: 197
                            frames: 16090
                            drawings: 16090
                          retake:
                            count: 0
                            frames: 0
                            drawings: 0
                          other:
                            count: 5
                            frames: 185
                            drawings: 185
                        all:
                          all:
                            max_retake_count: 4
                            done:
                              count: 500
                              frames: 50000
                              drawings: 50000
                            retake:
                              count: 100
                              frames: 10000
                              drawings: 10000
                            other:
                              count: 10
                              frames: 1000
                              drawings: 1000
        """
        projects_service.get_project(project_id)
        user_service.check_project_access(project_id)
        return stats_service.get_episode_retake_stats_for_project(
            project_id, only_assigned=permissions.has_vendor_permissions()
        )


class EpisodeResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, episode_id):
        """
        Get episode
        ---
        tags:
        - Shots
        description: Get an episode by id.
          needs.
        parameters:
          - in: path
            name: episode_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Episode found and returned
                content:
                  application/json:
                    schema:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          example: EP01
                        project_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        description:
                          type: string
                          example: A short description of the episode
                        status:
                          type: string
                          example: running
        """
        episode = shots_service.get_full_episode(episode_id)
        user_service.check_project_access(episode["project_id"])
        return episode

    @jwt_required()
    def delete(self, episode_id):
        """
        Delete episode
        ---
        tags:
        - Shots
        description: Delete an episode by id. Requires manager access or
          ownership.
        parameters:
          - in: path
            name: episode_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
                description: Episode deleted
        """
        force = self.get_force()
        episode = shots_service.get_episode(episode_id)
        if episode["created_by"] == persons_service.get_current_user()["id"]:
            user_service.check_belong_to_project(episode["project_id"])
        else:
            user_service.check_manager_project_access(episode["project_id"])
        deletion_service.remove_episode(episode_id, force=force)
        return "", 204


class EpisodesResource(Resource):
    @jwt_required()
    def get(self):
        """
        Get episodes
        ---
        tags:
        - Shots
        description: Get episodes with optional filters. Use project_id to
          filter by project.
        parameters:
          - in: query
            name: project_id
            required: False
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All episode entries
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: EP01
                          project_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          description:
                            type: string
                            example: A short description of the episode
                          status:
                            type: string
                            example: running
        """
        criterions = query.get_query_criterions_from_request(request)
        user_service.check_project_access(criterions.get("project_id", None))
        return shots_service.get_episodes(criterions)


class EpisodeSequencesResource(Resource):
    @jwt_required()
    def get(self, episode_id):
        """
        Get episode sequences
        ---
        tags:
        - Shots
        description: Get sequences for an episode. You can add query filters
          if needed.
        parameters:
          - in: path
            name: episode_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: project_id
            required: False
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All sequence entries for given episode
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: SQ01
                          project_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          parent_id:
                            type: string
                            format: uuid
                            example: c24a6ea4-ce75-4665-a070-57453082c25
        """
        if not fields.is_valid_id(episode_id):
            return []
        episode = shots_service.get_episode(episode_id)
        user_service.check_project_access(episode["project_id"])
        criterions = query.get_query_criterions_from_request(request)
        criterions["parent_id"] = episode_id
        if permissions.has_vendor_permissions():
            return shots_service.get_sequences_for_episode(
                episode_id, only_assigned=True
            )
        else:
            return shots_service.get_sequences(criterions)


class EpisodeTaskTypesResource(Resource):
    @jwt_required()
    def get(self, episode_id):
        """
        Get episode task types
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: episode_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All task types related to given episode
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: Animation
        """
        episode = shots_service.get_episode(episode_id)
        user_service.check_project_access(episode["project_id"])
        return tasks_service.get_task_types_for_episode(episode_id)


class EpisodeTasksResource(Resource):
    @jwt_required()
    def get(self, episode_id):
        """
        Get episode tasks
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: episode_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All tasks related to given episode
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: EP01 Layout
                          task_type_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          task_status_id:
                            type: string
                            format: uuid
                            example: c24a6ea4-ce75-4665-a070-57453082c25
                          entity_id:
                            type: string
                            format: uuid
                            example: d24a6ea4-ce75-4665-a070-57453082c25
                          project_id:
                            type: string
                            format: uuid
                            example: e24a6ea4-ce75-4665-a070-57453082c25
                          assignees:
                            type: array
                            items:
                              type: string
                              format: uuid
                            example: ["f24a6ea4-ce75-4665-a070-57453082c25"]
        """
        episode = shots_service.get_episode(episode_id)
        user_service.check_project_access(episode["project_id"])
        return tasks_service.get_tasks_for_episode(episode_id)


class SequenceResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, sequence_id):
        """
        Get sequence
        ---
        tags:
        - Shots
        description: Get a sequence by id.
        parameters:
          - in: path
            name: sequence_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Sequence found and returned
                content:
                  application/json:
                    schema:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          example: SQ01
                        project_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        parent_id:
                          type: string
                          format: uuid
                          example: c24a6ea4-ce75-4665-a070-57453082c25
        """
        sequence = shots_service.get_full_sequence(sequence_id)
        user_service.check_project_access(sequence["project_id"])
        return sequence

    @jwt_required()
    def delete(self, sequence_id):
        """
        Delete sequence
        ---
        tags:
        - Shots
        description: Delete a sequence by id. Requires manager access or
          ownership.
        parameters:
          - in: path
            name: sequence_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
                description: Sequence deleted
        """
        force = self.get_force()
        sequence = shots_service.get_sequence(sequence_id)
        if sequence["created_by"] != persons_service.get_current_user()["id"]:
            user_service.check_belong_to_project(sequence["project_id"])
        else:
            user_service.check_manager_project_access(sequence["project_id"])
        shots_service.remove_sequence(sequence_id, force=force)
        return "", 204


class SequencesResource(Resource):
    @jwt_required()
    def get(self):
        """
        Get sequences
        ---
        tags:
        - Shots
        description: Get sequences with optional filters. Use episode_id to
          filter by episode.
        parameters:
          - in: query
            name: episode_id
            required: False
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All sequence entries
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: SQ01
                          project_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          parent_id:
                            type: string
                            format: uuid
                            example: c24a6ea4-ce75-4665-a070-57453082c25
        """
        criterions = query.get_query_criterions_from_request(request)
        if "episode_id" in criterions:
            episode = shots_service.get_episode(criterions["episode_id"])
            criterions["project_id"] = episode["project_id"]
            criterions["parent_id"] = episode["id"]
            del criterions["episode_id"]
        user_service.check_project_access(criterions.get("project_id", None))
        return shots_service.get_sequences(criterions)


class SequenceShotsResource(Resource):
    @jwt_required()
    def get(self, sequence_id):
        """
        Get sequence shots
        ---
        tags:
        - Shots
        description: Get shots for a sequence. Supports filtering using query
          params.
        parameters:
          - in: path
            name: sequence_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: project_id
            required: False
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All shot entries for given sequence
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: SH010
                          project_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          parent_id:
                            type: string
                            format: uuid
                            example: c24a6ea4-ce75-4665-a070-57453082c25
        """
        sequence = shots_service.get_sequence(sequence_id)
        user_service.check_project_access(sequence["project_id"])
        criterions = query.get_query_criterions_from_request(request)
        criterions["parent_id"] = sequence_id
        if permissions.has_vendor_permissions():
            criterions["assigned_to"] = persons_service.get_current_user()[
                "id"
            ]
        return shots_service.get_shots(criterions)


class ProjectScenesResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, project_id):
        """
        Get project scenes
        ---
        tags:
        - Shots
        description: Get all scenes for a project.
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All scenes related to given project
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: SC001
                          project_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          parent_id:
                            type: string
                            format: uuid
                            example: c24a6ea4-ce75-4665-a070-57453082c25
        """
        projects_service.get_project(project_id)
        user_service.check_project_access(project_id)
        return shots_service.get_scenes_for_project(project_id)

    @jwt_required()
    def post(self, project_id):
        """
        Create project scene
        ---
        tags:
        - Shots
        description: Create a new scene in a project. Provide a name and the
          related sequence id.
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - name
                  - sequence_id
                properties:
                  name:
                    type: string
                    required: true
                    example: "Name of scene"
                  sequence_id:
                    type: string
                    format: uuid
                    required: true
                    example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
                description: Scene created for given project
                content:
                  application/json:
                    schema:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          example: SC001
                        project_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        parent_id:
                          type: string
                          format: uuid
                          example: c24a6ea4-ce75-4665-a070-57453082c25
        """
        (sequence_id, name) = self.get_arguments()
        projects_service.get_project(project_id)
        user_service.check_manager_project_access(project_id)
        scene = shots_service.create_scene(
            project_id,
            sequence_id,
            name,
            created_by=persons_service.get_current_user()["id"],
        )
        return scene, 201

    def get_arguments(self):
        args = self.get_args(
            [{"name": "name", "required": True}, "sequence_id"]
        )

        return (args["sequence_id"], args["name"])


class SequenceScenesResource(Resource):
    @jwt_required()
    def get(self, sequence_id):
        """
        Get sequence scenes
        ---
        tags:
        - Shots
        description: Get scenes that belong to a sequence.
        parameters:
          - in: path
            name: sequence_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All scenes related to given sequence
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: SC010
                          project_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          parent_id:
                            type: string
                            format: uuid
                            example: c24a6ea4-ce75-4665-a070-57453082c25
        """
        sequence = shots_service.get_sequence(sequence_id)
        user_service.check_project_access(sequence["project_id"])
        return shots_service.get_scenes_for_sequence(sequence_id)


class SceneTaskTypesResource(Resource):
    @jwt_required()
    def get(self, scene_id):
        """
        Get scene task types
        ---
        tags:
        - Shots
        description: Get task types for a scene.
        parameters:
          - in: path
            name: scene_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All task types related to given scene
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: Animation
        """
        scene = shots_service.get_scene(scene_id)
        user_service.check_project_access(scene["project_id"])
        user_service.check_entity_access(scene["id"])
        return tasks_service.get_task_types_for_scene(scene_id)


class SceneTasksResource(Resource):
    @jwt_required()
    def get(self, scene_id):
        """
        Get scene tasks
        ---
        tags:
        - Shots
        description: Get tasks for a scene.
        parameters:
          - in: path
            name: scene_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All tasks related to given scene
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: SC001 Layout
                          task_type_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          task_status_id:
                            type: string
                            format: uuid
                            example: c24a6ea4-ce75-4665-a070-57453082c25
                          entity_id:
                            type: string
                            format: uuid
                            example: d24a6ea4-ce75-4665-a070-57453082c25
                          project_id:
                            type: string
                            format: uuid
                            example: e24a6ea4-ce75-4665-a070-57453082c25
        """
        scene = shots_service.get_scene(scene_id)
        user_service.check_entity_access(scene["id"])
        return tasks_service.get_tasks_for_scene(scene_id)


class SceneShotsResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, scene_id):
        """
        Get scene shots
        ---
        tags:
        - Shots
        description: Get shots that come from a scene.
        parameters:
          - in: path
            name: scene_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All shots that come from given scene
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: SH010
                          project_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
        """
        scene = shots_service.get_scene(scene_id)
        user_service.check_entity_access(scene["id"])
        return scenes_service.get_shots_by_scene(scene_id)

    @jwt_required()
    def post(self, scene_id):
        """
        Link shot to scene
        ---
        tags:
        - Shots
        description: Link a shot to a scene as its source.
        parameters:
          - in: path
            name: scene_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - shot_id
                properties:
                  shot_id:
                    type: string
                    format: uuid
                    required: true
                    example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
                description: Scene marked as source of shot
                content:
                  application/json:
                    schema:
                      type: object
                      properties:
                        scene_id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        shot_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
        """
        args = self.get_args([("shot_id", None, True)])

        scene = shots_service.get_scene(scene_id)
        user_service.check_project_access(scene["project_id"])
        shot = shots_service.get_shot(args["shot_id"])
        return scenes_service.add_shot_to_scene(scene, shot), 201


class RemoveShotFromSceneResource(Resource):
    @jwt_required()
    def delete(self, scene_id, shot_id):
        """
        Delete given shot from given scene.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: scene_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: shot_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
                description: Given shot deleted from given scene
        """
        scene = shots_service.get_scene(scene_id)
        user_service.check_project_access(scene["project_id"])
        shot = shots_service.get_shot(shot_id)
        scenes_service.remove_shot_from_scene(scene, shot)
        return "", 204


class ShotVersionsResource(Resource):
    """
    Get shot versions
    """

    @jwt_required()
    def get(self, shot_id):
        """
        Get shot versions
        ---
        tags:
        - Shots
        description: Get data versions of a shot. Use this to inspect version
          history.
        parameters:
          - in: path
            name: shot_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Data versions of given shot
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
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          created_at:
                            type: string
                            format: date-time
                            example: "2024-01-15T10:30:00Z"
        """
        shot = shots_service.get_shot(shot_id)
        user_service.check_project_access(shot["project_id"])
        user_service.check_entity_access(shot["id"])
        return shots_service.get_shot_versions(shot_id)


class ProjectQuotasResource(Resource, ArgsMixin):

    @jwt_required()
    def get(self, project_id, task_type_id):
        """
        Get project quotas
        ---
        tags:
        - Shots
        description: Get quotas statistics for a project and task type. Supports
          weighted and raw modes with optional feedback filtering.
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: count_mode
            required: True
            type: string
            enum: [weighted, weigtheddone, feedback, done]
            example: weighted
          - in: query
            name: studio_id
            required: False
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Quotas statistics for shots
                content:
                  application/json:
                    schema:
                      type: object
                      additionalProperties:
                        type: object
                        properties:
                          count:
                            type: integer
                            example: 42
                          frames:
                            type: integer
                            example: 1200
            400:
                description: Invalid count_mode or parameter
        """
        projects_service.get_project(project_id)
        user_service.check_project_access(project_id)
        args = self.get_args(
            [
                ("count_mode", "weighted", False, str),
                ("studio_id", None, False, str),
            ]
        )
        count_mode = args["count_mode"]
        studio_id = args["studio_id"]

        if count_mode not in ["weighted", "weighteddone", "feedback", "done"]:
            raise WrongParameterException(
                "count_mode must be equal to weighted, weigtheddone, feedback"
                ", or done"
            )

        feedback = "done" not in count_mode
        weighted = "weighted" in count_mode

        if weighted:
            return shots_service.get_weighted_quotas(
                project_id,
                task_type_id,
                feedback=feedback,
                studio_id=studio_id,
            )
        else:
            return shots_service.get_raw_quotas(
                project_id,
                task_type_id,
                feedback=feedback,
                studio_id=studio_id,
            )


class ProjectPersonQuotasResource(Resource, ArgsMixin):

    @jwt_required()
    def get(self, project_id, person_id):
        """
        Get project person quotas
        ---
        tags:
        - Shots
        description: Get quotas statistics for a person in a project. Supports
          weighted and raw modes with optional feedback filtering.
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: person_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: count_mode
            required: True
            type: string
            enum: [weighted, weigtheddone, feedback, done]
            example: weighted
          - in: query
            name: studio_id
            required: False
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Quotas statistics for shots
                content:
                  application/json:
                    schema:
                      type: object
                      additionalProperties:
                        type: object
                        properties:
                          count:
                            type: integer
                            example: 15
                          frames:
                            type: integer
                            example: 360
            400:
                description: Invalid count_mode or parameter
        """
        projects_service.get_project(project_id)
        if (
            permissions.has_manager_permissions()
            or permissions.has_supervisor_permissions()
        ):
            user_service.check_project_access(project_id)
        else:
            user_service.check_person_access(person_id)
        args = self.get_args(
            [
                ("count_mode", "weighted", False, str),
                ("studio_id", None, False, str),
            ]
        )
        count_mode = args["count_mode"]
        studio_id = args["studio_id"]

        if count_mode not in ["weighted", "weighteddone", "feedback", "done"]:
            raise WrongParameterException(
                "count_mode must be equal to weighted, weigtheddone, feedback"
                ", or done"
            )

        feedback = "done" not in count_mode
        weighted = "weighted" in count_mode

        if weighted:
            return shots_service.get_weighted_quotas(
                project_id,
                person_id=person_id,
                feedback=feedback,
                studio_id=studio_id,
            )
        else:
            return shots_service.get_raw_quotas(
                project_id,
                person_id=person_id,
                feedback=feedback,
                studio_id=studio_id,
            )


class SetShotsFramesResource(Resource, ArgsMixin):
    @jwt_required()
    def post(self, project_id, task_type_id):
        """
        Set shots frames
        ---
        tags:
        - Shots
        description: Set number of frames on shots based on latest preview
          files for a task type. Optionally scope by episode via query
          param.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - shots
                properties:
                  shots:
                    type: array
                    required: true
                    items:
                      type: object
                      properties:
                        shot_id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        nb_frames:
                          type: integer
                          example: 24
        responses:
            200:
                description: Frames set for given shots
                content:
                  application/json:
                    schema:
                      type: object
                      properties:
                        updated:
                          type: integer
                          example: 12
            400:
                description: Invalid ids or parameters
        """
        user_service.check_manager_project_access(project_id)
        if not fields.is_valid_id(task_type_id) or not fields.is_valid_id(
            project_id
        ):
            raise WrongParameterException("Invalid project or task type id")

        episode_id = self.get_episode_id()
        if not episode_id in ["", None] and not fields.is_valid_id(episode_id):
            raise WrongParameterException("Invalid episode id")

        if episode_id == "":
            episode_id = None

        return shots_service.set_frames_from_task_type_preview_files(
            project_id,
            task_type_id,
            episode_id=episode_id,
        )
