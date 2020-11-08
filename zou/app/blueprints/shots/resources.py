from flask import request
from flask_restful import Resource, reqparse
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
from zou.app.utils import permissions, query


class ShotResource(Resource, ArgsMixin):
    @jwt_required
    def get(self, shot_id):
        """
        Retrieve given shot.
        """
        shot = shots_service.get_full_shot(shot_id)
        if shot is None:
            shots_service.clear_shot_cache(shot_id)
            shot = shots_service.get_full_shot(shot_id)
        user_service.check_project_access(shot["project_id"])
        user_service.check_entity_access(shot["id"])
        return shot

    @jwt_required
    def delete(self, shot_id):
        """
        Delete given shot.
        """
        force = self.get_force()
        shot = shots_service.get_shot(shot_id)
        user_service.check_manager_project_access(shot["project_id"])
        shots_service.remove_shot(shot_id, force=force)
        return "", 204


class SceneResource(Resource):
    @jwt_required
    def get(self, scene_id):
        """
        Retrieve given scene.
        """
        scene = shots_service.get_full_scene(scene_id)
        user_service.check_project_access(scene["project_id"])
        user_service.check_entity_access(scene["id"])
        return scene

    @jwt_required
    def delete(self, scene_id):
        """
        Delete given scene.
        """
        scene = shots_service.get_scene(scene_id)
        user_service.check_manager_project_access(scene["project_id"])
        shots_service.remove_scene(scene_id)
        return "", 204


class ShotsResource(Resource):
    @jwt_required
    def get(self):
        """
        Retrieve all shot entries. Filters can be specified in the query string.
        """
        criterions = query.get_query_criterions_from_request(request)
        if "sequence_id" in criterions:
            sequence = shots_service.get_sequence(criterions["sequence_id"])
            criterions["project_id"] = sequence["project_id"]
            criterions["parent_id"] = sequence["id"]
            del criterions["sequence_id"]
        user_service.check_project_access(criterions.get("project_id", None))
        if permissions.has_vendor_permissions():
            criterions["assigned_to"] = persons_service.get_current_user()["id"]
        return shots_service.get_shots(criterions)


class AllShotsResource(Resource):
    @jwt_required
    def get(self):
        """
        Retrieve all shot entries. Filters can be specified in the query string.
        """
        criterions = query.get_query_criterions_from_request(request)
        if "sequence_id" in criterions:
            sequence = shots_service.get_sequence(criterions["sequence_id"])
            criterions["project_id"] = sequence["project_id"]
            criterions["parent_id"] = sequence["id"]
            del criterions["sequence_id"]
        if permissions.has_vendor_permissions():
            criterions["assigned_to"] = persons_service.get_current_user()["id"]
        user_service.check_project_access(criterions.get("project_id", None))
        return shots_service.get_shots(criterions)


class ScenesResource(Resource):
    @jwt_required
    def get(self):
        """
        Retrieve all scene entries. Filters can be specified in the query
        string.
        """
        criterions = query.get_query_criterions_from_request(request)
        user_service.check_project_access(criterions.get("project_id", None))
        return shots_service.get_scenes(criterions)


class ShotAssetsResource(Resource):
    @jwt_required
    def get(self, shot_id):
        """
        Retrieve all assets for a given shot.
        """
        shot = shots_service.get_shot(shot_id)
        user_service.check_project_access(shot["project_id"])
        user_service.check_entity_access(shot["id"])
        return breakdown_service.get_entity_casting(shot_id)


class ShotTaskTypesResource(Resource):
    @jwt_required
    def get(self, shot_id):
        """
        Retrieve all task types related to a given shot.
        """
        shot = shots_service.get_shot(shot_id)
        user_service.check_project_access(shot["project_id"])
        user_service.check_entity_access(shot["id"])
        return tasks_service.get_task_types_for_shot(shot_id)


class ShotTasksResource(Resource, ArgsMixin):

    @jwt_required
    def get(self, shot_id):
        """
        Retrieve all tasks related to a given shot.
        """
        shot = shots_service.get_shot(shot_id)
        user_service.check_project_access(shot["project_id"])
        user_service.check_entity_access(shot["id"])
        relations = self.get_relations()
        return tasks_service.get_tasks_for_shot(shot_id, relations=relations)


class SequenceShotTasksResource(Resource, ArgsMixin):

    @jwt_required
    def get(self, sequence_id):
        """
        Retrieve all tasks related to a given sequence.
        """
        sequence = shots_service.get_sequence(sequence_id)
        user_service.check_project_access(sequence["project_id"])
        user_service.check_entity_access(sequence["id"])
        if permissions.has_vendor_permissions():
            raise permissions.PermissionDenied
        relations = self.get_relations()
        return tasks_service.get_shot_tasks_for_sequence(
            sequence_id,
            relations=relations
        )


