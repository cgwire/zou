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
    user_service,
)

from zou.app.utils import date_helpers


class TaskTypeEstimationsCsvImportResource(BaseCsvProjectImportResource):

    def check_permissions(self, project_id, task_type, episode_id=None):
        return user_service.check_supervisor_project_task_type_access(
            project_id, task_type["id"]
        )

    def post(self, project_id, task_type_id, episode_id=None):
        """
        Import task type estimations csv
        ---
        tags:
          - Import
        description: Import task type estimations from a CSV file. Updates
          estimations, dates, and other task properties for assets or shots
          based on CSV rows.
        consumes:
          - multipart/form-data
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
            required: true
            schema:
              type: string
              format: uuid
            example: b24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: file
            type: file
            required: true
            description: CSV file with task estimation data
        responses:
            201:
              description: Task estimations imported successfully
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          example: Asset Modeling
                        estimation:
                          type: integer
                          example: 480
                        start_date:
                          type: string
                          format: date
                          example: "2024-01-15"
                        due_date:
                          type: string
                          format: date
                          example: "2024-01-25"
            400:
              description: Invalid CSV format or entity not found
        """
        task_type = tasks_service.get_task_type(task_type_id)
        return super().post(project_id, task_type, episode_id)

    def prepare_import(self, project_id, task_type, episode_id=None):
        self.organisation = persons_service.get_organisation()
        self.assets_map = {}
        self.shots_map = {}
        self.tasks_map = {}

        if task_type["for_entity"] == "Asset":
            asset_types_map = {}
            asset_types = assets_service.get_asset_types_for_project(
                project_id
            )
            for asset_type in asset_types:
                asset_types_map[asset_type["id"]] = slugify(asset_type["name"])

            criterions_assets = {"project_id": project_id}
            if episode_id is not None and episode_id not in ["main", "all"]:
                criterions_assets["source_id"] = episode_id
            assets = assets_service.get_assets(criterions_assets)
            for asset in assets:
                key = "%s%s" % (
                    asset_types_map[asset["entity_type_id"]],
                    slugify(asset["name"]),
                )
                self.assets_map[key] = asset["id"]
        elif task_type["for_entity"] == "Shot":
            sequences_map = {}
            criterions_sequences = {"project_id": project_id}
            if episode_id is not None and episode_id not in ["main", "all"]:
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
            project_id, task_type["id"]
        ):
            self.tasks_map[task["entity_id"]] = task["id"]

    def import_row(self, row, project_id, task_type, episode_id=None):
        key = slugify("%s%s" % (row["Parent"], row["Entity"]))

        if task_type["for_entity"] == "Asset" and self.assets_map.get(key):
            entity_id = self.assets_map[key]
        elif task_type["for_entity"] == "Shot" and self.shots_map.get(key):
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
        Import episode task type estimations csv
        ---
        tags:
          - Import
        description: Import task type estimations from a CSV file for a
          specific episode. Updates estimations, dates, and other task
          properties for assets or shots based on CSV rows.
        consumes:
          - multipart/form-data
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
            required: true
            schema:
              type: string
              format: uuid
            example: b24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: episode_id
            required: true
            schema:
              type: string
              format: uuid
            example: c24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: file
            type: file
            required: true
            description: CSV file with task estimation data
        responses:
            201:
              description: Task estimations imported successfully
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          example: Asset Modeling
                        estimation:
                          type: integer
                          example: 480
                        start_date:
                          type: string
                          format: date
                          example: "2024-01-15"
                        due_date:
                          type: string
                          format: date
                          example: "2024-01-25"
            400:
              description: Invalid CSV format or entity not found
        """
        return super().post(project_id, task_type_id, episode_id)
