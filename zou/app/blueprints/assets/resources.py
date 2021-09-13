from flask import request
from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required

from zou.app.utils import permissions, query
from zou.app.mixin import ArgsMixin
from zou.app.services import (
    assets_service,
    breakdown_service,
    persons_service,
    shots_service,
    tasks_service,
    user_service,
)


def check_criterion_access(criterions):
    project_id = None
    if "project_id" in criterions:
        project_id = criterions.get("project_id", None)
    elif "episode_id" in criterions:
        episode_id = criterions.get("episode_id", None)
        project_id = shots_service.get_episode(episode_id)["project_id"]
    return user_service.check_project_access(project_id)


class AssetResource(Resource):
    @jwt_required
    def get(self, asset_id):
        """
        Retrieve given asset.
        """
        asset = assets_service.get_full_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        user_service.check_entity_access(asset["id"])
        return asset

    @jwt_required
    def delete(self, asset_id):
        parser = reqparse.RequestParser()
        parser.add_argument("force", default=False, type=bool)
        args = parser.parse_args()
        force = args["force"]

        asset = assets_service.get_full_asset(asset_id)
        user_service.check_manager_project_access(asset["project_id"])

        assets_service.remove_asset(asset_id, force=force)
        return "", 204


class AllAssetsResource(Resource):
    @jwt_required
    def get(self):
        """
        Retrieve all entities that are not shot or sequence.
        Adds project name and asset type name.
        """
        criterions = query.get_query_criterions_from_request(request)
        check_criterion_access(criterions)
        if permissions.has_vendor_permissions():
            criterions["assigned_to"] = persons_service.get_current_user()[
                "id"
            ]
        return assets_service.get_assets(criterions)


class AllAssetsAliasResource(AllAssetsResource):
    pass


class AssetsAndTasksResource(Resource):
    @jwt_required
    def get(self):
        """
        Retrieve all entities that are not shot or sequence.
        Adds project name and asset type name and all related tasks.
        If episode_id is given as parameter, it returns assets not linked
        to an episode and assets linked to given episode.
        """
        criterions = query.get_query_criterions_from_request(request)
        page = query.get_page_from_request(request)
        check_criterion_access(criterions)
        if permissions.has_vendor_permissions():
            criterions["assigned_to"] = persons_service.get_current_user()[
                "id"
            ]
        return assets_service.get_assets_and_tasks(criterions, page)


class AssetTypeResource(Resource):
    @jwt_required
    def get(self, asset_type_id):
        """
        Retrieve given asset type.
        """
        return assets_service.get_asset_type(asset_type_id)


class AssetTypesResource(Resource):
    @jwt_required
    def get(self):
        """
        Retrieve all asset types (entity types that are not shot, sequence or
        episode).
        """
        criterions = query.get_query_criterions_from_request(request)
        return assets_service.get_asset_types(criterions)


class ProjectAssetTypesResource(Resource):
    @jwt_required
    def get(self, project_id):
        """
        Retrieve all asset types for given project.
        """
        user_service.check_project_access(project_id)
        return assets_service.get_asset_types_for_project(project_id)


class ShotAssetTypesResource(Resource):
    @jwt_required
    def get(self, shot_id):
        """
        Retrieve all asset shots for given soht.
        """
        shot = shots_service.get_shot(shot_id)
        user_service.check_project_access(shot["project_id"])
        return assets_service.get_asset_types_for_shot(shot_id)


class ProjectAssetsResource(Resource):
    @jwt_required
    def get(self, project_id):
        """
        Retrieve all assets for given project.
        """
        user_service.check_project_access(project_id)
        criterions = query.get_query_criterions_from_request(request)
        criterions["project_id"] = project_id
        if permissions.has_vendor_permissions():
            criterions["assigned_to"] = persons_service.get_current_user()[
                "id"
            ]
        return assets_service.get_assets(criterions)