class EpisodeShotTasksResource(Resource, ArgsMixin):

    @jwt_required
    def get(self, episode_id):
        """
        Retrieve all tasks related to a given episode.
        """
        episode = shots_service.get_episode(episode_id)
        user_service.check_project_access(episode["project_id"])
        user_service.check_entity_access(episode["id"])
        if permissions.has_vendor_permissions():
            raise permissions.PermissionDenied
        relations = self.get_relations()
        return tasks_service.get_shot_tasks_for_episode(
            episode_id,
            relations=relations
        )


class EpisodeShotsResource(Resource, ArgsMixin):

    @jwt_required
    def get(self, episode_id):
        """
        Retrieve all shots related to a given episode.
        """
        episode = shots_service.get_episode(episode_id)
        user_service.check_project_access(episode["project_id"])
        user_service.check_entity_access(episode["id"])
        relations = self.get_relations()
        return shots_service.get_shots_for_episode(
            episode_id,
            relations=relations
        )



class ShotPreviewsResource(Resource):
    @jwt_required
    def get(self, shot_id):
        """
        Retrieve all previews related to a given shot. It sends them
        as a dict. Keys are related task type ids and values are arrays
        of preview for this task type.
        """
        shot = shots_service.get_shot(shot_id)
        user_service.check_project_access(shot["project_id"])
        user_service.check_entity_access(shot["id"])
        return playlists_service.get_preview_files_for_entity(shot_id)


class SequenceTasksResource(Resource, ArgsMixin):
    @jwt_required
    def get(self, sequence_id):
        """
        Retrieve all tasks related to a given shot.
        """
        sequence = shots_service.get_sequence(sequence_id)
        user_service.check_project_access(sequence["project_id"])
        relations = self.get_relations()
        return tasks_service.get_tasks_for_sequence(
            sequence_id,
            relations=relations
        )


class SequenceTaskTypesResource(Resource):
    @jwt_required
    def get(self, sequence_id):
        """
        Retrieve all task types related to a given shot.
        """
        sequence = shots_service.get_sequence(sequence_id)
        user_service.check_project_access(sequence["project_id"])
        return tasks_service.get_task_types_for_sequence(sequence_id)


class ShotsAndTasksResource(Resource):
    @jwt_required
    def get(self):
        """
        Retrieve all shots, adds project name and asset type name and all
        related tasks.
        """
        criterions = query.get_query_criterions_from_request(request)
        user_service.check_project_access(criterions.get("project_id", None))
        if permissions.has_vendor_permissions():
            criterions["assigned_to"] = persons_service.get_current_user()["id"]
        return shots_service.get_shots_and_tasks(criterions)


class SceneAndTasksResource(Resource):
    @jwt_required
    def get(self):
        """
        Retrieve all scene, adds project name and asset type name and all
        related tasks.
        """
        criterions = query.get_query_criterions_from_request(request)
        user_service.check_project_access(criterions.get("project_id", None))
        criterions["entity_type_id"] = shots_service.get_scene_type()["id"]
        return entities_service.get_entities_and_tasks(criterions)


class SequenceAndTasksResource(Resource):
    @jwt_required
    def get(self):
        """
        Retrieve all sequence, adds project name and asset type name and all
        related tasks.
        """
        criterions = query.get_query_criterions_from_request(request)
        user_service.check_project_access(criterions.get("project_id", None))
        criterions["entity_type_id"] = shots_service.get_sequence_type()["id"]
        return entities_service.get_entities_and_tasks(criterions)


class EpisodeAndTasksResource(Resource):
    @jwt_required
    def get(self):
        """
        Retrieve all episode, adds project name and asset type name and all
        related tasks.
        """
        criterions = query.get_query_criterions_from_request(request)
        user_service.check_project_access(criterions.get("project_id", None))
        criterions["entity_type_id"] = shots_service.get_episode_type()["id"]
        return entities_service.get_entities_and_tasks(criterions)


class ProjectShotsResource(Resource):
    @jwt_required
    def get(self, project_id):
        """
        Retrieve all shots related to a given project.
        """
        projects_service.get_project(project_id)
        user_service.check_project_access(project_id)
        return shots_service.get_shots_for_project(
            project_id,
            only_assigned=permissions.has_vendor_permissions()
        )

    @jwt_required
    def post(self, project_id):
        """
        Create a shot for given project.
        """
        (sequence_id, name, data, nb_frames) = self.get_arguments()
        projects_service.get_project(project_id)
        user_service.check_manager_project_access(project_id)

        shot = shots_service.create_shot(
            project_id, sequence_id, name, data=data, nb_frames=nb_frames
        )
        return shot, 201

    def get_arguments(self):
        parser = reqparse.RequestParser()
        parser.add_argument("name", required=True)
        parser.add_argument("sequence_id", default=None)
        parser.add_argument("data", type=dict)
        parser.add_argument("nb_frames", default=None, type=int)
        args = parser.parse_args()
        return (
            args["sequence_id"], args["name"], args["data"], args["nb_frames"]
        )


