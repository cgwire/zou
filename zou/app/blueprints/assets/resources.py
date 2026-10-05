from flasgger import swag_from
from flask import request
from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app.utils import (
    flask_utils,
    http_cache,
    permissions,
    query,
    validation,
)
from zou.app.mixin import ArgsMixin
from zou.app.services import (
    assets_service,
    breakdown_service,
    entities_service,
    persons_service,
    shots_service,
    tasks_service,
    permissions_service,
)
from zou.app.blueprints.assets.schemas import (
    CastingEntrySchema,
    NewAssetSchema,
    AssetInstanceSchema,
    SetSharedAssetsSchema,
)


def check_criterion_access(criterions):
    """
    Raise 403 if the caller filters by a project or episode they cannot access.

    Resolves ``project_id`` from the criterions (directly, or via the episode)
    and calls ``permissions_service.check_project_access``. When no project/episode is
    given, access is not checked here: ``assets_service.get_assets`` already
    scopes the list with ``only_user_projects``.
    """
    project_id = None
    if "project_id" in criterions:
        project_id = criterions.get("project_id", None)
    elif "episode_id" in criterions:
        episode_id = criterions.get("episode_id", None)
        project_id = shots_service.get_episode(episode_id)["project_id"]

    if project_id is not None:
        permissions_service.check_project_access(project_id)
    return True


class AssetResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/AssetResource_get.yml")
    def get(self, asset_id):
        """
        Get asset
        """
        asset = assets_service.get_full_asset(asset_id)
        permissions_service.check_project_access(asset["project_id"])
        permissions_service.check_entity_access(asset["id"])
        return asset

    @jwt_required()
    @swag_from("openapi/AssetResource_delete.yml")
    def delete(self, asset_id):
        """
        Delete asset
        """
        force = self.get_force()

        asset = assets_service.get_full_asset(asset_id)
        if asset["created_by"] == persons_service.get_current_user()["id"]:
            permissions_service.check_belong_to_project(asset["project_id"])
        else:
            permissions_service.check_manager_project_access(
                asset["project_id"]
            )

        assets_service.remove_asset(asset_id, force=force)
        return "", 204


class AllAssetsResource(MethodView):

    @jwt_required()
    @swag_from("openapi/AllAssetsResource_get.yml")
    def get(self):
        """
        Get all assets
        """
        criterions = query.get_query_criterions_from_request(request)
        check_criterion_access(criterions)
        permissions_service.scope_criterions_to_vendor(criterions)
        return assets_service.get_assets(
            criterions,
            only_user_projects=not permissions.has_admin_permissions(),
        )


class AssetsAndTasksResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/AssetsAndTasksResource_get.yml")
    def get(self):
        """
        Get assets with tasks
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
        check_criterion_access(criterions)
        permissions_service.scope_criterions_to_vendor(criterions)
        only_user_projects = not permissions.has_admin_permissions()
        etag = entities_service.get_project_board_etag(criterions)
        if etag is not None and http_cache.is_fresh(etag):
            return http_cache.not_modified(etag)
        if not stream and not compact:
            body = assets_service.get_assets_and_tasks(
                criterions, only_user_projects=only_user_projects
            )
            if etag is None:
                return body
            return http_cache.json_response(body, etag)

        rows = assets_service.prepare_assets_and_tasks(
            criterions,
            compact=compact,
            only_user_projects=only_user_projects,
        )
        header = {"compact": compact}
        if compact:
            header["asset_fields"] = (
                assets_service.ASSETS_AND_TASKS_ASSET_FIELDS
            )
            header["task_fields"] = assets_service.ASSETS_AND_TASKS_TASK_FIELDS
        response = flask_utils.rows_response(header, rows, stream)
        if etag is not None:
            # rows_response returns a plain dict when not streaming.
            if stream:
                http_cache.mark(response, etag)
            else:
                response = http_cache.json_response(response, etag)
        return response


class AssetTypeResource(MethodView):

    @jwt_required()
    @swag_from("openapi/AssetTypeResource_get.yml")
    def get(self, asset_type_id):
        """
        Get asset type
        """
        return assets_service.get_asset_type(asset_type_id)


class AssetTypesResource(MethodView):

    @jwt_required()
    @swag_from("openapi/AssetTypesResource_get.yml")
    def get(self):
        """
        Get asset types
        """
        criterions = query.get_query_criterions_from_request(request)
        return assets_service.get_asset_types(criterions)


class ProjectAssetTypesResource(MethodView):

    @jwt_required()
    @swag_from("openapi/ProjectAssetTypesResource_get.yml")
    def get(self, project_id):
        """
        Get project asset types
        """
        permissions_service.check_project_access(project_id)
        return assets_service.get_asset_types_for_project(project_id)


class ShotAssetTypesResource(MethodView):

    @jwt_required()
    @swag_from("openapi/ShotAssetTypesResource_get.yml")
    def get(self, shot_id):
        """
        Get shot asset types
        """
        shot = shots_service.get_shot(shot_id)
        permissions_service.check_project_access(shot["project_id"])
        return assets_service.get_asset_types_for_shot(shot_id)


class ProjectAssetsResource(MethodView):

    @jwt_required()
    @swag_from("openapi/ProjectAssetsResource_get.yml")
    def get(self, project_id):
        """
        Get project assets
        """
        permissions_service.check_project_access(project_id)
        criterions = query.get_query_criterions_from_request(request)
        criterions["project_id"] = project_id
        permissions_service.scope_criterions_to_vendor(criterions)
        return assets_service.get_assets(criterions)


class ProjectAssetTypeAssetsResource(MethodView):

    @jwt_required()
    @swag_from("openapi/ProjectAssetTypeAssetsResource_get.yml")
    def get(self, project_id, asset_type_id):
        """
        Get project asset type assets
        """
        permissions_service.check_project_access(project_id)
        criterions = query.get_query_criterions_from_request(request)
        criterions["project_id"] = project_id
        criterions["entity_type_id"] = asset_type_id
        permissions_service.scope_criterions_to_vendor(criterions)
        return assets_service.get_assets(criterions)


class AssetAssetsResource(MethodView):

    @jwt_required()
    @swag_from("openapi/AssetAssetsResource_get.yml")
    def get(self, asset_id):
        """
        Get linked assets
        """
        asset = assets_service.get_asset(asset_id)
        permissions_service.check_project_access(asset["project_id"])
        permissions_service.check_entity_access(asset_id)
        return breakdown_service.get_entity_casting(asset_id)


class AssetTasksResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/AssetTasksResource_get.yml")
    def get(self, asset_id):
        """
        Get asset tasks
        """
        asset = assets_service.get_asset(asset_id)
        permissions_service.check_project_access(asset["project_id"])
        permissions_service.check_entity_access(asset["id"])
        return tasks_service.get_tasks_for_asset(
            asset_id, relations=self.get_relations()
        )


class AssetTaskTypesResource(MethodView):

    @jwt_required()
    @swag_from("openapi/AssetTaskTypesResource_get.yml")
    def get(self, asset_id):
        """
        Get asset task types
        """
        asset = assets_service.get_asset(asset_id)
        permissions_service.check_project_access(asset["project_id"])
        permissions_service.check_entity_access(asset["id"])
        return tasks_service.get_task_types_for_asset(asset_id)


class NewAssetResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/NewAssetResource_post.yml")
    def post(self, project_id, asset_type_id):
        """
        Create asset
        """
        body = validation.validate_request_body(NewAssetSchema)

        permissions_service.check_manager_project_access(project_id)
        asset = assets_service.create_asset(
            project_id,
            asset_type_id,
            body.name,
            body.description,
            body.data,
            body.is_shared,
            str(body.episode_id) if body.episode_id else None,
            created_by=persons_service.get_current_user()["id"],
        )
        return asset, 201


class AssetCastingResource(MethodView):

    @jwt_required()
    @swag_from("openapi/AssetCastingResource_get.yml")
    def get(self, asset_id):
        """
        Get asset casting
        """
        asset = assets_service.get_asset(asset_id)
        permissions_service.check_project_access(asset["project_id"])
        permissions_service.check_entity_access(asset_id)
        return breakdown_service.get_casting(asset_id)

    @jwt_required()
    @swag_from("openapi/AssetCastingResource_put.yml")
    def put(self, asset_id):
        """
        Update asset casting
        """
        casting = [
            entry.model_dump(mode="json")
            for entry in validation.validate_request_list(CastingEntrySchema)
        ]
        asset = assets_service.get_asset(asset_id)
        permissions_service.check_manager_project_access(asset["project_id"])
        return breakdown_service.update_casting(asset_id, casting)


class AssetCastInResource(MethodView):

    @jwt_required()
    @swag_from("openapi/AssetCastInResource_get.yml")
    def get(self, asset_id):
        """
        Get shots casting asset
        """
        asset = assets_service.get_asset(asset_id)
        permissions_service.check_project_access(asset["project_id"])
        permissions_service.check_entity_access(asset["id"])
        return breakdown_service.get_cast_in(asset_id)


class AssetShotAssetInstancesResource(MethodView):

    @jwt_required()
    @swag_from("openapi/AssetShotAssetInstancesResource_get.yml")
    def get(self, asset_id):
        """
        Get shot asset instances
        """
        asset = assets_service.get_asset(asset_id)
        permissions_service.check_project_access(asset["project_id"])
        return breakdown_service.get_shot_asset_instances_for_asset(asset_id)


class AssetSceneAssetInstancesResource(MethodView):
    @jwt_required()
    @swag_from("openapi/AssetSceneAssetInstancesResource_get.yml")
    def get(self, asset_id):
        """
        Get scene asset instances
        """
        asset = assets_service.get_asset(asset_id)
        permissions_service.check_project_access(asset["project_id"])
        return breakdown_service.get_scene_asset_instances_for_asset(asset_id)


class AssetAssetInstancesResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/AssetAssetInstancesResource_get.yml")
    def get(self, asset_id):
        """
        Get asset instances
        """
        asset = assets_service.get_asset(asset_id)
        permissions_service.check_project_access(asset["project_id"])
        return breakdown_service.get_asset_instances_for_asset(asset_id)

    @jwt_required()
    @swag_from("openapi/AssetAssetInstancesResource_post.yml")
    def post(self, asset_id):
        """
        Create asset instance
        """
        body = validation.validate_request_body(AssetInstanceSchema)

        asset = assets_service.get_asset(asset_id)
        permissions_service.check_project_access(asset["project_id"])
        asset_instance = breakdown_service.add_asset_instance_to_asset(
            asset_id, str(body.asset_to_instantiate_id), body.description
        )
        return asset_instance, 201


class BaseSetSharedAssetsResource(MethodView, ArgsMixin):

    @jwt_required()
    def post(self, project_id=None, asset_type_id=None, asset_ids=None):
        body = validation.validate_request_body(SetSharedAssetsSchema)
        return assets_service.set_shared_assets(
            is_shared=body.is_shared,
            project_id=project_id,
            asset_type_id=asset_type_id,
            asset_ids=asset_ids,
        )


class SetSharedProjectAssetsResource(BaseSetSharedAssetsResource):

    @jwt_required()
    @swag_from("openapi/SetSharedProjectAssetsResource_post.yml")
    def post(self, project_id):
        """
        Set project assets shared
        """
        body = validation.validate_request_body(SetSharedAssetsSchema)
        permissions_service.check_manager_project_access(project_id)
        asset_ids = (
            [str(a) for a in body.asset_ids] if body.asset_ids else None
        )
        return super().post(project_id=project_id, asset_ids=asset_ids)


class SetSharedProjectAssetTypeAssetsResource(BaseSetSharedAssetsResource):

    @jwt_required()
    @swag_from("openapi/SetSharedProjectAssetTypeAssetsResource_post.yml")
    def post(self, project_id, asset_type_id):
        """
        Set asset type assets shared
        """
        permissions_service.check_manager_project_access(project_id)
        return super().post(project_id=project_id, asset_type_id=asset_type_id)


class SetSharedAssetsResource(BaseSetSharedAssetsResource):

    @jwt_required()
    @swag_from("openapi/SetSharedAssetsResource_post.yml")
    def post(self):
        """
        Set assets shared
        """
        body = validation.validate_request_body(SetSharedAssetsSchema)
        asset_ids = [str(a) for a in body.asset_ids] if body.asset_ids else []
        project_ids = set()
        for asset_id in asset_ids:
            project_ids.add(assets_service.get_asset(asset_id)["project_id"])
        for project_id in project_ids:
            permissions_service.check_manager_project_access(project_id)
        return super().post(asset_ids=asset_ids)


class ProjectAssetsSharedUsedResource(MethodView):
    @jwt_required()
    @swag_from("openapi/ProjectAssetsSharedUsedResource_get.yml")
    def get(self, project_id):
        """
        Get shared assets used in project
        """
        permissions_service.check_project_access(project_id)
        return assets_service.get_shared_assets_used_in_project(project_id)


class ProjectEpisodeAssetsSharedUsedResource(MethodView):

    @jwt_required()
    @swag_from("openapi/ProjectEpisodeAssetsSharedUsedResource_get.yml")
    def get(self, project_id, episode_id):
        """
        Get shared assets used in episode
        """
        permissions_service.check_project_access(project_id)
        return assets_service.get_shared_assets_used_in_project(
            project_id, episode_id
        )
