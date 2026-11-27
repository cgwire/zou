from flask import request
from flask.views import MethodView
from flask_jwt_extended import jwt_required
from slugify import slugify

from zou.app.blueprints.export.csv.base import EntityCsvExportMixin
from zou.app.services import (
    assets_service,
    permissions_service,
    persons_service,
    projects_service,
    task_types_service,
)
from zou.app.utils import csv_utils, query
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi.yml")


class AssetsCsvExport(EntityCsvExportMixin, MethodView):
    entity_type = "Asset"
    entity_headers = ["Project", "Type", "Name", "Description", "Time Spent"]

    @jwt_required()
    @swag_from(SPECS["AssetsCsvExport_get"])
    def get(self, project_id):
        """
        Export assets csv
        """
        project = projects_service.get_project(project_id)
        self.check_permissions(project["id"])

        criterions = query.get_query_criterions_from_request(request)
        query.check_criterion_id_format(criterions, ["id", "episode_id"])
        criterions["project_id"] = project["id"]

        self.task_type_map = task_types_service.get_task_type_map()
        self.task_status_map = task_types_service.get_task_status_map()
        self.persons_map = persons_service.get_persons_map()

        csv_content = []
        results = self.get_assets_data(criterions)
        metadata_infos = self.get_metadata_infos(project_id)
        validation_columns = self.get_validation_columns(results)
        headers = self.build_headers(metadata_infos, validation_columns)
        csv_content.append(headers)

        for result in results:
            result["project_name"] = project["name"]
            csv_content.append(
                self.build_row(result, metadata_infos, validation_columns)
            )

        file_name = f"{project['name']} assets"
        return csv_utils.build_csv_response(csv_content, slugify(file_name))

    def check_permissions(self, project_id):
        permissions_service.check_project_access(project_id)
        permissions_service.block_access_to_vendor()

    def get_assets_data(self, criterions):
        results = assets_service.get_assets_and_tasks(criterions)
        return sorted(
            results,
            key=lambda asset: (asset["asset_type_name"], asset["name"]),
        )

    def build_entity_columns(self, result):
        return [
            result["project_name"],
            result["asset_type_name"],
            result["name"],
            result["description"],
            self.get_time_spent(result),
        ]