class ProjectSequencesResource(Resource):
    @jwt_required
    def get(self, project_id):
        """
        Retrieve all sequences related to a given project.
        """
        projects_service.get_project(project_id)
        user_service.check_project_access(project_id)
        return shots_service.get_sequences_for_project(
            project_id,
            only_assigned=permissions.has_vendor_permissions()
        )

    @jwt_required
    def post(self, project_id):
        """
        Create a sequence for given project.
        """
        (episode_id, name) = self.get_arguments()
        projects_service.get_project(project_id)
        user_service.check_manager_project_access(project_id)
        sequence = shots_service.create_sequence(project_id, episode_id, name)
        return sequence, 201

    def get_arguments(self):
        parser = reqparse.RequestParser()
        parser.add_argument("name", required=True)
        parser.add_argument("episode_id", default=None)
        args = parser.parse_args()
        return (args["episode_id"], args["name"])


class ProjectEpisodesResource(Resource):
    @jwt_required
    def get(self, project_id):
        """
        Retrieve all episodes related to a given project.
        """
        projects_service.get_project(project_id)
        user_service.check_project_access(project_id)
        return shots_service.get_episodes_for_project(
            project_id,
            only_assigned=permissions.has_vendor_permissions()
        )

    @jwt_required
    def post(self, project_id):
        """
        Create an episode for given project.
        """
        name = self.get_arguments()
        projects_service.get_project(project_id)
        user_service.check_manager_project_access(project_id)
        return shots_service.create_episode(project_id, name), 201

    def get_arguments(self):
        parser = reqparse.RequestParser()
        parser.add_argument("name", required=True)
        args = parser.parse_args()
        return args["name"]


class ProjectEpisodeStatsResource(Resource):
    @jwt_required
    def get(self, project_id):
        """
        Retrieve number of tasks by status, task_types and episodes
        for given project.
        """
        projects_service.get_project(project_id)
        user_service.check_project_access(project_id)
        return stats_service.get_episode_stats_for_project(
            project_id,
            only_assigned=permissions.has_vendor_permissions()
        )


class ProjectEpisodeRetakeStatsResource(Resource):
    @jwt_required
    def get(self, project_id):
        """
        Retrieve number of tasks by status, task_types and episodes
        for given project.
        """
        projects_service.get_project(project_id)
        user_service.check_project_access(project_id)
        return stats_service.get_episode_retake_stats_for_project(
            project_id,
            only_assigned=permissions.has_vendor_permissions()
        )


class EpisodeResource(Resource, ArgsMixin):
    @jwt_required
    def get(self, episode_id):
        """
        Retrieve given episode.
        """
        episode = shots_service.get_full_episode(episode_id)
        user_service.check_project_access(episode["project_id"])
        return episode

    @jwt_required
    def delete(self, episode_id):
        """
        Retrieve given episode.
        """
        force = self.get_force()
        episode = shots_service.get_episode(episode_id)
        user_service.check_manager_project_access(episode["project_id"])
        deletion_service.remove_episode(episode_id, force=force)
        return "", 204


class EpisodesResource(Resource):
    @jwt_required
    def get(self):
        """
        Retrieve all episode entries. Filters can be specified in the query
        string.
        """
        criterions = query.get_query_criterions_from_request(request)
        user_service.check_project_access(criterions.get("project_id", None))
        return shots_service.get_episodes(criterions)


class EpisodeSequencesResource(Resource):
    @jwt_required
    def get(self, episode_id):
        """
        Retrieve all sequence entries for a given episode.
        Filters can be specified in the query string.
        """
        episode = shots_service.get_episode(episode_id)
        user_service.check_project_access(episode["project_id"])
        criterions = query.get_query_criterions_from_request(request)
        criterions["parent_id"] = episode_id
        if permissions.has_vendor_permissions():
            return shots_service.get_sequences_for_episode(
                episode_id,
                only_assigned=True
            )
        else:
            return shots_service.get_sequences(criterions)


class EpisodeTaskTypesResource(Resource):
    @jwt_required
    def get(self, episode_id):
        """
        Retrieve all task types related to a given episode.
        """
        episode = shots_service.get_episode(episode_id)
        user_service.check_project_access(episode["project_id"])
        return tasks_service.get_task_types_for_episode(episode_id)


