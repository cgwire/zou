from flask_jwt_extended import jwt_required

from zou.app.blueprints.export.csv.base import BaseCsvExport
from zou.app.services import task_types_service
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi.yml")


class TaskTypesCsvExport(BaseCsvExport):
    def __init__(self):
        BaseCsvExport.__init__(self)

        self.file_name = "task_types_export"

    @jwt_required()
    @swag_from(SPECS["TaskTypesCsvExport_get"])
    def get(self):
        """
        Export task types csv
        """
        return super().get()

    def build_headers(self):
        return ["Department", "Name"]

    def build_query(self):
        return task_types_service.get_task_types_with_department_names_query()

    def build_row(self, task_type_row):
        task_type, department_name = task_type_row
        return [department_name, task_type.name]
