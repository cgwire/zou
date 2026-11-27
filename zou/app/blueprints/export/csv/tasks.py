from flask_jwt_extended import jwt_required

from zou.app.blueprints.export.csv.base import BaseCsvExport
from zou.app.services import tasks_service
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi.yml")


class TasksCsvExport(BaseCsvExport):
    def __init__(self):
        BaseCsvExport.__init__(self)

        self.file_name = "tasks_export"

    @jwt_required()
    @swag_from(SPECS["TasksCsvExport_get"])
    def get(self):
        """
        Export tasks csv
        """
        return super().get()

    def build_headers(self):
        return [
            "Project",
            "Task Type",
            "Episode",
            "Sequence",
            "Entity Type",
            "Entity",
            "Assigner",
            "Assignees",
            "Duration",
            "Estimation",
            "Start date",
            "Due date",
            "WIP date",
            "Validation date",
            "Task Status",
        ]

    def build_query(self):
        return tasks_service.get_open_projects_tasks_query()

    def build_row(self, task_data):
        (
            task,
            project_name,
            task_type_name,
            task_status_name,
            episode_name,
            sequence_name,
            entity_type_name,
            entity_name,
            assigner_first_name,
            assigner_last_name,
        ) = task_data

        assigner_name = ""
        if assigner_first_name is not None and assigner_last_name is not None:
            assigner_name = assigner_first_name + " " + assigner_last_name
        elif assigner_first_name is not None:
            assigner_name = assigner_first_name
        elif assigner_last_name is not None:
            assigner_name = assigner_last_name

        persons = task.assignees_as_string()

        start_date = ""
        if task.start_date is not None:
            start_date = task.start_date.strftime("%Y-%m-%d")

        due_date = ""
        if task.due_date is not None:
            due_date = task.due_date.strftime("%Y-%m-%d")

        real_start_date = ""
        if task.real_start_date is not None:
            real_start_date = task.real_start_date.strftime("%Y-%m-%d")

        end_date = ""
        if task.end_date is not None:
            end_date = task.end_date.strftime("%Y-%m-%d")

        return [
            project_name,
            task_type_name,
            episode_name,
            sequence_name,
            entity_type_name,
            entity_name,
            assigner_name,
            persons,
            task.duration,
            task.estimation,
            start_date,
            due_date,
            real_start_date,
            end_date,
            task_status_name,
        ]
