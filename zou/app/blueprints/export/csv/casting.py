from flask_restful import Resource
from flask_jwt_extended import jwt_required
from slugify import slugify
from sqlalchemy.orm import aliased

from zou.app.models.entity import Entity, EntityLink
from zou.app.models.entity_type import EntityType

from zou.app.services import projects_service, shots_service, user_service
from zou.app.utils import csv_utils

from zou.app.mixin import ArgsMixin


class CastingCsvExport(Resource, ArgsMixin):
    @jwt_required
    def get(self, project_id):
        project = projects_service.get_project(project_id)  # Check existence
        self.check_permissions(project_id)

        episode_id = self.get_episode_id()

        results = self.build_results(project_id, episode_id=episode_id)
        headers = self.build_headers(episode_id=episode_id)

        csv_content = [headers]
        for result in results:
            csv_content.append(self.build_row(result, episode_id=episode_id))

        file_name = "%s casting" % project["name"]
        return csv_utils.build_csv_response(csv_content, slugify(file_name))

    def check_permissions(self, project_id):
        user_service.check_project_access(project_id)
        user_service.block_access_to_vendor()

    def build_headers(self, episode_id=None):
        headers = [
            "Parent",
            "Name",
            "Asset Type",
            "Asset",
            "Occurences",
            "Label",
        ]
        if episode_id is not None:
            return ["Episode"] + headers
        else:
            return headers

    def build_row(self, result, episode_id=None):
        if episode_id is not None:
            (
                episode_name,
                target_parent_name,
                target_entity_type_name,
                target_name,
                asset_type_name,
                asset_name,
                entity_link_nb_occurences,
                entity_link_label,
            ) = result
            row = [
                episode_name or "",
                target_parent_name or target_entity_type_name,
                target_name,
                asset_type_name,
                asset_name,
                entity_link_nb_occurences,
                entity_link_label or "",
            ]
        else:
            (
                target_parent_name,
                target_entity_type_name,
                target_name,
                asset_type_name,
                asset_name,
                entity_link_nb_occurences,
                entity_link_label,
            ) = result
            row = [
                target_parent_name or target_entity_type_name,
                target_name,
                asset_type_name,
                asset_name,
                entity_link_nb_occurences,
                entity_link_label or "",
            ]
        return row

    def build_results(self, project_id, episode_id=None):
        results = []
        results = self.build_shot_results(project_id, episode_id)
        results += self.build_asset_results(project_id, episode_id)
        return results

    def build_shot_results(self, project_id, episode_id=None):
        results = []
        Shot = aliased(Entity, name="shot")
        Asset = aliased(Entity, name="asset")
        Sequence = aliased(Entity, name="sequence")
        Episode = aliased(Entity, name="episode")
        AssetType = aliased(EntityType, name="asset_type")

        query = (
            EntityLink.query.join(Shot, EntityLink.entity_in_id == Shot.id)
            .join(Sequence, Shot.parent_id == Sequence.id)
            .join(Asset, EntityLink.entity_out_id == Asset.id)
            .join(AssetType, Asset.entity_type_id == AssetType.id)
            .filter(Shot.project_id == project_id)
        )
        if episode_id is not None:
            query = query.join(Episode, Sequence.parent_id == Episode.id)
            query = query.filter(Episode.id == episode_id)
            query = query.add_columns(
                Episode.name,
                Sequence.name,
                Shot.name,
                AssetType.name,
                Asset.name,
            ).order_by(
                Episode.name,
                Sequence.name,
                Shot.name,
                AssetType.name,
                Asset.name,
            )
            for (
                entity_link,
                episode_name,
                sequence_name,
                shot_name,
                asset_type_name,
                asset_name,
            ) in query.all():
                results.append(
                    (
                        episode_name,
                        sequence_name,
                        "Shot",
                        shot_name,
                        asset_type_name,
                        asset_name,
                        entity_link.nb_occurences,
                        entity_link.label,
                    )
                )
        else:
            query = query.add_columns(
                Sequence.name,
                Shot.name,
                AssetType.name,
                Asset.name,
            ).order_by(
                Sequence.name,
                Shot.name,
                AssetType.name,
                Asset.name,
            )

            for (
                entity_link,
                sequence_name,
                shot_name,
                asset_type_name,
                asset_name,
            ) in query.all():
                results.append(
                    (
                        sequence_name,
                        "Shot",
                        shot_name,
                        asset_type_name,
                        asset_name,
                        entity_link.nb_occurences,
                        entity_link.label,
                    )
                )

        return results

    def build_asset_results(self, project_id, episode_id=None):
        results = []
        ParentAsset = aliased(Entity, name="parent_asset")
        ParentAssetType = aliased(EntityType, name="parent_asset_type")
        Asset = aliased(Entity, name="asset")
        AssetType = aliased(EntityType, name="asset_type")
        Episode = aliased(Entity, name="episode")
        shot_type = shots_service.get_shot_type()

        query = (
            EntityLink.query.join(
                ParentAsset, EntityLink.entity_in_id == ParentAsset.id
            )
            .join(
                ParentAssetType,
                ParentAsset.entity_type_id == ParentAssetType.id,
            )
            .join(Asset, EntityLink.entity_out_id == Asset.id)
            .join(AssetType, Asset.entity_type_id == AssetType.id)
            .filter(ParentAsset.project_id == project_id)
            .filter(ParentAssetType.id != shot_type["id"])
        )
        if episode_id is not None:
            query = query.join(Episode, ParentAsset.source_id == Episode.id)
            query = query.filter(Episode.id == episode_id)
            query = query.add_columns(
                Episode.name,
                ParentAssetType.name,
                ParentAsset.name,
                AssetType.name,
                Asset.name,
            ).order_by(
                Episode.name,
                ParentAssetType.name,
                ParentAsset.name,
                AssetType.name,
                Asset.name,
            )
            for (
                entity_link,
                episode_name,
                parent_asset_type_name,
                parent_name,
                asset_type_name,
                asset_name,
            ) in query.all():
                results.append(
                    (
                        episode_name,
                        "",
                        parent_asset_type_name,
                        parent_name,
                        asset_type_name,
                        asset_name,
                        entity_link.nb_occurences,
                        entity_link.label,
                    )
                )
            results += self.build_main_pack_results(project_id)
        else:
            query = query.add_columns(
                ParentAssetType.name,
                ParentAsset.name,
                AssetType.name,
                Asset.name,
            ).order_by(
                ParentAssetType.name,
                ParentAsset.name,
                AssetType.name,
                Asset.name,
            )
            for (
                entity_link,
                parent_asset_type_name,
                parent_name,
                asset_type_name,
                asset_name,
            ) in query.all():
                results.append(
                    (
                        parent_asset_type_name,
                        "Shot",
                        parent_name,
                        asset_type_name,
                        asset_name,
                        entity_link.nb_occurences,
                        entity_link.label,
                    )
                )

        return results

    def build_main_pack_results(self, project_id):
        results = []
        ParentAsset = aliased(Entity, name="parent_asset")
        ParentAssetType = aliased(EntityType, name="parent_asset_type")
        Asset = aliased(Entity, name="asset")
        AssetType = aliased(EntityType, name="asset_type")
        shot_type = shots_service.get_shot_type()

        query = (
            EntityLink.query.join(
                ParentAsset, EntityLink.entity_in_id == ParentAsset.id
            )
            .join(
                ParentAssetType,
                ParentAsset.entity_type_id == ParentAssetType.id,
            )
            .join(Asset, EntityLink.entity_out_id == Asset.id)
            .join(AssetType, Asset.entity_type_id == AssetType.id)
            .filter(ParentAsset.project_id == project_id)
            .filter(ParentAsset.source_id == None)
            .filter(ParentAssetType.id != shot_type["id"])
        )
        query = query.add_columns(
            ParentAssetType.name,
            ParentAsset.name,
            AssetType.name,
            Asset.name,
        ).order_by(
            ParentAssetType.name,
            ParentAsset.name,
            AssetType.name,
            Asset.name,
        )
        for (
            entity_link,
            parent_asset_type_name,
            parent_name,
            asset_type_name,
            asset_name,
        ) in query.all():
            results.append(
                (
                    "MP",
                    "",
                    parent_asset_type_name,
                    parent_name,
                    asset_type_name,
                    asset_name,
                    entity_link.nb_occurences,
                    entity_link.label,
                )
            )
        return results
