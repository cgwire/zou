from flask_jwt_extended import jwt_required

from zou.app.blueprints.export.csv.base import BaseCsvExport
from zou.app.models.project import Project
from zou.app.models.project_status import ProjectStatus
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi.yml")


class ProjectsCsvExport(BaseCsvExport):
    def __init__(self):
        BaseCsvExport.__init__(self)

    @jwt_required()
    @swag_from(SPECS["ProjectsCsvExport_get"])
    def get(self):
        """
        Export projects csv
        """
        return super().get()

    def build_headers(self):
        return ["Name", "Status"]

    def build_query(self):
        query = Project.query.join(
            ProjectStatus, Project.project_status_id == ProjectStatus.id
        )
        query = query.add_columns(ProjectStatus.name)
        query = query.order_by(Project.name)
        return query

    def build_row(self, project_data):
        project, project_status_name = project_data
        return [project.name, project_status_name]
