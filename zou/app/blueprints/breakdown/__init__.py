from zou.app.utils.api import create_blueprint_for_api

from .resources import (
    EpisodesCastingResource,
    ProjectEntityLinkResource,
    ProjectEntityLinksResource,
    ShotAssetInstancesResource,
    RemoveShotAssetInstanceResource,
    SceneAssetInstancesResource,
    SceneCameraInstancesResource,
    CastingResource,
    AssetTypeCastingResource,
    SequenceCastingResource,
    EpisodeSequenceAllCastingResource,
    SequenceAllCastingResource,
)


routes = [
    (
        "/data/projects/<uuid:project_id>/entities/<uuid:entity_id>/casting",
        CastingResource,
    ),
    (
        "/data/projects/<uuid:project_id>/asset-types/<uuid:asset_type_id>/casting",
        AssetTypeCastingResource,
    ),
    (
        "/data/projects/<uuid:project_id>/episodes/casting",
        EpisodesCastingResource,
    ),
    (
        "/data/projects/<uuid:project_id>/sequences/<uuid:sequence_id>/casting",
        SequenceCastingResource,
    ),
    (
        "/data/projects/<uuid:project_id>/episodes/<uuid:episode_id>/sequences/all/casting",
        EpisodeSequenceAllCastingResource,
    ),
    (
        "/data/projects/<uuid:project_id>/sequences/all/casting",
        SequenceAllCastingResource,
    ),
    (
        "/data/projects/<uuid:project_id>/entity-links",
        ProjectEntityLinksResource,
    ),
    (
        "/data/projects/<uuid:project_id>/entity-links/<uuid:entity_link_id>",
        ProjectEntityLinkResource,
    ),
    (
        "/data/scenes/<uuid:scene_id>/asset-instances",
        SceneAssetInstancesResource,
    ),
    (
        "/data/scenes/<uuid:scene_id>/camera-instances",
        SceneCameraInstancesResource,
    ),
    ("/data/shots/<uuid:shot_id>/asset-instances", ShotAssetInstancesResource),
    (
        "/data/shots/<uuid:shot_id>/asset-instances/<uuid:asset_instance_id>",
        RemoveShotAssetInstanceResource,
    ),
]


blueprint = create_blueprint_for_api("breakdown", routes)
