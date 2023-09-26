from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required

from zou.app.services import (
    assets_service,
    breakdown_service,
    entities_service,
    projects_service,
    shots_service,
    user_service,
)

from zou.app.mixin import ArgsMixin


class CastingResource(Resource):
    @jwt_required()
    def get(self, project_id, entity_id):
        """
        Resource to retrieve the casting of a given entity.
        ---
        tags:
          - Breakdown
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: entity_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Casting of given entity
        """
        user_service.check_project_access(project_id)
        return breakdown_service.get_casting(entity_id)

    @jwt_required()
    def put(self, project_id, entity_id):
        """
        Resource to allow the modification of assets linked to an entity.
        ---
        tags:
          - Breakdown
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: entity_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Modification of assets linked to an entity
        """
        casting = request.json
        user_service.check_manager_project_access(project_id)
        return breakdown_service.update_casting(entity_id, casting)


class EpisodesCastingResource(Resource):
    @jwt_required()
    def get(self, project_id):
        """
        Resource to retrieve the casting of episodes.
        ---
        tags:
          - Breakdown
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Casting of episodes
        """
        user_service.check_project_access(project_id)
        return breakdown_service.get_production_episodes_casting(project_id)


class EpisodeSequenceAllCastingResource(Resource):
    @jwt_required()
    def get(self, project_id, episode_id):
        """
        Resource to retrieve the casting of shots from given episode.
        ---
        tags:
          - Breakdown
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: episode_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Casting for all shots from given episode.
        """
        user_service.check_project_access(project_id)
        return breakdown_service.get_all_sequences_casting(
            project_id, episode_id=episode_id
        )


class SequenceAllCastingResource(Resource):
    @jwt_required()
    def get(self, project_id):
        """
        Resource to retrieve the casting of shots from all sequences of given
        project.
        ---
        tags:
          - Breakdown
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Casting for all shots from given project.
        """
        user_service.check_project_access(project_id)
        return breakdown_service.get_all_sequences_casting(project_id)


class SequenceCastingResource(Resource):
    @jwt_required()
    def get(self, project_id, sequence_id):
        """
        Resource to retrieve the casting of shots from given sequence.
        ---
        tags:
          - Breakdown
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: sequence_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Casting of shots from given sequence
        """
        user_service.check_project_access(project_id)
        shots_service.get_sequence(sequence_id)
        return breakdown_service.get_sequence_casting(sequence_id)


class AssetTypeCastingResource(Resource):
    @jwt_required()
    def get(self, project_id, asset_type_id):
        """
        Resource to retrieve the casting of assets from given asset type.
        ---
        tags:
          - Breakdown
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: asset_type_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Casting of assets from given asset type
        """
        user_service.check_project_access(project_id)
        assets_service.get_asset_type(asset_type_id)
        return breakdown_service.get_asset_type_casting(
            project_id, asset_type_id
        )


class ShotAssetInstancesResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, shot_id):
        """
        Retrieve all asset instances linked to shot.
        ---
        tags:
          - Breakdown
        parameters:
          - in: path
            name: shot_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All assets linked to shot
        """
        shot = shots_service.get_shot(shot_id)
        user_service.check_project_access(shot["project_id"])
        return breakdown_service.get_asset_instances_for_shot(shot_id)

    @jwt_required()
    def post(self, shot_id):
        """
        Add an asset instance to given shot.
        ---
        tags:
          - Breakdown
        parameters:
          - in: path
            name: shot_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
                description: Asset instance added to given shot
        """
        args = self.get_args([("asset_instance_id", None, True)])

        shot = shots_service.get_shot(shot_id)
        user_service.check_project_access(shot["project_id"])
        shot = breakdown_service.add_asset_instance_to_shot(
            shot_id, args["asset_instance_id"]
        )
        return shot, 201


class RemoveShotAssetInstanceResource(Resource, ArgsMixin):
    @jwt_required()
    def delete(self, shot_id, asset_instance_id):
        """
        Remove an asset instance from given shot.
        ---
        tags:
          - Breakdown
        parameters:
          - in: path
            name: shot_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: asset_instance_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
                description: Asset instance removed from given shot
        """
        shot = shots_service.get_shot(shot_id)
        user_service.check_project_access(shot["project_id"])
        shot = breakdown_service.remove_asset_instance_for_shot(
            shot_id, asset_instance_id
        )
        return "", 204


class SceneAssetInstancesResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, scene_id):
        """
        Retrieve all asset instances linked to scene.
        ---
        tags:
          - Breakdown
        parameters:
          - in: path
            name: scene_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All asset instances linked to given scene
        """
        scene = shots_service.get_scene(scene_id)
        user_service.check_project_access(scene["project_id"])
        return breakdown_service.get_asset_instances_for_scene(scene_id)

    @jwt_required()
    def post(self, scene_id):
        """
        Create an asset instance on given scene.
        ---
        tags:
          - Breakdown
        parameters:
          - in: path
            name: scene_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
                description: Asset instances created on given scene
        """
        args = self.get_args(
            [("asset_id", None, True), ("description", None, False)]
        )

        scene = shots_service.get_scene(scene_id)
        user_service.check_project_access(scene["project_id"])
        asset_instance = breakdown_service.add_asset_instance_to_scene(
            scene_id, args["asset_id"], args["description"]
        )
        return asset_instance, 201


class SceneCameraInstancesResource(Resource):
    @jwt_required()
    def get(self, scene_id):
        """
        Retrieve all camera instances linked to scene.
        ---
        tags:
          - Breakdown
        parameters:
          - in: path
            name: scene_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
                description: All camera instances linked to scene
        """
        scene = shots_service.get_scene(scene_id)
        user_service.check_project_access(scene["project_id"])
        return breakdown_service.get_camera_instances_for_scene(scene_id)


class ProjectEntityLinksResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, project_id):
        """
        Retrieve all entity links related to given project.
        ---
        tags:
          - Breakdown
        description: It's mainly used for synchronisation purpose.
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All entity links related to given project
        """
        user_service.check_manager_project_access(project_id)
        projects_service.get_project(project_id)
        page = self.get_page()
        limit = self.get_limit()
        return entities_service.get_entity_links_for_project(
            project_id, page, limit
        )


class ProjectEntityLinkResource(Resource):
    @jwt_required()
    def delete(self, project_id, entity_link_id):
        """
        Delete given entity link.
        ---
        tags:
          - Breakdown
        description: It's mainly used for synchronisation purpose.
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: entity_link_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Entity link deleted
        """
        user_service.check_manager_project_access(project_id)
        return entities_service.remove_entity_link(entity_link_id)
