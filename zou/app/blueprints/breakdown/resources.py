from flasgger import swag_from
from flask import request
from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app.services import (
    assets_service,
    breakdown_service,
    entities_service,
    projects_service,
    shots_service,
    permissions_service,
    entity_types_service,
)

from zou.app.mixin import ArgsMixin
from zou.app.utils import permissions, validation
from zou.app.blueprints.breakdown.schemas import (
    AddAssetInstanceSchema,
    AddSceneAssetInstanceSchema,
    CastAssetSchema,
)


class CastingResource(MethodView):
    @jwt_required()
    @swag_from("openapi/CastingResource_get.yml")
    def get(self, project_id, entity_id):
        """
        Get entity casting
        """
        permissions_service.check_project_access(project_id)
        if permissions.has_vendor_permissions():
            raise permissions.PermissionDenied
        permissions_service.check_entities_belong_to_project(
            [entity_id], project_id
        )
        return breakdown_service.get_casting(entity_id)

    @jwt_required()
    @swag_from("openapi/CastingResource_put.yml")
    def put(self, project_id, entity_id):
        """
        Update entity casting
        """
        casting = request.json
        if not isinstance(casting, list):
            return {
                "error": True,
                "message": "Request body must be a JSON array",
            }, 400
        permissions_service.check_manager_project_access(project_id)
        permissions_service.check_entities_belong_to_project(
            [entity_id], project_id
        )
        return breakdown_service.update_casting(entity_id, casting)


class EntitiesCastingResource(MethodView):
    @jwt_required()
    @swag_from("openapi/EntitiesCastingResource_put.yml")
    def put(self, project_id):
        """
        Update several entity castings
        """
        castings = request.json
        if not isinstance(castings, dict) or not all(
            isinstance(casting, list) for casting in castings.values()
        ):
            return {
                "error": True,
                "message": "Request body must be a JSON object mapping "
                "entity ids to casting arrays",
            }, 400
        permissions_service.check_manager_project_access(project_id)
        permissions_service.check_entities_belong_to_project(
            castings.keys(), project_id
        )
        return {
            entity_id: breakdown_service.update_casting(entity_id, casting)
            for entity_id, casting in castings.items()
        }


class EntitiesAssetCastingResource(MethodView):
    @jwt_required()
    @swag_from("openapi/EntitiesAssetCastingResource_put.yml")
    def put(self, project_id, asset_id):
        """
        Cast one asset in several entities
        """
        args = validation.validate_request_body(CastAssetSchema)
        permissions_service.check_manager_project_access(project_id)
        assets_service.get_asset(asset_id)
        entity_ids = [str(entity_id) for entity_id in args.entity_ids]
        permissions_service.check_entities_belong_to_project(
            entity_ids, project_id
        )
        if args.nb_occurences == 0:
            return {
                entity_id: breakdown_service.uncast_asset(entity_id, asset_id)
                for entity_id in entity_ids
            }
        return {
            entity_id: breakdown_service.cast_asset(
                entity_id, asset_id, args.nb_occurences, args.label
            )
            for entity_id in entity_ids
        }


class EpisodesCastingResource(MethodView):
    @jwt_required()
    @swag_from("openapi/EpisodesCastingResource_get.yml")
    def get(self, project_id):
        """
        Get episodes casting
        """
        permissions_service.check_project_access(project_id)
        if permissions.has_vendor_permissions():
            raise permissions.PermissionDenied
        return breakdown_service.get_production_episodes_casting(project_id)


class EpisodeSequenceAllCastingResource(MethodView):
    @jwt_required()
    @swag_from("openapi/EpisodeSequenceAllCastingResource_get.yml")
    def get(self, project_id, episode_id):
        """
        Get episode shots casting
        """
        permissions_service.check_project_access(project_id)
        if permissions.has_vendor_permissions():
            raise permissions.PermissionDenied
        return breakdown_service.get_all_sequences_casting(
            project_id, episode_id=episode_id
        )


class SequenceAllCastingResource(MethodView):
    @jwt_required()
    @swag_from("openapi/SequenceAllCastingResource_get.yml")
    def get(self, project_id):
        """
        Get project shots casting
        """
        permissions_service.check_project_access(project_id)
        if permissions.has_vendor_permissions():
            raise permissions.PermissionDenied
        return breakdown_service.get_all_sequences_casting(project_id)