class EpisodeTasksResource(Resource):
    @jwt_required
    def get(self, episode_id):
        """
        Retrieve all tasks related to a given episode.
        """
        episode = shots_service.get_episode(episode_id)
        user_service.check_project_access(episode["project_id"])
        return tasks_service.get_tasks_for_episode(episode_id)


class SequenceResource(Resource, ArgsMixin):
    @jwt_required
    def get(self, sequence_id):
        """
        Retrieve given sequence.
        """
        sequence = shots_service.get_full_sequence(sequence_id)
        user_service.check_project_access(sequence["project_id"])
        return sequence

    @jwt_required
    def delete(self, sequence_id):
        """
        Delete given sequence.
        """
        force = self.get_force()
        sequence = shots_service.get_sequence(sequence_id)
        user_service.check_manager_project_access(sequence["project_id"])
        shots_service.remove_sequence(sequence_id, force=force)
        return "", 204


class SequencesResource(Resource):
    @jwt_required
    def get(self):
        """
        Retrieve all sequence entries. Filters can be specified in the query
        string.
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
    @jwt_required
    def get(self, sequence_id):
        """
        Retrieve all shot entries for a given sequence.
        Filters can be specified in the query string.
        """
        sequence = shots_service.get_sequence(sequence_id)
        user_service.check_project_access(sequence["project_id"])
        criterions = query.get_query_criterions_from_request(request)
        criterions["parent_id"] = sequence_id
        if permissions.has_vendor_permissions():
            criterions["assigned_to"] = persons_service.get_current_user()["id"]
        return shots_service.get_shots(criterions)


class ProjectScenesResource(Resource):
    @jwt_required
    def get(self, project_id):
        """
        Retrieve all shots related to a given project.
        """
        projects_service.get_project(project_id)
        user_service.check_project_access(project_id)
        return shots_service.get_scenes_for_project(project_id)

    @jwt_required
    def post(self, project_id):
        """
        Create a shot for given project.
        """
        (sequence_id, name) = self.get_arguments()
        projects_service.get_project(project_id)
        user_service.check_manager_project_access(project_id)
        scene = shots_service.create_scene(project_id, sequence_id, name)
        return scene, 201

    def get_arguments(self):
        parser = reqparse.RequestParser()
        parser.add_argument("name", required=True)
        parser.add_argument("sequence_id", default=None)
        args = parser.parse_args()
        return (args["sequence_id"], args["name"])


class SequenceScenesResource(Resource):
    @jwt_required
    def get(self, sequence_id):
        """
        Retrieve all scenes related to a given sequence.
        """
        sequence = shots_service.get_sequence(sequence_id)
        user_service.check_project_access(sequence["project_id"])
        return shots_service.get_scenes_for_sequence(sequence_id)


class SceneTaskTypesResource(Resource):
    @jwt_required
    def get(self, scene_id):
        """
        Retrieve all task types related to a given scene.
        """
        scene = shots_service.get_scene(scene_id)
        user_service.check_project_access(scene["project_id"])
        user_service.check_entity_access(scene["id"])
        return tasks_service.get_task_types_for_scene(scene_id)


class SceneTasksResource(Resource):
    @jwt_required
    def get(self, scene_id):
        """
        Retrieve all tasks related to a given scene.
        """
        scene = shots_service.get_scene(scene_id)
        user_service.check_entity_access(scene["id"])
        return tasks_service.get_tasks_for_scene(scene_id)


class SceneShotsResource(Resource, ArgsMixin):
    @jwt_required
    def get(self, scene_id):
        """
        Retrieve all shots that comes from given scene.
        """
        scene = shots_service.get_scene(scene_id)
        user_service.check_entity_access(scene["id"])
        return scenes_service.get_shots_by_scene(scene_id)

    @jwt_required
    def post(self, scene_id):
        """
        Mark given scene as source of given shot.
        """
        args = self.get_args([("shot_id", None, True)])
        scene = shots_service.get_scene(scene_id)
        user_service.check_project_access(scene["project_id"])
        shot = shots_service.get_shot(args["shot_id"])
        return scenes_service.add_shot_to_scene(scene, shot), 201


class RemoveShotFromSceneResource(Resource):
    @jwt_required
    def delete(self, scene_id, shot_id):
        scene = shots_service.get_scene(scene_id)
        user_service.check_project_access(scene["project_id"])
        shot = shots_service.get_shot(shot_id)
        scenes_service.remove_shot_from_scene(scene, shot)
        return "", 204


class ShotVersionsResource(Resource):
    """
    Retrieve data versions of given shot.
    """

    @jwt_required
    def get(self, shot_id):
        shot = shots_service.get_shot(shot_id)
        user_service.check_project_access(shot["project_id"])
        user_service.check_entity_access(shot["id"])
        return shots_service.get_shot_versions(shot_id)
