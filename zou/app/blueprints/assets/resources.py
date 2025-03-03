from flask import request
from flask_restful import Resource, inputs
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

    if "project_id" in criterions:
        user_service.check_project_access(project_id)

    return True


class AssetResource(Resource, ArgsMixin):
    """
    Retrieve or delete given asset.
    """

    @jwt_required()
    def get(self, asset_id):
        """
        Retrieve given asset.
        ---
        tags:
          - Assets
        parameters:
          - in: path
            name: asset_id
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
            required: True
        responses:
          200:
            description: Given asset
        """
        asset = assets_service.get_full_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        user_service.check_entity_access(asset["id"])
        return asset

    @jwt_required()
    def delete(self, asset_id):
        """
        Delete given asset.
        ---
        tags:
          - Assets
        parameters:
          - in: path
            name: asset_id
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
            required: True
        responses:
          204:
            description: Given asset deleted
        """
        force = self.get_force()

        asset = assets_service.get_full_asset(asset_id)
        if asset["created_by"] == persons_service.get_current_user()["id"]:
            user_service.check_belong_to_project(asset["project_id"])
        else:
            user_service.check_manager_project_access(asset["project_id"])

        assets_service.remove_asset(asset_id, force=force)
        return "", 204


class AllAssetsResource(Resource):
    """
    Retrieve all entities that are not shot or sequence.
    Adds project name and asset type name.
    """

    @jwt_required()
    def get(self):
        """
        Retrieve all entities that are not shot or sequence.
        Adds project name and asset type name.
        ---
        tags:
          - Assets
        responses:
          200:
            description: All assets
        """
        criterions = query.get_query_criterions_from_request(request)
        check_criterion_access(criterions)
        if permissions.has_vendor_permissions():
            criterions["assigned_to"] = persons_service.get_current_user()[
                "id"
            ]
        return assets_service.get_assets(
            criterions,
            is_admin=permissions.has_admin_permissions(),
        )


class AllAssetsAliasResource(AllAssetsResource):
    pass


class AssetsAndTasksResource(Resource, ArgsMixin):
    """
    Retrieve all entities that are not shot or sequence.
    """

    @jwt_required()
    def get(self):
        """
        Retrieve all entities that are not shot or sequence.
        ---
        description: Adds project name and asset type name and all related tasks.
                     If episode_id is given as parameter, it returns assets not linked
                     to an episode and assets linked to given episode.
        tags:
          - Assets
        responses:
          200:
            description: All assets with tasks
        """
        criterions = query.get_query_criterions_from_request(request)
        check_criterion_access(criterions)
        if permissions.has_vendor_permissions():
            criterions["assigned_to"] = persons_service.get_current_user()[
                "id"
            ]
            criterions["vendor_departments"] = [
                str(department.id)
                for department in persons_service.get_current_user_raw().departments
            ]
        return assets_service.get_assets_and_tasks(criterions)


class AssetTypeResource(Resource):
    """
    Retrieve given asset type.
    """

    @jwt_required()
    def get(self, asset_type_id):
        """
        Retrieve given asset type.
        ---
        tags:
          - Assets
        parameters:
          - in: path
            name: asset_type_id
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
            required: True
        responses:
          200:
            description: Given asset type
        """
        return assets_service.get_asset_type(asset_type_id)


class AssetTypesResource(Resource):
    """
    Retrieve all asset types (entity types that are not shot, sequence or episode).
    """

    @jwt_required()
    def get(self):
        """
        Retrieve all asset types (entity types that are not shot, sequence or episode).
        ---
        tags:
          - Assets
        responses:
          200:
            description: All asset types
        """
        criterions = query.get_query_criterions_from_request(request)
        return assets_service.get_asset_types(criterions)


class ProjectAssetTypesResource(Resource):
    """
    Retrieve all asset types for given project.
    """

    @jwt_required()
    def get(self, project_id):
        """
        Retrieve all asset types for given project.
        ---
        tags:
          - Assets
        parameters:
          - in: path
            name: project_id
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
            required: True
        responses:
          200:
            description: All asset types for given project
        """
        user_service.check_project_access(project_id)
        return assets_service.get_asset_types_for_project(project_id)


class ShotAssetTypesResource(Resource):
    """
    Retrieve all asset shots for given shot.
    """

    @jwt_required()
    def get(self, shot_id):
        """
        Retrieve all asset shots for given shot.
        ---
        tags:
          - Assets
        parameters:
          - in: path
            name: shot_id
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
            required: True
        responses:
          200:
            description: All asset shots for given shot
        """
        shot = shots_service.get_shot(shot_id)
        user_service.check_project_access(shot["project_id"])
        return assets_service.get_asset_types_for_shot(shot_id)


