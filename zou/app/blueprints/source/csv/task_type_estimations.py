from slugify import slugify
from zou.app.blueprints.source.csv.base import (
    BaseCsvProjectImportResource,
    RowException,
)

from zou.app.services import (
    assets_service,
    shots_service,
    tasks_service,
    persons_service,
)

from zou.app.utils import date_helpers


class TaskTypeEstimationsCsvImportResource(BaseCsvProjectImportResource):
    def post(self, project_id, task_type_id, episode_id=None):
        """
        Import the estimations of task-types for given project.
        ---
        tags:
          - Import
        consumes:
          - multipart/form-data
        parameters:
          - in: formData
            name: file
            type: file
            required: true
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
                description: Estimations imported
            400:
                description: Format error
        """
        return super().post(project_id, task_type_id, episode_id)

    def prepare_import(self, project_id, task_type_id, episode_id=None):
        self.organisation = persons_service.get_organisation()
        self.assets_map = {}
        self.shots_map = {}
        self.tasks_map = {}

        asset_types_map = {}
        asset_types = assets_service.get_asset_types_for_project(project_id)
        for asset_type in asset_types:
            asset_types_map[asset_type["id"]] = slugify(asset_type["name"])

        criterions_assets = {"project_id": project_id}
        if episode_id is not None and episode_id not in ["all"]:
            criterions_assets["source_id"] = episode_id
        assets = assets_service.get_assets(criterions_assets)
        for asset in assets:
            key = "%s%s" % (
                asset_types_map[asset["entity_type_id"]],
                slugify(asset["name"]),
            )
            self.assets_map[key] = asset["id"]

        sequences_map = {}
        criterions_sequences = {"project_id": project_id}
        if episode_id is not None and episode_id not in ["all"]:
            criterions_sequences["parent_id"] = episode_id
        sequences = shots_service.get_sequences(criterions_sequences)
        for sequence in sequences:
            sequences_map[sequence["id"]] = slugify(sequence["name"])

        shots = shots_service.get_shots({"project_id": project_id})
        for shot in shots:
            sequence_key = sequences_map.get(shot["parent_id"])
            if sequence_key is not None:
                key = "%s%s" % (sequence_key, slugify(shot["name"]))
                self.shots_map[key] = shot["id"]

        for task in tasks_service.get_tasks_for_project_and_task_type(
            project_id, task_type_id
        ):
            self.tasks_map[task["entity_id"]] = task["id"]

    def import_row(self, row, project_id, task_type_id, episode_id=None):
        key = slugify("%s%s" % (row["Parent"], row["Entity"]))

        if self.assets_map.get(key):
            entity_id = self.assets_map[key]
        elif self.shots_map.get(key):
            entity_id = self.shots_map[key]
        else:
            raise RowException(f"Entity {key} not found")

        new_data = {}

        if row.get("Estimation") not in [None, ""]:
            new_data["estimation"] = round(
                float(row["Estimation"])
                * self.organisation["hours_by_day"]
                * 60
            )

        if row.get("Drawings") not in [None, ""]:
            new_data["nb_drawings"] = int(row["Drawings"])

        if row.get("Start date") not in [None, ""]:
            new_data["start_date"] = date_helpers.get_date_from_string(
                row["Start date"]
            )

        if row.get("Due date") not in [None, ""]:
            new_data["due_date"] = date_helpers.get_date_from_string(
                row["Due date"]
            )
        elif new_data.get("start_date") and new_data.get("estimation"):
            new_data["due_date"] = date_helpers.add_business_days_to_date(
                new_data["start_date"], float(row["Estimation"]) - 1
            )

        if row.get("Difficulty") not in [None, ""]:
            new_data["difficulty"] = int(row["Difficulty"])

        tasks_service.update_task(self.tasks_map[entity_id], new_data)


class TaskTypeEstimationsEpisodeCsvImportResource(
    TaskTypeEstimationsCsvImportResource
):
    def post(self, project_id, task_type_id, episode_id):
        """
        Import the estimations of task-types for given episode of given project.
        ---
        tags:
          - Import
        consumes:
          - multipart/form-data
        parameters:
          - in: formData
            name: file
            type: file
            required: true
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
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
            201:
                description: Estimations imported
            400:
                description: Format error
        """
        return super().post(project_id, task_type_id, episode_id)
