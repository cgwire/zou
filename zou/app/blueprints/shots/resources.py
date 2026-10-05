from flasgger import swag_from
from flask import request
from flask.views import MethodView
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
    permissions_service,
    user_service,
)

from zou.app.mixin import ArgsMixin
from zou.app.utils import (
    fields,
    flask_utils,
    http_cache,
    permissions,
    query,
    validation,
)
from zou.app.blueprints.shots.schemas import (
    NewShotSchema,
    UpdateShotSchema,
    NewSequenceSchema,
    NewEpisodeSchema,
    NewSceneSchema,
    AddShotToSceneSchema,
)
from zou.app.exceptions import (
    WrongParameterException,
)


class ShotResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/ShotResource_get.yml")
    def get(self, shot_id):
        """
        Get shot
        """
        shot = shots_service.get_full_shot(shot_id)
        permissions_service.check_project_access(shot["project_id"])
        permissions_service.check_entity_access(shot["id"])
        return shot

    @jwt_required()
    @swag_from("openapi/ShotResource_put.yml")
    def put(self, shot_id):
        """
        Update shot
        """
        shot = shots_service.get_shot(shot_id)
        permissions_service.check_manager_project_access(shot["project_id"])
        data = validation.validate_request_body(UpdateShotSchema).model_dump(
            mode="json", exclude_unset=True
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
    @swag_from("openapi/ShotResource_delete.yml")
    def delete(self, shot_id):
        """
        Delete shot
        """
        force = self.get_force()
        shot = shots_service.get_shot(shot_id)
        if shot["created_by"] == persons_service.get_current_user()["id"]:
            permissions_service.check_belong_to_project(shot["project_id"])
        else:
            permissions_service.check_manager_project_access(
                shot["project_id"]
            )
        shots_service.remove_shot(shot_id, force=force)
        return "", 204


class SceneResource(MethodView):
    @jwt_required()
    @swag_from("openapi/SceneResource_get.yml")
    def get(self, scene_id):
        """
        Get scene
        """
        scene = shots_service.get_full_scene(scene_id)
        permissions_service.check_project_access(scene["project_id"])
        permissions_service.check_entity_access(scene["id"])
        return scene

    @jwt_required()
    @swag_from("openapi/SceneResource_delete.yml")
    def delete(self, scene_id):
        """
        Delete scene
        """
        scene = shots_service.get_scene(scene_id)
        if scene["created_by"] == persons_service.get_current_user()["id"]:
            permissions_service.check_belong_to_project(scene["project_id"])
        else:
            permissions_service.check_manager_project_access(
                scene["project_id"]
            )
        shots_service.remove_scene(scene_id)
        return "", 204


class AllShotsResource(MethodView):
    @jwt_required()
    @swag_from("openapi/AllShotsResource_get.yml")
    def get(self):
        """
        Get all shots
        """
        criterions = query.get_query_criterions_from_request(request)
        if "sequence_id" in criterions:
            sequence = shots_service.get_sequence(criterions["sequence_id"])
            criterions["project_id"] = sequence["project_id"]
            criterions["parent_id"] = sequence["id"]
            del criterions["sequence_id"]
        permissions_service.check_project_access(
            criterions.get("project_id", None)
        )
        permissions_service.scope_criterions_to_vendor(criterions)
        return shots_service.get_shots(criterions)


class ScenesResource(MethodView):
    @jwt_required()
    @swag_from("openapi/ScenesResource_get.yml")
    def get(self):
        """
        Get scenes
        """
        criterions = query.get_query_criterions_from_request(request)
        permissions_service.check_project_access(
            criterions.get("project_id", None)
        )
        if permissions.has_vendor_permissions():
            raise permissions.PermissionDenied
        return shots_service.get_scenes(criterions)


class ShotAssetsResource(MethodView):
    @jwt_required()
    @swag_from("openapi/ShotAssetsResource_get.yml")
    def get(self, shot_id):
        """
        Get shot assets
        """
        shot = shots_service.get_shot(shot_id)
        permissions_service.check_project_access(shot["project_id"])
        permissions_service.check_entity_access(shot["id"])
        return breakdown_service.get_entity_casting(shot_id)


class ShotTaskTypesResource(MethodView):
    @jwt_required()
    @swag_from("openapi/ShotTaskTypesResource_get.yml")
    def get(self, shot_id):
        """
        Get shot task types
        """
        shot = shots_service.get_shot(shot_id)
        permissions_service.check_project_access(shot["project_id"])
        permissions_service.check_entity_access(shot["id"])
        return tasks_service.get_task_types_for_shot(shot_id)


class ShotTasksResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/ShotTasksResource_get.yml")
    def get(self, shot_id):
        """
        Get shot tasks
        """
        shot = shots_service.get_shot(shot_id)
        permissions_service.check_project_access(shot["project_id"])
        permissions_service.check_entity_access(shot["id"])
        relations = self.get_relations()
        return tasks_service.get_tasks_for_shot(shot_id, relations=relations)


class SequenceShotTasksResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/SequenceShotTasksResource_get.yml")
    def get(self, sequence_id):
        """
        Get sequence shot tasks
        """
        sequence = shots_service.get_sequence(sequence_id)
        permissions_service.check_project_access(sequence["project_id"])
        permissions_service.check_entity_access(sequence["id"])
        if permissions.has_vendor_permissions():
            raise permissions.PermissionDenied
        relations = self.get_relations()
        return tasks_service.get_shot_tasks_for_sequence(
            sequence_id, relations=relations
        )


class EpisodeShotTasksResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/EpisodeShotTasksResource_get.yml")
    def get(self, episode_id):
        """
        Get episode shot tasks
        """
        episode = shots_service.get_episode(episode_id)
        permissions_service.check_project_access(episode["project_id"])
        permissions_service.check_entity_access(episode["id"])
        if permissions.has_vendor_permissions():
            raise permissions.PermissionDenied
        relations = self.get_relations()
        return tasks_service.get_shot_tasks_for_episode(
            episode_id, relations=relations
        )


class EpisodeAssetTasksResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/EpisodeAssetTasksResource_get.yml")
    def get(self, episode_id):
        """
        Get episode asset tasks
        """
        episode = shots_service.get_episode(episode_id)
        permissions_service.check_project_access(episode["project_id"])
        permissions_service.check_entity_access(episode["id"])
        if permissions.has_vendor_permissions():
            raise permissions.PermissionDenied
        relations = self.get_relations()
        return tasks_service.get_asset_tasks_for_episode(
            episode_id, relations=relations
        )


class EpisodeShotsResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/EpisodeShotsResource_get.yml")
    def get(self, episode_id):
        """
        Get episode shots
        """
        episode = shots_service.get_episode(episode_id)
        permissions_service.check_project_access(episode["project_id"])
        permissions_service.check_entity_access(episode["id"])
        relations = self.get_relations()
        return permissions_service.mask_metadata_for_vendor(
            "Shot",
            shots_service.get_shots_for_episode(
                episode_id, relations=relations
            ),
        )


class ShotPreviewsResource(MethodView):
    @jwt_required()
    @swag_from("openapi/ShotPreviewsResource_get.yml")
    def get(self, shot_id):
        """
        Get shot previews
        """
        shot = shots_service.get_shot(shot_id)
        permissions_service.check_project_access(shot["project_id"])
        permissions_service.check_entity_access(shot["id"])
        return playlists_service.get_entity_previews_by_task_type(shot_id)


class SequenceTasksResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/SequenceTasksResource_get.yml")
    def get(self, sequence_id):
        """
        Get sequence tasks
        """
        sequence = shots_service.get_sequence(sequence_id)
        permissions_service.check_project_access(sequence["project_id"])
        permissions_service.check_entity_access(sequence["id"])
        relations = self.get_relations()
        if permissions.has_vendor_permissions():
            return user_service.get_tasks_for_entity(sequence["id"])
        return tasks_service.get_tasks_for_sequence(
            sequence_id, relations=relations
        )


class SequenceTaskTypesResource(MethodView):
    @jwt_required()
    @swag_from("openapi/SequenceTaskTypesResource_get.yml")
    def get(self, sequence_id):
        """
        Get sequence task types
        """
        sequence = shots_service.get_sequence(sequence_id)
        permissions_service.check_project_access(sequence["project_id"])
        permissions_service.check_entity_access(sequence_id)
        return tasks_service.get_task_types_for_sequence(sequence_id)


class ShotsAndTasksResource(MethodView):

    @jwt_required()
    @swag_from("openapi/ShotsAndTasksResource_get.yml")
    def get(self):
        """
        Get shots and tasks
        """
        criterions = query.get_query_criterions_from_request(request)
        # Kitsu-oriented options for full-project views: compact halves
        # the payload (positional rows, field names in the header) and
        # stream sends NDJSON without holding the response in memory.
        # They are response options, not filters: pop them before the
        # criterions reach the service.
        stream = criterions.pop("stream", "false") == "true"
        compact = criterions.pop("compact", "false") == "true"
        query.check_criterion_id_format(criterions)
        permissions_service.check_project_access(
            criterions.get("project_id", None)
        )
        permissions_service.scope_criterions_to_vendor(criterions)
        etag = entities_service.get_project_board_etag(criterions)
        if etag is not None and http_cache.is_fresh(etag):
            return http_cache.not_modified(etag)
        if not stream and not compact:
            body = shots_service.get_shots_and_tasks(criterions)
            if etag is None:
                return body
            return http_cache.json_response(body, etag)

        rows = shots_service.prepare_shots_and_tasks(
            criterions, compact=compact
        )
        header = {"compact": compact}
        if compact:
            header["shot_fields"] = shots_service.SHOTS_AND_TASKS_SHOT_FIELDS
            header["task_fields"] = shots_service.SHOTS_AND_TASKS_TASK_FIELDS
        response = flask_utils.rows_response(header, rows, stream)
        if etag is not None:
            # rows_response returns a plain dict when not streaming.
            if stream:
                http_cache.mark(response, etag)
            else:
                response = http_cache.json_response(response, etag)
        return response


class SceneAndTasksResource(MethodView):
    @jwt_required()
    @swag_from("openapi/SceneAndTasksResource_get.yml")
    def get(self):
        """
        Get scenes and tasks
        """
        criterions = query.get_query_criterions_from_request(request)
        query.check_criterion_id_format(
            criterions, ["project_id", "episode_id"]
        )
        permissions_service.check_project_access(
            criterions.get("project_id", None)
        )
        if permissions.has_vendor_permissions():
            raise permissions.PermissionDenied
        criterions["entity_type_id"] = shots_service.get_scene_type()["id"]
        return entities_service.get_entities_and_tasks(criterions)


class SequenceAndTasksResource(MethodView):
    @jwt_required()
    @swag_from("openapi/SequenceAndTasksResource_get.yml")
    def get(self):
        """
        Get sequences and tasks
        """
        criterions = query.get_query_criterions_from_request(request)
        query.check_criterion_id_format(
            criterions, ["project_id", "episode_id"]
        )
        permissions_service.check_project_access(
            criterions.get("project_id", None)
        )
        criterions["entity_type_id"] = shots_service.get_sequence_type()["id"]
        if permissions.has_vendor_permissions():
            # Vendors only see sequences holding a shot with a task assigned
            # to them, and only their own tasks on those sequences.
            if criterions.get("episode_id") not in (None, "all"):
                sequences = shots_service.get_sequences_for_episode(
                    criterions["episode_id"], only_assigned=True
                )
            else:
                sequences = shots_service.get_sequences_for_project(
                    criterions["project_id"], only_assigned=True
                )
            criterions["entity_ids"] = [
                sequence["id"] for sequence in sequences
            ]
            criterions["assigned_to"] = persons_service.get_current_user()[
                "id"
            ]
        return permissions_service.mask_metadata_for_vendor(
            "Sequence",
            entities_service.get_entities_and_tasks(criterions),
            criterions.get("project_id"),
        )


class EpisodeAndTasksResource(MethodView):
    @jwt_required()
    @swag_from("openapi/EpisodeAndTasksResource_get.yml")
    def get(self):
        """
        Get episodes and tasks
        """
        criterions = query.get_query_criterions_from_request(request)
        query.check_criterion_id_format(
            criterions, ["project_id", "episode_id"]
        )
        permissions_service.check_project_access(
            criterions.get("project_id", None)
        )
        criterions["entity_type_id"] = shots_service.get_episode_type()["id"]
        if permissions.has_vendor_permissions():
            # Vendors only see episodes holding a shot with a task assigned
            # to them, and only their own tasks on those episodes.
            episodes = shots_service.get_episodes_for_project(
                criterions["project_id"], only_assigned=True
            )
            criterions["entity_ids"] = [episode["id"] for episode in episodes]
            criterions["assigned_to"] = persons_service.get_current_user()[
                "id"
            ]
        return permissions_service.mask_metadata_for_vendor(
            "Episode",
            entities_service.get_entities_and_tasks(criterions),
            criterions.get("project_id"),
        )


class ProjectShotsResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/ProjectShotsResource_get.yml")
    def get(self, project_id):
        """
        Get project shots
        """
        projects_service.get_project(project_id)
        permissions_service.check_project_access(project_id)
        return permissions_service.mask_metadata_for_vendor(
            "Shot",
            shots_service.get_shots_for_project(
                project_id, only_assigned=permissions.has_vendor_permissions()
            ),
            project_id,
        )

    @jwt_required()
    @swag_from("openapi/ProjectShotsResource_post.yml")
    def post(self, project_id):
        """
        Create project shot
        """
        body = validation.validate_request_body(NewShotSchema)
        projects_service.get_project(project_id)
        permissions_service.check_manager_project_access(project_id)

        shot = shots_service.create_shot(
            project_id,
            str(body.sequence_id) if body.sequence_id else None,
            body.name,
            data=body.data,
            nb_frames=body.nb_frames,
            description=body.description,
            created_by=persons_service.get_current_user()["id"],
        )
        return shot, 201


class ProjectSequencesResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/ProjectSequencesResource_get.yml")
    def get(self, project_id):
        """
        Get project sequences
        """
        projects_service.get_project(project_id)
        permissions_service.check_project_access(project_id)
        return permissions_service.mask_metadata_for_vendor(
            "Sequence",
            shots_service.get_sequences_for_project(
                project_id, only_assigned=permissions.has_vendor_permissions()
            ),
            project_id,
        )

    @jwt_required()
    @swag_from("openapi/ProjectSequencesResource_post.yml")
    def post(self, project_id):
        """
        Create project sequence
        """
        body = validation.validate_request_body(NewSequenceSchema)
        projects_service.get_project(project_id)
        permissions_service.check_manager_project_access(project_id)
        sequence = shots_service.create_sequence(
            project_id,
            str(body.episode_id) if body.episode_id else None,
            body.name,
            description=body.description,
            data=body.data,
            created_by=persons_service.get_current_user()["id"],
        )
        return sequence, 201


class ProjectEpisodesResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/ProjectEpisodesResource_get.yml")
    def get(self, project_id):
        """
        Get project episodes
        """
        projects_service.get_project(project_id)
        permissions_service.check_project_access(project_id)
        return permissions_service.mask_metadata_for_vendor(
            "Episode",
            shots_service.get_episodes_for_project(
                project_id, only_assigned=permissions.has_vendor_permissions()
            ),
            project_id,
        )

    @jwt_required()
    @swag_from("openapi/ProjectEpisodesResource_post.yml")
    def post(self, project_id):
        """
        Create project episode
        """
        body = validation.validate_request_body(NewEpisodeSchema)
        projects_service.get_project(project_id)
        permissions_service.check_manager_project_access(project_id)
        return (
            shots_service.create_episode(
                project_id,
                body.name,
                body.status,
                body.description,
                body.data,
                created_by=persons_service.get_current_user()["id"],
            ),
            201,
        )


class ProjectEpisodeStatsResource(MethodView):
    @jwt_required()
    @swag_from("openapi/ProjectEpisodeStatsResource_get.yml")
    def get(self, project_id):
        """
        Get episode stats
        """
        projects_service.get_project(project_id)
        permissions_service.check_project_access(project_id)
        return stats_service.get_episode_stats_for_project(
            project_id, only_assigned=permissions.has_vendor_permissions()
        )


class ProjectEpisodeRetakeStatsResource(MethodView):
    @jwt_required()
    @swag_from("openapi/ProjectEpisodeRetakeStatsResource_get.yml")
    def get(self, project_id):
        """
        Get episode retake stats
        """
        projects_service.get_project(project_id)
        permissions_service.check_project_access(project_id)
        return stats_service.get_episode_retake_stats_for_project(
            project_id, only_assigned=permissions.has_vendor_permissions()
        )


class EpisodeResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/EpisodeResource_get.yml")
    def get(self, episode_id):
        """
        Get episode
        """
        episode = shots_service.get_full_episode(episode_id)
        permissions_service.check_project_access(episode["project_id"])
        permissions_service.check_entity_access(episode["id"])
        return episode

    @jwt_required()
    @swag_from("openapi/EpisodeResource_delete.yml")
    def delete(self, episode_id):
        """
        Delete episode
        """
        force = self.get_force()
        episode = shots_service.get_episode(episode_id)
        if episode["created_by"] == persons_service.get_current_user()["id"]:
            permissions_service.check_belong_to_project(episode["project_id"])
        else:
            permissions_service.check_manager_project_access(
                episode["project_id"]
            )
        deletion_service.remove_episode(episode_id, force=force)
        return "", 204


class EpisodesResource(MethodView):
    @jwt_required()
    @swag_from("openapi/EpisodesResource_get.yml")
    def get(self):
        """
        Get episodes
        """
        criterions = query.get_query_criterions_from_request(request)
        permissions_service.check_project_access(
            criterions.get("project_id", None)
        )
        if permissions.has_vendor_permissions():
            project_id = criterions.get("project_id", None)
            if project_id is not None:
                return permissions_service.mask_metadata_for_vendor(
                    "Episode",
                    shots_service.get_episodes_for_project(
                        project_id, only_assigned=True
                    ),
                    project_id,
                )
            return []
        return shots_service.get_episodes(criterions)


class EpisodeSequencesResource(MethodView):
    @jwt_required()
    @swag_from("openapi/EpisodeSequencesResource_get.yml")
    def get(self, episode_id):
        """
        Get episode sequences
        """
        if not fields.is_valid_id(episode_id):
            return []
        episode = shots_service.get_episode(episode_id)
        permissions_service.check_project_access(episode["project_id"])
        criterions = query.get_query_criterions_from_request(request)
        criterions["parent_id"] = episode_id
        if permissions.has_vendor_permissions():
            return permissions_service.mask_metadata_for_vendor(
                "Sequence",
                shots_service.get_sequences_for_episode(
                    episode_id, only_assigned=True
                ),
            )
        else:
            return shots_service.get_sequences(criterions)


class EpisodeTaskTypesResource(MethodView):
    @jwt_required()
    @swag_from("openapi/EpisodeTaskTypesResource_get.yml")
    def get(self, episode_id):
        """
        Get episode task types
        """
        episode = shots_service.get_episode(episode_id)
        permissions_service.check_project_access(episode["project_id"])
        permissions_service.check_entity_access(episode_id)
        return tasks_service.get_task_types_for_episode(episode_id)


class EpisodeTasksResource(MethodView):
    @jwt_required()
    @swag_from("openapi/EpisodeTasksResource_get.yml")
    def get(self, episode_id):
        """
        Get episode tasks
        """
        episode = shots_service.get_episode(episode_id)
        permissions_service.check_project_access(episode["project_id"])
        permissions_service.check_entity_access(episode["id"])
        if permissions.has_vendor_permissions():
            return user_service.get_tasks_for_entity(episode["id"])
        return tasks_service.get_tasks_for_episode(episode_id)


class SequenceResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/SequenceResource_get.yml")
    def get(self, sequence_id):
        """
        Get sequence
        """
        sequence = shots_service.get_full_sequence(sequence_id)
        permissions_service.check_project_access(sequence["project_id"])
        permissions_service.check_entity_access(sequence["id"])
        return sequence

    @jwt_required()
    @swag_from("openapi/SequenceResource_delete.yml")
    def delete(self, sequence_id):
        """
        Delete sequence
        """
        force = self.get_force()
        sequence = shots_service.get_sequence(sequence_id)
        if sequence["created_by"] != persons_service.get_current_user()["id"]:
            permissions_service.check_belong_to_project(sequence["project_id"])
        else:
            permissions_service.check_manager_project_access(
                sequence["project_id"]
            )
        shots_service.remove_sequence(sequence_id, force=force)
        return "", 204


class SequencesResource(MethodView):
    @jwt_required()
    @swag_from("openapi/SequencesResource_get.yml")
    def get(self):
        """
        Get sequences
        """
        criterions = query.get_query_criterions_from_request(request)
        if "episode_id" in criterions:
            episode = shots_service.get_episode(criterions["episode_id"])
            criterions["project_id"] = episode["project_id"]
            criterions["parent_id"] = episode["id"]
            del criterions["episode_id"]
        permissions_service.check_project_access(
            criterions.get("project_id", None)
        )
        if permissions.has_vendor_permissions():
            project_id = criterions.get("project_id", None)
            if project_id is not None:
                return permissions_service.mask_metadata_for_vendor(
                    "Sequence",
                    shots_service.get_sequences_for_project(
                        project_id, only_assigned=True
                    ),
                    project_id,
                )
            return []
        return shots_service.get_sequences(criterions)


class SequenceShotsResource(MethodView):
    @jwt_required()
    @swag_from("openapi/SequenceShotsResource_get.yml")
    def get(self, sequence_id):
        """
        Get sequence shots
        """
        sequence = shots_service.get_sequence(sequence_id)
        permissions_service.check_project_access(sequence["project_id"])
        criterions = query.get_query_criterions_from_request(request)
        criterions["parent_id"] = sequence_id
        permissions_service.scope_criterions_to_vendor(criterions)
        return shots_service.get_shots(criterions)


class ProjectScenesResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/ProjectScenesResource_get.yml")
    def get(self, project_id):
        """
        Get project scenes
        """
        projects_service.get_project(project_id)
        permissions_service.check_project_access(project_id)
        only_assigned = permissions.has_vendor_permissions()
        return permissions_service.mask_metadata_for_vendor(
            "Scene",
            shots_service.get_scenes_for_project(
                project_id, only_assigned=only_assigned
            ),
            project_id,
        )

    @jwt_required()
    @swag_from("openapi/ProjectScenesResource_post.yml")
    def post(self, project_id):
        """
        Create project scene
        """
        body = validation.validate_request_body(NewSceneSchema)
        projects_service.get_project(project_id)
        permissions_service.check_manager_project_access(project_id)
        scene = shots_service.create_scene(
            project_id,
            str(body.sequence_id) if body.sequence_id else None,
            body.name,
            created_by=persons_service.get_current_user()["id"],
        )
        return scene, 201


class SequenceScenesResource(MethodView):
    @jwt_required()
    @swag_from("openapi/SequenceScenesResource_get.yml")
    def get(self, sequence_id):
        """
        Get sequence scenes
        """
        sequence = shots_service.get_sequence(sequence_id)
        permissions_service.check_project_access(sequence["project_id"])
        permissions_service.check_entity_access(sequence_id)
        return permissions_service.mask_metadata_for_vendor(
            "Scene", shots_service.get_scenes_for_sequence(sequence_id)
        )


class SceneTaskTypesResource(MethodView):
    @jwt_required()
    @swag_from("openapi/SceneTaskTypesResource_get.yml")
    def get(self, scene_id):
        """
        Get scene task types
        """
        scene = shots_service.get_scene(scene_id)
        permissions_service.check_project_access(scene["project_id"])
        permissions_service.check_entity_access(scene["id"])
        return tasks_service.get_task_types_for_scene(scene_id)


class SceneTasksResource(MethodView):
    @jwt_required()
    @swag_from("openapi/SceneTasksResource_get.yml")
    def get(self, scene_id):
        """
        Get scene tasks
        """
        scene = shots_service.get_scene(scene_id)
        permissions_service.check_project_access(scene["project_id"])
        permissions_service.check_entity_access(scene["id"])
        return tasks_service.get_tasks_for_scene(scene_id)


class SceneShotsResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/SceneShotsResource_get.yml")
    def get(self, scene_id):
        """
        Get scene shots
        """
        scene = shots_service.get_scene(scene_id)
        permissions_service.check_project_access(scene["project_id"])
        permissions_service.check_entity_access(scene["id"])
        return scenes_service.get_shots_by_scene(scene_id)

    @jwt_required()
    @swag_from("openapi/SceneShotsResource_post.yml")
    def post(self, scene_id):
        """
        Link shot to scene
        """
        body = validation.validate_request_body(AddShotToSceneSchema)

        scene = shots_service.get_scene(scene_id)
        permissions_service.check_project_access(scene["project_id"])
        shot = shots_service.get_shot(str(body.shot_id))
        return scenes_service.add_shot_to_scene(scene, shot), 201


class RemoveShotFromSceneResource(MethodView):
    @jwt_required()
    @swag_from("openapi/RemoveShotFromSceneResource_delete.yml")
    def delete(self, scene_id, shot_id):
        """
        Delete given shot from given scene.
        """
        scene = shots_service.get_scene(scene_id)
        permissions_service.check_project_access(scene["project_id"])
        shot = shots_service.get_shot(shot_id)
        scenes_service.remove_shot_from_scene(scene, shot)
        return "", 204


class ShotVersionsResource(MethodView):
    """
    Get shot versions
    """

    @jwt_required()
    @swag_from("openapi/ShotVersionsResource_get.yml")
    def get(self, shot_id):
        """
        Get shot versions
        """
        shot = shots_service.get_shot(shot_id)
        permissions_service.check_project_access(shot["project_id"])
        permissions_service.check_entity_access(shot["id"])
        return shots_service.get_shot_versions(shot_id)


class ProjectQuotasResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/ProjectQuotasResource_get.yml")
    def get(self, project_id, task_type_id):
        """
        Get project quotas
        """
        projects_service.get_project(project_id)
        permissions_service.check_project_access(project_id)
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


class ProjectPersonQuotasResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/ProjectPersonQuotasResource_get.yml")
    def get(self, project_id, person_id):
        """
        Get project person quotas
        """
        projects_service.get_project(project_id)
        permissions_service.resolve_project_role(project_id)
        if (
            permissions.has_manager_permissions()
            or permissions.has_supervisor_permissions()
        ):
            permissions_service.check_project_access(project_id)
        else:
            permissions_service.check_person_access(person_id)
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


class SetShotsFramesResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/SetShotsFramesResource_post.yml")
    def post(self, project_id, task_type_id):
        """
        Set shots frames
        """
        permissions_service.check_manager_project_access(project_id)
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