class SequenceCastingResource(MethodView):
    @jwt_required()
    @swag_from("openapi/SequenceCastingResource_get.yml")
    def get(self, project_id, sequence_id):
        """
        Get sequence shots casting
        """
        permissions_service.check_project_access(project_id)
        if permissions.has_vendor_permissions():
            raise permissions.PermissionDenied
        sequence = shots_service.get_sequence(sequence_id)
        if sequence["project_id"] != project_id:
            raise permissions.PermissionDenied
        return breakdown_service.get_sequence_casting(sequence_id)


class AssetTypeCastingResource(MethodView):
    @jwt_required()
    @swag_from("openapi/AssetTypeCastingResource_get.yml")
    def get(self, project_id, asset_type_id):
        """
        Get asset type casting
        """
        permissions_service.check_project_access(project_id)
        if permissions.has_vendor_permissions():
            raise permissions.PermissionDenied
        entity_types_service.get_asset_type(asset_type_id)
        return breakdown_service.get_asset_type_casting(
            project_id, asset_type_id
        )


class ShotAssetInstancesResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/ShotAssetInstancesResource_get.yml")
    def get(self, shot_id):
        """
        Get shot asset instances
        """
        shot = shots_service.get_shot(shot_id)
        permissions_service.check_project_access(shot["project_id"])
        permissions_service.check_entity_access(shot_id)
        return breakdown_service.get_asset_instances_for_shot(shot_id)

    @jwt_required()
    @swag_from("openapi/ShotAssetInstancesResource_post.yml")
    def post(self, shot_id):
        """
        Add shot asset instance
        """
        body = validation.validate_request_body(AddAssetInstanceSchema)

        shot = shots_service.get_shot(shot_id)
        permissions_service.check_project_access(shot["project_id"])
        shot = breakdown_service.add_asset_instance_to_shot(
            shot_id, str(body.asset_instance_id)
        )
        return shot, 201


class RemoveShotAssetInstanceResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/RemoveShotAssetInstanceResource_delete.yml")
    def delete(self, shot_id, asset_instance_id):
        """
        Remove shot asset instance
        """
        shot = shots_service.get_shot(shot_id)
        permissions_service.check_project_access(shot["project_id"])
        shot = breakdown_service.remove_asset_instance_for_shot(
            shot_id, asset_instance_id
        )
        return "", 204


class SceneAssetInstancesResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/SceneAssetInstancesResource_get.yml")
    def get(self, scene_id):
        """
        Get scene asset instances
        """
        scene = shots_service.get_scene(scene_id)
        permissions_service.check_project_access(scene["project_id"])
        permissions_service.check_entity_access(scene_id)
        return breakdown_service.get_asset_instances_for_scene(scene_id)

    @jwt_required()
    @swag_from("openapi/SceneAssetInstancesResource_post.yml")
    def post(self, scene_id):
        """
        Create scene asset instance
        """
        body = validation.validate_request_body(AddSceneAssetInstanceSchema)

        scene = shots_service.get_scene(scene_id)
        permissions_service.check_project_access(scene["project_id"])
        asset_instance = breakdown_service.add_asset_instance_to_scene(
            scene_id, str(body.asset_id), body.description
        )
        return asset_instance, 201


class SceneCameraInstancesResource(MethodView):
    @jwt_required()
    @swag_from("openapi/SceneCameraInstancesResource_get.yml")
    def get(self, scene_id):
        """
        Get scene camera instances
        """
        scene = shots_service.get_scene(scene_id)
        permissions_service.check_project_access(scene["project_id"])
        permissions_service.check_entity_access(scene_id)
        return breakdown_service.get_camera_instances_for_scene(scene_id)


class ProjectEntityLinksResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/ProjectEntityLinksResource_get.yml")
    def get(self, project_id):
        """
        Get project entity links
        """
        permissions_service.check_manager_project_access(project_id)
        projects_service.get_project(project_id)
        page = self.get_page()
        limit = self.get_limit()
        cursor_created_at = self.get_text_parameter("cursor_created_at")
        return entities_service.get_entity_links_for_project(
            project_id,
            page=page,
            limit=limit,
            cursor_created_at=cursor_created_at,
        )


class ProjectEntityLinkResource(MethodView):
    @jwt_required()
    @swag_from("openapi/ProjectEntityLinkResource_delete.yml")
    def delete(self, project_id, entity_link_id):
        """
        Delete entity link
        """
        permissions_service.check_manager_project_access(project_id)
        link = entities_service.get_entity_link(entity_link_id)
        permissions_service.check_entities_belong_to_project(
            [link["entity_in_id"]], project_id
        )
        return breakdown_service.remove_entity_link(entity_link_id)
