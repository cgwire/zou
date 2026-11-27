from flask_jwt_extended import jwt_required

from zou.app.blueprints.export.csv.base import BaseCsvExport
from zou.app.services import (
    entities_service,
    persons_service,
    time_spents_service,
)
from zou.app.utils import date_helpers
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi.yml")


class TimeSpentsCsvExport(BaseCsvExport):
    @jwt_required()
    @swag_from(SPECS["TimeSpentsCsvExport_get"])
    def get(self):
        """
        Export time spents csv
        """
        return super().get()

    def prepare_import(self):
        user = persons_service.get_current_user()
        date = date_helpers.get_today_string_with_timezone(user["timezone"])
        self.file_name = f"{date}_open_projects_time_spents_export"

    def build_headers(self):
        return [
            "Project",
            "Person",
            "Entity Type Name",
            "Entity",
            "Task Type",
            "Date",
            "Time spent",
        ]

    def build_query(self):
        return time_spents_service.get_open_projects_time_spents_query()

    def build_row(self, time_spent_row):
        (
            time_spent,
            project_name,
            entity_type_name,
            entity_id,
            entity_name,
            task_type_name,
            person_first_name,
            person_last_name,
        ) = time_spent_row
        if entity_type_name == "Shot":
            entity_name, _, _ = entities_service.get_full_entity_name(
                entity_id
            )

        date = ""
        if time_spent.date is not None:
            date = time_spent.date.strftime("%Y-%m-%d")

        person_name = f"{person_first_name} {person_last_name}"

        return [
            project_name,
            person_name.strip(),
            entity_type_name,
            entity_name,
            task_type_name,
            date,
            time_spent.duration,
        ]
