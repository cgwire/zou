from zou.app.blueprints.export.csv.base import BaseCsvExport

from zou.app.models.project_status import ProjectStatus
from zou.app.models.project import Project


class ProjectsCsvExport(BaseCsvExport):
    def __init__(self):
        BaseCsvExport.__init__(self)

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