class ProjectAssetTypeAssetsResource(Resource):
    @jwt_required
    def get(self, project_id, asset_type_id):
        """
        Retrieve all assets for given project and entity type.
        """
        user_service.check_project_access(project_id)
        criterions = query.get_query_criterions_from_request(request)
        criterions["project_id"] = project_id
        criterions["entity_type_id"] = asset_type_id
        if permissions.has_vendor_permissions():
            criterions["assigned_to"] = persons_service.get_current_user()[
                "id"
            ]
        return assets_service.get_assets(criterions)


class AssetAssetsResource(Resource):
    @jwt_required
    def get(self, asset_id):
        """
        Retrieve all assets for a given asset.
        """
        asset = assets_service.get_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        user_service.check_entity_access(asset_id)
        return breakdown_service.get_entity_casting(asset_id)


class AssetTasksResource(Resource):
    @jwt_required
    def get(self, asset_id):
        """
        Retrieve all tasks related to a given shot.
        """
        asset = assets_service.get_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        return tasks_service.get_tasks_for_asset(asset_id)


class AssetTaskTypesResource(Resource):
    @jwt_required
    def get(self, asset_id):
        """
        Retrieve all task types related to a given asset.
        """
        asset = assets_service.get_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        return tasks_service.get_task_types_for_asset(asset_id)


class NewAssetResource(Resource):
    @jwt_required
    def post(self, project_id, asset_type_id):
        (name, description, data, source_id) = self.get_arguments()

        user_service.check_manager_project_access(project_id)
        asset = assets_service.create_asset(
            project_id, asset_type_id, name, description, data, source_id
        )
        return asset, 201

    def get_arguments(self):
        parser = reqparse.RequestParser()
        parser.add_argument(
            "name", help="The asset name is required.", required=True
        )
        parser.add_argument("description")
        parser.add_argument("data", type=dict, default={})
        parser.add_argument("episode_id", default=None)
        args = parser.parse_args()
        return (
            args["name"],
            args.get("description", ""),
            args["data"],
            args["episode_id"],
        )


class AssetCastingResource(Resource):
    @jwt_required
    def get(self, asset_id):
        """
        Resource to retrieve the casting of a given asset.
        """
        asset = assets_service.get_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        user_service.check_entity_access(asset_id)
        return breakdown_service.get_casting(asset_id)

    @jwt_required
    def put(self, asset_id):
        """
        Resource to allow the modification of assets linked to a asset.
        """
        casting = request.json
        asset = assets_service.get_asset(asset_id)
        user_service.check_manager_project_access(asset["project_id"])
        return breakdown_service.update_casting(asset_id, casting)


class AssetCastInResource(Resource):
    @jwt_required
    def get(self, asset_id):
        """
        Resource to retrieve the casting of a given asset.
        """
        asset = assets_service.get_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        user_service.check_entity_access(asset["id"])
        return breakdown_service.get_cast_in(asset_id)


class AssetShotAssetInstancesResource(Resource):
    @jwt_required
    def get(self, asset_id):
        """
        Retrieve all shot asset instances linked to asset.
        """
        asset = assets_service.get_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        return breakdown_service.get_shot_asset_instances_for_asset(asset_id)


class AssetSceneAssetInstancesResource(Resource):
    @jwt_required
    def get(self, asset_id):
        """
        Retrieve all scene asset instances linked to asset.
        """
        asset = assets_service.get_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        return breakdown_service.get_scene_asset_instances_for_asset(asset_id)


class AssetAssetInstancesResource(Resource, ArgsMixin):
    @jwt_required
    def get(self, asset_id):
        """
        Retrieve all asset instances instantiated inside this asset.
        """
        asset = assets_service.get_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        return breakdown_service.get_asset_instances_for_asset(asset_id)

    @jwt_required
    def post(self, asset_id):
        """
        Create an asset instance inside given asset.
        """
        args = self.get_args(
            [
                ("asset_to_instantiate_id", None, True),
                ("description", None, False),
            ]
        )
        asset = assets_service.get_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        asset_instance = breakdown_service.add_asset_instance_to_asset(
            asset_id, args["asset_to_instantiate_id"], args["description"]
        )
        return asset_instance, 201
