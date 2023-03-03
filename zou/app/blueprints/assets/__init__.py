from zou.app.utils.api import create_blueprint_for_api

from .resources import (
    AssetsAndTasksResource,
    AssetAssetInstancesResource,
    AssetResource,
    AssetAssetsResource,
    AssetCastingResource,
    AssetCastInResource,
    AssetShotAssetInstancesResource,
    AssetSceneAssetInstancesResource,
    AssetTypeResource,
    AssetTypesResource,
    AssetTasksResource,
    AssetTaskTypesResource,
    AllAssetsResource,
    AllAssetsAliasResource,
    NewAssetResource,
    ProjectAssetsResource,
    ProjectAssetTypeAssetsResource,
    ProjectAssetTypesResource,
    ShotAssetTypesResource,
)


routes = [
    ("/data/asset-types", AssetTypesResource),
    ("/data/asset-types/<uuid:asset_type_id>", AssetTypeResource),
    ("/data/assets", AllAssetsAliasResource),
    ("/data/assets/all", AllAssetsResource),
    ("/data/assets/with-tasks", AssetsAndTasksResource),
    ("/data/assets/<uuid:asset_id>", AssetResource),
    ("/data/assets/<uuid:asset_id>/assets", AssetAssetsResource),
    ("/data/assets/<uuid:asset_id>/tasks", AssetTasksResource),
    ("/data/assets/<uuid:asset_id>/task-types", AssetTaskTypesResource),
    ("/data/assets/<uuid:asset_id>/cast-in", AssetCastInResource),
    ("/data/assets/<uuid:asset_id>/casting", AssetCastingResource),
    (
        "/data/assets/<uuid:asset_id>/shot-asset-instances",
        AssetShotAssetInstancesResource,
    ),
    (
        "/data/assets/<uuid:asset_id>/scene-asset-instances",
        AssetSceneAssetInstancesResource,
    ),
    (
        "/data/assets/<uuid:asset_id>/asset-asset-instances",
        AssetAssetInstancesResource,
    ),
    (
        "/data/projects/<uuid:project_id>/asset-types/<uuid:asset_type_id>/assets",
        ProjectAssetTypeAssetsResource,
    ),
    (
        "/data/projects/<uuid:project_id>/asset-types/<uuid:asset_type_id>/assets/new",
        NewAssetResource,
    ),
    (
        "/data/projects/<uuid:project_id>/asset-types",
        ProjectAssetTypesResource,
    ),
    ("/data/shots/<uuid:shot_id>/asset-types", ShotAssetTypesResource),
    ("/data/projects/<uuid:project_id>/assets", ProjectAssetsResource),
]

blueprint = create_blueprint_for_api("assets", routes)