class ProjectAssetsResource(Resource):
    """
    Retrieve all assets for given project.
    """

    @jwt_required()
    def get(self, project_id):
        """
        Retrieve all assets for given project.
        ---
        tags:
          - Assets
        parameters:
          - in: path
            name: project_id
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
            required: True
        responses:
          200:
            description: All assets for given project
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
    """
    Retrieve all assets for given project and entity type.
    """

    @jwt_required()
    def get(self, project_id, asset_type_id):
        """
        Retrieve all assets for given project and entity type.
        ---
        tags:
            - Assets
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
                description: All assets for given project and entity type
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
    """
    Retrieve all assets for a given asset.
    """

    @jwt_required()
    def get(self, asset_id):
        """
        Retrieve all assets for a given asset.
        ---
        tags:
            - Assets
        parameters:
          - in: path
            name: asset_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All assets for a given asset
        """
        asset = assets_service.get_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        user_service.check_entity_access(asset_id)
        return breakdown_service.get_entity_casting(asset_id)


class AssetTasksResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, asset_id):
        """
        Retrieve all tasks related to a given shot.
        ---
        tags:
            - Assets
        parameters:
          - in: path
            name: asset_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All tasks related to given shot
        """
        asset = assets_service.get_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        return tasks_service.get_tasks_for_asset(
            asset_id, relations=self.get_relations()
        )


class AssetTaskTypesResource(Resource):
    @jwt_required()
    def get(self, asset_id):
        """
        Retrieve all task types related to a given asset.
        ---
        tags:
            - Assets
        parameters:
          - in: path
            name: asset_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All task types related to given asset
        """
        asset = assets_service.get_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        return tasks_service.get_task_types_for_asset(asset_id)


class NewAssetResource(Resource, ArgsMixin):
    """
    Create new asset resource.
    """

    @jwt_required()
    def post(self, project_id, asset_type_id):
        """
        Create new asset resource.
        ---
        tags:
            - Assets
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
          - in: body
            name: Asset
            description: Name, description, data and ID of asset
            schema:
                type: object
                required:
                - name
                - description
                - data
                - is_shared
                - source_id
                properties:
                    name:
                        type: string
                    description:
                        type: string
                    data:
                        type: string
                    is_shared:
                        type: boolean
                    source_id:
                        type: string
                        format: UUID
                        example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
                description: New asset resource created
        """
        (name, description, data, is_shared, source_id) = self.get_arguments()

        user_service.check_manager_project_access(project_id)
        asset = assets_service.create_asset(
            project_id,
            asset_type_id,
            name,
            description,
            data,
            is_shared,
            source_id,
            created_by=persons_service.get_current_user()["id"],
        )
        return asset, 201

    def get_arguments(self):
        args = self.get_args(
            [
                {
                    "name": "name",
                    "required": True,
                    "help": "The asset name is required.",
                },
                "description",
                ("data", {}, False, dict),
                (
                    "is_shared",
                    False,
                    False,
                    inputs.boolean,
                ),
                "episode_id",
            ]
        )

        return (
            args["name"],
            args.get("description", ""),
            args["data"],
            args["is_shared"],
            args["episode_id"],
        )


class AssetCastingResource(Resource):
    @jwt_required()
    def get(self, asset_id):
        """
        Resource to retrieve the casting of a given asset.
        ---
        tags:
            - Assets
        parameters:
          - in: path
            name: asset_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Casting of given asset
        """
        asset = assets_service.get_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        user_service.check_entity_access(asset_id)
        return breakdown_service.get_casting(asset_id)

    @jwt_required()
    def put(self, asset_id):
        """
        Resource to allow the modification of assets linked to a asset.
        ---
        tags:
            - Assets
        parameters:
          - in: path
            name: asset_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Modification of assets linked to given asset
        """
        casting = request.json
        asset = assets_service.get_asset(asset_id)
        user_service.check_manager_project_access(asset["project_id"])
        return breakdown_service.update_casting(asset_id, casting)


class AssetCastInResource(Resource):
    @jwt_required()
    def get(self, asset_id):
        """
        Resource to retrieve the casting of a given asset.
        ---
        tags:
            - Assets
        parameters:
          - in: path
            name: asset_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Casting of given asset
        """
        asset = assets_service.get_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        user_service.check_entity_access(asset["id"])
        return breakdown_service.get_cast_in(asset_id)


class AssetShotAssetInstancesResource(Resource):
    @jwt_required()
    def get(self, asset_id):
        """
        Retrieve all shot asset instances linked to asset.
        ---
        tags:
            - Assets
        parameters:
          - in: path
            name: asset_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All shot asset instances linked to asset
        """
        asset = assets_service.get_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        return breakdown_service.get_shot_asset_instances_for_asset(asset_id)


