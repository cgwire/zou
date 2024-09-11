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
    WrongParameterException,
)


class ShotResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, shot_id):
        """
        Retrieve given shot.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: shot_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Given shot
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
        Update given shot.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: shot_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: body
            name: data
            required: True
            type: object
        responses:
            200:
                description: Update given shot
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
        Delete given shot.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: shot_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
                description: Given shot deleted
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
        Retrieve given scene.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: scene_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Given scene
        """
        scene = shots_service.get_full_scene(scene_id)
        user_service.check_project_access(scene["project_id"])
        user_service.check_entity_access(scene["id"])
        return scene

    @jwt_required()
    def delete(self, scene_id):
        """
        Delete given scene.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: scene_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
                description: Given scene deleted
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
        Retrieve all shot entries.
        ---
        tags:
        - Shots
        description: Filters can be specified in the query string.
        parameters:
          - in: query
            name: sequence_id
            required: False
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: project_id
            required: False
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: parent_id
            required: False
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All shot entries
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
        Retrieve all shot entries.
        ---
        tags:
        - Shots
        description: Filters can be specified in the query string.
        parameters:
          - in: query
            name: sequence_id
            required: False
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: project_id
            required: False
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: parent_id
            required: False
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All shot entries
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
        Retrieve all scene entries.
        ---
        tags:
        - Shots
        description: Filters can be specified in the query string.
        parameters:
          - in: query
            name: project_id
            required: False
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All scene entries
        """
        criterions = query.get_query_criterions_from_request(request)
        user_service.check_project_access(criterions.get("project_id", None))
        return shots_service.get_scenes(criterions)


class ShotAssetsResource(Resource):
    @jwt_required()
    def get(self, shot_id):
        """
        Retrieve all assets for a given shot.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: shot_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All assets for given shot
        """
        shot = shots_service.get_shot(shot_id)
        user_service.check_project_access(shot["project_id"])
        user_service.check_entity_access(shot["id"])
        return breakdown_service.get_entity_casting(shot_id)


class ShotTaskTypesResource(Resource):
    @jwt_required()
    def get(self, shot_id):
        """
        Retrieve all task types related to a given shot.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: shot_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All task types related to given shot
        """
        shot = shots_service.get_shot(shot_id)
        user_service.check_project_access(shot["project_id"])
        user_service.check_entity_access(shot["id"])
        return tasks_service.get_task_types_for_shot(shot_id)


class ShotTasksResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, shot_id):
        """
        Retrieve all tasks related to a given shot.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: shot_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All tasks related to given shot
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
        Retrieve all tasks related to a given sequence.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: sequence_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All task types related to given sequence
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
        Retrieve all shots tasks related to a given episode.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: episode_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All shots tasks related to given episode
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
        Retrieve all assets tasks related to a given episode.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: episode_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All assets tasks related to given episode
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
        Retrieve all shots related to a given episode.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: episode_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All shots related to given episode
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
        Retrieve all previews related to a given shot.
        ---
        tags:
        - Shots
        description: It sends them as a dict.
                     Keys are related task type ids and values are arrays of preview for this task type.
        parameters:
          - in: path
            name: shot_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All previews related to given episode
        """
        shot = shots_service.get_shot(shot_id)
        user_service.check_project_access(shot["project_id"])
        user_service.check_entity_access(shot["id"])
        return playlists_service.get_preview_files_for_entity(shot_id)


class SequenceTasksResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, sequence_id):
        """
        Retrieve all tasks related to a given shot.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: sequence_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All tasks related to given shot
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
        Retrieve all task types related to a given shot.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: sequence_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All task types related to given shot
        """
        sequence = shots_service.get_sequence(sequence_id)
        user_service.check_project_access(sequence["project_id"])
        return tasks_service.get_task_types_for_sequence(sequence_id)


class ShotsAndTasksResource(Resource):
    @jwt_required()
    def get(self):
        """
        Retrieve all shots, adds project name and asset type name and all related tasks.
        ---
        tags:
        - Shots
        parameters:
          - in: query
            name: project_id
            required: False
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All shots
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
        Retrieve all scenes, adds project name and asset type name and all related tasks.
        ---
        tags:
        - Shots
        parameters:
          - in: query
            name: project_id
            required: False
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All scenes
        """
        criterions = query.get_query_criterions_from_request(request)
        user_service.check_project_access(criterions.get("project_id", None))
        criterions["entity_type_id"] = shots_service.get_scene_type()["id"]
        return entities_service.get_entities_and_tasks(criterions)


