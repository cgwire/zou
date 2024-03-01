from slugify import slugify
from zou.app.blueprints.source.csv.base import BaseCsvProjectImportResource

from zou.app.services import (
    assets_service,
    projects_service,
    shots_service,
    breakdown_service,
    entities_service,
)

from zou.app.utils import events


class CastingCsvImportResource(BaseCsvProjectImportResource):
    def post(self, project_id):
        """
        Import project casting links via a .csv file.
        ---
        tags:
          - Import
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
            name: file
            type: file
            required: true
        responses:
            201:
                description: The lists of imported casting links.
            400:
                description: The .csv file is not properly formatted.
        """
        return super().post(project_id)

    def prepare_import(self, project_id):
        self.asset_type_map = {}
        self.asset_map = {}
        self.episode_map = {}
        self.episode_name_map = {}
        self.sequence_map = {}
        self.shot_map = {}

        asset_types = assets_service.get_asset_types()
        for asset_type in asset_types:
            self.asset_type_map[asset_type["id"]] = slugify(asset_type["name"])

        assets = assets_service.get_assets({"project_id": project_id})
        for asset in assets:
            key = self.get_asset_key(asset)
            self.asset_map[key] = asset["id"]

        project = projects_service.get_project(project_id)
        self.is_tv_show = projects_service.is_tv_show(project)
        if self.is_tv_show:
            episodes = shots_service.get_episodes({"project_id": project_id})
            for episode in episodes:
                self.episode_map[episode["id"]] = slugify(episode["name"])
                key = self.get_episode_key(episode)
                self.episode_name_map[key] = episode["id"]

        sequences = shots_service.get_sequences({"project_id": project_id})
        for sequence in sequences:
            key = self.get_sequence_key(sequence)
            self.sequence_map[sequence["id"]] = key

        shots = shots_service.get_shots({"project_id": project_id})
        for shot in shots:
            key = self.get_shot_key(shot)
            self.shot_map[key] = shot["id"]

    def get_asset_key(self, asset):
        asset_type_name = self.asset_type_map[asset["entity_type_id"]]
        return f"{asset_type_name}{slugify(asset['name'])}"

    def get_sequence_key(self, sequence):
        episode_name = ""
        if sequence["parent_id"] in self.episode_map:
            episode_name = self.episode_map[sequence["parent_id"]]
        return f"{episode_name}{slugify(sequence['name'])}"

    def get_shot_key(self, shot):
        sequence_key = self.sequence_map[shot["parent_id"]]
        return f"{sequence_key}{slugify(shot['name'])}"

    def get_episode_key(self, episode):
        return f"episode{slugify(episode['name'])}"

    def import_row(self, row, project_id):
        asset_key = slugify(f"{row['Asset Type']}{row['Asset']}")
        if row.get("Episode") in ["MP", None]:
            row["Episode"] = ""
        target_key = slugify(f"{row['Episode']}{row['Parent']}{row['Name']}")
        occurences = 1
        if len(row["Occurences"]) > 0:
            occurences = int(row["Occurences"])

        asset_id = self.asset_map.get(asset_key, None)
        target_id = self.shot_map.get(target_key, None)
        if target_id is None:
            target_id = self.asset_map.get(
                slugify(f"{row['Parent']}{row['Name']}"), None
            )
            if target_id is None:
                target_id = self.episode_name_map.get(target_key, None)

        label = slugify(row.get("Label", "fixed"))

        if asset_id is not None and target_id is not None:
            entity = entities_service.get_entity_raw(target_id)
            link = breakdown_service.get_entity_link_raw(target_id, asset_id)
            if link is None:
                breakdown_service.create_casting_link(
                    target_id, asset_id, occurences, label
                )
                entity.update({"nb_entities_out": entity.nb_entities_out + 1})
            else:
                link.update({"nb_occurences": occurences, "label": label})
            entity_id = str(entity.id)
            if shots_service.is_shot(entity.serialize()):
                breakdown_service.refresh_shot_casting_stats(
                    entity.serialize()
                )
                events.emit(
                    "shot:casting-update",
                    {
                        "shot_id": entity_id,
                        "nb_entities_out": entity.nb_entities_out,
                    },
                    project_id=str(entity.project_id),
                )
            elif shots_service.is_episode(entity.serialize()):
                events.emit(
                    "episode:casting-update",
                    {
                        "episode_id": entity_id,
                        "nb_entities_out": entity.nb_entities_out,
                    },
                    project_id=str(entity.project_id),
                )
            else:
                events.emit(
                    "asset:casting-update",
                    {"asset_id": entity_id},
                    project_id=str(entity.project_id),
                )
