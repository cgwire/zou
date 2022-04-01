from flask import Blueprint
from zou.app.utils.api import configure_api_from_blueprint

from .resources import (
    EpisodeAssetInstancesResource,
    EpisodeCastingResource,
    ProjectEntityLinkResource,
    ProjectEntityLinksResource,
    RemoveEpisodeAssetInstanceResource,
    ShotAssetInstancesResource,
    RemoveShotAssetInstanceResource,
    SceneAssetInstancesResource,
    SceneCameraInstancesResource,
    CastingResource,
    AssetTypeCastingResource,
    SequenceCastingResource,
)


routes = [
    (
        "/data/projects/<project_id>/entities/<entity_id>/casting",
        CastingResource,
    ),
    (
        "/data/projects/<project_id>/asset-types/<asset_type_id>/casting",
        AssetTypeCastingResource,
    ),
    ("/data/episodes/<episode_id>/asset-instances", EpisodeAssetInstancesResource),
    (
        "/data/episodes/<episode_id>/asset-instances/<asset_instance_id>",
        RemoveEpisodeAssetInstanceResource,
    ),
    (
        "/data/projects/<project_id>/episodes/<episode_id>/casting",
        EpisodeCastingResource,
    ),
    (
        "/data/projects/<project_id>/sequences/<sequence_id>/casting",
        SequenceCastingResource,
    ),
    ("/data/projects/<project_id>/entity-links", ProjectEntityLinksResource),
    (
        "/data/projects/<project_id>/entity-links/<entity_link_id>",
        ProjectEntityLinkResource,
    ),
    ("/data/scenes/<scene_id>/asset-instances", SceneAssetInstancesResource),
    ("/data/scenes/<scene_id>/camera-instances", SceneCameraInstancesResource),
    ("/data/shots/<shot_id>/asset-instances", ShotAssetInstancesResource),
    (
        "/data/shots/<shot_id>/asset-instances/<asset_instance_id>",
        RemoveShotAssetInstanceResource,
    ),
]


blueprint = Blueprint("breakdown", "breakdown")
api = configure_api_from_blueprint(blueprint, routes)