class AssetSceneAssetInstancesResource(Resource):
    @jwt_required()
    def get(self, asset_id):
        """
        Retrieve all scene asset instances linked to asset.
        ---
        tags:
            - Assets
        parameters:
          - in: path
            name: asset_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All scene asset instances linked to asset
        """
        asset = assets_service.get_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        return breakdown_service.get_scene_asset_instances_for_asset(asset_id)


class AssetAssetInstancesResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, asset_id):
        """
        Retrieve all asset instances instantiated inside this asset.
        ---
        tags:
            - Assets
        parameters:
          - in: path
            name: asset_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All asset instances instantiated inside given asset
        """
        asset = assets_service.get_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        return breakdown_service.get_asset_instances_for_asset(asset_id)

    @jwt_required()
    def post(self, asset_id):
        """
        Create an asset instance inside given asset.
        ---
        tags:
            - Assets
        parameters:
          - in: path
            name: asset_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
                description: Asset instance created inside given asset
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


class BaseSetSharedAssetsResource(Resource, ArgsMixin):

    @jwt_required()
    def post(self, project_id=None, asset_type_id=None, asset_ids=None):
        args = self.get_args(
            [
                (
                    "is_shared",
                    True,
                    False,
                    inputs.boolean,
                ),
            ]
        )
        return assets_service.set_shared_assets(
            is_shared=args["is_shared"],
            project_id=project_id,
            asset_type_id=asset_type_id,
            asset_ids=asset_ids,
        )


class SetSharedProjectAssetsResource(BaseSetSharedAssetsResource):
    """
    Share or unshare all assets (or a list of assets) for given project.
    """

    @jwt_required()
    def post(self, project_id):
        """
        Share or unshare all assets (or a list of assets) for given project.
        ---
        tags:
        - Assets
        consumes:
            - multipart/form-data
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: asset_ids
            default: None,
            type: array
            items:
                type: UUID
            x-example: ["a24a6ea4-ce75-4665-a070-57453082c25"]
          - in: formData
            name: is_shared
            default: true
            type: boolean
            x-example: true
        responses:
            201:
                description: All assets modified.
        """
        args = self.get_args(
            [
                (
                    "asset_ids",
                    None,
                    False,
                    str,
                    "append",
                ),
            ]
        )
        user_service.check_manager_project_access(project_id)
        return super().post(project_id=project_id, asset_ids=args["asset_ids"])


class SetSharedProjectAssetTypeAssetsResource(BaseSetSharedAssetsResource):
    """
    Share or unshare all assets for given project and asset type.
    """

    @jwt_required()
    def post(self, project_id, asset_type_id):
        """
        Share or unshare all assets for given project and asset type.
        ---
        tags:
        - Assets
        consumes:
            - multipart/form-data
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
          - in: formData
            name: is_shared
            default: true
            type: boolean
            x-example: true
        responses:
            201:
                description: All assets modified.
        """
        user_service.check_manager_project_access(project_id)
        return super().post(project_id=project_id, asset_type_id=asset_type_id)


class SetSharedAssetsResource(BaseSetSharedAssetsResource):
    """
    Share or unshare all assets (or a list of assets) for given project.
    """

    @jwt_required()
    def post(self):
        """
        Share or unshare a list of assets.
        ---
        tags:
        - Assets
        consumes:
            - multipart/form-data
        parameters:
          - in: formData
            name: asset_ids
            default: None,
            type: array
            items:
                type: UUID
            x-example: ["a24a6ea4-ce75-4665-a070-57453082c25"]
          - in: formData
            name: is_shared
            default: true
            type: boolean
            x-example: true
        responses:
            201:
                description: All assets modified.
        """
        args = self.get_args(
            [
                (
                    "asset_ids",
                    [],
                    True,
                    str,
                    "append",
                ),
            ]
        )
        asset_ids = args["asset_ids"]
        project_ids = set()
        for asset_id in asset_ids:
            project_ids.add(assets_service.get_asset(asset_id)["project_id"])
        for project_id in project_ids:
            user_service.check_manager_project_access(project_id)
        return super().post(asset_ids=asset_ids)


class ProjectAssetsSharedUsedResource(Resource):
    @jwt_required()
    def get(self, project_id):
        """
        Retrieve all shared assets used in project.
        ---
        tags:
            - Assets
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All shared assets used in project
        """
        user_service.check_project_access(project_id)
        return assets_service.get_shared_assets_used_in_project(project_id)


class ProjectEpisodeAssetsSharedUsedResource(Resource):
    @jwt_required()
    def get(self, project_id, episode_id):
        """
        Retrieve all shared assets used in project episode.
        ---
        tags:
            - Assets
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
                description: All shared assets used in project episode
        """
        user_service.check_project_access(project_id)
        return assets_service.get_shared_assets_used_in_project(
            project_id, episode_id
        )