class SequenceAndTasksResource(Resource):
    @jwt_required()
    def get(self):
        """
        Retrieve all sequences, adds project name and asset type name and all related tasks.
        ---
        tags:
        - Shots
        parameters:
          - in: query
            name: project_id
            required: False
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All sequences
        """
        criterions = query.get_query_criterions_from_request(request)
        user_service.check_project_access(criterions.get("project_id", None))
        criterions["entity_type_id"] = shots_service.get_sequence_type()["id"]
        return entities_service.get_entities_and_tasks(criterions)


class EpisodeAndTasksResource(Resource):
    @jwt_required()
    def get(self):
        """
        Retrieve all episodes, adds project name and asset type name and all related tasks.
        ---
        tags:
        - Shots
        parameters:
          - in: query
            name: project_id
            required: False
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All episodes
        """
        criterions = query.get_query_criterions_from_request(request)
        user_service.check_project_access(criterions.get("project_id", None))
        criterions["entity_type_id"] = shots_service.get_episode_type()["id"]
        return entities_service.get_entities_and_tasks(criterions)


class ProjectShotsResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, project_id):
        """
        Retrieve all shots related to a given project.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All shots related to given project
        """
        projects_service.get_project(project_id)
        user_service.check_project_access(project_id)
        return shots_service.get_shots_for_project(
            project_id, only_assigned=permissions.has_vendor_permissions()
        )

    @jwt_required()
    def post(self, project_id):
        """
        Create a shot for given project.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: name
            required: True
            type: string
            x-example: Name of shot
          - in: formData
            name: description
            type: string
            x-example: Description of shot
          - in: formData
            name: sequence_id
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: nb_frames
            type: integer
        responses:
            201:
                description: Shot created for given project
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
        Retrieve all sequences related to a given project.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All sequences related to given project
        """
        projects_service.get_project(project_id)
        user_service.check_project_access(project_id)
        return shots_service.get_sequences_for_project(
            project_id, only_assigned=permissions.has_vendor_permissions()
        )

    @jwt_required()
    def post(self, project_id):
        """
        Create a sequence for given project.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: name
            required: True
            type: string
            x-example: Name of sequence
          - in: formData
            name: episode_id
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
                description: Sequence created for given project
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
        Retrieve all episodes related to a given project.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All episodes related to given project
        """
        projects_service.get_project(project_id)
        user_service.check_project_access(project_id)
        return shots_service.get_episodes_for_project(
            project_id, only_assigned=permissions.has_vendor_permissions()
        )

    @jwt_required()
    def post(self, project_id):
        """
        Create an episode for given project.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: name
            required: True
            type: string
            x-example: Name of the episode
          - in: formData
            name: description
            required: True
            type: string
            x-example: Description of the episode
        responses:
            201:
                description: Episode created for given project
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
        Retrieve number of tasks by status, task_types and episodes for given project.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Number of tasks by status, task types and episodes for given project
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
        Retrieve number of tasks by status, task_types and episodes for given project.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Number of tasks by status, task types and episodes for given project
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
        Retrieve given episode.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: episode_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Given episode
        """
        episode = shots_service.get_full_episode(episode_id)
        user_service.check_project_access(episode["project_id"])
        return episode

    @jwt_required()
    def delete(self, episode_id):
        """
        Delete given episode.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: episode_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
                description: Given episode deleted
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
        Retrieve all episode entries.
        ---
        tags:
        - Shots
        description: Filters can be specified in the query string.
        parameters:
          - in: query
            name: project_id
            required: False
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All episode entries
        """
        criterions = query.get_query_criterions_from_request(request)
        user_service.check_project_access(criterions.get("project_id", None))
        return shots_service.get_episodes(criterions)


class EpisodeSequencesResource(Resource):
    @jwt_required()
    def get(self, episode_id):
        """
        Retrieve all sequence entries for a given episode.
        ---
        tags:
        - Shots
        description: Filters can be specified in the query string.
        parameters:
          - in: path
            name: episode_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: project_id
            required: False
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All sequence entries for given episode
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
        Retrieve all task types related to a given episode.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: episode_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All task types related to given episode
        """
        episode = shots_service.get_episode(episode_id)
        user_service.check_project_access(episode["project_id"])
        return tasks_service.get_task_types_for_episode(episode_id)


