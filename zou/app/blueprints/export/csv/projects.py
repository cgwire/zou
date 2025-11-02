from zou.app.blueprints.export.csv.base import BaseCsvExport
from flask_jwt_extended import jwt_required

from zou.app.models.project_status import ProjectStatus
from zou.app.models.project import Project


class ProjectsCsvExport(BaseCsvExport):
    def __init__(self):
        BaseCsvExport.__init__(self)

    @jwt_required()
    def get(self):
        """
        Export projects csv
        ---
        tags:
          - Export
        description: Export projects as CSV file. Includes project name
          and status information.
        produces:
          - text/csv
        responses:
            200:
              description: Projects exported as CSV successfully
              content:
                text/csv:
                  schema:
                    type: string
                  example: "Name,Status\nProject A,Active\nProject B,Open"
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
        (project, project_status_name) = project_data
        return [project.name, project_status_name]
