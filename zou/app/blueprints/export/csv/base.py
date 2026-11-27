from flask import abort
from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app.services import metadata_descriptors_service
from zou.app.utils import csv_utils, permissions
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi.yml")


class BaseCsvExport(MethodView):
    def __init__(self):
        MethodView.__init__(self)
        self.file_name = "export"

    def check_permissions(self):
        permissions.check_manager_permissions()
        return True

    def prepare_import(self):
        pass

    @jwt_required()
    @swag_from(SPECS["BaseCsvExport_get"])
    def get(self):
        """
        Export csv
        """
        self.prepare_import()
        self.check_permissions()

        def row_generator():
            yield self.build_headers()
            for result in self.build_query().yield_per(500):
                yield self.build_row(result)

        return csv_utils.build_csv_stream_response(
            row_generator(), file_name=self.file_name
        )


class EntityCsvExportMixin:
    """
    Columns shared by the asset, shot and edit exports: the time spent,
    the metadata and a status and assignees pair for each task type.
    The subclass sets `entity_type` and `entity_headers`, and implements
    `build_entity_columns`.
    """

    entity_type = None
    entity_headers = []

    def build_entity_columns(self, result):
        raise NotImplementedError

    def build_headers(self, metadata_infos, validation_columns):
        metadata_headers = [name for (name, _, _) in metadata_infos]

        validation_assignations_columns = []
        for validation_column in validation_columns:
            validation_assignations_columns.append(validation_column)
            validation_assignations_columns.append("Assignations")

        return (
            self.entity_headers
            + metadata_headers
            + validation_assignations_columns
        )

    def build_row(self, result, metadata_infos, validation_columns):
        row = self.build_entity_columns(result)
        task_map = {}

        for task in result["tasks"]:
            task_status = self.task_status_map[task["task_status_id"]]
            task_type = self.task_type_map[task["task_type_id"]]
            task_map[task_type["name"]] = {}
            task_map[task_type["name"]]["short_name"] = task_status[
                "short_name"
            ]
            task_map[task_type["name"]]["assignees"] = ",".join(
                [
                    self.persons_map[person_id]["full_name"]
                    for person_id in task["assignees"]
                ]
            )

        result_data = result.get("data", {}) or {}
        for _, field_name, data_type in metadata_infos:
            result_metadata = result_data.get(field_name, "")
            if data_type == "boolean":
                row.append(
                    "true" if result_metadata.lower() == "true" else "false"
                )
            else:
                row.append(result_metadata)

        for column in validation_columns:
            if column in task_map:
                row.append(task_map[column]["short_name"])
                row.append(task_map[column]["assignees"])
            else:
                row.append("")
                row.append("")

        return row

    def get_validation_columns(self, results):
        task_type_map = {}

        for result in results:
            for task in result["tasks"]:
                task_type = self.task_type_map[task["task_type_id"]]
                task_type_map[task_type["name"]] = {
                    "name": task_type["name"],
                    "priority": task_type["priority"],
                }

        validation_columns = [
            task_type["name"]
            for task_type in sorted(
                task_type_map.values(),
                key=lambda task_type: (
                    task_type["priority"],
                    task_type["name"],
                ),
            )
        ]

        return validation_columns

    def get_metadata_infos(self, project_id):
        descriptors = [
            descriptor
            for descriptor in metadata_descriptors_service.get_metadata_descriptors(
                project_id
            )
            if descriptor["entity_type"] == self.entity_type
        ]

        columns = [
            (
                descriptor["name"],
                descriptor["field_name"],
                descriptor["data_type"],
            )
            for descriptor in descriptors
        ]

        return columns

    def get_time_spent(self, result):
        time_spent = 0
        for task in result["tasks"]:
            if task["duration"] is not None:
                time_spent += task["duration"]

        if time_spent > 0:
            time_spent = time_spent / 8.0 / 60.0

        return f"{time_spent:.2f}"