class EpisodeTasksResource(Resource):
    @jwt_required()
    def get(self, episode_id):
        """
        Retrieve all tasks related to a given episode.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: episode_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All tasks related to given episode
        """
        episode = shots_service.get_episode(episode_id)
        user_service.check_project_access(episode["project_id"])
        return tasks_service.get_tasks_for_episode(episode_id)


class SequenceResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, sequence_id):
        """
        Retrieve given sequence.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: sequence_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Given sequence
        """
        sequence = shots_service.get_full_sequence(sequence_id)
        user_service.check_project_access(sequence["project_id"])
        return sequence

    @jwt_required()
    def delete(self, sequence_id):
        """
        Delete given sequence.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: sequence_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
                description: Given sequence deleted
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
        Retrieve all sequence entries.
        ---
        tags:
        - Shots
        description: Filters can be specified in the query string.
        parameters:
          - in: query
            name: episode_id
            required: False
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All sequence entries
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
        Retrieve all shot entries for a given sequence.
        ---
        tags:
        - Shots
        description: Filters can be specified in the query string.
        parameters:
          - in: path
            name: sequence_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: project_id
            required: False
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All shot entries for given sequence
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
        Retrieve all scenes related to a given project.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All scenes related to given project
        """
        projects_service.get_project(project_id)
        user_service.check_project_access(project_id)
        return shots_service.get_scenes_for_project(project_id)

    @jwt_required()
    def post(self, project_id):
        """
        Create a scene for given project.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: name
            required: True
            type: string
            x-example: Name of scene
          - in: formData
            name: sequence_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
                description: Scene created for given project
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
        Retrieve all scenes related to a given sequence.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: sequence_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All scenes related to given sequence
        """
        sequence = shots_service.get_sequence(sequence_id)
        user_service.check_project_access(sequence["project_id"])
        return shots_service.get_scenes_for_sequence(sequence_id)


class SceneTaskTypesResource(Resource):
    @jwt_required()
    def get(self, scene_id):
        """
        Retrieve all task types related to a given scene.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: scene_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All task types related to given scene
        """
        scene = shots_service.get_scene(scene_id)
        user_service.check_project_access(scene["project_id"])
        user_service.check_entity_access(scene["id"])
        return tasks_service.get_task_types_for_scene(scene_id)


class SceneTasksResource(Resource):
    @jwt_required()
    def get(self, scene_id):
        """
        Retrieve all tasks related to a given scene.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: scene_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All tasks related to given scene
        """
        scene = shots_service.get_scene(scene_id)
        user_service.check_entity_access(scene["id"])
        return tasks_service.get_tasks_for_scene(scene_id)


class SceneShotsResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, scene_id):
        """
        Retrieve all shots that come from given scene.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: scene_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All shots that come from given scene
        """
        scene = shots_service.get_scene(scene_id)
        user_service.check_entity_access(scene["id"])
        return scenes_service.get_shots_by_scene(scene_id)

    @jwt_required()
    def post(self, scene_id):
        """
        Mark given scene as source of given shot.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: scene_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: shot_id
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Given scene marked as source of given shot
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: shot_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
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
    Retrieve data versions of given shot.
    """

    @jwt_required()
    def get(self, shot_id):
        """
        Retrieve data versions of given shot.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: shot_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
                description: Data versions of given shot
        """
        shot = shots_service.get_shot(shot_id)
        user_service.check_project_access(shot["project_id"])
        user_service.check_entity_access(shot["id"])
        return shots_service.get_shot_versions(shot_id)


class ProjectQuotasResource(Resource, ArgsMixin):
    """
    Retrieve quotas statistics for shots
    """

    @jwt_required()
    def get(self, project_id, task_type_id):
        """
        Retrieve quotas statistics for shots.
        ---
        tags:
        - Shots
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: count_mode
            required: True
            type: string
            enum: [weighted, weigtheddone, feedback, done]
            x-example: weighted
          - in: query
            name: studio_id
            required: False
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Quotas statistics for shots
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


class SetShotsFramesResource(Resource, ArgsMixin):
    @jwt_required()
    def post(self, project_id, task_type_id):
        """
        Set frames for given shots.
        ---
        tags:
        - Shots
        parameters:
          - in: formData
            name: shots
            required: True
            type: array
            items:
              type: object
              properties:
                shot_id:
                  type: string
                  format: UUID
                  x-example: a24a6ea4-ce75-4665-a070-57453082c25
                nb_frames:
                  type: integer
                  x-example: 24
        responses:
            200:
                description: Frames set for given shots
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
