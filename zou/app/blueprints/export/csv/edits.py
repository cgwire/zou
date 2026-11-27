from flask.views import MethodView
from flask_jwt_extended import jwt_required
from slugify import slugify

from zou.app.blueprints.export.csv.base import EntityCsvExportMixin
from zou.app.services import (
    edits_service,
    permissions_service,
    persons_service,
    projects_service,
    task_types_service,
)
from zou.app.utils import csv_utils
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi.yml")


class EditsCsvExport(EntityCsvExportMixin, MethodView):
    entity_type = "Edit"
    entity_headers = [
        "Project",
        "Episode",
        "Name",
        "Description",
        "Time Spent",
    ]

    @jwt_required()
    @swag_from(SPECS["EditsCsvExport_get"])
    def get(self, project_id):
        """
        Export edits csv
        """
        self.task_type_map = task_types_service.get_task_type_map()
        self.task_status_map = task_types_service.get_task_status_map()
        self.persons_map = persons_service.get_persons_map()

        project = projects_service.get_project(project_id)
        self.check_permissions(project["id"])

        csv_content = []
        results = self.get_edits_data(project_id)
        metadata_infos = self.get_metadata_infos(project_id)
        validation_columns = self.get_validation_columns(results)
        headers = self.build_headers(metadata_infos, validation_columns)
        csv_content.append(headers)

        for result in results:
            result["project_name"] = project["name"]
            csv_content.append(
                self.build_row(result, metadata_infos, validation_columns)
            )

        file_name = f"{project['name']} edits"
        return csv_utils.build_csv_response(csv_content, slugify(file_name))

    def check_permissions(self, project_id):
        permissions_service.check_project_access(project_id)
        permissions_service.block_access_to_vendor()

    def get_edits_data(self, project_id):
        results = edits_service.get_edits_and_tasks({"project_id": project_id})
        return sorted(
            results,
            key=lambda edit: (edit["episode_name"], edit["name"]),
        )

    def build_entity_columns(self, result):
        return [
            result["project_name"],
            result["episode_name"],
            result["name"],
            result["description"],
            self.get_time_spent(result),
        ]
